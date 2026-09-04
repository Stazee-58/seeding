"""
database.py — Quản lý cơ sở dữ liệu SQLite cho hệ thống Web Tracking Facebook (No API).
- Quản lý tài khoản người dùng, phân quyền (Admin / User)
- Quản lý trạng thái kích hoạt tài khoản
- Khởi tạo sẵn tài khoản Admin: nguyenhaonhien40@gmail.com / 050810
"""

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional

if os.environ.get("VERCEL"):
    DB_FILE = "/tmp/tracking_no_api.db"
else:
    DB_FILE = os.path.join(os.path.dirname(__file__), "tracking_no_api.db")

HOTLINE = "0984113158"
ADMIN_EMAIL = "nguyenhaonhien40@gmail.com"
ADMIN_DEFAULT_PASS = "050810"


def hash_password(password: str) -> str:
    """Băm mật khẩu an toàn với muối cố định + SHA256."""
    salt = "mxhfb_tracking_no_api_salt_2026"
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Khởi tạo cấu trúc các bảng và tạo sẵn tài khoản Admin."""
    conn = get_db()
    cursor = conn.cursor()

    # Bảng người dùng
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # Bảng phiên đăng nhập (Session)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Bảng lịch sử quét Tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracking_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        campaign_name TEXT,
        post_count INTEGER DEFAULT 0,
        member_count INTEGER DEFAULT 0,
        report_path TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    conn.commit()

    # Khởi tạo sẵn tài khoản Admin nếu chưa tồn tại
    admin = get_user_by_email(ADMIN_EMAIL)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    admin_hash = hash_password(ADMIN_DEFAULT_PASS)

    if not admin:
        cursor.execute("""
        INSERT INTO users (email, password_hash, full_name, phone, role, is_active, created_at)
        VALUES (?, ?, ?, ?, 'admin', 1, ?)
        """, (ADMIN_EMAIL, admin_hash, "Nguyễn Hạo Nhiên (Admin)", HOTLINE, now_str))
        conn.commit()
        print(f"[*] Da khoi tao tai khoan Admin mac dinh: {ADMIN_EMAIL}")
    else:
        # Luôn đảm bảo tài khoản admin có quyền admin, is_active = 1 và đúng mật khẩu
        cursor.execute("""
        UPDATE users 
        SET role = 'admin', is_active = 1, password_hash = ?
        WHERE LOWER(email) = LOWER(?)
        """, (admin_hash, ADMIN_EMAIL))
        conn.commit()

    conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(email: str, password: str, full_name: str, phone: str = "", role: str = "user", is_active: int = 0) -> int:
    """Tạo người dùng mới. Mặc định is_active = 0 (Chờ kích hoạt bởi Admin)."""
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pwd_hash = hash_password(password)

    cursor.execute("""
    INSERT INTO users (email, password_hash, full_name, phone, role, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (email.strip().lower(), pwd_hash, full_name.strip(), phone.strip(), role, is_active, now_str))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def get_all_users() -> list[dict]:
    """Lấy danh sách toàn bộ người dùng cho trang Admin quản lý."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, phone, role, is_active, created_at FROM users ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_user_active(user_id: int, is_active: int) -> bool:
    """Kích hoạt hoặc khóa tài khoản."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def delete_user(user_id: int) -> bool:
    """Xóa tài khoản người dùng (không cho phép xóa tài khoản Admin chính)."""
    user = get_user_by_id(user_id)
    if not user or user["email"].lower() == ADMIN_EMAIL.lower():
        return False
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True


def create_session(user_id: int) -> str:
    """Tạo session token cho user sau khi đăng nhập."""
    session_id = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(days=7)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sessions (session_id, user_id, created_at, expires_at)
    VALUES (?, ?, ?, ?)
    """, (session_id, user_id, now.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return session_id


def get_session_user(session_id: str) -> Optional[dict]:
    """Lấy thông tin người dùng từ session_id."""
    if not session_id:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.id, u.email, u.full_name, u.phone, u.role, u.is_active, u.created_at, s.expires_at
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.session_id = ?
    """, (session_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    try:
        exp = datetime.strptime(user["expires_at"], "%Y-%m-%d %H:%M:%S")
        if exp < datetime.now():
            delete_session(session_id)
            return None
    except Exception:
        pass
    return user


def delete_session(session_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def add_tracking_history(user_id: int, campaign_name: str, post_count: int, member_count: int, report_path: str):
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO tracking_history (user_id, campaign_name, post_count, member_count, report_path, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, campaign_name, post_count, member_count, report_path, now_str))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database tracking_no_api initialized successfully.")
