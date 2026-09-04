"""
server.py — Flask Server & REST APIs cho Hệ thống FB Tracking No-API Pro.
- Quản lý xác thực người dùng (Login / Register / Pending / Logout)
- Quản trị Admin kích hoạt tài khoản (/admin, toggle-active, delete-user)
- API Quét tương tác bài viết không cần Meta Graph API (/api/start-tracking)
- API Kiểm tra Cookie Facebook (/api/check-cookie)
- API Xuất báo cáo Excel 4 sheets (/download/report/<filename>)
"""

import os
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
import openpyxl

import database
from matcher import get_stranger_interactions, match_all
from no_api_tracker import (
    NoApiFacebookTracker,
    extract_post_id_from_url,
    validate_facebook_cookie,
)
from report import generate_excel_report

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fb_tracking_no_api_super_secret_2026")

# Khởi tạo database
database.init_db()

REPORTS_DIR = os.path.join(tempfile.gettempdir(), "fb_tracking_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper: Kiểm tra xác thực User qua Session Cookie
# ---------------------------------------------------------------------------
def get_current_user():
    session_id = request.cookies.get("tracking_session_id")
    if not session_id:
        return None
    return database.get_session_user(session_id)


def parse_members_excel(filepath_or_stream) -> List[Dict[str, Any]]:
    """Đọc file Excel danh sách thành viên (cột: Họ và tên, Facebook ID, Tên hiển thị)."""
    members = []
    try:
        wb = openpyxl.load_workbook(filepath_or_stream, data_only=True)
        ws = wb.active
        headers = []
        for cell in ws[1]:
            val = str(cell.value or "").strip().lower()
            headers.append(val)

        # Xác định chỉ số cột
        col_name = 0
        col_id = 1
        col_alias = 2

        for idx, h in enumerate(headers):
            if "họ" in h or "tên" in h or "name" in h:
                col_name = idx
            elif "id" in h or "uid" in h or "link" in h:
                col_id = idx
            elif "hiển thị" in h or "alias" in h or "phụ" in h:
                col_alias = idx

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not any(row):
                continue
            name = str(row[col_name] or "").strip()
            if not name:
                continue

            fb_id = str(row[col_id] or "").strip() if len(row) > col_id else ""
            if fb_id.endswith(".0"):
                fb_id = fb_id[:-2]

            alias = str(row[col_alias] or "").strip() if len(row) > col_alias else ""

            members.append({
                "ho_ten": name,
                "facebook_id": fb_id,
                "ten_hien_thi": alias,
            })
    except Exception as e:
        print(f"[-] Lỗi đọc file Excel thành viên: {e}")

    return members


def parse_posts_excel(filepath_or_stream) -> List[str]:
    """Đọc file Excel danh sách link bài viết."""
    urls = []
    try:
        wb = openpyxl.load_workbook(filepath_or_stream, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not any(row):
                continue
            for cell_val in row:
                val = str(cell_val or "").strip()
                if "facebook.com" in val or "fb.watch" in val:
                    urls.append(val)
                    break
    except Exception as e:
        print(f"[-] Lỗi đọc file Excel bài viết: {e}")
    return urls


# ---------------------------------------------------------------------------
# Routes: Xác thực (Auth)
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        user = get_current_user()
        if user:
            return redirect(url_for("index"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = database.get_user_by_email(email)
    if not user or not database.verify_password(password, user["password_hash"]):
        return render_template("login.html", error="Email hoặc mật khẩu không chính xác!", email=email)

    if user["is_active"] == 0 and user["role"] != "admin":
        session_id = database.create_session(user["id"])
        resp = make_response(redirect(url_for("pending")))
        resp.set_cookie("tracking_session_id", session_id, max_age=7*86400, httponly=True)
        return resp

    session_id = database.create_session(user["id"])
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("tracking_session_id", session_id, max_age=7*86400, httponly=True)
    return resp


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not full_name or not email or not password:
        return render_template("register.html", error="Vui lòng điền đầy đủ các thông tin bắt buộc!")

    if password != confirm_password:
        return render_template("register.html", error="Mật khẩu xác nhận không khớp!")

    if len(password) < 6:
        return render_template("register.html", error="Mật khẩu phải có ít nhất 6 ký tự!")

    existing = database.get_user_by_email(email)
    if existing:
        return render_template("register.html", error="Email này đã được đăng ký trên hệ thống!")

    database.create_user(email=email, password=password, full_name=full_name, phone=phone, role="user", is_active=0)
    return render_template("register.html", success=True)


@app.route("/logout")
def logout():
    session_id = request.cookies.get("tracking_session_id")
    if session_id:
        database.delete_session(session_id)
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie("tracking_session_id")
    return resp


@app.route("/pending")
def pending():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    if user["is_active"] == 1 or user["role"] == "admin":
        return redirect(url_for("index"))
    return render_template("pending.html", current_user=user)


# ---------------------------------------------------------------------------
# Routes: Quản trị Admin
# ---------------------------------------------------------------------------
@app.route("/admin")
def admin():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    if user["role"] != "admin":
        return redirect(url_for("index"))

    users = database.get_all_users()
    return render_template("admin.html", current_user=user, users=users)


@app.route("/api/admin/toggle-active", methods=["POST"])
def admin_toggle_active():
    user = get_current_user()
    if not user or user["role"] != "admin":
        return jsonify({"success": False, "error": "Không có quyền quản trị"}), 403

    data = request.get_json() or {}
    user_id = data.get("user_id")
    is_active = data.get("is_active", 0)

    if not user_id:
        return jsonify({"success": False, "error": "Thiếu user_id"}), 400

    success = database.set_user_active(int(user_id), int(is_active))
    return jsonify({"success": success})


@app.route("/api/admin/delete-user", methods=["POST"])
def admin_delete_user():
    user = get_current_user()
    if not user or user["role"] != "admin":
        return jsonify({"success": False, "error": "Không có quyền quản trị"}), 403

    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Thiếu user_id"}), 400

    success = database.delete_user(int(user_id))
    return jsonify({"success": success})


# ---------------------------------------------------------------------------
# Routes: Dashboard Chính & Quét Không API
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    if user["is_active"] == 0 and user["role"] != "admin":
        return redirect(url_for("pending"))

    return render_template("index.html", current_user=user)


@app.route("/api/check-cookie", methods=["POST"])
def check_cookie():
    data = request.get_json() or {}
    cookie_str = data.get("cookie", "")
    res = validate_facebook_cookie(cookie_str)
    return jsonify(res)


@app.route("/api/start-tracking", methods=["POST"])
def start_tracking():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Vui lòng đăng nhập"}), 401
    if user["is_active"] == 0 and user["role"] != "admin":
        return jsonify({"success": False, "error": "Tài khoản đang chờ duyệt"}), 403

    cookie_str = request.form.get("cookie", "").strip()
    post_urls_text = request.form.get("post_urls", "").strip()
    check_likes = request.form.get("check_likes") == "1"
    check_comments = request.form.get("check_comments") == "1"
    check_shares = request.form.get("check_shares") == "1"

    # Lấy danh sách link bài viết
    post_urls = []
    if post_urls_text:
        for line in post_urls_text.splitlines():
            line = line.strip()
            if line and ("facebook.com" in line or "fb.watch" in line):
                post_urls.append(line)

    if "post_file" in request.files:
        p_file = request.files["post_file"]
        if p_file and p_file.filename:
            file_urls = parse_posts_excel(p_file)
            post_urls.extend(file_urls)

    # Khử trùng lặp link
    post_urls = list(dict.fromkeys(post_urls))
    if not post_urls:
        return jsonify({"success": False, "error": "Không tìm thấy link bài viết hợp lệ nào!"})

    # Lấy danh sách thành viên
    members = []
    if "member_file" in request.files:
        m_file = request.files["member_file"]
        if m_file and m_file.filename:
            members = parse_members_excel(m_file)

    # Nếu không có file thành viên thì đọc file mẫu sẵn có
    if not members:
        sample_path = os.path.join(os.path.dirname(__file__), "members.xlsx")
        if os.path.exists(sample_path):
            members = parse_members_excel(sample_path)

    logs_list = []
    def log_cb(msg: str, lvl: str = "info"):
        logs_list.append({"msg": msg, "level": lvl})

    # Tiến hành cào dữ liệu không cần API
    tracker = NoApiFacebookTracker(cookie_str=cookie_str, log_callback=log_cb)
    raw_posts_data = tracker.track_posts(
        post_urls=post_urls,
        check_likes=check_likes,
        check_comments=check_comments,
        check_shares=check_shares,
    )

    # Chuẩn hoá sang dict collected
    collected = {}
    for p in raw_posts_data:
        pid = p["post_id"]
        collected[pid] = {
            "mo_ta": f"Bài ID {pid}",
            "permalink_url": p["post_url"],
            "comments": p["comments"],
            "reactions": p["reactions"],
            "shares": p["shares"],
        }

    # Đối soát thành viên (100% dữ liệu thực)
    match_results = match_all(members=members, collected=collected)
    strangers = get_stranger_interactions(members=members, collected=collected)

    # Thống kê bài viết
    post_summary = []
    for pid, pdata in collected.items():
        likes_cnt = len(pdata.get("reactions", []))
        cmts_cnt = len(pdata.get("comments", []))
        shares_cnt = len(pdata.get("shares", []))

        # Tính tỷ lệ hoàn thành của thành viên
        total_mems = len(members)
        if total_mems > 0:
            done_cnt = sum(
                1 for r in match_results 
                if r["post_id"] == pid and r["trang_thai"] != "chua_tuong_tac"
            )
            rate = round((done_cnt / total_mems) * 100, 1)
        else:
            rate = 0.0

        post_summary.append({
            "post_id": pid,
            "mo_ta": pdata.get("mo_ta", pid),
            "permalink_url": pdata.get("permalink_url", ""),
            "likes_count": likes_cnt,
            "comments_count": cmts_cnt,
            "shares_count": shares_cnt,
            "completion_rate": rate,
        })

    # Xuất file Excel báo cáo 4 sheets
    report_file_path = generate_excel_report(
        match_results=match_results,
        stranger_results=strangers,
        collected=collected,
        output_dir=REPORTS_DIR,
    )
    report_filename = os.path.basename(report_file_path)

    # Lưu lịch sử
    database.add_tracking_history(
        user_id=user["id"],
        campaign_name=f"Quét {len(collected)} bài",
        post_count=len(collected),
        member_count=len(members),
        report_path=report_file_path,
    )

    return jsonify({
        "success": True,
        "total_posts": len(collected),
        "total_members": len(members),
        "logs": logs_list,
        "match_results": match_results,
        "strangers": strangers,
        "post_summary": post_summary,
        "report_download_url": f"/download/report/{report_filename}",
    })


@app.route("/download/report/<filename>")
def download_report(filename):
    safe_name = os.path.basename(filename)
    path = os.path.join(REPORTS_DIR, safe_name)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=safe_name)
    return "File báo cáo không tồn tại hoặc đã bị xoá.", 404


@app.route("/download/sample/members")
def download_sample_members():
    path = os.path.join(os.path.dirname(__file__), "members.xlsx")
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name="members_sample.xlsx")
    return "Không tìm thấy file mẫu.", 404


@app.route("/download/sample/posts")
def download_sample_posts():
    path = os.path.join(os.path.dirname(__file__), "posts.xlsx")
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name="posts_sample.xlsx")
    return "Không tìm thấy file mẫu.", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"[*] FB Tracking No-API Server dang chay tai: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
