#!/usr/bin/env python3
import json
import os
from pathlib import Path
from collections import defaultdict

IGDB_CACHE_DIR = Path(__file__).parent.parent / "igdb-cache"
ALL_GAMES_FILE = IGDB_CACHE_DIR / "all_games.json"
GAMES_DIR = IGDB_CACHE_DIR / "games"

def normalize_name(name):
    """Normalize game name to first 2 characters for bucketing."""
    normalized = name.lower()
    # Remove special characters, keep only alphanumeric
    normalized = ''.join(c if c.isalnum() else '' for c in normalized)
    # Return first 2 chars, pad with '0' if shorter
    return (normalized[:2] or '00').lower()

def split_games():
    """Split all_games.json into bucket files by first 2 normalized chars."""
    
    print("[INIT] Creating games directory...")
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    
    print("[LOAD] Loading all_games.json...")
    with open(ALL_GAMES_FILE, 'r') as f:
        all_games = json.load(f)
    
    # Group games by bucket
    buckets = defaultdict(list)
    bucket_stats = {}
    
    print(f"[PROCESS] Processing {len(all_games)} games...")
    for game in all_games:
        name = game.get('name', 'unknown')
        bucket = normalize_name(name)
        buckets[bucket].append(game)
    
    # Write bucket files
    print(f"[WRITE] Writing {len(buckets)} bucket files...")
    for bucket in sorted(buckets.keys()):
        games_in_bucket = buckets[bucket]
        bucket_file = GAMES_DIR / f"{bucket}.json"
        
        with open(bucket_file, 'w') as f:
            json.dump(games_in_bucket, f, separators=(',', ':'), ensure_ascii=False)
        
        file_size = bucket_file.stat().st_size
        bucket_stats[bucket] = {
            "file": f"{bucket}.json",
            "count": len(games_in_bucket),
            "size": file_size,
            "size_kb": round(file_size / 1024, 1)
        }
        print(f"  {bucket}.json: {len(games_in_bucket)} games ({file_size / 1024:.1f}KB)")
    
    # Update index.json
    print("[INDEX] Updating index.json...")
    index = {
        "version": "1.0.0",
        "updated": None,  # Will be set by GitHub Actions
        "buckets": bucket_stats,
        "total_games": len(all_games),
        "total_buckets": len(buckets)
    }
    
    with open(IGDB_CACHE_DIR / "index.json", 'w') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    print(f"\n[COMPLETE] Split operation finished")
    print(f"[STATS] Total: {len(all_games)} games in {len(buckets)} buckets")
    print(f"[OUTPUT] Bucket directory: {GAMES_DIR}/")
    print(f"[OUTPUT] Index file: {IGDB_CACHE_DIR / 'index.json'}")

if __name__ == "__main__":
    split_games()
