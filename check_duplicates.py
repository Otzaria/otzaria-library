#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Report duplicate packaged names; link roots come only from the sync config."""

import os
from collections import defaultdict
from pathlib import Path

from manual_links_packaging import BOOK_ROOTS, CONFIG_NAME, load_json, validate_config


def configured_paths():
    config = validate_config(load_json(Path(CONFIG_NAME)))
    links = [entry["path"] for entry in config["links_roots"] if entry["expected_state"] == "present"]
    return list(BOOK_ROOTS) + links

def find_duplicates():
    """מוצא כפילויות בשמות קבצים"""
    # מילון: שם קובץ -> רשימת נתיבים מלאים
    files_dict = defaultdict(list)
    
    print("סורק קבצים...")
    
    for path in configured_paths():
        if not os.path.exists(path):
            print(f"⚠️  התיקייה לא קיימת: {path}")
            continue
            
        # עובר על כל הקבצים בתיקייה (כולל תתי-תיקיות)
        for root, dirs, files in os.walk(path):
            for filename in files:
                full_path = os.path.join(root, filename)
                files_dict[filename].append(full_path)
    
    # מוצא כפילויות
    duplicates = {name: paths for name, paths in files_dict.items() if len(paths) > 1}
    
    if not duplicates:
        print("\n✅ לא נמצאו כפילויות!")
        return
    
    # הדפסת כפילויות כלליות
    print(f"\n{'='*80}")
    print("חלק 1: כפילויות כלליות")
    print(f"{'='*80}")
    
    if duplicates:
        print(f"\n🔍 נמצאו {len(duplicates)} כפילויות כלליות:\n")
        for filename, paths in sorted(duplicates.items()):
            print(f"\n📄 {filename} ({len(paths)} פעמים):")
            for path in sorted(paths):
                print(f"   • {path}")
    else:
        print("\n✅ לא נמצאו כפילויות כלליות")
    
    # סיכום
    print(f"\n{'='*80}")
    print(f"סה\"כ כולל: {len(duplicates)}")
    print(f"{'='*80}")

if __name__ == "__main__":
    find_duplicates()
