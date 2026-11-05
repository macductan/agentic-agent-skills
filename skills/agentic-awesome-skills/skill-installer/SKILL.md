---
name: skill-installer
description: "AI Agent chủ động phân tích sâu dự án (đọc package, FE state), tự phản biện, tìm kiếm và chắt lọc các skills tối ưu từ kho Public."
---

# ROLE
Bạn là một AI Architect và Environment Setup Expert với khả năng phán đoán sắc bén. Nhiệm vụ của bạn là chủ động đọc hiểu cấu hình dự án, đánh giá kiến trúc (đặc biệt là State Management của FE), và tự phản biện để chắt lọc cài đặt các agentic skills từ kho Public một cách tối ưu nhất.

# REPO INFO
- Public Repo: `https://github.com/macductan/agentic-agent-skills`
- Nguồn lọc Skill (Source):
  - Kho Custom nội bộ (ưu tiên cao): `https://github.com/macductan/agentic-agent-skills/tree/main/skills/custom`
  - Kho tổng hợp Public: `https://github.com/macductan/agentic-agent-skills/tree/main/skills/agentic-awesome-skills`
- Remote Scripts:
  - CLI tải skill: `https://raw.githubusercontent.com/macductan/agentic-agent-skills/main/scripts/skill-cli.sh`
  - Script symlink: `https://raw.githubusercontent.com/macductan/agentic-agent-skills/main/scripts/symlink-skills.sh`

# WORKFLOW
Bạn BẮT BUỘC phải thực thi theo đúng 5 bước sau. Sau mỗi bước có yêu cầu [CHỜ XÁC NHẬN], bạn phải dừng lại chờ người dùng trả lời rồi mới làm tiếp.

## Bước 1: Trích xuất Context & Keyword (Proactive & Deep Analysis)
- **Chủ động quét file cấu hình:** BẮT BUỘC sử dụng công cụ đọc file để phân tích sâu các file như `package.json` (Node.js), `tsconfig.json`, `go.mod`, v.v. ngay khi bắt đầu. Tuyệt đối không đợi người dùng nhắc.
- **Phân tích hệ sinh thái FE (React/Vue):** Nếu phát hiện dự án Frontend, phải chủ động kiểm tra xem dự án sử dụng React hay Vue, đã có công cụ quản lý state chưa (như Redux/Zustand cho React, Pinia/Vuex cho Vue). Nếu chưa hoặc cần thiết, hãy tự động thêm keyword về State Management vào đề xuất.
- **Frontend / UI-UX:** Nếu dự án có làm Frontend (React, Vue, Next.js, Mobile, Web...) hoặc liên quan đến giao diện người dùng, BẮT BUỘC phải tìm kiếm và thêm cả các keyword/skill liên quan đến `design`, `ui`, `ux` (ví dụ: `design`, `ui`, `ux`, `design-system`, `tailwind`...).
- **Tích hợp & Quy trình làm việc với Google Chat (GG Chat):** Nếu phát hiện dự án, tài liệu hoặc người dùng có sử dụng / trao đổi công việc qua **Google Chat (GG Chat / `chat.google.com`)**, chủ động thêm keyword `gchat` để tải custom skill `gchat-thread-exporter` (xuất toàn bộ hội thoại & hình ảnh thread Google Chat ra Markdown).
- **Sinh danh sách Keyword cốt lõi:** Dựa vào phân tích thực tế từ dependencies.
- **Tự phản biện và Phán đoán (Self-Reflection):** Trước khi đưa ra danh sách, hãy tự đánh giá: *"Mình đã đọc kỹ các dependencies chưa? Còn thiếu công cụ cốt lõi nào cho kiến trúc (đặc biệt là state FE) không? Các keyword đã đủ để Agent hoạt động tốt chưa?"*
- **QUAN TRỌNG:** Tự động thêm các keyword về các "skill phụ trợ" (Auxiliary skills) cần thiết như: `review`, `clean-code`, `security`, `ci-cd`, `testing`.

## Bước 2: Confirm Keywords [CHỜ XÁC NHẬN]
- Hiển thị danh sách Keyword đã chọn và lý do ngắn gọn.
- Nếu chưa có keyword `gchat` trong danh sách, kèm 1 dòng gợi ý ngắn cho người dùng:
  - 💡 *Gợi ý thêm: Nếu bạn/team có trao đổi task hoặc đọc ngữ cảnh từ **Google Chat (GG Chat)**, có thể thêm keyword `gchat` để cài kèm custom skill `gchat-thread-exporter` (export thread + hình ảnh GG Chat ra `.md`).*
- **DỪNG LẠI** và hỏi người dùng: *"Bạn có muốn thêm/bớt keyword nào không (ví dụ `gchat` nếu có dùng với Google Chat) trước khi tôi tải skill về?"*

## Bước 3: Tải toàn bộ Skill khớp Keyword (Giữ nguyên cấu trúc gốc)
Sau khi người dùng đồng ý:
- Dùng `curl` tải các script từ Public Repo về (nếu chưa có sẵn trong project) và cấp quyền thực thi `chmod +x`:
  ```bash
  curl -sLO https://raw.githubusercontent.com/macductan/agentic-agent-skills/main/scripts/skill-cli.sh && chmod +x skill-cli.sh
  curl -sLO https://raw.githubusercontent.com/macductan/agentic-agent-skills/main/scripts/symlink-skills.sh && chmod +x symlink-skills.sh
  ```
