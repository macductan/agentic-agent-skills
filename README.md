# agentic-agent-skills

Kho lưu trữ và bộ công cụ tuyển chọn, cài đặt và đồng bộ Agentic Skills cho các AI Agent (Antigravity, Claude Code, Cursor, Windsurf, Codex...).

---

## 📂 Cấu trúc Repository

```text
agentic-agent-skills/
├── skills/
│   ├── custom/                    # Kho custom skills nội bộ (ví dụ: gchat-thread-exporter, glab...)
│   └── agentic-awesome-skills/    # Kho skills public tổng hợp từ cộng đồng
├── scripts/
│   ├── build_index.py             # Script tự động đánh index danh mục skills
│   ├── skills-index.json          # File index JSON phục vụ tìm kiếm nhanh theo keyword
│   ├── skill-cli.sh               # CLI tải skills từ GitHub giữ nguyên cấu trúc phân cấp gốc
│   └── symlink-skills.sh          # Script tạo relative symlink vào các thư mục agent
├── skill-curator/
│   └── SKILL.md                   # AI Skill hướng dẫn quy trình tuyển chọn & cài đặt kỹ năng chuẩn
├── .agent/skills/                 # Cấu hình skills cho Antigravity / Gemini CLI
├── .agents/skills/                # Cấu hình skills theo chuẩn Agents
└── .claude/skills/                # Cấu hình skills cho Claude Code
```

---

## 🚀 Quy trình Cài đặt & Cập nhật Skills

Quy trình chuẩn khi Agent cài đặt hoặc cập nhật skill vào dự án:

### 1. Tải Skills giữ nguyên cấu trúc phân cấp gốc
Tải skill trực tiếp vào thư mục `skills/` của dự án với cấu trúc phân cấp y hệt repo gốc để **luôn biết chính xác nguồn gốc xuất xứ**:
```bash
# Tải script CLI
curl -sLO https://raw.githubusercontent.com/macductan/agentic-agent-skills/main/scripts/skill-cli.sh && chmod +x skill-cli.sh

# Tìm kiếm và tải skill theo keyword
./skill-cli.sh download "react, state, gchat"
```
Cấu trúc được bảo toàn tại thư mục dự án:
- `skills/custom/<skill-name>`
- `skills/agentic-awesome-skills/<skill-name>`

### 2. Lọc & Chuẩn bị Script Symlink
- Sau khi AI phân tích và xóa các skill không cần thiết khỏi `skills/`:
- Agent quét tìm các folder skill hợp lệ (`find skills -type f -name "SKILL.md" -exec dirname {} \;`).
- Sử dụng script `symlink-skills.sh` làm sẵn, Agent bổ sung danh sách folder cần symlink vào mảng `SKILL_DIRS`:
```bash
SKILL_DIRS=(
    "skills/custom/gchat-thread-exporter"
    "skills/agentic-awesome-skills/react-best-practices"
)
```
*(Hoặc truyền trực tiếp qua tham số CLI hoặc để trống để script tự động quét)*.

### 3. Chạy Script Symlink
```bash
curl -sLO https://raw.githubusercontent.com/macductan/agentic-agent-skills/main/scripts/symlink-skills.sh && chmod +x symlink-skills.sh
./symlink-skills.sh
```
Script sẽ tự động:
- Tạo **relative symlinks** vào `.agent/skills/`, `.agents/skills/`, `.claude/skills/` trỏ về đúng thư mục gốc trong `skills/`.
- Không nhân bản file, tiết kiệm dung lượng, cập nhật code skill một nơi là mọi agent đều nhận ngay.
- Tự động dọn dẹp các symlink hỏng nếu skill gốc bị xóa.
