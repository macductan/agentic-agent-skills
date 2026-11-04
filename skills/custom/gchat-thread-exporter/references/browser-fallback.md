# Chế độ dự phòng Không Cần Key (Browser Extractor)

Dùng phương án này khi:
- Bạn đang dùng tài khoản **`@gmail.com` cá nhân** (Google không mở Google Chat REST API cho tài khoản cá nhân).
- Hoặc công ty bạn chặn quyền tạo OAuth App trên Google Cloud (`admin_policy_enforced`).
- Hoặc bạn chỉ cần xuất nhanh 1 thread ngay lập tức mà không muốn thiết lập OAuth key.

---

## Quy trình 2 bước

### Bước 1: Trích xuất hội thoại + ảnh trực tiếp trên tab trình duyệt đang mở

1. Mở đúng đường dẫn thread Google Chat trên Chrome / Edge / Brave (đã đăng nhập), ví dụ:
   `https://chat.google.com/u/0/app/chat/AAAA9sg0Pfc/topic/K2bBfiSrccc`
2. Đợi khung hội thoại của thread hiển thị đầy đủ trên màn hình.
3. Mở **DevTools Console**:
   - Windows / Linux: nhấn `F12` hoặc `Ctrl + Shift + J`
   - macOS: nhấn `Cmd + Option + J`
   *(Nếu lần đầu dán code vào Console trên Chrome, gõ `allow pasting` rồi nhấn Enter nếu Chrome yêu cầu).*
4. Copy toàn bộ nội dung file `scripts/browser_extract.js`, dán vào Console và nhấn **Enter**.
5. Đợi vài giây để script tự cuộn lên đầu thread tải hết tin nhắn cũ, đọc dữ liệu hình ảnh qua phiên đăng nhập hiện tại và tự động tải về file `gchat-thread-<THREAD_ID>.json`.

### Bước 2: Chuyển đổi file JSON sang Markdown + thư mục ảnh `images/`

Chạy lệnh sau để giải mã toàn bộ ảnh ra file thật trong `images/` và tạo bản `.md` chuẩn:

```bash
python3 skills/custom/gchat-thread-exporter/scripts/export_gchat_thread.py \
  --from-browser-json ~/Downloads/gchat-thread-K2bBfiSrccc.json \
  -o exports/gchat-K2bBfiSrccc/thread.md
```

Kết quả đầu ra:
- `exports/gchat-K2bBfiSrccc/thread.md` — Toàn bộ nội dung hội thoại định dạng Markdown.
- `exports/gchat-K2bBfiSrccc/images/` — Toàn bộ hình ảnh trong thread đã được lưu thành file `.png` / `.jpg` / `.gif` / `.webp` độc lập và nhúng bằng đường dẫn tương đối `![...](images/...)`.
