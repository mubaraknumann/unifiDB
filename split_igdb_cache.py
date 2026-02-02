#!/usr/bin/env python3
"""
IGDB Database Splitter
Splits all_games.json into organized subdirectory structure
Structure: games/{first_char}/{first_two_chars}.json
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime

IGDB_CACHE_DIR = Path(__file__).parent
ALL_GAMES_FILE = IGDB_CACHE_DIR / "all_games.json"
GAMES_DIR = IGDB_CACHE_DIR / "games"

def normalize_name(name):
    """Normalize game name to first 2 characters for bucketing."""
    normalized = name.lower()
    # Remove special characters, keep only alphanumeric
    normalized = ''.join(c if c.isalnum() else '' for c in normalized)
    # Return first 2 chars, pad with '0' if shorter
    bucket = (normalized[:2] or '00').lower()
    return bucket

def get_first_char(bucket):
    """Get first character for subdirectory."""
    if not bucket:
        return '0'
    first = bucket[0]
    # Group non-alphanumeric into '0' directory
    if not first.isalnum():
        return '0'
    return first

def split_games():
    """Split all_games.json into bucket files organized by subdirectories."""
    
    print("[INIT] Creating games directory structure...")
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    
    print("[LOAD] Loading all_games.json...")
    if not ALL_GAMES_FILE.exists():
        print("[ERROR] all_games.json not found!")
        return False
    
    with open(ALL_GAMES_FILE, 'r') as f:
        all_games = json.load(f)
    
    if not all_games:
        print("[ERROR] No games found in all_games.json")
        return False
    
    print(f"[PROCESS] Processing {len(all_games)} games...")
    
    # Group games by bucket
    buckets = defaultdict(list)
    for game in all_games:
        name = game.get('name', 'unknown')
        bucket = normalize_name(name)
        buckets[bucket].append(game)
    
    # Track statistics
    bucket_stats = {}
    subdirs_created = set()
    
    print(f"[WRITE] Writing {len(buckets)} bucket files...")
    for bucket in sorted(buckets.keys()):
        games_in_bucket = buckets[bucket]
        
        # Determine subdirectory
        first_char = get_first_char(bucket)
        subdir = GAMES_DIR / first_char
        
        # Create subdirectory if needed
        if first_char not in subdirs_created:
            subdir.mkdir(parents=True, exist_ok=True)
            subdirs_created.add(first_char)
        
        bucket_file = subdir / f"{bucket}.json"
        
        with open(bucket_file, 'w') as f:
            json.dump(games_in_bucket, f, separators=(',', ':'), ensure_ascii=False)
        
        file_size = bucket_file.stat().st_size
        relative_path = f"{first_char}/{bucket}.json"
        bucket_stats[bucket] = {
            "file": relative_path,
            "count": len(games_in_bucket),
            "size": file_size,
            "size_kb": round(file_size / 1024, 1)
        }
    
    # Update index.json
    print("[INDEX] Updating index.json...")
    index = {
        "version": "1.0.0",
        "updated": datetime.utcnow().isoformat() + 'Z',
        "total_games": len(all_games),
        "total_buckets": len(buckets),
        "total_subdirs": len(subdirs_created),
        "structure": "games/{first_char}/{bucket}.json",
        "buckets": bucket_stats
    }
    
    with open(IGDB_CACHE_DIR / "index.json", 'w') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    print(f"\n[COMPLETE] Split operation finished")
    print(f"[STATS] Total: {len(all_games)} games in {len(buckets)} buckets across {len(subdirs_created)} subdirectories")
    print(f"[OUTPUT] Bucket directory: {GAMES_DIR}/")
    print(f"[OUTPUT] Index file: {IGDB_CACHE_DIR / 'index.json'}")
    
    return True

if __name__ == "__main__":
    import sys
    success = split_games()
    if not success:
        sys.exit(1)
