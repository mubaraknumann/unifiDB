# unifiDB - IGDB Game Database

Comprehensive game metadata database powered by IGDB API, optimized for CDN delivery and updated via GitHub Actions.

## Overview

This repository provides structured access to 350,000+ games from the IGDB database, split into efficient CDN-friendly bucket files for fast lookups by game name.

### Database Statistics

- **Total Games**: 350,374+
- **Bucket Files**: 1,495 (indexed by normalized name)
- **Database Size**: ~185MB uncompressed, ~48MB compressed
- **CDN Provider**: jsDelivr (unlimited bandwidth)
- **Update Frequency**: Weekly (configurable)

## API Usage

### Direct CDN Access

Fetch games by normalized name. Files are organized in subdirectories by first character, then by first 2 characters:

```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/games/{first_char}/{bucket}.json
```

**Example** - Fetch games starting with "wi" (Witcher, etc.):

```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/games/w/wi.json
```

### File Structure

```
games/
├── a/
│   ├── aa.json
│   ├── ab.json
│   └── ...
├── b/
│   ├── ba.json
│   └── ...
├── w/
│   ├── wi.json  ← Contains "The Witcher 3", etc.
│   └── ...
└── ...
```

### Metadata Index

Access database metadata and statistics:

```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/index.json
```

## Configuration

### GitHub Secrets Setup

To enable automated database updates:

1. Navigate to **Settings → Secrets and variables → Actions**
2. Add the following repository secrets:

| Secret Name          | Description                      | Source                                                         |
| -------------------- | -------------------------------- | -------------------------------------------------------------- |
| `IGDB_CLIENT_ID`     | Twitch application Client ID     | [Twitch Developer Console](https://dev.twitch.tv/console/apps) |
| `IGDB_CLIENT_SECRET` | Twitch application Client Secret | [Twitch Developer Console](https://dev.twitch.tv/console/apps) |

### Update Schedule

- **Manual Trigger**: Navigate to Actions tab → "Update IGDB Database" → "Run workflow"
- **Automatic Updates**: Uncomment the `schedule` section in `.github/workflows/update-igdb.yml`

```yaml
schedule:
  - cron: "0 0 * * 0" # Weekly on Sundays at midnight UTC
```

## Data Structure

Each game entry contains the following fields:

| Field               | Type    | Description                                                 |
| ------------------- | ------- | ----------------------------------------------------------- |
| `igdb_id`           | Integer | IGDB unique game identifier                                 |
| `name`              | String  | Game title                                                  |
| `summary`           | String  | Game description/synopsis                                   |
| `genres`            | Array   | Genre names                                                 |
| `developers`        | Array   | Developer studio names                                      |
| `publishers`        | Array   | Publisher company names                                     |
| `aggregated_rating` | Float   | Metacritic-style aggregated score                           |
| `release_date`      | Integer | Unix timestamp of release date                              |
| `platforms`         | Array   | Platform names (PC, PlayStation, Xbox, etc.)                |
| `cover_url`         | String  | IGDB cover image URL                                        |
| `external_ids`      | Array   | Cross-platform store identifiers (Steam, Epic, GOG, Amazon) |

### External IDs Format

```json
"external_ids": [
  {
    "category": 1,
    "store": "steam",
    "uid": "292030",
    "url": "https://store.steampowered.com/app/292030"
  }
]
```

**Store Categories**:

- `1` - Steam
- `5` - GOG
- `26` - Epic Games Store
- `23` - Amazon Games
- `30` - itch.io

## Local Development

### Prerequisites

```bash
pip install aiohttp
```

### Download Full Database

```bash
python download_igdb_cache.py
```

### Generate Bucket Files

```bash
python split_igdb_cache.py
```

## License

Database content provided by [IGDB.com](https://www.igdb.com/). Commercial use permitted under IGDB API Terms of Service.

## Attribution

Powered by IGDB API - https://www.igdb.com/
