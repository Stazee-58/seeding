"""
no_api_tracker.py — Engine Cào dữ liệu Tương tác Facebook KHÔNG DÙNG GRAPH API.
- Cào Lượt Thả tim / Cảm xúc (Reactions: Like, Love, Care, Haha, Wow, Sad, Angry)
- Cào Bình luận (Comments, bao gồm cả câu trả lời con / replies)
- Cào Lượt chia sẻ (Shares)
- Sử dụng Cookie tài khoản Facebook (hoặc Cookie chim mồi) gửi qua HTTP requests / DOM Parsing.
- Hoạt động nhẹ nhàng, tương thích 100% với Vercel Serverless (Không cần cài đặt Chrome hay Selenium).
"""

import logging
import random
import re
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("NoApiTracker")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.6613.88 Mobile Safari/537.36"
)


def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    """Chuyển chuỗi cookie dạng 'c_user=...; xs=...' thành dict."""
    cookies = {}
    if not cookie_str:
        return cookies
    # Xử lý trường hợp cookie có định dạng JSON từ extension
    cookie_str = cookie_str.strip()
    if cookie_str.startswith("[") and cookie_str.endswith("]"):
        try:
            import json
            items = json.loads(cookie_str)
            for item in items:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    cookies[item["name"]] = str(item["value"])
            return cookies
        except Exception:
            pass

    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def validate_facebook_cookie(cookie_str: str) -> Dict[str, Any]:
    """
    Kiểm tra cookie Facebook có hợp lệ hay không.
    Trả về dict: {'valid': bool, 'user_id': str, 'name': str, 'message': str}
    """
    cookies = parse_cookie_string(cookie_str)
    if not cookies or "c_user" not in cookies:
        return {
            "valid": False,
            "user_id": "",
            "name": "",
            "message": "Cookie không chứa trường 'c_user'. Vui lòng kiểm tra lại!",
        }

    c_user = cookies.get("c_user", "")
    session = requests.Session()
    session.headers.update({
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    session.cookies.update(cookies)

    try:
        # Thử truy cập mbasic.facebook.com hoặc m.facebook.com để kiểm tra phiên đăng nhập
        url = "https://mbasic.facebook.com/me"
        res = session.get(url, allow_redirects=True, timeout=12)
        
        if "login" in res.url.lower() or "checkpoint" in res.url.lower():
            return {
                "valid": False,
                "user_id": c_user,
                "name": "",
                "message": "Cookie đã hết hạn hoặc đang bị checkpoint!",
            }

        # Trích xuất tên từ tiêu đề hoặc DOM
        soup = BeautifulSoup(res.text, "html.parser")
        name = ""
        title_el = soup.find("title")
        if title_el and title_el.text:
            name = title_el.text.strip().replace(" | Facebook", "")
        
        if not name or name.lower() == "facebook":
            # Thử tìm thẻ h1 hoặc strong
            h_el = soup.find(["strong", "h1", "h3"])
            if h_el:
                name = h_el.text.strip()

        return {
            "valid": True,
            "user_id": c_user,
            "name": name if name else f"User {c_user}",
            "message": f"Cookie hợp lệ! Tài khoản: {name or c_user}",
        }
    except Exception as e:
        return {
            "valid": True,  # Nếu timeout vẫn cho phép với c_user
            "user_id": c_user,
            "name": f"User {c_user}",
            "message": f"Đã nhận diện c_user: {c_user} (Lưu ý: mạng phản hồi chậm: {str(e)[:50]})",
        }


def extract_post_id_from_url(url: str) -> Optional[str]:
    """Trích xuất Post ID từ nhiều định dạng URL Facebook khác nhau."""
    if not url:
        return None
    url = url.strip()

    # 1. Dạng story_fbid=123 hoặc fbid=123
    fbid_match = re.search(r"[?&](?:story_fbid|fbid|id)=(\d+)", url)
    if fbid_match:
        return fbid_match.group(1)

    # 2. Dạng /posts/123, /videos/123, /photos/123, /reels/123, /permalink/123
    path_match = re.search(r"/(?:posts|videos|photos|reels|permalink)/(\d+)", url)
    if path_match:
        return path_match.group(1)

    # 3. Dạng group post: /groups/.../permalink/123
    grp_match = re.search(r"/groups/[^/]+/posts/(\d+)", url)
    if grp_match:
        return grp_match.group(1)

    # 4. Dạng chuỗi số ở cuối URL
    num_match = re.search(r"/(\d{10,30})(?:/|\?|$)", url)
    if num_match:
        return num_match.group(1)

    return None


def is_page_or_profile_url(url: str) -> bool:
    """Kiểm tra URL có phải là link Fanpage/Trang thay vì link 1 bài viết cụ thể."""
    if not url:
        return False
    # Nếu đã có post id thì không phải là trang chung
    if extract_post_id_from_url(url):
        # Ngoại lệ: profile.php?id=... không có story_fbid
        if "story_fbid" not in url and "permalink" not in url and "/posts/" not in url:
            if "profile.php?id=" in url:
                return True
        return False

    url_clean = url.split("?")[0].rstrip("/")
    parts = [p for p in url_clean.split("/") if p and "facebook.com" not in p and "http" not in p]
    return len(parts) >= 1


def clean_facebook_url(url: str) -> str:
    """Loại bỏ các tham số tracking thừa của Facebook."""
    if not url:
        return ""
    url = url.split("?")[0].split("&")[0]
    return url.rstrip("/")


def normalize_fanpage_mbasic_url(page_input: str) -> str:
    """Chuẩn hoá URL/ID Fanpage thành link timeline trên mbasic."""
    if not page_input:
        return ""
    page_input = page_input.strip()
    if not page_input.startswith("http://") and not page_input.startswith("https://"):
        if page_input.isdigit():
            return f"https://mbasic.facebook.com/profile.php?id={page_input}&v=timeline"
        return f"https://mbasic.facebook.com/{page_input}?v=timeline"

    parsed = urlparse(page_input)
    qs = parse_qs(parsed.query)

    if "profile.php" in parsed.path:
        p_id = qs.get("id", [""])[0]
        if p_id:
            return f"https://mbasic.facebook.com/profile.php?id={p_id}&v=timeline"

    clean_path = parsed.path.strip("/")
    parts = [p for p in clean_path.split("/") if p and p not in ("pages", "category", "groups")]
    if parts:
        page_handle = parts[-1]
        return f"https://mbasic.facebook.com/{page_handle}?v=timeline"

    return f"https://mbasic.facebook.com{parsed.path}?v=timeline"


class NoApiFacebookTracker:
    """Bộ thu thập dữ liệu tương tác bài viết Facebook không cần Graph API."""

    def __init__(self, cookie_str: str = "", log_callback: Optional[Callable[[str, str], None]] = None):
        self.cookie_str = cookie_str
        self.cookies = parse_cookie_string(cookie_str)
        self.log_callback = log_callback or (lambda msg, lvl="info": None)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        })
        if self.cookies:
            self.session.cookies.update(self.cookies)

    def log(self, message: str, level: str = "info"):
        logger.info(f"[{level.upper()}] {message}")
        if self.log_callback:
            self.log_callback(message, level)

    def _sleep_random(self, a: float = 0.6, b: float = 1.4):
        """Random delay chống bị rate-limit."""
        time.sleep(random.uniform(a, b))

    # -------------------------------------------------------------------------
    # 1. Cào Lượt Thả Tim / Cảm Xúc (Reactions)
    # -------------------------------------------------------------------------
    def fetch_reactions(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        """
        Cào toàn bộ danh sách người thả cảm xúc (Like, Love, Care, Haha, Wow, Sad, Angry)
        thông qua endpoint browser cảm xúc mbasic/mobile.
        """
        reactions: List[Dict[str, Any]] = []
        seen_ids = set()

        # URL xem danh sách người react trên mbasic
        base_reaction_url = f"https://mbasic.facebook.com/ufi/reaction/profile/browser/?ft_ent_identifier={post_id}"
        current_url: Optional[str] = base_reaction_url

        self.log(f"🔎 Đang cào danh sách cảm xúc/like bài viết ID: {post_id}...", "info")
        page_count = 0
        max_pages = 25  # Giới hạn an toàn phòng lặp vô tận

        while current_url and page_count < max_pages:
            page_count += 1
            try:
                res = self.session.get(current_url, timeout=12)
                if res.status_code != 200:
                    self.log(f"⚠️ Không thể truy cập trang reaction ({res.status_code})", "warning")
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                
                # Tìm các phần tử người dùng trong danh sách react
                user_elements = soup.find_all("li")
                if not user_elements:
                    # Thử tìm theo thẻ div hoặc table
                    user_elements = soup.find_all("div", class_=lambda c: c and "item" in c.lower())

                new_found = 0
                for el in user_elements:
                    link_tag = el.find("a")
                    if not link_tag:
                        continue
                    
                    href = link_tag.get("href", "")
                    name = link_tag.text.strip()
                    if not name or len(name) < 2:
                        continue

                    # Trích xuất user id / handle
                    user_id = ""
                    if "profile.php" in href:
                        qs = parse_qs(urlparse(href).query)
                        user_id = qs.get("id", [""])[0]
                    else:
                        user_id = href.split("?")[0].strip("/").split("/")[-1]

                    uid_key = user_id or name.lower()
                    if uid_key in seen_ids:
                        continue
                    seen_ids.add(uid_key)

                    # Xác định loại cảm xúc (LIKE, LOVE, HAHA,...)
                    react_type = "LIKE"
                    img_tag = el.find("img")
                    if img_tag and img_tag.get("alt"):
                        alt_text = img_tag["alt"].upper()
                        if "THÍCH" in alt_text or "LIKE" in alt_text:
                            react_type = "LIKE"
                        elif "YÊU" in alt_text or "LOVE" in alt_text:
                            react_type = "LOVE"
                        elif "THƯƠNG" in alt_text or "CARE" in alt_text:
                            react_type = "CARE"
                        elif "HAHA" in alt_text:
                            react_type = "HAHA"
                        elif "WOW" in alt_text:
                            react_type = "WOW"
                        elif "BUỒN" in alt_text or "SAD" in alt_text:
                            react_type = "SAD"
                        elif "PHẪN" in alt_text or "ANGRY" in alt_text:
                            react_type = "ANGRY"

                    reactions.append({
                        "id": user_id,
                        "name": name,
                        "type": react_type,
                        "profile_url": f"https://www.facebook.com/{user_id}" if user_id else href,
                    })
                    new_found += 1

                # Tìm nút "Xem thêm" (Next page)
                next_link = None
                for a in soup.find_all("a"):
                    text = a.text.strip().lower()
                    if "xem thêm" in text or "see more" in text or "tiếp" in text:
                        href = a.get("href", "")
                        if "reaction" in href or "limit=" in href or "shown_ids=" in href:
                            next_link = "https://mbasic.facebook.com" + href if href.startswith("/") else href
                            break

                current_url = next_link
                if current_url:
                    self._sleep_random(0.5, 1.2)

            except Exception as e:
                self.log(f"⚠️ Lỗi cào reactions trang {page_count}: {e}", "warning")
                break

        self.log(f"✅ Đã cào được {len(reactions)} lượt cảm xúc/like thật.", "success")
        return reactions

    # -------------------------------------------------------------------------
    # 2. Cào Bình Luận (Comments & Nested Replies)
    # -------------------------------------------------------------------------
    def fetch_comments(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        """
        Cào toàn bộ bình luận của bài viết (bao gồm cả các câu trả lời con).
        """
        comments: List[Dict[str, Any]] = []
        seen_comment_keys = set()

        # URL bài viết trên mbasic
        target_url: Optional[str] = f"https://mbasic.facebook.com/{post_id}"
        self.log(f"💬 Đang cào bình luận bài viết ID: {post_id}...", "info")

        page_count = 0
        max_pages = 30  # Giới hạn an toàn

        while target_url and page_count < max_pages:
            page_count += 1
            try:
                res = self.session.get(target_url, timeout=12)
                if res.status_code != 200:
                    break

                soup = BeautifulSoup(res.text, "html.parser")

                # Tìm tất cả khối comment (thường nằm trong thẻ div có id dạng 'c_...')
                comment_blocks = soup.find_all("div", id=lambda i: i and (i.startswith("c_") or i.isdigit()))
                if not comment_blocks:
                    # Fallback tìm các thẻ div chứa comment
                    comment_blocks = soup.find_all("div", class_=lambda c: c and "msg" in c.lower())

                for block in comment_blocks:
                    # Tìm tên người bình luận
                    author_link = block.find("a")
                    if not author_link:
                        continue

                    author_name = author_link.text.strip()
                    author_href = author_link.get("href", "")
                    if not author_name or author_name.lower() in ["thích", "trả lời", "like", "reply", "báo cáo"]:
                        continue

                    # Trích xuất author id
                    author_id = ""
                    if "profile.php" in author_href:
                        qs = parse_qs(urlparse(author_href).query)
                        author_id = qs.get("id", [""])[0]
                    else:
                        author_id = author_href.split("?")[0].strip("/").split("/")[-1]

                    # Trích xuất nội dung bình luận
                    # Thường nội dung nằm ngay sau thẻ tên tác giả
                    message = ""
                    text_div = block.find("div")
                    if text_div:
                        message = text_div.text.strip()
                    else:
                        message = block.text.replace(author_name, "", 1).strip()

                    # Trích xuất comment ID
                    comment_id = block.get("id", f"cmt_{len(comments)+1}")
                    dedup_key = f"{author_id}_{author_name}_{message[:30]}"

                    if dedup_key in seen_comment_keys:
                        continue
                    seen_comment_keys.add(dedup_key)

                    comments.append({
                        "id": comment_id,
                        "from_id": author_id,
                        "from_name": author_name,
                        "message": message,
                        "created_time": "",
                    })

                # Tìm phân trang bình luận ("Xem thêm bình luận...", "Xem các bình luận trước...")
                next_cmt_url = None
                for a in soup.find_all("a"):
                    text = a.text.strip().lower()
                    if any(kw in text for kw in ["xem thêm bình luận", "bình luận trước", "xem các bình luận khác", "view more comments", "previous comments"]):
                        href = a.get("href", "")
                        if href and ("p=" in href or "story_fbid=" in href or post_id in href):
                            next_cmt_url = "https://mbasic.facebook.com" + href if href.startswith("/") else href
                            break

                target_url = next_cmt_url
                if target_url:
                    self._sleep_random(0.5, 1.2)

            except Exception as e:
                self.log(f"⚠️ Lỗi cào bình luận trang {page_count}: {e}", "warning")
                break

        self.log(f"✅ Đã cào được {len(comments)} bình luận thật.", "success")
        return comments

    # -------------------------------------------------------------------------
    # 3. Cào Lượt Chia Sẻ (Shares)
    # -------------------------------------------------------------------------
    def fetch_shares(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        """
        Cào danh sách người dùng đã chia sẻ bài viết.
        """
        shares: List[Dict[str, Any]] = []
        shares_url = f"https://mbasic.facebook.com/shares/view/?id={post_id}"
        self.log(f"🔁 Đang cào lượt chia sẻ bài viết ID: {post_id}...", "info")

        try:
            res = self.session.get(shares_url, timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                seen_share_ids = set()

                for a in soup.find_all("a"):
                    href = a.get("href", "")
                    name = a.text.strip()
                    if not name or len(name) < 2:
                        continue
                    if any(kw in name.lower() for kw in ["thích", "bình luận", "chia sẻ", "xem thêm", "facebook"]):
                        continue

                    user_id = ""
                    if "profile.php" in href:
                        qs = parse_qs(urlparse(href).query)
                        user_id = qs.get("id", [""])[0]
                    elif href.startswith("/"):
                        user_id = href.split("?")[0].strip("/").split("/")[-1]

                    if not user_id or user_id in seen_share_ids:
                        continue
                    seen_share_ids.add(user_id)

                    shares.append({
                        "id": user_id,
                        "name": name,
                    })

        except Exception as e:
            self.log(f"⚠️ Không thể cào danh sách chia sẻ: {e}", "warning")

        self.log(f"✅ Đã cào được {len(shares)} lượt chia sẻ công khai.", "success")
        return shares

    # -------------------------------------------------------------------------
    # 4. Cào Danh Sách Tất Cả Bài Viết Từ Fanpage/Trang (Hỗ trợ phân trang đến hết)
    # -------------------------------------------------------------------------
    def fetch_page_posts(self, page_url_or_id: str, limit: int = 0) -> List[Dict[str, Any]]:
        """
        Cào danh sách tất cả các bài viết trên Fanpage bằng cách phân trang liên tục.
        limit = 0: Quét TẤT CẢ bài viết trên trang (đến bài cuối cùng).
        limit > 0: Quét tối đa `limit` bài viết mới nhất.
        Trả về: [{'post_id': str, 'post_url': str, 'mo_ta': str, 'time_text': str}, ...]
        """
        target_url = normalize_fanpage_mbasic_url(page_url_or_id)
        self.log(f"🔎 Bắt đầu quét các bài viết trên Fanpage: {page_url_or_id}...", "info")

        posts_found: List[Dict[str, Any]] = []
        seen_post_ids = set()
        current_url: Optional[str] = target_url
        page_num = 0
        max_pages = 50 if limit == 0 else max(10, (limit // 5) + 3)

        while current_url and page_num < max_pages:
            page_num += 1
            self.log(f"📄 Đang đọc dòng thời gian Fanpage (Trang #{page_num})...", "info")

            try:
                res = self.session.get(current_url, timeout=14)
                if res.status_code != 200:
                    self.log(f"⚠️ Máy chủ Facebook phản hồi mã {res.status_code} khi tải trang {page_num}", "warning")
                    break

                soup = BeautifulSoup(res.text, "html.parser")

                # Tìm tất cả khối bài viết
                post_blocks = soup.find_all(["article", "div"], role=lambda r: r and "article" in r.lower())
                if not post_blocks:
                    post_blocks = soup.find_all("div", id=lambda i: i and "story" in i.lower())
                if not post_blocks:
                    post_blocks = soup.find_all("div", class_=lambda c: c and ("story" in c.lower() or "feed" in c.lower()))

                new_on_page = 0
                
                # Nếu tìm thấy các khối bài viết, duyệt từng khối
                if post_blocks:
                    for block in post_blocks:
                        pid = None
                        purl = ""
                        for a in block.find_all("a"):
                            href = a.get("href", "")
                            if ("story_fbid=" in href or "/posts/" in href or "/photos/" in href or "/videos/" in href or "permalink" in href) and "comment" not in href and "like" not in href:
                                extracted_id = extract_post_id_from_url(href)
                                if extracted_id:
                                    pid = extracted_id
                                    clean_href = href.split("&")[0] if "story_fbid" in href else href.split("?")[0]
                                    purl = "https://www.facebook.com" + clean_href if clean_href.startswith("/") else clean_href
                                    break

                        if pid and pid not in seen_post_ids:
                            seen_post_ids.add(pid)
                            # Trích xuất đoạn văn bản mô tả bài viết
                            caption = ""
                            text_lines = []
                            for p_tag in block.find_all(["p", "span", "div"]):
                                t = p_tag.text.strip()
                                if t and len(t) > 5 and not any(kw in t.lower() for kw in ["thích", "bình luận", "chia sẻ", "like", "comment", "share"]):
                                    text_lines.append(t)
                            if text_lines:
                                caption = " ".join(text_lines[:2])
                            else:
                                caption = block.text.strip().replace("\n", " ")[:90]

                            caption_clean = caption[:100] + ("..." if len(caption) > 100 else "")
                            posts_found.append({
                                "post_id": pid,
                                "post_url": purl or f"https://www.facebook.com/{pid}",
                                "mo_ta": caption_clean or f"Bài viết ID {pid}",
                                "time_text": "",
                            })
                            new_on_page += 1
                            if limit > 0 and len(posts_found) >= limit:
                                break

                # Nếu duyệt theo khối không có hoặc còn sót, quét toàn bộ liên kết trên trang
                if len(posts_found) < (limit if limit > 0 else 999):
                    for a in soup.find_all("a"):
                        href = a.get("href", "")
                        if ("story_fbid=" in href or "/posts/" in href or "/photos/" in href or "/videos/" in href) and "comment" not in href and "like" not in href and "sharer" not in href:
                            pid = extract_post_id_from_url(href)
                            if pid and pid not in seen_post_ids:
                                seen_post_ids.add(pid)
                                clean_href = href.split("&")[0] if "story_fbid" in href else href.split("?")[0]
                                purl = "https://www.facebook.com" + clean_href if clean_href.startswith("/") else clean_href
                                posts_found.append({
                                    "post_id": pid,
                                    "post_url": purl,
                                    "mo_ta": f"Bài viết ID {pid}",
                                    "time_text": "",
                                })
                                new_on_page += 1
                                if limit > 0 and len(posts_found) >= limit:
                                    break

                self.log(f"   ➕ Trang #{page_num}: Thu thập thêm {new_on_page} bài (Tổng cộng hiện có: {len(posts_found)} bài)", "info")

                if limit > 0 and len(posts_found) >= limit:
                    self.log(f"🎯 Đã đạt chỉ tiêu quét {limit} bài viết theo yêu cầu.", "success")
                    break

                # Tìm nút phân trang "Xem thêm tin" / "Show more stories"
                next_link = None
                for a in soup.find_all("a"):
                    text = a.text.strip().lower()
                    href = a.get("href", "")
                    if any(kw in text for kw in ["xem thêm tin", "tin cũ hơn", "xem bài viết cũ hơn", "xem bài cũ hơn", "bài viết cũ hơn", "show more stories", "more stories", "older stories", "see more posts", "older posts"]) or (("cursor=" in href or "sectionLoadingID=" in href) and "v=timeline" in href):
                        if "login" not in href and "checkpoint" not in href:
                            next_link = "https://mbasic.facebook.com" + href if href.startswith("/") else href
                            break

                if not next_link:
                    for a in soup.find_all("a", href=True):
                        h = a["href"]
                        if ("cursor=" in h or "unit_cursor=" in h or "sectionLoadingID=" in h) and "login" not in h:
                            next_link = "https://mbasic.facebook.com" + h if h.startswith("/") else h
                            break

                current_url = next_link
                if current_url:
                    self._sleep_random(0.7, 1.4)
                else:
                    self.log(f"🏁 Đã quét đến bài viết cuối cùng của Fanpage! Không còn bài cũ hơn.", "info")
                    break

            except Exception as e:
                self.log(f"⚠️ Lỗi quét trang #{page_num}: {e}", "warning")
                break

        self.log(f"✅ Quét xong Fanpage! Tổng cộng thu thập được {len(posts_found)} bài viết.", "success")
        return posts_found

    def fetch_page_post_urls(self, page_url: str, limit: int = 15) -> List[str]:
        """Tương thích ngược: Trả về danh sách URL dạng chuỗi."""
        posts = self.fetch_page_posts(page_url, limit=limit)
        return [p["post_url"] for p in posts]

    # -------------------------------------------------------------------------
    # 5. Quét Toàn Diện Một Hoặc Nhiều Bài Đăng
    # -------------------------------------------------------------------------
    def track_posts(
        self,
        post_urls: List[Any],
        check_likes: bool = True,
        check_comments: bool = True,
        check_shares: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Duyệt qua danh sách bài viết và cào dữ liệu tương tác thực tế 100%.
        `post_urls` có thể là danh sách URL (str) hoặc danh sách dict {'post_id', 'post_url', 'mo_ta'}.
        """
        results = []
        total = len(post_urls)

        for idx, item in enumerate(post_urls, 1):
            if isinstance(item, dict):
                url = item.get("post_url", "").strip()
                post_id = item.get("post_id") or extract_post_id_from_url(url)
                initial_mo_ta = item.get("mo_ta", f"Bài viết ID {post_id}")
            else:
                url = str(item).strip()
                post_id = extract_post_id_from_url(url)
                initial_mo_ta = f"Bài viết ID {post_id}"

            if not url or not post_id:
                self.log(f"❌ [{idx}/{total}] Không tìm thấy Post ID hợp lệ trong link: {url}", "error")
                continue

            self.log(f"📌 [{idx}/{total}] Đang xử lý bài viết ID: {post_id}", "info")
            post_data = {
                "post_id": post_id,
                "post_url": url,
                "message": initial_mo_ta,
                "mo_ta": initial_mo_ta,
                "reactions": [],
                "comments": [],
                "shares": [],
            }

            # Lấy thêm mô tả chi tiết nếu chưa có
            if not initial_mo_ta or initial_mo_ta.startswith("Bài viết ID"):
                try:
                    post_res = self.session.get(f"https://mbasic.facebook.com/{post_id}", timeout=10)
                    if post_res.status_code == 200:
                        soup = BeautifulSoup(post_res.text, "html.parser")
                        content_div = soup.find("div", id=lambda i: i and "story" in i.lower()) or soup.find("p")
                        if content_div and content_div.text.strip():
                            txt = content_div.text.strip().replace("\n", " ")
                            post_data["mo_ta"] = txt[:90] + ("..." if len(txt) > 90 else "")
                            post_data["message"] = txt
                except Exception:
                    pass

            if check_likes:
                post_data["reactions"] = self.fetch_reactions(url, post_id)
                self._sleep_random(0.5, 1.0)

            if check_comments:
                post_data["comments"] = self.fetch_comments(url, post_id)
                self._sleep_random(0.5, 1.0)

            if check_shares:
                post_data["shares"] = self.fetch_shares(url, post_id)
                self._sleep_random(0.5, 1.0)

            results.append(post_data)

        return results
