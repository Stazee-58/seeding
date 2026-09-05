"""
report.py — Xuất báo cáo Excel linh hoạt từ kết quả đối chiếu không cần API:
  - Trường hợp 1: Có danh sách thành viên -> Xuất 4 sheet đối soát thành viên, người lạ, tổng hợp bài, nhắc nhở.
  - Trường hợp 2: KHÔNG có danh sách thành viên -> Xuất chi tiết toàn bộ người Like/Tim, Comment, Share theo từng bài viết.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

_RED_FILL       = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
_HEADER_FILL    = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
_DONE_BOTH_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_DONE_PART_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
_STRANGER_FILL  = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
_HEADER_FONT    = Font(bold=True, color="FFFFFF", name="Segoe UI", size=10)
_BODY_FONT      = Font(name="Segoe UI", size=9)
_BORDER_SIDE    = Side(border_style="thin", color="CCCCCC")
_THIN_BORDER    = Border(
    left=_BORDER_SIDE, right=_BORDER_SIDE,
    top=_BORDER_SIDE,  bottom=_BORDER_SIDE,
)


def _write_header(ws: Any, headers: list[str]) -> None:
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER


def _write_row(ws: Any, row_idx: int, values: list[Any], fill: PatternFill | None = None) -> None:
    for col_idx, val in enumerate(values, start=1):
        cell = ws.cell(row=row_idx, column=col_idx, value=val)
        cell.font = _BODY_FONT
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=False)
        if fill:
            cell.fill = fill


def _auto_fit_columns(ws: Any, max_len_cap: int = 45) -> None:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 10)


def generate_excel_report(
    match_results: list[dict[str, Any]],
    stranger_results: list[dict[str, Any]],
    collected: dict[str, dict[str, Any]],
    has_members: bool = False,
    users_directory: list[dict[str, Any]] | None = None,
    output_dir: str = "",
) -> str:
    """Tạo file Excel báo cáo hoàn chỉnh 100% dữ liệu thực tế."""
    wb = Workbook()
    wb.remove(wb.active)  # Xoá sheet mặc định

    # =========================================================================
    # SHEET 1: BẢNG TỔNG HỢP THEO TÊN TẤT CẢ NGƯỜI DÙNG TƯƠNG TÁC TOÀN TRANG
    # =========================================================================
    if users_directory:
        ws_users = wb.create_sheet(title="Danh_sach_ten_nguoi_tuong_tac")
        h_u = [
            "STT", "Họ và tên người dùng Facebook", "Facebook ID", "Link Facebook cá nhân",
            "Số bài đã Tim/Like", "Số bài đã Comment", "Số bài đã Share",
            "Tổng số tương tác", "Số bài tham gia", "Tỷ lệ tương tác toàn trang (%)"
        ]
        _write_header(ws_users, h_u)
        for idx, u in enumerate(users_directory, start=1):
            rate_val = f"{u.get('participation_rate', 0)}%"
            row_vals = [
                idx,
                u.get("name", ""),
                u.get("user_id", ""),
                u.get("profile_url", ""),
                u.get("likes_count", 0),
                u.get("comments_count", 0),
                u.get("shares_count", 0),
                u.get("total_interactions", 0),
                u.get("distinct_posts_count", 0),
                rate_val,
            ]
            fill_u = _DONE_BOTH_FILL if u.get("participation_rate", 0) >= 80 else (_DONE_PART_FILL if u.get("participation_rate", 0) >= 30 else None)
            _write_row(ws_users, idx + 1, row_vals, fill=fill_u)
        _auto_fit_columns(ws_users)

    if has_members and match_results:
        # =====================================================================
        # TRƯỜNG HỢP CÓ DANH SÁCH THÀNH VIÊN ĐỐI SOÁT
        # =====================================================================
        ws1 = wb.create_sheet(title="Chi_tiet_Thanh_vien")
        h1 = [
            "STT", "Họ và tên", "Facebook ID", "Tên hiển thị",
            "Mô tả bài đăng", "Link bài",
            "Đã like/tim?", "Loại cảm xúc",
            "Đã comment?", "Số comment", "Nội dung comment", "Thời gian comment",
            "Đã share?", "Trạng thái tương tác", "Cách đối chiếu",
        ]
        _write_header(ws1, h1)

        for idx, r in enumerate(match_results, start=1):
            st = r.get("trang_thai", "")
            if st in ("da_tat_ca", "da_comment_va_like"):
                row_fill = _DONE_BOTH_FILL
                st_text = "Đầy đủ"
            elif st in ("da_comment", "da_like", "da_share", "da_comment_va_share", "da_like_va_share"):
                row_fill = _DONE_PART_FILL
                st_text = "Chưa đủ (1 phần)"
            else:
                row_fill = _RED_FILL
                st_text = "Chưa tương tác"

            row_vals = [
                idx,
                r.get("ho_ten", ""),
                r.get("facebook_id", ""),
                r.get("ten_hien_thi", ""),
                r.get("mo_ta", ""),
                r.get("permalink_url", ""),
                "Đã Like" if r.get("da_like") else "Chưa",
                r.get("loai_reaction", ""),
                "Đã Comment" if r.get("da_comment") else "Chưa",
                r.get("so_comment", 0),
                r.get("noi_dung_comment", ""),
                r.get("thoi_gian_comment", ""),
                "Đã Share" if r.get("da_share") else "Chưa",
                st_text,
                r.get("cach_doi_chieu", ""),
            ]
            _write_row(ws1, idx + 1, row_vals, fill=row_fill)
        _auto_fit_columns(ws1)

        # Sheet: Người lạ tương tác
        ws2 = wb.create_sheet(title="Nguoi_la_tuong_tac")
        h2 = ["STT", "Mô tả bài đăng", "Link bài", "Tên người lạ", "Facebook ID / Link", "Loại tương tác", "Nội dung tương tác", "Thời gian"]
        _write_header(ws2, h2)
        for idx, s in enumerate(stranger_results, start=1):
            row_vals = [
                idx, s.get("mo_ta", ""), s.get("permalink_url", ""),
                s.get("nguoi_dung", ""), s.get("facebook_id", ""),
                s.get("loai_tuong_tac", ""), s.get("noi_dung", ""), s.get("thoi_gian", "")
            ]
            _write_row(ws2, idx + 1, row_vals, fill=_STRANGER_FILL)
        _auto_fit_columns(ws2)

        # Sheet: Cần nhắc nhở
        ws4 = wb.create_sheet(title="Can_nhac_nho")
        h4 = ["STT", "Họ và tên", "Facebook ID", "Tên hiển thị", "Bài chưa làm", "Link bài"]
        _write_header(ws4, h4)
        remind_idx = 1
        for r in match_results:
            if r.get("trang_thai") == "chua_tuong_tac":
                row_vals = [
                    remind_idx, r.get("ho_ten", ""), r.get("facebook_id", ""),
                    r.get("ten_hien_thi", ""), r.get("mo_ta", ""), r.get("permalink_url", "")
                ]
                _write_row(ws4, remind_idx + 1, row_vals, fill=_RED_FILL)
                remind_idx += 1
        _auto_fit_columns(ws4)

    # =========================================================================
    # SHEET CHI TIẾT TỪNG NGƯỜI TƯƠNG TÁC (TIM, CMT, SHARE) THEO TỪNG BÀI
    # =========================================================================
    ws_all = wb.create_sheet(title="Chi_tiet_tuong_tac_bai")
    h_all = ["STT", "Bài đăng", "Link bài", "Loại tương tác", "Tên người dùng Facebook", "Facebook ID / Link Profile", "Cảm xúc / Nội dung Comment", "Thời gian"]
    _write_header(ws_all, h_all)

    row_count = 1
    for pid, pdata in collected.items():
        mo_ta = pdata.get("mo_ta", f"Bài {pid}")
        p_url = pdata.get("permalink_url", "")

        # 1. Danh sách Like / Thả tim
        for r in pdata.get("reactions", []):
            row_count += 1
            r_name = r.get("name", "")
            r_id = r.get("id", "") or r.get("user_id", "")
            r_type = r.get("type", "") or r.get("reaction_type", "LIKE")
            r_url = r.get("profile_url", "") or (f"https://facebook.com/{r_id}" if r_id else "")
            _write_row(ws_all, row_count, [
                row_count - 1, mo_ta, p_url, f"Thả tim ({r_type})", r_name, r_url or r_id, f"Cảm xúc {r_type}", ""
            ])

        # 2. Danh sách Comment
        for c in pdata.get("comments", []):
            row_count += 1
            c_name = c.get("from_name", "") or c.get("name", "")
            c_id = c.get("from_id", "") or c.get("id", "")
            c_msg = c.get("message", "")
            c_time = c.get("created_time", "")
            c_url = f"https://facebook.com/{c_id}" if c_id else ""
            _write_row(ws_all, row_count, [
                row_count - 1, mo_ta, p_url, "Bình luận", c_name, c_url or c_id, c_msg, c_time
            ])

        # 3. Danh sách Share
        for s in pdata.get("shares", []):
            row_count += 1
            s_name = s.get("name", "")
            s_id = s.get("id", "") or s.get("user_id", "")
            s_url = f"https://facebook.com/{s_id}" if s_id else ""
            _write_row(ws_all, row_count, [
                row_count - 1, mo_ta, p_url, "Chia sẻ", s_name, s_url or s_id, "Chia sẻ bài viết", ""
            ])

    _auto_fit_columns(ws_all)

    # Sheet: Tổng hợp bài viết
    ws3 = wb.create_sheet(title="Tong_hop_bai")
    h3 = ["STT", "ID bài đăng", "Mô tả bài", "Link bài", "Lượt Like thực tế", "Lượt Comment thực tế", "Lượt Share thực tế"]
    _write_header(ws3, h3)

    for idx, (pid, pdata) in enumerate(collected.items(), start=1):
        row_vals = [
            idx,
            pid,
            pdata.get("mo_ta", f"Bài {pid}"),
            pdata.get("permalink_url", ""),
            pdata.get("likes_count", len(pdata.get("reactions", []))),
            pdata.get("comments_count", len(pdata.get("comments", []))),
            pdata.get("shares_count", len(pdata.get("shares", []))),
        ]
        _write_row(ws3, idx + 1, row_vals)

    _auto_fit_columns(ws3)

    # Lưu file
    if not output_dir:
        output_dir = tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bao_cao_tracking_no_api_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    wb.save(filepath)
    return filepath
