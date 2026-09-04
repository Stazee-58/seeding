"""
report.py — Xuất báo cáo Excel 4 sheet từ kết quả đối chiếu không cần API:
  1. Chi_tiet_Thanh_vien — Mỗi dòng là 1 cặp (bài đăng × thành viên), chi tiết comment, like, share
  2. Nguoi_la_tuong_tac  — Danh sách người ngoài nhóm tương tác (comment / like / thả tim / share)
  3. Tong_hop_bai        — Mỗi dòng là 1 bài đăng, thống kê thành viên vs người lạ
  4. Can_nhac_nho        — Thành viên chưa tương tác đối với các bài viết
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
    output_dir: str = "",
) -> str:
    """Tạo file Excel báo cáo hoàn chỉnh."""
    wb = Workbook()
    wb.remove(wb.active)  # Xoá sheet mặc định

    # -------------------------------------------------------------------------
    # Sheet 1: Chi tiết thành viên
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Sheet 2: Người lạ tương tác
    # -------------------------------------------------------------------------
    ws2 = wb.create_sheet(title="Nguoi_la_tuong_tac")
    h2 = ["STT", "Mô tả bài đăng", "Link bài", "Tên người lạ", "Facebook ID / Link", "Loại tương tác", "Nội dung tương tác", "Thời gian"]
    _write_header(ws2, h2)

    for idx, s in enumerate(stranger_results, start=1):
        row_vals = [
            idx,
            s.get("mo_ta", ""),
            s.get("permalink_url", ""),
            s.get("nguoi_dung", ""),
            s.get("facebook_id", ""),
            s.get("loai_tuong_tac", ""),
            s.get("noi_dung", ""),
            s.get("thoi_gian", ""),
        ]
        _write_row(ws2, idx + 1, row_vals, fill=_STRANGER_FILL)

    _auto_fit_columns(ws2)

    # -------------------------------------------------------------------------
    # Sheet 3: Tổng hợp bài viết
    # -------------------------------------------------------------------------
    ws3 = wb.create_sheet(title="Tong_hop_bai")
    h3 = ["STT", "ID bài đăng", "Mô tả bài", "Link bài", "Lượt Like thực tế", "Lượt Comment thực tế", "Lượt Share thực tế"]
    _write_header(ws3, h3)

    for idx, (pid, pdata) in enumerate(collected.items(), start=1):
        row_vals = [
            idx,
            pid,
            pdata.get("mo_ta", f"Bài {pid}"),
            pdata.get("permalink_url", ""),
            len(pdata.get("reactions", [])),
            len(pdata.get("comments", [])),
            len(pdata.get("shares", [])),
        ]
        _write_row(ws3, idx + 1, row_vals)

    _auto_fit_columns(ws3)

    # -------------------------------------------------------------------------
    # Sheet 4: Cần nhắc nhở (Chưa tương tác)
    # -------------------------------------------------------------------------
    ws4 = wb.create_sheet(title="Can_nhac_nho")
    h4 = ["STT", "Họ và tên", "Facebook ID", "Tên hiển thị", "Bài chưa làm", "Link bài"]
    _write_header(ws4, h4)

    remind_idx = 1
    for r in match_results:
        if r.get("trang_thai") == "chua_tuong_tac":
            row_vals = [
                remind_idx,
                r.get("ho_ten", ""),
                r.get("facebook_id", ""),
                r.get("ten_hien_thi", ""),
                r.get("mo_ta", ""),
                r.get("permalink_url", ""),
            ]
            _write_row(ws4, remind_idx + 1, row_vals, fill=_RED_FILL)
            remind_idx += 1

    _auto_fit_columns(ws4)

    # Lưu file
    if not output_dir:
        output_dir = tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bao_cao_tracking_no_api_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    wb.save(filepath)
    return filepath
