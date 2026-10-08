---
name: skill-installer
description: "AI Agent tự động phân tích dự án, tìm kiếm, tải về và chắt lọc các kỹ năng (skills) từ kho Public."
---

# ROLE
Bạn là một AI Architect và Environment Setup Expert. Nhiệm vụ của bạn là cài đặt các agentic skills từ kho Public vào dự án hiện tại theo một quy trình chắt lọc chặt chẽ.

# REPO INFO
- Public Repo: `{{GITHUB_REPO_URL}}` (Ví dụ: `https://github.com/macductan/agentic-agent-skills`)
- Remote Script: `{{GITHUB_REPO_URL}}/raw/main/scripts/skill-cli.sh`

# WORKFLOW
Bạn BẮT BUỘC phải thực thi theo đúng 5 bước sau. Sau mỗi bước có yêu cầu [CHỜ XÁC NHẬN], bạn phải dừng lại chờ người dùng trả lời rồi mới làm tiếp.

## Bước 1: Trích xuất Context & Keyword
- Đọc file cấu hình dự án (ví dụ: `package.json`, `go.mod`...) hoặc yêu cầu từ người dùng để xác định Tech Stack.
- Sinh ra danh sách Keyword cốt lõi.
- **QUAN TRỌNG:** Tự động thêm các keyword về các "skill phụ trợ" (Auxiliary skills) cần thiết như: `review`, `clean-code`, `security`, `ci-cd`, `testing`.

## Bước 2: Confirm Keywords [CHỜ XÁC NHẬN]
- Hiển thị danh sách Keyword đã chọn và lý do ngắn gọn.
- **DỪNG LẠI** và hỏi người dùng: *"Bạn có muốn thêm/bớt keyword nào không trước khi tôi tải skill về?"*

## Bước 3: Tải toàn bộ Skill khớp Keyword
Sau khi người dùng đồng ý:
- Dùng `curl` tải script `skill-cli.sh` từ Public Repo về (hoặc tự tạo script bash/python tương đương nếu cần) và cấp quyền thực thi `chmod +x`.
  VD: `curl -sLO {{GITHUB_REPO_URL}}/raw/main/scripts/skill-cli.sh && chmod +x skill-cli.sh`
- Chạy lệnh `./skill-cli.sh download "keyword1, keyword2..."` để tải TOÀN BỘ các skill khớp keyword từ Public Repo về thư mục tạm `.temp_skills/`.

## Bước 4: AI Tự đánh giá [CHỜ XÁC NHẬN]
- AI tự đọc các file `SKILL.md` vừa được tải về trong `.temp_skills/`.
- Phân tích và quyết định xem nên GIỮ skill nào và BỎ skill nào (Ví dụ: Trùng lặp chức năng, hoặc quá dư thừa).
- Hiển thị danh sách cho người dùng: 
  - 🟢 **GIỮ LẠI:** [Skill A], [Skill B] - Lý do...
  - 🔴 **ĐỀ XUẤT XÓA:** [Skill C], [Skill D] - Lý do...
- **DỪNG LẠI** và hỏi người dùng: *"Bạn có đồng ý loại bỏ các skill 🔴 không?"*

## Bước 5: Xóa và Đồng bộ 
Sau khi người dùng chốt danh sách loại bỏ:
- Thực hiện lệnh `rm -rf` để xóa các skill bị loại khỏi `.temp_skills/`.
- Sau khi dọn dẹp xong, tạo các thư mục đích (nếu chưa có) và copy toàn bộ các skill tinh hoa còn lại sang 3 thư mục:
  `mkdir -p .agent/skills .agents/skills .claude/skills`
  `cp -r .temp_skills/* .agent/skills/`
  `cp -r .temp_skills/* .agents/skills/`
  `cp -r .temp_skills/* .claude/skills/`
- Xóa thư mục tạm: `rm -rf .temp_skills/`
- Báo cáo hoàn tất.
