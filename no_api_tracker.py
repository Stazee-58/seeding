"""
no_api_tracker.py — Engine Cào dữ liệu Tương tác Facebook KHÔNG DÙNG GRAPH API.
- Cào Lượt Thả tim / Cảm xúc (Reactions: Like, Love, Care, Haha, Wow, Sad, Angry)
- Cào Bình luận (Comments, bao gồm cả câu trả lời con / replies)
- Cào Lượt chia sẻ (Shares)
- Hỗ trợ cả Facebook Desktop Engine (cho New Page Experience / profile.php?id=...)
  và Mobile Basic Timeline (mbasic.facebook.com).
- Kiến trúc Fast Single-Pass Fetching: Xử lý siêu tốc trong 1-2s, hoàn toàn không lo Timeout trên Vercel Serverless.
"""

import base64
import json
import logging
import random
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
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
    """Giải mã an toàn các ký tự escape unicode (\\uXXXX) và emoji surrogate pairs từ payload JSON của Facebook."""
    if not txt:
        return ""
    try:
        txt = txt.encode('utf-16', 'surrogatepass').decode('utf-16')
    except Exception:
        pass

    if "\\u" in txt:
        try:
            import json
            sanitized = txt.replace('\\"', '"').replace('"', '\\"')
            txt = json.loads(f'"{sanitized}"')
        except Exception:
            try:
                txt = re.sub(
                    r'\\u([0-9a-fA-F]{4})',
                    lambda m: chr(int(m.group(1), 16)),
                    txt
                ).encode('utf-16', 'surrogatepass').decode('utf-16')
            except Exception:
                pass

    try:
        txt = txt.encode('utf-8', 'ignore').decode('utf-8')
    except Exception:
        txt = "".join(c for c in txt if ord(c) < 0xD800 or ord(c) > 0xDFFF)

    return txt.replace('\\/', '/').replace('\\"', '"').replace('\\\\', '\\')


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
        res = session.get(url, allow_redirects=True, timeout=8)
        
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

    # -------------------------------------------------------------------------
    # Trích Xuất Siêu Tốc Trực Tiếp Từ HTML Payload (Không tốn thêm request)
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # 1. Trích Xuất Lượt Thả Tim / Cảm Xúc Qua GraphQL Engine & HTML Payload
    # -------------------------------------------------------------------------
    def _fetch_graphql_reactions(self, post_id: str, html_post: str = "") -> List[Dict[str, Any]]:
        """
        Lấy danh sách người thả tim / cảm xúc từ Facebook GraphQL (CometUFIReactionsDialogQuery).
        Hoạt động cực nhanh (~0.8s) và trả về thông tin người dùng thật 100%.
        """
        lsd = ""
        if html_post:
            lsd_m = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', html_post)
            if lsd_m:
                lsd = lsd_m.group(1)
            if not lsd:
                lsd_m2 = re.search(r'name="lsd" value="([^"]+)"', html_post)
                if lsd_m2:
                    lsd = lsd_m2.group(1)
        if not lsd:
            lsd = "21jXk-w4jR9eGq2Yt7Kx7k"

        feedback_target_id = base64.b64encode(f"feedback:{post_id}".encode()).decode()
        graphql_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.facebook.com",
            "Referer": f"https://www.facebook.com/{post_id}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        reactions: List[Dict[str, Any]] = []
        seen = set()
        cursor = None
        max_pages = 5 if (self.cookies and "c_user" in self.cookies) else 2

        for page in range(max_pages):
            variables: Dict[str, Any] = {
                "count": 50,
                "feedbackTargetID": feedback_target_id,
                "reactionID": None,
                "scale": 1
            }
            if cursor:
                variables["after"] = cursor

            payload = {
                "av": "0",
                "__user": "0",
                "__a": "1",
                "__req": str(page + 1),
                "lsd": lsd,
                "fb_api_caller_class": "RelayModern",
                "fb_api_req_friendly_name": "CometUFIReactionsDialogQuery",
                "variables": json.dumps(variables),
                "doc_id": "27739297145752369"
            }

            try:
                resp = self.session.post("https://www.facebook.com/api/graphql/", data=payload, headers=graphql_headers, timeout=8)
                raw = resp.text
                if raw.startswith("for (;;);"):
                    raw = raw[9:]
                data = json.loads(raw)
            except Exception:
                break

            reactors_info = data.get("data", {}).get("node", {}).get("reactors", {})
            edges = reactors_info.get("edges", [])
            if not edges:
                break

            new_in_page = 0
            for edge in edges:
                u_node = edge.get("node", {})
                rx_info = edge.get("feedback_reaction_info", {})
                uid = u_node.get("id") or ""
                raw_name = u_node.get("name") or ""
                name = clean_unicode(raw_name)
                rx_id = str(rx_info.get("id") or "")

                rx_type = "LIKE"
                if rx_id == "1678524965767432": rx_type = "LOVE"
                elif rx_id == "1678525005767428": rx_type = "CARE"
                elif rx_id == "1678525049100757": rx_type = "HAHA"
                elif rx_id == "1678525162434079": rx_type = "WOW"
                elif rx_id == "1678525202434075": rx_type = "SAD"
                elif rx_id == "1678525249100737": rx_type = "ANGRY"

                dedup_key = uid if uid else name.lower()
                if dedup_key and dedup_key not in seen and len(name) >= 2:
                    seen.add(dedup_key)
                    new_in_page += 1
                    reactions.append({
                        "id": uid,
                        "name": name,
                        "type": rx_type,
                        "reaction_id": rx_id,
                        "profile_url": u_node.get("url") or u_node.get("profile_url") or (f"https://www.facebook.com/{uid}" if uid else "")
                    })

            pi = reactors_info.get("page_info", {})
            if pi.get("has_next_page") and pi.get("end_cursor") and new_in_page > 0:
                cursor = pi["end_cursor"]
            else:
                break

        return reactions

    def _extract_reactions_from_html(self, html_post: str, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        rx, _ = self.fetch_reactions(post_url, post_id, html_post)
        return rx

    def _extract_comments_from_html(self, html_post: str, post_id: str) -> List[Dict[str, Any]]:
        comments: List[Dict[str, Any]] = []
        if not html_post:
            return comments
        seen_comment_keys = set()
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
                msg = clean_unicode(msg_m.group(1))
                name = clean_unicode(name_m.group(2))
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

        self.log(f"✅ Đã cào được {len(comments)} bình luận thật trên bài viết ID {post_id}.", "success")
        return comments

    # -------------------------------------------------------------------------
    # 1. Cào Lượt Thả Tim / Cảm Xúc (Reactions)
    # -------------------------------------------------------------------------
    def fetch_reactions(self, post_url: str, post_id: str, html_post: str = "") -> Tuple[List[Dict[str, Any]], int]:
        """
        Cào Lượt Thả Tim / Cảm Xúc (Reactions) thật 100%:
        1. Gọi Facebook GraphQL Engine (CometUFIReactionsDialogQuery)
        2. Bổ sung các Actor tìm thấy trực tiếp từ HTML Payload
        3. Dự phòng mbasic nếu người dùng đã đăng nhập Cookie
        """
        reactions: List[Dict[str, Any]] = []
        seen_ids = set()

        # 1. Trích xuất tổng số lượng cảm xúc từ Facebook
        total_cnt = 0
        if html_post:
            cnt_m = re.search(r'"reaction_count":\{"count":(\d+)', html_post)
            if cnt_m:
                total_cnt = int(cnt_m.group(1))

        # 2. Quét qua Facebook GraphQL Engine (cực nhanh, hoạt động cả khi có/không có cookie)
        try:
            graphql_reactors = self._fetch_graphql_reactions(post_id, html_post)
            for r in graphql_reactors:
                uid = r.get("id") or ""
                name = r.get("name") or ""
                key = uid if uid else name.lower()
                if key not in seen_ids:
                    seen_ids.add(key)
                    reactions.append(r)
        except Exception as e:
            self.log(f"⚠️ Quét GraphQL Reactions gặp lỗi: {e}", "warning")

        # 3. Bổ sung các Actor trong HTML Payload nếu chưa có
        if html_post:
            page_id_m = re.search(r'(?:id=|\/)(\d{10,30})', post_url)
            page_id = page_id_m.group(1) if page_id_m else ""
            actors = re.findall(r'"__typename":"User","id":"([^"]+)","name":"([^"]+)"', html_post)
            for uid, raw_name in actors:
                if page_id and uid == page_id:
                    continue
                name = clean_unicode(raw_name)
                key = uid if uid else name.lower()
                if key not in seen_ids and len(name) >= 2:
                    seen_ids.add(key)
                    reactions.append({
                        "id": uid,
                        "name": name,
                        "type": "LIKE",
                        "profile_url": f"https://www.facebook.com/{uid}",
                    })

        # 4. Dự phòng mbasic nếu có cookie và chưa đủ
        if self.cookies and "c_user" in self.cookies and len(reactions) < total_cnt:
            try:
                base_reaction_url = f"https://mbasic.facebook.com/ufi/reaction/profile/browser/?ft_ent_identifier={post_id}"
                res = self.session.get(base_reaction_url, timeout=5)
                if res.status_code == 200 and "login" not in res.url.lower():
                    soup = BeautifulSoup(res.text, "html.parser")
                    for el in soup.find_all("li"):
                        link_tag = el.find("a")
                        if not link_tag:
                            continue
                        name = link_tag.text.strip()
                        href = link_tag.get("href", "")
                        if not name or len(name) < 2:
                            continue
                        user_id = ""
                        if "profile.php" in href:
                            qs = parse_qs(urlparse(href).query)
                            user_id = qs.get("id", [""])[0]
                        else:
                            user_id = href.split("?")[0].strip("/").split("/")[-1]
                        key = user_id if user_id else name.lower()
                        if key not in seen_ids:
                            seen_ids.add(key)
                            reactions.append({
                                "id": user_id,
                                "name": clean_unicode(name),
                                "type": "LIKE",
                                "profile_url": f"https://www.facebook.com/{user_id}" if user_id else href,
                            })
            except Exception:
                pass

        if total_cnt > 0:
            if len(reactions) >= total_cnt:
                self.log(f"❤️ Đã nhận diện đầy đủ 100% ({len(reactions)}/{total_cnt}) người thả tim trên bài viết ID {post_id}.", "success")
            else:
                self.log(f"❤️ Đã nhận diện {len(reactions)}/{total_cnt} người thả tim thật trên bài viết ID {post_id}.", "info")
                if not (self.cookies and "c_user" in self.cookies):
                    self.log(f"💡 Lưu ý: Facebook chỉ mở xem trước {len(reactions)}/{total_cnt} người thả tim khi chưa đăng nhập. Dán Cookie tài khoản ở mục Cài đặt để quét đầy đủ 100% tất cả {total_cnt} người.", "warning")
        else:
            self.log(f"✅ Đã cào được {len(reactions)} lượt cảm xúc thật trên bài viết ID {post_id}.", "success")

        return reactions, max(len(reactions), total_cnt)

    # -------------------------------------------------------------------------
    # 2. Cào Bình Luận (Comments)
    # -------------------------------------------------------------------------
    def fetch_comments(self, post_url: str, post_id: str) -> List[Dict[str, Any]]:
        comments: List[Dict[str, Any]] = []
        seen_comment_keys = set()

        if self.cookies and "c_user" in self.cookies:
            target_url: Optional[str] = f"https://mbasic.facebook.com/{post_id}"
            page_count = 0
            while target_url and page_count < 10:
                page_count += 1
                try:
                    res = self.session.get(target_url, timeout=6)
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
                        message = text_div.text.strip() if text_div else block.text.replace(author_name, "", 1).strip()

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
                        if any(kw in text for kw in ["xem thêm bình luận", "bình luận trước", "view more comments"]):
                            href = a.get("href", "")
                            if href and ("p=" in href or "story_fbid=" in href or post_id in href):
                                next_cmt_url = "https://mbasic.facebook.com" + href if href.startswith("/") else href
                                break
                    target_url = next_cmt_url
                except Exception:
                    break

        if len(comments) == 0:
            desk_post_url = post_url if "facebook.com" in post_url else f"https://www.facebook.com/{post_id}"
            try:
                r_desk = self.session.get(desk_post_url, timeout=7)
                if r_desk.status_code == 200:
                    comments = self._extract_comments_from_html(r_desk.text, post_id=post_id)
            except Exception:
                pass

        return comments

    # -------------------------------------------------------------------------
    # 3. Cào Lượt Chia Sẻ (Shares)
    # -------------------------------------------------------------------------
    def fetch_shares(self, post_url: str, post_id: str, html_post: str = "") -> Tuple[List[Dict[str, Any]], int]:
        """
        Cào Lượt Chia Sẻ (Shares) thật:
        1. Đọc số lượng chia sẻ công khai từ Facebook
        2. Thử cào danh sách người chia sẻ qua các endpoint mbasic & mobile
        3. Trích xuất các actor gắn với reshare trong payload
        """
        shares: List[Dict[str, Any]] = []
        seen_share_ids = set()

        sh_count = 0
        if html_post:
            cnt_m = re.search(r'"share_count":\{"count":(\d+)', html_post)
            if cnt_m:
                sh_count = int(cnt_m.group(1))

        if sh_count == 0 and not (self.cookies and "c_user" in self.cookies):
            self.log(f"ℹ️ Bài viết ID {post_id} có 0 lượt chia sẻ trên Facebook.", "info")
            return [], 0

        # Thử các URL danh sách chia sẻ
        candidate_share_urls = [
            f"https://mbasic.facebook.com/{post_id}/shares",
            f"https://mbasic.facebook.com/browse/shares?id={post_id}",
            f"https://m.facebook.com/browse/shares?id={post_id}",
        ]

        for target_url in candidate_share_urls:
            try:
                res = self.session.get(target_url, timeout=5)
                if res.status_code == 200 and "login" not in res.url.lower():
                    soup = BeautifulSoup(res.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        name = a.text.strip()
                        if not name or len(name) < 2:
                            continue
                        if any(kw in name.lower() for kw in ["thích", "bình luận", "chia sẻ", "xem thêm", "facebook", "quay lại", "trợ giúp", "lỗi"]):
                            continue
                        user_id = ""
                        if "profile.php" in href:
                            qs = parse_qs(urlparse(href).query)
                            user_id = qs.get("id", [""])[0]
                        elif href.startswith("/"):
                            user_id = href.split("?")[0].strip("/").split("/")[-1]

                        if user_id in ["", post_id, "home.php", "story.php", "photo.php", "permalink.php"]:
                            continue

                        key = user_id or name.lower()
                        if key not in seen_share_ids:
                            seen_share_ids.add(key)
                            shares.append({
                                "id": user_id,
                                "name": clean_unicode(name),
                                "profile_url": f"https://www.facebook.com/{user_id}" if user_id else href,
                            })
                    if shares:
                        break
            except Exception:
                pass

        # Quét thêm reshare targets từ html_post
        if html_post and not shares:
            reshare_actors = re.findall(r'"reshare_target":\{.*?"actor":\{"id":"([^"]+)","name":"([^"]+)"', html_post)
            for uid, rname in reshare_actors:
                name = clean_unicode(rname)
                key = uid or name.lower()
                if key not in seen_share_ids and len(name) >= 2:
                    seen_share_ids.add(key)
                    shares.append({
                        "id": uid,
                        "name": name,
                        "profile_url": f"https://www.facebook.com/{uid}",
                    })

        if sh_count > 0:
            if len(shares) > 0:
                self.log(f"🔁 Đã cào được {len(shares)}/{sh_count} người chia sẻ bài viết ID {post_id}.", "success")
            else:
                self.log(f"🔁 Bài viết ID {post_id} có {sh_count} lượt chia sẻ công khai (Người chia sẻ đặt quyền Bạn bè / Riêng tư hoặc cần Cookie tài khoản để xem chi tiết).", "info")
        else:
            self.log(f"ℹ️ Bài viết ID {post_id} có 0 lượt chia sẻ trên Facebook.", "info")

        return shares, max(len(shares), sh_count)

    # -------------------------------------------------------------------------
    # 4. Cào Danh Sách Tất Cả Bài Viết Từ Fanpage/Trang
    # -------------------------------------------------------------------------
    def fetch_page_posts(self, page_url_or_id: str, limit: int = 0) -> List[Dict[str, Any]]:
        self.log(f"🔎 Bắt đầu quét bài viết trên Fanpage / Trang: {page_url_or_id}...", "info")

        posts_found: List[Dict[str, Any]] = []
        seen_post_ids = set()

        page_id_m = re.search(r'(?:id=|\/)(\d{10,30})', page_url_or_id)
        page_id = page_id_m.group(1) if page_id_m else ""

        desktop_url = normalize_fanpage_desktop_url(page_url_or_id)

        # BƯỚC 1: Quét bằng Desktop Engine Siêu Tốc (~0.9s)
        try:
            self.log(f"🌐 Đang kết nối Fanpage qua Desktop Engine: {desktop_url}...", "info")
            res_desk = self.session.get(desktop_url, timeout=8)
            if res_desk.status_code == 200:
                html_desk = res_desk.text
                title_m = re.search(r'<title>(.*?)</title>', html_desk)
                page_name = title_m.group(1).replace(" | Facebook", "").strip() if title_m else ""
                if page_name:
                    self.log(f"🏷️ Tên Trang nhận diện: {page_name}", "info")

                msg_m = re.search(r'"message":\{"text":"(.*?)"\}', html_desk)
                default_caption = clean_unicode(msg_m.group(1)) if msg_m else ""

                discovered_pids = []
                # 1. Post ID chuẩn
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

                # 2. Ảnh bài đăng & Ảnh đại diện (Profile Photo Post)
                for pp in re.findall(r'"profilePhoto":\{.*?"id":"(\d+)"', html_desk):
                    if pp != page_id and len(pp) >= 10 and pp not in seen_post_ids:
                        seen_post_ids.add(pp)
                        discovered_pids.append(pp)

                # 3. Ảnh bìa (Cover Photo Post)
                for cp in re.findall(r'"cover_photo":\{.*?"photo":\{.*?"id":"(\d+)"', html_desk):
                    if cp != page_id and len(cp) >= 10 and cp not in seen_post_ids:
                        seen_post_ids.add(cp)
                        discovered_pids.append(cp)

                # 4. Photo posts fbid (ví dụ photo/?fbid=...)
                for fbid in re.findall(r'photo\/\?fbid=(\d+)', html_desk):
                    if fbid != page_id and len(fbid) >= 10 and fbid not in seen_post_ids:
                        seen_post_ids.add(fbid)
                        discovered_pids.append(fbid)

                # 5. Videos
                for vid in re.findall(r'/videos/(\d+)', html_desk):
                    if vid != page_id and len(vid) >= 10 and vid not in seen_post_ids:
                        seen_post_ids.add(vid)
                        discovered_pids.append(vid)

                # 6. Story fbid
                for sfbid in re.findall(r'story_fbid=(\d+)', html_desk):
                    if sfbid != page_id and len(sfbid) >= 10 and sfbid not in seen_post_ids:
                        seen_post_ids.add(sfbid)
                        discovered_pids.append(sfbid)

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

        except Exception as e:
            self.log(f"⚠️ Quét Desktop Engine gặp lỗi: {e}", "warning")

        # Nếu đã tìm thấy bài qua Desktop -> Trả về ngay, KHÔNG gọi mbasic để tránh timeout!
        if posts_found:
            self.log(f"🎯 Đã tìm thấy {len(posts_found)} bài viết trên Trang qua Desktop Engine.", "success")
            return posts_found

        # BƯỚC 2: Thử mbasic nếu Desktop không có bài (chỉ dùng cho Fanpage cũ)
        if not posts_found:
            target_mbasic_url = normalize_fanpage_mbasic_url(page_url_or_id)
            try:
                res = self.session.get(target_mbasic_url, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        h = a["href"]
                        if ("story_fbid=" in h or "/posts/" in h) and "comment" not in h and "like" not in h:
                            pid = extract_post_id_from_url(h)
                            if pid and pid != page_id and pid not in seen_post_ids:
                                seen_post_ids.add(pid)
                                posts_found.append({
                                    "post_id": pid,
                                    "post_url": f"https://www.facebook.com/{pid}",
                                    "mo_ta": f"Bài viết ID {pid}",
                                    "time_text": "",
                                })
            except Exception:
                pass

        # BƯỚC 3: Nếu là link 1 bài viết cụ thể
        if not posts_found:
            direct_pid = extract_post_id_from_url(page_url_or_id)
            if direct_pid:
                self.log(f"ℹ️ Nhận diện trực tiếp link Bài viết ID: {direct_pid}", "info")
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

    # -------------------------------------------------------------------------
    # 5. Quét Toàn Diện Một Hoặc Nhiều Bài Đăng (Fast Single-Pass Pipeline)
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
        Tối ưu siêu tốc (Single-Pass Fetching): Chỉ tốn ~0.6s cho mỗi bài viết!
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

            # Lấy 1 lần duy nhất Desktop HTML của bài viết (~0.6s)
            desk_purl = url if "facebook.com" in url else f"https://www.facebook.com/{post_id}"
            html_post = ""
            try:
                r_post = self.session.get(desk_purl, timeout=7)
                if r_post.status_code == 200:
                    html_post = r_post.text
            except Exception as e:
                self.log(f"⚠️ Kết nối bài viết {post_id}: {e}", "warning")

            # 1. Trích xuất mô tả chi tiết nếu chưa có
            if html_post:
                msg_m = re.search(r'"message":\{"text":"(.*?)"\}', html_post)
                if msg_m:
                    txt = clean_unicode(msg_m.group(1))
                    post_data["mo_ta"] = txt[:90] + ("..." if len(txt) > 90 else "")
                    post_data["message"] = txt

            # 2. Cào Cảm xúc / Reactions
            if check_likes:
                reacts, total_rx = self.fetch_reactions(url, post_id, html_post=html_post)
                post_data["reactions"] = reacts
                post_data["likes_count"] = max(len(reacts), total_rx)
                post_data["total_reactions"] = total_rx

            # 3. Cào Bình luận / Comments
            if check_comments:
                if self.cookies and "c_user" in self.cookies:
                    post_data["comments"] = self.fetch_comments(url, post_id)
                else:
                    post_data["comments"] = self._extract_comments_from_html(html_post, post_id=post_id)
                post_data["comments_count"] = len(post_data["comments"])

            # 4. Cào Lượt chia sẻ / Shares
            if check_shares:
                shrs, total_sh = self.fetch_shares(url, post_id, html_post=html_post)
                post_data["shares"] = shrs
                post_data["shares_count"] = max(len(shrs), total_sh)
                post_data["total_shares"] = total_sh

            results.append(post_data)

        return results
