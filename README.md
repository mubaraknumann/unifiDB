# unifiDB - IGDB Game Database

Game metadata database powered by IGDB, updated weekly via GitHub Actions.

## 📊 Database Stats

- **Games**: 350,374+
- **Bucket files**: 1,495
- **Total size**: ~185MB uncompressed
- **CDN**: jsDelivr

## 🚀 Usage

### Direct CDN Access

Fetch games by normalized name (first 2 characters):

```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/games/{bucket}.json
```

Example - Witcher games:
```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/games/wi.json
```

### Index Metadata

```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/index.json
```

## 🔧 GitHub Secrets Setup

To enable automated updates, add these secrets in **Settings → Secrets and variables → Actions**:

1. `IGDB_CLIENT_ID` - Your Twitch application Client ID
2. `IGDB_CLIENT_SECRET` - Your Twitch application Client Secret

Get credentials at: https://dev.twitch.tv/console/apps

## 📅 Update Schedule

- **Manual**: Actions tab → "Update IGDB Database" → Run workflow
- **Automatic**: Uncomment `schedule` in `.github/workflows/update-igdb.yml`

## 📦 Data Structure

Each game includes:
- `igdb_id` - IGDB game ID
- `name` - Game title
- `summary` - Description
- `genres[]` - Genre names
- `developers[]` - Developer names
- `publishers[]` - Publisher names
- `aggregated_rating` - Metacritic-style score
- `release_date` - Unix timestamp
- `platforms[]` - Platform names
- `cover_url` - Cover image URL
- `external_ids[]` - Store IDs (Steam, Epic, GOG, Amazon)

## 🛠️ Local Development

```bash
# Download full database
python download_igdb_cache.py

# Split into buckets
python split_igdb_cache.py
```

## 📜 License

Database powered by [IGDB.com](https://www.igdb.com/) - Commercial use allowed under IGDB API terms.
