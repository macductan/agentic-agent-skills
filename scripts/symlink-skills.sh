#!/usr/bin/env bash
# ==============================================================================
# Script: symlink-skills.sh
# Tự động tạo relative symlink từ thư mục skills/ gốc vào các thư mục AI Agent:
#   - .agent/skills/
#   - .agents/skills/
#   - .claude/skills/
#
# Cơ chế hoạt động:
# 1. Agent có thể điền trực tiếp danh sách folder skill cần symlink vào mảng
#    SKILL_DIRS bên dưới.
# 2. Hoặc Agent có thể truyền tham số qua dòng lệnh:
#    ./scripts/symlink-skills.sh skills/custom/glab skills/agentic-awesome-skills/react-pro
# 3. Nếu để trống và không truyền tham số, script sẽ tự động tìm kiếm tất cả các
#    thư mục có chứa SKILL.md trong thư mục skills/ để symlink.
# ==============================================================================

set -e

# ==============================================================================
# CẤU HÌNH DANH SÁCH FOLDER SKILL CẦN SYMLINK
# Agent bổ sung các folder skill vào mảng dưới đây:
# ==============================================================================
SKILL_DIRS=(
    # [AGENT_INJECT_SKILLS_HERE]
    # Ví dụ:
    # "skills/custom/glab"
    # "skills/agentic-awesome-skills/react-best-practices"
)

# Thư mục đích của các AI Agent
TARGET_AGENT_DIRS=(
    ".agent/skills"
    ".agents/skills"
    ".claude/skills"
)

# 1. Ưu tiên tham số dòng lệnh nếu được truyền vào
if [ "$#" -gt 0 ]; then
    SKILL_DIRS=("$@")
fi

# 2. Nếu mảng SKILL_DIRS rỗng, tự động tìm các folder chứa SKILL.md trong skills/
if [ "${#SKILL_DIRS[@]}" -eq 0 ]; then
    echo ">> Chưa chỉ định folder cụ thể. Đang quét tự động các skill có trong 'skills/'..."
    if [ -d "skills" ]; then
        while IFS= read -r skill_file; do
            [ -z "$skill_file" ] && continue
            SKILL_DIRS+=("$(dirname "$skill_file")")
        done < <(find skills -type f -name "SKILL.md" 2>/dev/null | sort -u)
    fi
fi

if [ "${#SKILL_DIRS[@]}" -eq 0 ]; then
    echo "❌ Không tìm thấy skill nào để symlink trong skills/. Hãy kiểm tra lại thư mục hoặc bổ sung vào SKILL_DIRS."
    exit 1
fi

# Hàm tính đường dẫn tương đối (hỗ trợ Linux và macOS)
compute_relative_path() {
    local src="$1"
    local dest_dir="$2"
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import os, sys; print(os.path.relpath(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])))" "$src" "$dest_dir"
    else
        # Fallback pure bash: từ .agent/skills (độ sâu 2 từ root) trỏ về project root là ../..
        local clean_src="${src#./}"
        echo "../../$clean_src"
    fi
}

echo "=================================================================="
echo ">> Thiết lập symlink cho ${#SKILL_DIRS[@]} skill..."
echo "=================================================================="

for target_dir in "${TARGET_AGENT_DIRS[@]}"; do
    mkdir -p "$target_dir"
    echo ""
    echo "📁 Đồng bộ vào: $target_dir"

    # Dọn dẹp broken symlinks cũ nếu skill gốc đã bị xóa
    for item in "$target_dir"/*; do
        if [ -L "$item" ] && [ ! -e "$item" ]; then
            echo "   🗑️ [Dọn dẹp] Xóa symlink hỏng: $(basename "$item")"
            rm -f "$item"
        fi
    done

    for skill_path in "${SKILL_DIRS[@]}"; do
        skill_path="${skill_path%/}"
        if [ ! -d "$skill_path" ]; then
            echo "   ⚠️ [Bỏ qua] Không tìm thấy thư mục: $skill_path"
            continue
        fi

        skill_name=$(basename "$skill_path")
        link_target="$target_dir/$skill_name"
        rel_target=$(compute_relative_path "$skill_path" "$target_dir")

        # Xóa symlink, file hoặc thư mục cũ nếu đã tồn tại để tránh xung đột
        if [ -L "$link_target" ] || [ -d "$link_target" ] || [ -f "$link_target" ]; then
            rm -rf "$link_target"
        fi

        ln -sfn "$rel_target" "$link_target"
        echo "   🔗 $skill_name -> $rel_target"
    done
done

echo ""
echo "=================================================================="
echo "✅ Hoàn tất! Tất cả skills đã được symlink thành công."
echo "=================================================================="
