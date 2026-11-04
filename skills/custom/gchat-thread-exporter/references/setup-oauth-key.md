# Hướng dẫn lấy OAuth Key (`credentials.json`) cho Google Chat Thread Exporter

Tài liệu này hướng dẫn từng bước tạo OAuth Client Key (`credentials.json`) trên Google Cloud Console để xuất toàn bộ hội thoại + hình ảnh gốc từ Google Chat API.

> **Lưu ý quan trọng trước khi bắt đầu:**
> - **Google Chat API chỉ hỗ trợ tài khoản Google Workspace** (email công ty / tổ chức / trường học).
> - Nếu bạn đang dùng tài khoản **`@gmail.com` cá nhân**, hoặc IT Admin công ty chặn quyền tạo Google Cloud Project / OAuth App (`admin_policy_enforced`), **bạn không cần lấy key** — hãy chuyển sang chế độ xuất trực tiếp trên trình duyệt tại [browser-fallback.md](browser-fallback.md).

---

## Bước 1: Tạo hoặc chọn Google Cloud Project

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/) bằng đúng tài khoản Google Workspace đang có quyền xem thread Google Chat.
2. Nhấn vào thanh chọn Project ở góc trên bên trái → chọn **New Project** (ví dụ đặt tên: `gchat-exporter`) → bấm **Create**, sau đó chọn Project vừa tạo.

---

## Bước 2: Bật các API cần thiết

Vào **APIs & Services → Library** (hoặc mở trực tiếp link bên dưới khi đã chọn đúng Project) và bấm **Enable** cho:

1. **Google Chat API** *(Bắt buộc — đọc tin nhắn & tải ảnh đính kèm)*:
   `https://console.cloud.google.com/apis/library/chat.googleapis.com`
2. **Google People API** *(Khuyên bật — để hiển thị tên thật đồng nghiệp thay vì mã `users/12345...`)*:
   `https://console.cloud.google.com/apis/library/people.googleapis.com`
3. *(Tùy chọn)* **Google Drive API** *(Chỉ cần nếu muốn dùng cờ `--with-drive` để tải trực tiếp file ảnh đính kèm qua Drive)*:
   `https://console.cloud.google.com/apis/library/drive.googleapis.com`

---

## Bước 3: Lưu cấu hình cơ bản cho Google Chat API *(Bắt buộc để tránh lỗi 404)*

Ngay cả khi chỉ đọc tin nhắn bằng tài khoản cá nhân (User OAuth), Google vẫn yêu cầu Project phải có hồ sơ Chat App tối thiểu, nếu không API sẽ báo lỗi `404: Google Chat app not found`.

1. Mở **APIs & Services → Enabled APIs & services → Google Chat API → tab Configuration**
   (Link nhanh: `https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat`)
2. Điền nhanh các trường bắt buộc (copy-paste nguyên mẫu dưới đây):
   - **App name:** `GChat Thread Exporter`
   - **Avatar URL:** `https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/chat/default/24px.svg`
   - **Description:** `Export Google Chat threads to Markdown`
3. Phần **Interactive features**: Nếu form yêu cầu cấu hình **Connection settings**, bật chọn **HTTP endpoint URL** và điền `https://example.com` (script chạy local qua REST API nên không gọi webhook này, chỉ dùng để lưu form hợp lệ).
4. Phần **Visibility**: **Không cần tích** chia sẻ cho ai khác.
5. Bấm **Save**.

---

## Bước 4: Cấu hình OAuth Consent Screen

1. Mở **Google Auth Platform / OAuth consent screen**:
   `https://console.cloud.google.com/auth/overview` (hoặc **APIs & Services → OAuth consent screen**).
2. Điền **App name** (`GChat Thread Exporter`) và email của bạn ở **User support email** & **Developer contact information**.
3. Ở mục **Audience / User Type**:
   - Chọn **Internal** *(Khuyên dùng cho Google Workspace — dùng được ngay lập tức, không bị cảnh báo unverified app)*.
   - Nếu tài khoản chỉ cho chọn **External**, hãy để ở chế độ **Testing** và vào mục **Audience → Test users → + Add users** để thêm địa chỉ email của bạn vào danh sách.
4. Bấm **Save and Continue** để hoàn tất.

---

## Bước 5: Tạo OAuth Client ID (`Desktop app`) & lưu `credentials.json`

1. Mở **APIs & Services → Credentials** (`https://console.cloud.google.com/apis/credentials`)
   hoặc **Google Auth Platform → Clients**.
2. Bấm **+ Create Credentials → OAuth client ID**.
3. Ở **Application type**, bắt buộc chọn **Desktop app** *(không chọn Web application hay Service account)*.
4. Đặt tên (ví dụ `Local CLI`) → bấm **Create**.
5. Bấm **Download JSON** để tải file về máy, sau đó lưu vào thư mục cấu hình an toàn ngoài Git repo:

```bash
mkdir -p ~/.config/gchat-thread-exporter
mv ~/Downloads/client_secret_*.json ~/.config/gchat-thread-exporter/credentials.json
chmod 600 ~/.config/gchat-thread-exporter/credentials.json
```

> **Bảo mật:** Tuyệt đối không đặt `credentials.json` hoặc `token.json` vào trong thư mục Git public.

---

## Bước 6: Đăng nhập lần đầu để lấy `token.json`

### Trường hợp A: Chạy trực tiếp trên máy tính cá nhân có trình duyệt
```bash
python3 skills/custom/gchat-thread-exporter/scripts/export_gchat_thread.py --auth
```
Trình duyệt sẽ tự mở trang đăng nhập Google → bấm **Allow** → script tự lưu `~/.config/gchat-thread-exporter/token.json` và dùng lại tự động cho mọi lần sau.

### Trường hợp B: Chạy qua SSH / máy chủ từ xa / chạy cùng AI Agent
1. Tạo link đăng nhập kèm phiên PKCE:
   ```bash
   python3 skills/custom/gchat-thread-exporter/scripts/export_gchat_thread.py --print-auth-url
   ```
2. Mở `auth_url` được in ra trên trình duyệt máy cá nhân của bạn và bấm **Allow**.
3. Sau khi bấm Allow, trình duyệt chuyển hướng sang `http://127.0.0.1:8765/?state=...&code=4/0A...` *(việc trình duyệt báo "This site can't be reached" trên máy từ xa là hoàn toàn bình thường)*.
4. Copy **toàn bộ đường link `http://127.0.0.1:8765/...`** trên thanh địa chỉ trình duyệt và chạy:
   ```bash
   python3 skills/custom/gchat-thread-exporter/scripts/export_gchat_thread.py --complete-auth "http://127.0.0.1:8765/?state=...&code=..."
   ```

---

## Xử lý lỗi thường gặp

| Triệu chứng / Mã lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `404: Google Chat app not found` | Chưa lưu tab **Configuration** của Google Chat API | Làm lại **Bước 3** và bấm **Save** |
| `403: Access blocked: admin_policy_enforced` | IT Admin công ty khóa ứng dụng OAuth tự tạo | Chuyển sang [browser-fallback.md](browser-fallback.md) (không cần key) |
| `403: Google Chat API is only available to Google Workspace users` | Đang đăng nhập bằng `@gmail.com` cá nhân | Chuyển sang [browser-fallback.md](browser-fallback.md) |
| Tên người gửi hiển thị dạng `users/112233...` | Chưa bật **Google People API** trên Cloud Project | Bật Google People API ở **Bước 2** rồi chạy lại lệnh export |
