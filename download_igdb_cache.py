#!/usr/bin/env python3
"""
IGDB Database Downloader
Downloads all games from IGDB with external store IDs
Generates all_games.json with embedded external_ids
"""

import aiohttp
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
import sys

# Configuration
IGDB_API_URL = "https://api.igdb.com/v4"
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"

# Get credentials from environment or use hardcoded (for GitHub Actions secrets)
CLIENT_ID = os.getenv("IGDB_CLIENT_ID", "c38emwbj8xb0wi44vqr91r5aw0c4o4")
CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET", "sbkoa76c214wpvpe3vjo91kwn95zt5")

# Output settings
OUTPUT_DIR = Path(__file__).parent
ALL_GAMES_FILE = OUTPUT_DIR / "all_games.json"
ALL_GAMES_TEMP = OUTPUT_DIR / "all_games_temp.json"
INDEX_FILE = OUTPUT_DIR / "index.json"

# Rate limiting
BATCH_SIZE = 500
REQUEST_DELAY = 0.286  # ~3.5 req/sec to stay under 4 req/sec limit
MIN_GAMES_THRESHOLD = 100000  # Minimum games required before overwriting existing data

class IGDBDownloader:
    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        
    async def authenticate(self, session):
        """Authenticate with Twitch and get IGDB access token."""
        print("[AUTH] Authenticating with Twitch...")
        
        auth_params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        
        async with session.post(TWITCH_AUTH_URL, data=auth_params) as resp:
            if resp.status != 200:
                raise Exception(f"Auth failed: {resp.status}")
            
            data = await resp.json()
            self.access_token = data['access_token']
            expires_in = data.get('expires_in', 3600)
            
            hours = expires_in // 3600
            print(f"[AUTH] Authenticated successfully (token expires in {hours} hours)")
    
    def get_headers(self):
        """Get IGDB API headers."""
        return {
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {self.access_token}"
        }
    
    async def fetch_games_batch(self, session, offset, limit=500):
        """Fetch a batch of games from IGDB."""
        # IGDB API uses expanded fields - not nested dot notation for some fields
        query = f"""
        fields id, name, summary, 
               genres.name, 
               involved_companies.company.name, 
               involved_companies.developer,
               involved_companies.publisher,
               aggregated_rating, 
               first_release_date, 
               platforms.name, 
               cover.url;
        where category = 0;
        offset {offset};
        limit {limit};
        sort id asc;
        """
        
        async with session.post(
            f"{IGDB_API_URL}/games",
            headers=self.get_headers(),
            data=query
        ) as resp:
            if resp.status == 429:
                print(f"[WARNING] Rate limited, waiting 5s...")
                await asyncio.sleep(5)
                return await self.fetch_games_batch(session, offset, limit)
            
            if resp.status != 200:
                error_text = await resp.text()
                print(f"[ERROR] Failed to fetch games at offset {offset}: {resp.status}")
                print(f"[ERROR] Response: {error_text}")
                return []
            
            result = await resp.json()
            if offset == 0:
                print(f"[DEBUG] First batch returned {len(result)} games")
                if result:
                    print(f"[DEBUG] Sample game: {result[0].get('name', 'N/A')}")
            return result
    
    async def fetch_external_ids_batch(self, session, game_ids):
        """Fetch external store IDs for a batch of games."""
        if not game_ids:
            return []
        
        ids_str = ",".join(str(gid) for gid in game_ids)
        query = f"""
        fields id, game, category, uid, url;
        where game = ({ids_str});
        limit 500;
        """
        
        async with session.post(
            f"{IGDB_API_URL}/external_games",
            headers=self.get_headers(),
            data=query
        ) as resp:
            if resp.status == 429:
                await asyncio.sleep(5)
                return await self.fetch_external_ids_batch(session, game_ids)
            
            if resp.status != 200:
                print(f"[ERROR] Failed to fetch external IDs: {resp.status}")
                return []
            
            return await resp.json()
    
    async def download_all_games(self, session, limit=400000):
        """Download all games with their external IDs."""
        print(f"[DOWNLOAD] Starting IGDB download (limit: {limit:,})...")
        print(f"[DOWNLOAD] Batching strategy: games + external IDs together")
        
        # Create output directory
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file first (validation before overwrite)
        with open(ALL_GAMES_TEMP, 'w') as f:
            f.write('[\n')
        
        total_games = 0
        first_game = True
        consecutive_empty = 0
        
        for offset in range(0, limit, BATCH_SIZE):
            # Fetch games batch
            games = await self.fetch_games_batch(session, offset, BATCH_SIZE)
            
            if not games:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    print(f"[INFO] No more games found after offset {offset}")
                    break
                continue
            
            consecutive_empty = 0
            game_ids = [g.get('id') for g in games if g.get('id')]
            
            # Fetch external IDs for this batch
            external_ids = await self.fetch_external_ids_batch(session, game_ids)
            
            # Map external IDs to games
            ext_id_map = {}
            for ext in external_ids:
                game_id = ext.get('game')
                if game_id not in ext_id_map:
                    ext_id_map[game_id] = []
                ext_id_map[game_id].append({
                    'category': ext.get('category'),
                    'store': self._category_to_store(ext.get('category')),
                    'uid': ext.get('uid'),
                    'url': ext.get('url')
                })
            
            # Write games to temp file
            with open(ALL_GAMES_TEMP, 'a') as f:
                for game in games:
                    game_id = game.get('id')
                    
                    # Extract developers and publishers from involved_companies
                    developers = []
                    publishers = []
                    for ic in game.get('involved_companies', []):
                        company = ic.get('company', {})
                        company_name = company.get('name') if isinstance(company, dict) else None
                        if company_name:
                            if ic.get('developer'):
                                developers.append(company_name)
                            if ic.get('publisher'):
                                publishers.append(company_name)
                    
                    game_data = {
                        'igdb_id': game_id,
                        'name': game.get('name'),
                        'summary': game.get('summary'),
                        'genres': [g.get('name') for g in game.get('genres', []) if g.get('name')],
                        'developers': developers,
                        'publishers': publishers,
                        'aggregated_rating': game.get('aggregated_rating'),
                        'release_date': game.get('first_release_date'),
                        'platforms': [p.get('name') for p in game.get('platforms', []) if p.get('name')],
                        'cover_url': game.get('cover', {}).get('url') if game.get('cover') else None,
                        'external_ids': ext_id_map.get(game_id, [])
                    }
                    
                    if not first_game:
                        f.write(',\n')
                    f.write(json.dumps(game_data, ensure_ascii=False, separators=(',', ':')))
                    first_game = False
                    total_games += 1
            
            # Rate limiting
            await asyncio.sleep(REQUEST_DELAY)
            
            # Progress
            if (total_games % BATCH_SIZE) == 0:
                print(f"[PROGRESS] Processed {total_games:,} games")
        
        # Close JSON array
        with open(ALL_GAMES_TEMP, 'a') as f:
            f.write('\n]')
        
        print(f"\n[COMPLETE] Download finished")
        print(f"[STATS] Total games: {total_games:,}")
        
        return total_games
    
    def _category_to_store(self, category):
        """Map IGDB external_games category to store name."""
        stores = {
            1: 'steam',
            5: 'gog',
            26: 'epic',
            23: 'amazon',
            30: 'itch',
            11: 'android',
            12: 'ios',
            13: 'microsoft',
            14: 'playstation',
            15: 'xbox',
            20: 'twitch',
            28: 'oculus'
        }
        return stores.get(category, f'store_{category}')
    
    def validate_and_commit(self, game_count):
        """Validate download and commit changes if successful."""
        print(f"[VALIDATE] Checking download integrity...")
        
        # Check minimum threshold
        if game_count < MIN_GAMES_THRESHOLD:
            print(f"[ERROR] Download failed: Only {game_count:,} games (minimum: {MIN_GAMES_THRESHOLD:,})")
            print(f"[ERROR] Keeping existing data intact")
            if ALL_GAMES_TEMP.exists():
                ALL_GAMES_TEMP.unlink()
            return False
        
        # Verify temp file exists and is valid JSON
        if not ALL_GAMES_TEMP.exists():
            print(f"[ERROR] Temp file not found")
            return False
        
        try:
            with open(ALL_GAMES_TEMP, 'r') as f:
                # Just check it's valid JSON by loading first and last few bytes
                content = f.read(100)
                if not content.startswith('['):
                    raise ValueError("Invalid JSON structure")
            
            # Check file size is reasonable (at least 50MB for 100k+ games)
            file_size = ALL_GAMES_TEMP.stat().st_size
            if file_size < 50_000_000:
                print(f"[WARNING] File size seems small: {file_size / 1_000_000:.1f}MB")
        except Exception as e:
            print(f"[ERROR] Validation failed: {e}")
            if ALL_GAMES_TEMP.exists():
                ALL_GAMES_TEMP.unlink()
            return False
        
        # All checks passed - replace existing file
        print(f"[VALIDATE] All checks passed, committing changes...")
        if ALL_GAMES_FILE.exists():
            ALL_GAMES_FILE.unlink()
        ALL_GAMES_TEMP.rename(ALL_GAMES_FILE)
        
        print(f"[SUCCESS] Database updated with {game_count:,} games")
        return True
    
    def update_index(self, game_count):
        """Update index.json with metadata."""
        index = {
            'version': '1.0.0',
            'updated': datetime.utcnow().isoformat() + 'Z',
            'all_games': {
                'file': 'all_games.json',
                'count': game_count,
                'size': ALL_GAMES_FILE.stat().st_size if ALL_GAMES_FILE.exists() else 0,
                'size_mb': round(ALL_GAMES_FILE.stat().st_size / 1048576, 1) if ALL_GAMES_FILE.exists() else 0
            },
            'buckets': {
                'available': True,
                'directory': 'games/',
                'count': 0  # Updated after split script runs
            }
        }
        
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

async def main():
    downloader = IGDBDownloader()
    
    async with aiohttp.ClientSession() as session:
        try:
            await downloader.authenticate(session)
            game_count = await downloader.download_all_games(session)
            
            # Validate before committing
            if not downloader.validate_and_commit(game_count):
                print(f"[ABORT] Download validation failed, exiting with error")
                sys.exit(1)
            
            downloader.update_index(game_count)
            print(f"[SUCCESS] All done! {game_count:,} games downloaded and validated.")
        except Exception as e:
            print(f"[ERROR] {e}")
            # Clean up temp file on error
            if ALL_GAMES_TEMP.exists():
                ALL_GAMES_TEMP.unlink()
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
