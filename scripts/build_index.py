import os
import json
import re

SKILLS_DIR = "agentic-awesome-skills"
OUTPUT_FILE = "scripts/skills-index.json"

def build_index():
    index = {}
    if not os.path.exists(SKILLS_DIR):
        print(f"Directory {SKILLS_DIR} not found.")
        return

    for skill_name in os.listdir(SKILLS_DIR):
        skill_path = os.path.join(SKILLS_DIR, skill_name)
        if not os.path.isdir(skill_path):
            continue
            
        skill_md_path = os.path.join(skill_path, "SKILL.md")
        description = ""
        
        if os.path.exists(skill_md_path):
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Try to extract description from frontmatter or first few lines
                desc_match = re.search(r'description:\s*["\']?(.*?)["\']?\n', content)
                if desc_match:
                    description = desc_match.group(1).strip()
                else:
                    description = content[:200].replace('\n', ' ')
                    
        index[skill_name] = {
            "name": skill_name,
            "description": description
        }
        
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully indexed {len(index)} skills to {OUTPUT_FILE}")

if __name__ == "__main__":
    build_index()
