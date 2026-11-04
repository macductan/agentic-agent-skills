import os
import json
import re

AWESOME_SKILLS_DIR = "skills/agentic-awesome-skills"
CUSTOM_SKILLS_DIR = "skills/custom"
SKILL_SOURCES = [
    (AWESOME_SKILLS_DIR, False),
    (CUSTOM_SKILLS_DIR, True),
]
OUTPUT_FILE = "scripts/skills-index.json"


def extract_description(skill_md_path):
    if not os.path.exists(skill_md_path):
        return ""
    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    desc_match = re.search(r'description:\s*["\']?(.*?)["\']?\n', content)
    if desc_match:
        return desc_match.group(1).strip()
    return content[:200].replace("\n", " ")


def build_index():
    raw_entries = {}
    found_any_dir = False

    for base_dir, is_custom in SKILL_SOURCES:
        if not os.path.exists(base_dir):
            continue
        found_any_dir = True
        for skill_name in sorted(os.listdir(base_dir)):
            skill_path = os.path.join(base_dir, skill_name)
            if not os.path.isdir(skill_path):
                continue

            skill_md_path = os.path.join(skill_path, "SKILL.md")
            entry = {
                "name": skill_name,
                "description": extract_description(skill_md_path),
            }
            if is_custom:
                entry["path"] = f"{base_dir}/{skill_name}"
            raw_entries[skill_name] = entry

    if not found_any_dir:
        print("No skills directories found.")
        return

    index = {k: raw_entries[k] for k in sorted(raw_entries)}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"Successfully indexed {len(index)} skills to {OUTPUT_FILE}")


if __name__ == "__main__":
    build_index()
