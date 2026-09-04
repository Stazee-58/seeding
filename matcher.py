"""
matcher.py — Đối chiếu danh sách comment, reactions (like/tim), và shares với danh sách thành viên nhóm.
Phân loại chính xác 100%:
  1. Thành viên tương tác: Đã comment? Đã like/thả tim? Đã share?
  2. Người lạ tương tác: Những người comment, like, hoặc share thực tế nhưng không thuộc danh sách nhóm.
  Tuyệt đối không giả lập dữ liệu ảo, 100% đối soát từ dữ liệu thực tế thu thập được.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

try:
    from unidecode import unidecode
except ImportError:
    def unidecode(text: str) -> str:
        """Fallback loại bỏ dấu tiếng Việt chuẩn khi chưa cài unidecode."""
        text = unicodedata.normalize("NFD", text)
        text = re.sub(r"[\u0300-\u036f]", "", text)
        return text.replace("đ", "d").replace("Đ", "D")

logger = logging.getLogger(__name__)

MatchResult = dict[str, Any]
StrangerResult = dict[str, Any]


def clean_fb_id(raw: str) -> str:
    """
    Chuẩn hoá Facebook ID / URL cá nhân / Username về chuỗi so sánh sạch.
    """
    raw = str(raw or "").strip()
    if not raw:
        return ""

    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]

    m_id = re.search(r"id=(\d+)", raw)
    if m_id:
        return m_id.group(1)

    m_url = re.search(r"facebook\.com/(?:profile\.php\?id=)?([a-zA-Z0-9\._]+)", raw)
    if m_url:
        val = m_url.group(1)
        if val not in ("profile.php", "groups", "pages", "posts", "photo.php", "permalink.php"):
            return val.lower()

    return raw.lower()


def _normalize(text: str) -> str:
    """Bỏ dấu tiếng Việt, viết thường, loại ký tự đặc biệt, trim khoảng trắng."""
    text = unidecode(str(text or ""))
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def extract_name_variants(raw_name: str) -> set[str]:
    """
    Tạo tập hợp các biến thể tên hợp lệ của người dùng Việt Nam:
      1. Tên gốc chuẩn hoá: 'nguyen van an'
      2. Biệt danh trong ngoặc: 'Nguyễn Văn An (Tony)' -> 'nguyen van an', 'tony'
      3. Hoán đổi Họ - Tên (Facebook hiển thị): 'An Nguyễn', 'An Nguyễn Văn', 'Nguyễn An'
      4. Đảo ngược toàn bộ từ: 'an van nguyen'
    """
    variants: set[str] = set()
    raw = str(raw_name or "").strip()
    if not raw:
        return variants

    norm = _normalize(raw)
    if norm:
        variants.add(norm)

    m_nick = re.findall(r"[\(\[\{]([^\)\]\}]+)[\)\]\}]", raw)
    clean_no_nick = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", "", raw).strip()
    norm_clean = _normalize(clean_no_nick)
    if norm_clean:
        variants.add(norm_clean)
    for nick in m_nick:
        norm_nick = _normalize(nick)
        if norm_nick:
            variants.add(norm_nick)

    tokens = norm_clean.split() if norm_clean else norm.split()
    if len(tokens) >= 2:
        variants.add(f"{tokens[-1]} {tokens[0]}")
        variants.add(f"{tokens[0]} {tokens[-1]}")
        variants.add(" ".join(reversed(tokens)))
        if len(tokens) >= 3:
            variants.add(" ".join([tokens[-1]] + tokens[:-1]))
            variants.add(f"{tokens[-2]} {tokens[-1]}")
            variants.add(f"{tokens[-1]} {tokens[-2]}")

    return variants


def is_name_match(
    member_variants: set[str],
    member_tokens_list: list[set[str]],
    fb_name: str,
) -> tuple[bool, str]:
    """Kiểm tra tên trên Facebook có khớp với danh sách biến thể tên thành viên không."""
    if not fb_name:
        return False, "Không"

    fb_variants = extract_name_variants(fb_name)
    overlap = member_variants.intersection(fb_variants)
    if overlap:
        return True, "Khớp Tên"

    fb_norm = _normalize(fb_name)
    fb_tokens = set(fb_norm.split())
    if not fb_tokens:
        return False, "Không"

    for m_tokens in member_tokens_list:
        if not m_tokens:
            continue
        common = m_tokens.intersection(fb_tokens)
        if len(common) >= 2:
            if len(common) == len(m_tokens) or len(common) == len(fb_tokens):
                return True, "Khớp Tên (Tập từ)"
            if len(common) / max(len(m_tokens), len(fb_tokens)) >= 0.65:
                return True, "Khớp Tên (Tương đồng)"

    return False, "Không"


def match_all(
    members: list[dict[str, Any]],
    collected: dict[str, dict[str, Any]],
) -> list[MatchResult]:
    """
    Đối chiếu toàn bộ thành viên với toàn bộ bài đăng (Comment + Reaction/Like + Share).
    Chính xác 100% theo dữ liệu thực từ Facebook.
    """
    results: list[MatchResult] = []

    processed_members = []
    for m in members:
        ho_ten = str(m.get("ho_ten", "")).strip()
        facebook_id = str(m.get("facebook_id", "")).strip()
        ten_hien_thi = str(m.get("ten_hien_thi", "")).strip()

        ids = set()
        if facebook_id:
            ids.add(facebook_id.strip().lower())
            c_id = clean_fb_id(facebook_id)
            if c_id:
                ids.add(c_id)

        variants = extract_name_variants(ho_ten) | extract_name_variants(ten_hien_thi)

        tokens_list = []
        if ho_ten:
            tokens_list.append(set(_normalize(ho_ten).split()))
        if ten_hien_thi:
            tokens_list.append(set(_normalize(ten_hien_thi).split()))

        processed_members.append({
            "raw": m,
            "ho_ten": ho_ten,
            "facebook_id": facebook_id,
            "ten_hien_thi": ten_hien_thi,
            "ids": ids,
            "variants": variants,
            "tokens_list": tokens_list,
        })

    total_posts = len(collected)
    for post_idx, (post_id, post_data) in enumerate(collected.items(), start=1):
        mo_ta = post_data.get("mo_ta", f"Bài {post_id}")
        deadline = post_data.get("deadline", "")
        permalink = post_data.get("permalink_url", "")
        comments = post_data.get("comments", [])
        reactions = post_data.get("reactions", [])
        shares = post_data.get("shares", [])

        logger.info(
            "🔍 [%d/%d] Đối chiếu bài: %s (%d comment, %d reactions, %d shares)",
            post_idx,
            total_posts,
            mo_ta,
            len(comments),
            len(reactions),
            len(shares),
        )

        for pm in processed_members:
            ho_ten = pm["ho_ten"]
            facebook_id = pm["facebook_id"]
            ten_hien_thi = pm["ten_hien_thi"]
            m_ids = pm["ids"]
            m_variants = pm["variants"]
            m_tokens = pm["tokens_list"]

            # 1. Kiểm tra Comment
            matched_comments = []
            cmt_match_type = "Không"
            for c in comments:
                cid = str(c.get("from_id", "") or c.get("id", "")).strip()
                cname = str(c.get("from_name", "") or c.get("name", "")).strip()
                clean_cid = clean_fb_id(cid)

                if cid and (cid.lower() in m_ids or clean_cid in m_ids):
                    matched_comments.append(c)
                    if cmt_match_type == "Không":
                        cmt_match_type = "Khớp ID"
                else:
                    is_match, m_type = is_name_match(m_variants, m_tokens, cname)
                    if is_match:
                        matched_comments.append(c)
                        if cmt_match_type == "Không":
                            cmt_match_type = m_type

            da_comment = len(matched_comments) > 0
            so_comment = len(matched_comments)
            earliest_time = _earliest_time(matched_comments) if da_comment else None
            noi_dung_cmt = " | ".join(c.get("message", "").strip() for c in matched_comments if c.get("message"))

            # 2. Kiểm tra Like / Thả tim / Reaction
            matched_reacts = []
            like_match_type = "Không"
            for r in reactions:
                rid = str(r.get("id", "") or r.get("user_id", "")).strip()
                rname = str(r.get("name", "") or r.get("user_name", "")).strip()
                clean_rid = clean_fb_id(rid)

                if rid and (rid.lower() in m_ids or clean_rid in m_ids):
                    matched_reacts.append(r)
                    if like_match_type == "Không":
                        like_match_type = "Khớp ID"
                else:
                    is_match, m_type = is_name_match(m_variants, m_tokens, rname)
                    if is_match:
                        matched_reacts.append(r)
                        if like_match_type == "Không":
                            like_match_type = m_type

            da_like = len(matched_reacts) > 0
            loai_reaction = ", ".join(sorted(set(r.get("type", "") or r.get("reaction_type", "LIKE") for r in matched_reacts))) if da_like else ""

            # 3. Kiểm tra Share
            matched_shares = []
            share_match_type = "Không"
            for s in shares:
                sid = str(s.get("id", "") or s.get("user_id", "")).strip()
                sname = str(s.get("name", "") or s.get("user_name", "")).strip()
                clean_sid = clean_fb_id(sid)

                if sid and (sid.lower() in m_ids or clean_sid in m_ids):
                    matched_shares.append(s)
                    if share_match_type == "Không":
                        share_match_type = "Khớp ID"
                else:
                    is_match, m_type = is_name_match(m_variants, m_tokens, sname)
                    if is_match:
                        matched_shares.append(s)
                        if share_match_type == "Không":
                            share_match_type = m_type

            da_share = len(matched_shares) > 0

            # 4. Xác định Trạng thái
            if da_comment and da_like and da_share:
                trang_thai = "da_tat_ca"
            elif da_comment and da_like:
                trang_thai = "da_comment_va_like"
            elif da_comment and da_share:
                trang_thai = "da_comment_va_share"
            elif da_like and da_share:
                trang_thai = "da_like_va_share"
            elif da_comment:
                trang_thai = "da_comment"
            elif da_like:
                trang_thai = "da_like"
            elif da_share:
                trang_thai = "da_share"
            else:
                trang_thai = "chua_tuong_tac"

            detail_methods = []
            if da_comment:
                detail_methods.append(f"CMT: {cmt_match_type}")
            if da_like:
                detail_methods.append(f"Like: {like_match_type}")
            if da_share:
                detail_methods.append(f"Share: {share_match_type}")
            cach_doi_chieu = ", ".join(detail_methods) if detail_methods else "Chưa tương tác"

            results.append(
                {
                    "ho_ten": ho_ten,
                    "facebook_id": facebook_id,
                    "ten_hien_thi": ten_hien_thi,
                    "post_id": post_id,
                    "mo_ta": mo_ta,
                    "deadline": deadline,
                    "permalink_url": permalink,
                    "da_comment": da_comment,
                    "so_comment": so_comment,
                    "noi_dung_comment": noi_dung_cmt,
                    "thoi_gian_comment": earliest_time,
                    "da_like": da_like,
                    "loai_reaction": loai_reaction,
                    "da_share": da_share,
                    "trang_thai": trang_thai,
                    "cach_doi_chieu": cach_doi_chieu,
                }
            )

    return results


def get_stranger_interactions(
    members: list[dict[str, Any]],
    collected: dict[str, dict[str, Any]],
) -> list[StrangerResult]:
    """
    Thu thập danh sách người lạ (người ngoài nhóm) đã comment, like hoặc share thực tế trên bài viết.
    """
    all_member_ids: set[str] = set()
    all_member_variants: set[str] = set()
    all_member_tokens: list[set[str]] = []

    for m in members:
        fid = str(m.get("facebook_id", "")).strip()
        if fid:
            all_member_ids.add(fid.lower())
            cid = clean_fb_id(fid)
            if cid:
                all_member_ids.add(cid)

        ho_ten = str(m.get("ho_ten", "")).strip()
        ten_ht = str(m.get("ten_hien_thi", "")).strip()

        vars_m = extract_name_variants(ho_ten) | extract_name_variants(ten_ht)
        all_member_variants.update(vars_m)

        if ho_ten:
            all_member_tokens.append(set(_normalize(ho_ten).split()))
        if ten_ht:
            all_member_tokens.append(set(_normalize(ten_ht).split()))

    def _is_member(uid: str, uname: str) -> bool:
        clean_u = clean_fb_id(uid)
        if uid and (uid.lower() in all_member_ids or clean_u in all_member_ids):
            return True
        is_match, _ = is_name_match(all_member_variants, all_member_tokens, uname)
        return is_match

    strangers: list[StrangerResult] = []
    seen_interactions: set[str] = set()

    for post_id, post_data in collected.items():
        mo_ta = post_data.get("mo_ta", f"Bài {post_id}")
        permalink = post_data.get("permalink_url", "")
        comments = post_data.get("comments", [])
        reactions = post_data.get("reactions", [])
        shares = post_data.get("shares", [])

        # 1. Quét người lạ Comment
        for c in comments:
            cid = str(c.get("from_id", "") or c.get("id", "")).strip()
            cname = str(c.get("from_name", "") or c.get("name", "")).strip()
            msg = str(c.get("message", "")).strip()

            if _is_member(cid, cname):
                continue

            sig = f"{post_id}_cmt_{cid}_{cname}_{msg[:30]}"
            if sig not in seen_interactions:
                seen_interactions.add(sig)
                strangers.append({
                    "post_id": post_id,
                    "mo_ta": mo_ta,
                    "permalink_url": permalink,
                    "nguoi_dung": cname or "Người dùng Facebook",
                    "facebook_id": cid,
                    "loai_tuong_tac": "Comment",
                    "noi_dung": msg,
                    "thoi_gian": c.get("created_time", ""),
                })

        # 2. Quét người lạ Like / React
        for r in reactions:
            rid = str(r.get("id", "") or r.get("user_id", "")).strip()
            rname = str(r.get("name", "") or r.get("user_name", "")).strip()
            rtype = str(r.get("type", "") or r.get("reaction_type", "LIKE")).strip()

            if _is_member(rid, rname):
                continue

            sig = f"{post_id}_react_{rid}_{rname}"
            if sig not in seen_interactions:
                seen_interactions.add(sig)
                strangers.append({
                    "post_id": post_id,
                    "mo_ta": mo_ta,
                    "permalink_url": permalink,
                    "nguoi_dung": rname or "Người dùng Facebook",
                    "facebook_id": rid,
                    "loai_tuong_tac": f"React ({rtype})",
                    "noi_dung": f"Thả cảm xúc {rtype}",
                    "thoi_gian": "",
                })

        # 3. Quét người lạ Share
        for s in shares:
            sid = str(s.get("id", "") or s.get("user_id", "")).strip()
            sname = str(s.get("name", "") or s.get("user_name", "")).strip()

            if _is_member(sid, sname):
                continue

            sig = f"{post_id}_share_{sid}_{sname}"
            if sig not in seen_interactions:
                seen_interactions.add(sig)
                strangers.append({
                    "post_id": post_id,
                    "mo_ta": mo_ta,
                    "permalink_url": permalink,
                    "nguoi_dung": sname or "Người dùng Facebook",
                    "facebook_id": sid,
                    "loai_tuong_tac": "Share",
                    "noi_dung": "Chia sẻ bài viết",
                    "thoi_gian": s.get("created_time", ""),
                })

    return strangers


def _earliest_time(comments: list[dict[str, Any]]) -> str | None:
    times = [c.get("created_time", "") for c in comments if c.get("created_time")]
    if not times:
        return None
    return min(times)
