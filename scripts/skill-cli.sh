#!/bin/bash

# Configuration (Change this to your actual public GitHub repo, e.g., macductan/agentic-agent-skills)
GITHUB_REPO="macductan/agentic-agent-skills"
BRANCH="main"
SKILLS_DIR="agentic-awesome-skills"
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

# Convert keywords to an array (separated by comma or space)
IFS=',' read -ra KWS <<< "$KEYWORDS"

echo "Searching for matching skills..."
MATCHED_SKILLS=()

# Using python to parse JSON and match keywords
MATCHES=$(python3 -c "
import json
import sys
import re

try:
    with open('/tmp/skills-index.json', 'r') as f:
        data = json.load(f)
except:
    sys.exit(0)

keywords = [k.strip().lower() for k in '$KEYWORDS'.replace(',', ' ').split() if k.strip()]
matched = set()

for k, v in data.items():
    name = str(v.get('name', '')).lower()
    desc = str(v.get('description', '')).lower()
    
    # Check if ANY keyword matches as a whole word or substring
    for kw in keywords:
        if kw in name or kw in desc:
            matched.add(k)
            break

for m in matched:
    print(m)
")

if [ -z "$MATCHES" ]; then
    echo "No skills matched the keywords."
    exit 0
fi

echo "Found matching skills. Downloading from GitHub..."
# Collect all patterns into an array
TAR_PATTERNS=()
for skill in $MATCHES; do
    echo "-> Queueing $skill..."
    TAR_PATTERNS+=("*/$SKILLS_DIR/$skill")
done

# Download the tarball once and extract all matched folders
echo "Downloading repository archive and extracting skills..."
curl -sL "https://github.com/$GITHUB_REPO/tarball/$BRANCH" | tar -xz -C "$TARGET_DIR" --strip-components=2 --wildcards "${TAR_PATTERNS[@]}" > /dev/null 2>&1

for skill in $MATCHES; do
    # Check if tar succeeded. If not, it means the wildcard failed or tar syntax differs (Mac vs Linux).
    if [ ! -d "$TARGET_DIR/$skill" ]; then
        # Fallback to svn if tar wildcard fails (e.g., on some OS)
        if command -v svn >/dev/null 2>&1; then
             echo "-> Fallback: Downloading $skill via svn..."
             svn export --force -q "https://github.com/$GITHUB_REPO/trunk/$SKILLS_DIR/$skill" "$TARGET_DIR/$skill" > /dev/null 2>&1
        else
            echo "   Failed to extract $skill. Please install 'svn' or GNU 'tar'."
        fi
    fi
done

echo "Download complete! Skills are in $TARGET_DIR/"
