#!/bin/bash

# Configuration (Change this to your actual public GitHub repo, e.g., macductan/agentic-agent-skills)
GITHUB_REPO="macductan/agentic-agent-skills"
BRANCH="main"
DEFAULT_SKILLS_DIR="skills/agentic-awesome-skills"
INDEX_URL="https://raw.githubusercontent.com/$GITHUB_REPO/$BRANCH/scripts/skills-index.json"
TARGET_DIR=".temp_skills"

if [ "$1" != "download" ] || [ -z "$2" ]; then
    echo "Usage: ./skill-cli.sh download \"keyword1, keyword2\""
    exit 1
fi

KEYWORDS=$2
mkdir -p "$TARGET_DIR"

echo "Fetching index from $INDEX_URL..."
curl -sL "$INDEX_URL" -o /tmp/skills-index.json

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
    TAR_PATTERNS+=("*/$skill_path")
    MATCH_LIST+=("$entry")
done <<< "$MATCHES"

# Download the tarball once and extract all matched folders (both skills/agentic-awesome-skills/* and skills/custom/* have depth 3)
echo "Downloading repository archive and extracting skills..."
curl -sL "https://github.com/$GITHUB_REPO/tarball/$BRANCH" | tar -xz -C "$TARGET_DIR" --strip-components=3 --wildcards "${TAR_PATTERNS[@]}" > /dev/null 2>&1

for entry in "${MATCH_LIST[@]}"; do
    skill_name="${entry%%|*}"
    skill_path="${entry#*|}"
    # Check if tar succeeded. If not, fallback to svn if available (e.g., BSD tar on macOS).
    if [ ! -d "$TARGET_DIR/$skill_name" ]; then
        if command -v svn >/dev/null 2>&1; then
            echo "-> Fallback: Downloading $skill_name via svn..."
            svn export --force -q "https://github.com/$GITHUB_REPO/trunk/$skill_path" "$TARGET_DIR/$skill_name" > /dev/null 2>&1
        else
            echo "   Failed to extract $skill_name. Please install 'svn' or GNU 'tar'."
        fi
    fi
done

echo "Download complete! Skills are in $TARGET_DIR/"
