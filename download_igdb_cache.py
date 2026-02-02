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
INDEX_FILE = OUTPUT_DIR / "index.json"

# Rate limiting
BATCH_SIZE = 500
REQUEST_DELAY = 0.286  # ~3.5 req/sec to stay under 4 req/sec limit

class IGDBDownloader:
    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        
    async def authenticate(self, session):
        """Authenticate with Twitch and get IGDB access token."""
        print("🔐 Authenticating with Twitch...")
        
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
            print(f"✅ Authenticated (token expires in {hours} hours)")
    
    def get_headers(self):
        """Get IGDB API headers."""
        return {
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {self.access_token}"
        }
    
    async def fetch_games_batch(self, session, offset, limit=500):
        """Fetch a batch of games from IGDB."""
        query = f"""
        fields id, name, summary, genres.name, developers.name, publishers.name, 
                aggregated_rating, release_date, platforms.name, cover.url;
        offset {offset};
        limit {limit};
        """
        
        async with session.post(
            f"{IGDB_API_URL}/games",
            headers=self.get_headers(),
            data=query
        ) as resp:
            if resp.status == 429:
                # Rate limited, wait and retry
                await asyncio.sleep(5)
                return await self.fetch_games_batch(session, offset, limit)
            
            if resp.status != 200:
                print(f"Error fetching games at offset {offset}: {resp.status}")
                return []
            
            return await resp.json()
    
    async def fetch_external_ids_batch(self, session, game_ids):
        """Fetch external store IDs for a batch of games."""
        if not game_ids:
            return []
        
        # Build WHERE clause: where game = (id1,id2,id3,...)
        ids_str = ",".join(str(gid) for gid in game_ids)
        query = f"""
        fields id, game, category, uid, url;
        where game = ({ids_str});
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
                print(f"Error fetching external IDs: {resp.status}")
                return []
            
            return await resp.json()
    
    async def download_all_games(self, session, limit=400000):
        """Download all games with their external IDs."""
        print(f"📥 Downloading IGDB games (limit: {limit:,})...")
        print(f"⏱️  Batching: games + external IDs together")
        
        # Create output file
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        with open(ALL_GAMES_FILE, 'w') as f:
            f.write('[\n')
        
        total_games = 0
        first_game = True
        
        for offset in range(0, limit, BATCH_SIZE):
            # Fetch games batch
            games = await self.fetch_games_batch(session, offset, BATCH_SIZE)
            if not games:
                break
            
            game_ids = [g.get('id') for g in games]
            
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
            
            # Write games to file
            with open(ALL_GAMES_FILE, 'a') as f:
                for game in games:
                    game_id = game.get('id')
                    
                    game_data = {
                        'igdb_id': game_id,
                        'name': game.get('name'),
                        'summary': game.get('summary'),
                        'genres': [g.get('name') for g in game.get('genres', [])],
                        'developers': [d.get('name') for d in game.get('developers', [])],
                        'publishers': [p.get('name') for p in game.get('publishers', [])],
                        'aggregated_rating': game.get('aggregated_rating'),
                        'release_date': game.get('release_date'),
                        'platforms': [p.get('name') for p in game.get('platforms', [])],
                        'cover_url': game.get('cover', {}).get('url'),
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
                print(f"📊 Processed {total_games:,} games | Written: {total_games:,}")
        
        # Close JSON array
        with open(ALL_GAMES_FILE, 'a') as f:
            f.write('\n]')
        
        print(f"\n✅ Download complete!")
        print(f"📊 Total: {total_games:,} games")
        print(f"📄 Output: {ALL_GAMES_FILE}")
        
        return total_games
    
    def _category_to_store(self, category):
        """Map IGDB external_games category to store name."""
        stores = {
            1: 'steam',
            5: 'gog',
            26: 'epic',
            23: 'amazon',
            30: 'itch'
        }
        return stores.get(category, f'store_{category}')
    
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
            downloader.update_index(game_count)
            print(f"✅ All done! {game_count:,} games downloaded.")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
