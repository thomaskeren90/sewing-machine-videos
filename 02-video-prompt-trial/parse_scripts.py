#!/usr/bin/env python3
"""
Parse all 90 video scripts from markdown files into structured JSON.
Usage: python3 parse_scripts.py
Output: scripts.json (90 entries with id, category, title, script, product, duration)
"""

import os
import re
import json

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")
OUTPUT = os.path.join(os.path.dirname(__file__), "scripts.json")

def extract_scripts(filepath):
    """Extract individual video scripts from a markdown file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Split by "## Video X-Y:" headers
    sections = re.split(r'\n## Video (\d+-\d+):', content)
    
    scripts = []
    category = os.path.basename(filepath).replace(".md", "").replace("-", " ").title()
    
    for i in range(1, len(sections), 2):
        video_id = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        
        # Extract title
        title_match = re.search(r'\*\*Title:\*\*\s*"(.*?)"', body)
        title = title_match.group(1) if title_match else f"Video {video_id}"
        
        # Extract script text (Bahasa Indonesia)
        script_match = re.search(r'\*\*Script.*?:\*\*\s*\n"(.*?)"', body, re.DOTALL)
        if not script_match:
            script_match = re.search(r'\*\*Script.*?:\*\*\s*\n(.*?)(?:\n\*\*Filming|\n\*\*Alt|\n---|\n##)', body, re.DOTALL)
        
        script_text = ""
        if script_match:
            script_text = script_match.group(1).strip()
            # Clean up - remove quotes if wrapped
            script_text = script_text.strip('"').strip()
        
        # Extract duration
        dur_match = re.search(r'\*\*Duration\*\*\s*(\d+[-–]\d+\s*(?:detik|menit))', body)
        duration = dur_match.group(1) if dur_match else "30-60 detik"
        
        # Extract product reference
        prod_match = re.search(r'\*\*Product\*\*\s*([A-C]\d+[^\n]*)', body)
        product = prod_match.group(1).strip() if prod_match else ""
        
        # Determine platform
        platform_match = re.search(r'\*\*Post On\*\*\s*([^\n]+)', body)
        platform = platform_match.group(1).strip() if platform_match else "TikTok + YouTube"
        
        # Category number
        cat_num = re.search(r'(\d+)', os.path.basename(filepath))
        cat_number = int(cat_num.group(1)) if cat_num else 0
        
        scripts.append({
            "id": int(video_id.replace("-", "")),
            "video_id": video_id,
            "category": category,
            "category_number": cat_number,
            "title": title,
            "script": script_text,
            "product": product,
            "duration": duration,
            "platform": platform,
            "status": "pending"
        })
    
    return scripts

def main():
    all_scripts = []
    
    md_files = sorted([
        f for f in os.listdir(SCRIPTS_DIR) 
        if f.endswith(".md")
    ])
    
    for md_file in md_files:
        filepath = os.path.join(SCRIPTS_DIR, md_file)
        scripts = extract_scripts(filepath)
        all_scripts.extend(scripts)
        print(f"  ✅ {md_file}: {len(scripts)} scripts")
    
    # Sort by ID
    all_scripts.sort(key=lambda x: x["id"])
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_scripts, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 Total: {len(all_scripts)} scripts parsed → {OUTPUT}")
    
    # Print summary
    categories = {}
    for s in all_scripts:
        cat = s["category"]
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\n📋 By Category:")
    for cat, count in categories.items():
        print(f"  {cat}: {count}")

if __name__ == "__main__":
    main()