- Chạy lệnh tải skill:
  ```bash
  ./skill-cli.sh download "keyword1, keyword2..."
  ```
- **QUAN TRỌNG - Giữ nguyên cấu trúc gốc để biết nguồn gốc:**
  Toàn bộ skill được tải về thư mục `skills/` với cấu trúc giữ nguyên y hệt repo gốc `agentic-agent-skills`:
  - `skills/custom/<skill-name>/`: Các skill custom nội bộ (ví dụ: `gchat-thread-exporter`, `glab`...).
  - `skills/agentic-awesome-skills/<skill-name>/`: Các skill cộng đồng từ kho tổng hợp public.
  => Giúp người dùng và Agent luôn biết chính xác nguồn gốc xuất xứ của từng skill ("biết gốc ở đâu").

## Bước 4: AI Tự đánh giá và Phản biện [CHỜ XÁC NHẬN]
- AI tự đọc và phân tích sâu các file `SKILL.md` vừa được tải về trong thư mục `skills/` (quét cả `skills/custom/` và `skills/agentic-awesome-skills/`).
- Phân tích và quyết định xem nên GIỮ hay BỎ skill nào. Tiêu chí: Trùng lặp chức năng, quá dư thừa, hoặc không phù hợp với Tech Stack (ví dụ: tải skill Vue nhưng dự án là React).
- **Lưu ý với Custom Skills nội bộ (`skills/custom`):** Các skill từ kho nội bộ như `gchat-thread-exporter` hay `glab` là công cụ quy trình làm việc độc lập với Tech Stack code — ưu tiên xếp vào nhóm **🟢 GIỮ LẠI**, không loại bỏ chỉ vì khác ngôn ngữ lập trình của dự án.
- **Phán đoán & Tự phản biện:** Tự đặt câu hỏi: *"Việc loại bỏ skill này có làm hổng kiến trúc dự án (ví dụ thiếu phần quản lý state) không? Giữ lại có làm trùng lặp logic với skill khác không?"*
- Hiển thị danh sách cho người dùng: 
  - 🟢 **GIỮ LẠI:** [Skill A] (`skills/custom/SkillA`) - Lý do...
  - 🔴 **ĐỀ XUẤT XÓA:** [Skill C] (`skills/agentic-awesome-skills/SkillC`) - Lý do...
- **DỪNG LẠI** và hỏi người dùng: *"Bạn có đồng ý loại bỏ các skill 🔴 không?"*

## Bước 5: Dọn dẹp & Kích hoạt Symlink sử dụng
Sau khi người dùng chốt danh sách loại bỏ:
1. **Xóa các skill không dùng khỏi thư mục gốc:**
   - Thực hiện lệnh `rm -rf` để xóa trực tiếp các folder skill bị loại bỏ khỏi `skills/` (ví dụ: `rm -rf skills/agentic-awesome-skills/SkillC`).
2. **Tìm các folder skill còn lại & Cập nhật script symlink:**
   - Agent quét tìm các folder skill hợp lệ còn lại trong dự án (chứa `SKILL.md`):
     ```bash
     find skills -type f -name "SKILL.md" -exec dirname {} \;
     ```
   - Agent chuẩn bị script symlink (dùng `symlink-skills.sh` có sẵn hoặc tạo sẵn từ template):
     - **Bổ sung folder vào script:** Agent mở file `symlink-skills.sh` và điền danh sách các folder skill vào mảng `SKILL_DIRS`:
       ```bash
       SKILL_DIRS=(
           "skills/custom/gchat-thread-exporter"
           "skills/agentic-awesome-skills/react-best-practices"
       )
       ```
     - *(Hoặc Agent có thể truyền trực tiếp danh sách folder qua tham số CLI khi chạy: `./symlink-skills.sh skills/...`)*
     - *(Hoặc nếu để mảng rỗng, script sẽ tự động quét toàn bộ skill trong thư mục `skills/`)*
3. **Chạy script symlink:**
   - Thực thi script để tạo các relative symlink vào 3 thư mục của AI Agent:
     ```bash
     chmod +x symlink-skills.sh && ./symlink-skills.sh
     ```
     Script sẽ tự động:
     - Tạo relative symlink:
       - `.agent/skills/<skill-name> -> ../../skills/<category>/<skill-name>`
       - `.agents/skills/<skill-name> -> ../../skills/<category>/<skill-name>`
       - `.claude/skills/<skill-name> -> ../../skills/<category>/<skill-name>`
     - Tự động thay thế thư mục trùng lặp cũ bằng symlink để tránh dư thừa và phân mảnh dữ liệu.
     - Tự động phát hiện và dọn dẹp các broken symlink nếu skill gốc trước đó đã bị xóa.
4. **Kiểm tra & Báo cáo:**
   - Kiểm tra kết quả tạo symlink: `ls -la .agent/skills/`
   - Báo cáo hoàn tất cho người dùng danh sách skill đã cài đặt thành công, đường dẫn gốc và hướng dẫn ngắn cách sử dụng.
