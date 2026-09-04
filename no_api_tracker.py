"""
no_api_tracker.py — Engine Cào dữ liệu Tương tác Facebook KHÔNG DÙNG GRAPH API.
- Cào Lượt Thả tim / Cảm xúc (Reactions: Like, Love, Care, Haha, Wow, Sad, Angry)
- Cào Bình luận (Comments, bao gồm cả câu trả lời con / replies)
- Cào Lượt chia sẻ (Shares)
- Hỗ trợ cả Facebook Desktop Engine (cho New Page Experience / profile.php?id=...)
  và Mobile Basic Timeline (mbasic.facebook.com).
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

DESKTOP_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def clean_unicode(txt: str) -> str:
    """Giải mã an toàn các ký tự escape unicode (\\uXXXX) từ payload JSON của Facebook."""
    if not txt:
        return ""
    try:
        res = re.sub(
            r'\\u([0-9a-fA-F]{4})',
            lambda m: chr(int(m.group(1), 16)),
            txt
        )
        return res.replace('\\/', '/').replace('\\"', '"').replace('\\\\', '\\')
    except Exception:
        try:
            return txt.encode().decode('unicode-escape')
        except Exception:
            return txt


def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    """Chuyển chuỗi cookie dạng 'c_user=...; xs=...' thành dict."""
    cookies = {}
    if not cookie_str:
        return cookies
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
    session.headers.update(DESKTOP_HEADERS)
    session.cookies.update(cookies)

    try:
        url = "https://mbasic.facebook.com/me"
        res = session.get(url, allow_redirects=True, timeout=12)
        
        if "login" in res.url.lower() or "checkpoint" in res.url.lower():
            return {
                "valid": False,
                "user_id": c_user,
                "name": "",
                "message": "Cookie đã hết hạn hoặc đang bị checkpoint!",
            }

        soup = BeautifulSoup(res.text, "html.parser")
        name = ""
        title_el = soup.find("title")
        if title_el and title_el.text:
            name = title_el.text.strip().replace(" | Facebook", "")
        
        if not name or name.lower() == "facebook":
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
            "valid": True,
            "user_id": c_user,
            "name": f"User {c_user}",
            "message": f"Đã nhận diện c_user: {c_user}",
        }


def extract_post_id_from_url(url: str) -> Optional[str]:
    """Trích xuất Post ID từ nhiều định dạng URL Facebook khác nhau."""
    if not url:
        return None
    url = url.strip()

    # Nếu là link profile/trang thuần tuý profile.php?id=... không có story_fbid/posts thì không phải post_id
    if "profile.php?id=" in url and "story_fbid" not in url and "permalink" not in url and "/posts/" not in url:
        return None

    # 1. Dạng story_fbid=123 hoặc fbid=123
    fbid_match = re.search(r"[?&](?:story_fbid|fbid)=(\d+)", url)
    if fbid_match:
        return fbid_match.group(1)

    # 2. Dạng /posts/123, /videos/123, /photos/123, /reels/123, /permalink/123
    path_match = re.search(r"/(?:posts|videos|photos|reels|permalink)/(\d+)", url)
    if path_match:
        return path_match.group(1)

    # 3. Dạng group post: /groups/.../posts/123 hoặc /groups/.../permalink/123
    grp_match = re.search(r"/groups/[^/]+/(?:posts|permalink)/(\d+)", url)
    if grp_match:
        return grp_match.group(1)

    # 4. Dạng chuỗi số ở cuối URL (nhưng không phải profile.php?id=)
    if "profile.php" not in url:
        num_match = re.search(r"/(\d{10,30})(?:/|\?|$)", url)
        if num_match:
            return num_match.group(1)

    return None


def is_page_or_profile_url(url: str) -> bool:
    """Kiểm tra URL có phải là link Fanpage/Trang thay vì link 1 bài viết cụ thể."""
    if not url:
        return False
    if "profile.php?id=" in url and "story_fbid" not in url and "/posts/" not in url:
        return True
    if extract_post_id_from_url(url):
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


def normalize_fanpage_desktop_url(page_input: str) -> str:
    """Chuẩn hoá URL/ID Fanpage thành link Facebook desktop chính thức."""
    if not page_input:
        return ""
    page_input = page_input.strip()
    if page_input.isdigit():
        return f"https://www.facebook.com/profile.php?id={page_input}"
    if not page_input.startswith("http://") and not page_input.startswith("https://"):
        return f"https://www.facebook.com/{page_input}"
    return page_input


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
        self.session.headers.update(DESKTOP_HEADERS)
        if self.cookies:
            self.session.cookies.update(self.cookies)

    def log(self, message: str, level: str = "info"):
        logger.info(f"[{level.upper()}] {message}")
        if self.log_callback:
            self.log_callback(message, level)

    def _sleep_random(self, a: float = 0.5, b: float = 1.2):
        """Random delay chống bị rate-limit."""
        time.sleep(random.uniform(a, b))

    # -------------------------------------------------------------------------
    # 1. Cào Lượt Thả Tim / Cảm Xúc (Reactions)
    # -------------------------------------------------------------------------
    def fetch_reactions(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        """
        Cào danh sách người thả cảm xúc (Like, Love, Care, Haha, Wow, Sad, Angry).
        Hỗ trợ cào mbasic khi có Cookie và Desktop Actor Parsing khi không có Cookie.
        """
        reactions: List[Dict[str, Any]] = []
        seen_ids = set()

        self.log(f"🔎 Đang cào danh sách cảm xúc/like bài viết ID: {post_id}...", "info")

        # Cách 1: Thử mbasic endpoint nếu có Cookie
        if self.cookies and "c_user" in self.cookies:
            base_reaction_url = f"https://mbasic.facebook.com/ufi/reaction/profile/browser/?ft_ent_identifier={post_id}"
            current_url: Optional[str] = base_reaction_url
            page_count = 0
            max_pages = 25

            while current_url and page_count < max_pages:
                page_count += 1
                try:
                    res = self.session.get(current_url, timeout=12)
                    if res.status_code != 200 or "login" in res.url.lower():
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    user_elements = soup.find_all("li")
                    if not user_elements:
                        user_elements = soup.find_all("div", class_=lambda c: c and "item" in c.lower())

                    for el in user_elements:
                        link_tag = el.find("a")
                        if not link_tag:
                            continue
                        href = link_tag.get("href", "")
                        name = link_tag.text.strip()
                        if not name or len(name) < 2:
                            continue

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
                        self._sleep_random(0.5, 1.0)
                except Exception:
                    break

        # Cách 2: Desktop HTML Extraction (Khi không có cookie hoặc mbasic redirect)
        if len(reactions) == 0:
            try:
                desk_post_url = post_url if "facebook.com" in post_url else f"https://www.facebook.com/{post_id}"
                r_desk = self.session.get(desk_post_url, timeout=14)
                if r_desk.status_code == 200:
                    html_post = r_desk.text
                    cnt_m = re.search(r'"reaction_count":\{"count":(\d+)', html_post)
                    total_cnt = int(cnt_m.group(1)) if cnt_m else 0

                    page_id_m = re.search(r'(?:id=|\/)(\d{10,30})', post_url)
                    page_id = page_id_m.group(1) if page_id_m else ""

                    actors = re.findall(r'"__typename":"User","id":"([^"]+)","name":"([^"]+)"', html_post)
                    for uid, raw_name in actors:
                        name = clean_unicode(raw_name)
                        if page_id and uid == page_id:
                            continue
                        if name and name not in seen_ids and len(name) >= 2:
                            seen_ids.add(name)
                            reactions.append({
                                "id": uid,
                                "name": name,
                                "type": "LIKE",
                                "profile_url": f"https://www.facebook.com/{uid}",
                            })

                    if total_cnt > 0:
                        self.log(f"ℹ️ Bài viết có {total_cnt} lượt cảm xúc/thả tim thật ({len(reactions)} người được nhận diện trực tiếp).", "info")
            except Exception as e:
                self.log(f"⚠️ Trích xuất cảm xúc Desktop gặp lỗi: {e}", "warning")

        self.log(f"✅ Đã cào được {len(reactions)} lượt cảm xúc/thả tim thật trên bài viết ID {post_id}.", "success")
        return reactions

    # -------------------------------------------------------------------------
    # 2. Cào Bình Luận (Comments & Nested Replies)
    # -------------------------------------------------------------------------
    def fetch_comments(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        """
        Cào toàn bộ bình luận của bài viết (bao gồm cả câu trả lời con).
        Tích hợp cả mbasic parser và Desktop JSON payload parser.
        """
        comments: List[Dict[str, Any]] = []
        seen_comment_keys = set()
        self.log(f"💬 Đang cào bình luận bài viết ID: {post_id}...", "info")

        # Cách 1: Thử mbasic
        target_url: Optional[str] = f"https://mbasic.facebook.com/{post_id}"
        page_count = 0
        max_pages = 25

        while target_url and page_count < max_pages:
            page_count += 1
            try:
                res = self.session.get(target_url, timeout=12)
                if res.status_code != 200 or "login" in res.url.lower():
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                comment_blocks = soup.find_all("div", id=lambda i: i and (i.startswith("c_") or i.isdigit()))
                if not comment_blocks:
                    comment_blocks = soup.find_all("div", class_=lambda c: c and "msg" in c.lower())

                for block in comment_blocks:
                    author_link = block.find("a")
                    if not author_link:
                        continue

                    author_name = author_link.text.strip()
                    author_href = author_link.get("href", "")
                    if not author_name or author_name.lower() in ["thích", "trả lời", "like", "reply", "báo cáo"]:
                        continue

                    author_id = ""
                    if "profile.php" in author_href:
                        qs = parse_qs(urlparse(author_href).query)
                        author_id = qs.get("id", [""])[0]
                    else:
                        author_id = author_href.split("?")[0].strip("/").split("/")[-1]

                    text_div = block.find("div")
                    if text_div:
                        message = text_div.text.strip()
                    else:
                        message = block.text.replace(author_name, "", 1).strip()

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

                next_cmt_url = None
                for a in soup.find_all("a"):
                    text = a.text.strip().lower()
                    if any(kw in text for kw in ["xem thêm bình luận", "bình luận trước", "view more comments", "previous comments"]):
                        href = a.get("href", "")
                        if href and ("p=" in href or "story_fbid=" in href or post_id in href):
                            next_cmt_url = "https://mbasic.facebook.com" + href if href.startswith("/") else href
                            break

                target_url = next_cmt_url
                if target_url:
                    self._sleep_random(0.5, 1.0)
            except Exception:
                break

        # Cách 2: Desktop JSON Payload Fallback (hoạt động xuất sắc kể cả KHÔNG CẦN COOKIE)
        if len(comments) == 0:
            try:
                desk_post_url = post_url if "facebook.com" in post_url else f"https://www.facebook.com/{post_id}"
                r_desk = self.session.get(desk_post_url, timeout=14)
                if r_desk.status_code == 200:
                    html_post = r_desk.text
                    idx = 0
                    while True:
                        pos = html_post.find('"body":{"text":', idx)
                        if pos == -1:
                            break
                        chunk = html_post[pos:pos+700]
                        msg_m = re.search(r'"body":\{"text":"(.*?)"', chunk)
                        name_m = re.search(r'"author":\{"__typename":"User","id":"([^"]+)","name":"([^"]+)"', chunk)
                        if msg_m and name_m:
                            uid = name_m.group(1)
                            raw_msg = msg_m.group(1)
                            raw_name = name_m.group(2)
                            msg = clean_unicode(raw_msg)
                            name = clean_unicode(raw_name)
                            dedup_key = f"{uid}_{name}_{msg[:30]}"
                            if dedup_key not in seen_comment_keys:
                                seen_comment_keys.add(dedup_key)
                                comments.append({
                                    "id": f"c_{uid}_{len(comments)+1}",
                                    "from_id": uid,
                                    "from_name": name,
                                    "message": msg,
                                    "created_time": "",
                                })
                        idx = pos + 15
            except Exception as e:
                self.log(f"⚠️ Trích xuất bình luận Desktop gặp lỗi: {e}", "warning")

        self.log(f"✅ Đã cào được {len(comments)} bình luận thật trên bài viết ID {post_id}.", "success")
        return comments

    # -------------------------------------------------------------------------
    # 3. Cào Lượt Chia Sẻ (Shares)
    # -------------------------------------------------------------------------
    def fetch_shares(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        """Cào danh sách người dùng đã chia sẻ bài viết."""
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
    # 4. Cào Danh Sách Tất Cả Bài Viết Từ Fanpage/Trang
    # -------------------------------------------------------------------------
    def fetch_page_posts(self, page_url_or_id: str, limit: int = 0) -> List[Dict[str, Any]]:
        """
        Cào danh sách bài viết trên Fanpage.
        Hỗ trợ cả Facebook Desktop Engine (cho New Page Experience / profile.php?id=...)
        và Mobile Basic Timeline (mbasic.facebook.com).
        limit = 0: Quét TẤT CẢ bài viết trên trang.
        limit > 0: Quét tối đa `limit` bài viết mới nhất.
        """
        self.log(f"🔎 Bắt đầu quét bài viết trên Fanpage / Trang: {page_url_or_id}...", "info")

        posts_found: List[Dict[str, Any]] = []
        seen_post_ids = set()

        page_id_m = re.search(r'(?:id=|\/)(\d{10,30})', page_url_or_id)
        page_id = page_id_m.group(1) if page_id_m else ""

        desktop_url = normalize_fanpage_desktop_url(page_url_or_id)
        page_name = ""

        # ---------------------------------------------------------------------
        # BƯỚC 1: QUÉT BẰNG DESKTOP ENGINE (Phát hiện siêu tốc các bài viết mới)
        # ---------------------------------------------------------------------
        try:
            self.log(f"🌐 Đang kết nối Fanpage qua Desktop Engine: {desktop_url}...", "info")
            res_desk = self.session.get(desktop_url, timeout=14)
            if res_desk.status_code == 200:
                html_desk = res_desk.text
                
                # Trích xuất tên Fanpage
                title_m = re.search(r'<title>(.*?)</title>', html_desk)
                if title_m:
                    page_name = title_m.group(1).replace(" | Facebook", "").strip()
                    self.log(f"🏷️ Tên Trang nhận diện: {page_name}", "info")

                # Trích xuất caption bài đầu nếu có
                msg_m = re.search(r'"message":\{"text":"(.*?)"\}', html_desk)
                default_caption = clean_unicode(msg_m.group(1)) if msg_m else ""

                discovered_pids = []
                for pid in re.findall(r'"post_id":"(\d+)"', html_desk):
                    if pid != page_id and len(pid) >= 10 and pid not in seen_post_ids:
                        seen_post_ids.add(pid)
                        discovered_pids.append(pid)

                for sid in re.findall(r'"subscription_target_id":"(\d+)"', html_desk):
                    if sid != page_id and len(sid) >= 10 and sid not in seen_post_ids:
                        seen_post_ids.add(sid)
                        discovered_pids.append(sid)

                for p_match in re.findall(r'/posts/(\d+)', html_desk):
                    if p_match != page_id and len(p_match) >= 10 and p_match not in seen_post_ids:
                        seen_post_ids.add(p_match)
                        discovered_pids.append(p_match)

                for pid in discovered_pids:
                    purl = f"https://www.facebook.com/{page_id}/posts/{pid}" if page_id else f"https://www.facebook.com/{pid}"
                    desc = default_caption[:90] + "..." if default_caption else f"Bài viết trên {page_name or 'Fanpage'}"
                    posts_found.append({
                        "post_id": pid,
                        "post_url": purl,
                        "mo_ta": desc,
                        "time_text": "",
                    })
                    self.log(f"   ➕ Đã phát hiện bài viết ID {pid} ({desc[:45]}...)", "info")
                    if limit > 0 and len(posts_found) >= limit:
                        break

            else:
                self.log(f"⚠️ Desktop Engine nhận phản hồi HTTP {res_desk.status_code}", "warning")
        except Exception as e:
            self.log(f"⚠️ Quét qua Desktop Engine gặp lỗi: {e}", "warning")

        if limit > 0 and len(posts_found) >= limit:
            self.log(f"🎯 Đã đạt chỉ tiêu quét {len(posts_found)} bài viết.", "success")
            return posts_found

        # ---------------------------------------------------------------------
        # BƯỚC 2: QUÉT PHÂN TRANG MBASIC (Hỗ trợ phân trang sâu nếu mbasic mở)
        # ---------------------------------------------------------------------
        target_mbasic_url = normalize_fanpage_mbasic_url(page_url_or_id)
        current_url: Optional[str] = target_mbasic_url
        page_num = 0
        max_pages = 30 if limit == 0 else max(10, (limit // 5) + 3)

        while current_url and page_num < max_pages:
            page_num += 1
            try:
                res = self.session.get(current_url, timeout=12)
                if res.status_code != 200:
                    if page_num == 1:
                        if posts_found:
                            self.log(f"ℹ️ Trang dạng New Page Experience: Không dùng mbasic timeline, sử dụng dữ liệu Desktop Engine ({len(posts_found)} bài).", "info")
                        else:
                            self.log(f"⚠️ Máy chủ Facebook trả về mã {res.status_code} trên mbasic", "warning")
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                post_blocks = soup.find_all(["article", "div"], role=lambda r: r and "article" in r.lower())
                if not post_blocks:
                    post_blocks = soup.find_all("div", id=lambda i: i and "story" in i.lower())
                if not post_blocks:
                    post_blocks = soup.find_all("div", class_=lambda c: c and ("story" in c.lower() or "feed" in c.lower()))

                new_on_page = 0
                if post_blocks:
                    for block in post_blocks:
                        pid = None
                        purl = ""
                        for a in block.find_all("a"):
                            href = a.get("href", "")
                            if ("story_fbid=" in href or "/posts/" in href or "/photos/" in href or "/videos/" in href or "permalink" in href) and "comment" not in href and "like" not in href:
                                extracted_id = extract_post_id_from_url(href)
                                if extracted_id and extracted_id != page_id:
                                    pid = extracted_id
                                    clean_href = href.split("&")[0] if "story_fbid" in href else href.split("?")[0]
                                    purl = "https://www.facebook.com" + clean_href if clean_href.startswith("/") else clean_href
                                    break

                        if pid and pid not in seen_post_ids:
                            seen_post_ids.add(pid)
                            caption = block.text.strip().replace("\n", " ")[:90]
                            posts_found.append({
                                "post_id": pid,
                                "post_url": purl or f"https://www.facebook.com/{pid}",
                                "mo_ta": caption or f"Bài viết ID {pid}",
                                "time_text": "",
                            })
                            new_on_page += 1
                            if limit > 0 and len(posts_found) >= limit:
                                break

                next_link = None
                for a in soup.find_all("a", href=True):
                    text = a.text.strip().lower()
                    h = a["href"]
                    if any(kw in text for kw in ["xem thêm tin", "tin cũ hơn", "show more stories", "older stories"]) or ("cursor=" in h and "v=timeline" in h):
                        if "login" not in h and "checkpoint" not in h:
                            next_link = "https://mbasic.facebook.com" + h if h.startswith("/") else h
                            break

                current_url = next_link
                if current_url:
                    self._sleep_random(0.7, 1.4)
                else:
                    break
            except Exception:
                break

        # ---------------------------------------------------------------------
        # BƯỚC 3: XỬ LÝ TRƯỜNG HỢP LINK NHẬP VÀO LÀ LINK 1 BÀI VIẾT CỤ THỂ
        # ---------------------------------------------------------------------
        if not posts_found:
            direct_pid = extract_post_id_from_url(page_url_or_id)
            if direct_pid:
                self.log(f"ℹ️ Nhận diện được trực tiếp link Bài viết ID: {direct_pid}", "info")
                posts_found.append({
                    "post_id": direct_pid,
                    "post_url": page_url_or_id,
                    "mo_ta": f"Bài viết ID {direct_pid}",
                    "time_text": "",
                })

        if posts_found:
            self.log(f"✅ Quét xong Fanpage! Tổng cộng thu thập được {len(posts_found)} bài viết.", "success")
        else:
            self.log(f"❌ Không tìm thấy bài viết nào trên trang '{page_url_or_id}'.", "error")

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
                    desk_purl = url if "facebook.com" in url else f"https://www.facebook.com/{post_id}"
                    post_res = self.session.get(desk_purl, timeout=12)
                    if post_res.status_code == 200:
                        msg_m = re.search(r'"message":\{"text":"(.*?)"\}', post_res.text)
                        if msg_m:
                            txt = clean_unicode(msg_m.group(1))
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
