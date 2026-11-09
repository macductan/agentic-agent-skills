#!/usr/bin/env bash

# Configuration (Change this to your actual public GitHub repo, e.g., macductan/agentic-agent-skills)
GITHUB_REPO="macductan/agentic-agent-skills"
BRANCH="main"
DEFAULT_SKILLS_DIR="skills/agentic-awesome-skills"
INDEX_URL="https://raw.githubusercontent.com/$GITHUB_REPO/$BRANCH/scripts/skills-index.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Xử lý lệnh symlink / link
if [ "$1" = "symlink" ] || [ "$1" = "link" ]; then
    shift
    if [ -f "$SCRIPT_DIR/symlink-skills.sh" ]; then
        exec "$SCRIPT_DIR/symlink-skills.sh" "$@"
    elif [ -f "./symlink-skills.sh" ]; then
        exec "./symlink-skills.sh" "$@"
    elif [ -f "./scripts/symlink-skills.sh" ]; then
        exec "./scripts/symlink-skills.sh" "$@"
    else
        echo "symlink-skills.sh không tìm thấy tại local. Đang tải từ repo..."
        curl -sLO "https://raw.githubusercontent.com/$GITHUB_REPO/$BRANCH/scripts/symlink-skills.sh"
        chmod +x symlink-skills.sh
        exec "./symlink-skills.sh" "$@"
    fi
fi

if [ "$1" != "download" ] || [ -z "$2" ]; then
    echo "Usage:"
    echo "  $0 download \"keyword1, keyword2\" [target_dir]   - Tải skill về theo cấu trúc gốc skills/"
    echo "  $0 symlink [skill_folder1 skill_folder2 ...]      - Tạo symlink vào .agent, .agents, .claude"
    exit 1
fi

KEYWORDS=$2
# Mặc định tải về thư mục gốc hiện tại (giữ nguyên cấu trúc skills/custom/ và skills/agentic-awesome-skills/)
TARGET_DIR="${3:-.}"
mkdir -p "$TARGET_DIR"

# Lấy skills-index.json (ưu tiên file local nếu đang ở trong repo hoặc đã tải)
if [ -f "$SCRIPT_DIR/skills-index.json" ]; then
    cp "$SCRIPT_DIR/skills-index.json" /tmp/skills-index.json
elif [ -f "scripts/skills-index.json" ]; then
    cp "scripts/skills-index.json" /tmp/skills-index.json
elif [ -f "./skills-index.json" ]; then
    cp "./skills-index.json" /tmp/skills-index.json
else
    echo "Fetching index from $INDEX_URL..."
    curl -sL "$INDEX_URL" -o /tmp/skills-index.json
fi

if [ ! -s /tmp/skills-index.json ]; then
    echo "Error: Could not fetch skills-index.json. Check the GITHUB_REPO variable in this script."
    exit 1
fi

echo "Searching for matching skills..."

# Using python to parse JSON and match keywords (supports both awesome and custom skill paths)
MATCHES=$(python3 - "$KEYWORDS" "$DEFAULT_SKILLS_DIR" <<'PY'
import json
import re
import sys

raw_keywords = sys.argv[1].lower()
default_dir = sys.argv[2]

# Normalize common multi-word aliases before splitting so "gg chat" / "google chat" don't fan out to generic "google"/"chat"
raw_keywords = re.sub(r"\bgg\s+chat\b", "gg-chat", raw_keywords)
raw_keywords = re.sub(r"\bgoogle\s+chat\b", "google-chat", raw_keywords)

try:
    with open("/tmp/skills-index.json", "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(0)

keywords = [k.strip() for k in raw_keywords.replace(",", " ").split() if k.strip()]
matched = []

for k, v in sorted(data.items()):
    name = str(v.get("name", k)).lower()
    desc = str(v.get("description", "")).lower()
    rel_path = str(v.get("path") or f"{default_dir}/{k}")

    for kw in keywords:
        if kw in name or kw in desc:
            matched.append(f"{k}|{rel_path}")
            break

for item in matched:
    print(item)
PY
)

if [ -z "$MATCHES" ]; then
    echo "No skills matched the keywords."
    exit 0
fi

echo "Found matching skills. Downloading from GitHub..."
TAR_PATTERNS=()
MATCH_LIST=()
while IFS= read -r entry; do
    [ -z "$entry" ] && continue
    skill_name="${entry%%|*}"
    skill_path="${entry#*|}"
    echo "-> Queueing $skill_name ($skill_path)..."
    TAR_PATTERNS+=("*/$skill_path/*" "*/$skill_path")
    MATCH_LIST+=("$entry")
done <<< "$MATCHES"

# Download the tarball once and extract preserving the exact original path (skills/custom/... or skills/agentic-awesome-skills/...)
echo "Downloading repository archive and extracting skills preserving hierarchy..."
curl -sL "https://github.com/$GITHUB_REPO/tarball/$BRANCH" | tar -xz -C "$TARGET_DIR" --strip-components=1 --wildcards "${TAR_PATTERNS[@]}" > /dev/null 2>&1

for entry in "${MATCH_LIST[@]}"; do
    skill_name="${entry%%|*}"
    skill_path="${entry#*|}"
    # Check if tar succeeded. If not, fallback to svn if available (e.g., BSD tar on macOS).
    if [ ! -d "$TARGET_DIR/$skill_path" ]; then
        if command -v svn >/dev/null 2>&1; then
            echo "-> Fallback: Downloading $skill_name via svn..."
            mkdir -p "$TARGET_DIR/$(dirname "$skill_path")"
            svn export --force -q "https://github.com/$GITHUB_REPO/trunk/$skill_path" "$TARGET_DIR/$skill_path" > /dev/null 2>&1
        else
            echo "   Failed to extract $skill_name ($skill_path). Please install 'svn' or GNU 'tar'."
        fi
    fi
done

echo ""
echo "Download complete! Skills are saved in $TARGET_DIR/skills/ with origin structure preserved."
