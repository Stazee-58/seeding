# FB Tracking No-API Pro 🚀

Hệ thống Web Tracking & Đối Soát Tương Tác Facebook (Like, Comment, Share) **hoàn toàn không cần Meta Graph API**.
Chạy siêu nhẹ, tương thích 100% với **Vercel Serverless**.

---

## 🌟 Tính Năng Nổi Bật
1. **Không Cần Tạo App Meta Developer**:
   - Không cần xin cấp quyền `pages_read_engagement` hay `pages_read_user_content`.
   - Không bao giờ bị lỗi Facebook Code 10.
2. **Cào 100% Dữ Liệu Thực Tế**:
   - Quét toàn bộ Thả tim / Like (Reactions: Like, Love, Care, Haha, Wow, Sad, Angry).
   - Quét toàn bộ Bình luận (bao gồm cả câu trả lời con / replies).
   - Quét Lượt chia sẻ công khai (Shares).
3. **Phân Quyền & Kích Hoạt Tài Khoản (Admin Panel)**:
   - Tài khoản Admin tạo sẵn: `nguyenhaonhien40@gmail.com` / Mật khẩu: `050810`.
   - Người dùng mới đăng ký phải được Admin vào trang `/admin` bấm **Kích hoạt** thì mới sử dụng được.
   - Hotline hỗ trợ: `0984113158`.
4. **Đối Soát Thành Viên & Phát Hiện Người Lạ**:
   - Nhận diện họ tên tiếng Việt, biệt danh, URL UID.
   - Tab 1: Chi tiết từng thành viên (Đã like? Đã comment? Đã share? Tỷ lệ hoàn thành %).
   - Tab 2: Danh sách người lạ tương tác (Lọc theo Like, Comment).
   - Tab 3: Tổng hợp bài viết.
   - Xuất file Excel báo cáo 4 sheet chuẩn mực (`.xlsx`).

---

## 🛠️ Hướng Dẫn Chạy Cục Bộ (Local)
1. Cài đặt thư viện:
   ```bash
   pip install -r requirements.txt
   ```
2. Chạy ứng dụng:
   ```bash
   python server.py
   ```
3. Truy cập trình duyệt: `http://localhost:5050`

---

## 🚀 Triển Khai Lên Vercel
1. Đã có sẵn file cấu hình `vercel.json` và `api/index.py`.
2. Đẩy thư mục này lên GitHub repository của bạn.
3. Import project vào Vercel, chọn Framework Preset: `Other`. Vercel sẽ tự động build và cấp domain miễn phí!
