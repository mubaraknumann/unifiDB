# unifiDB - IGDB Game Database

[![Total CDN Hits](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mubaraknumann/unifiDB/main/stats/hits_total.json)](https://github.com/mubaraknumann/unifiDB/blob/main/stats/stats.json)
[![Monthly CDN Hits](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mubaraknumann/unifiDB/main/stats/hits_month.json)](https://github.com/mubaraknumann/unifiDB/blob/main/stats/stats.json)
[![Total Bandwidth](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mubaraknumann/unifiDB/main/stats/bandwidth_total.json)](https://github.com/mubaraknumann/unifiDB/blob/main/stats/stats.json)
[![Monthly Bandwidth](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mubaraknumann/unifiDB/main/stats/bandwidth_month.json)](https://github.com/mubaraknumann/unifiDB/blob/main/stats/stats.json)

Comprehensive game metadata database powered by IGDB API, optimized for CDN delivery and updated via GitHub Actions.

## Overview

This repository provides structured access to 350,000+ games from the IGDB database, split into efficient CDN-friendly bucket files for fast lookups by game name.

## CDN Usage & Statistics

unifiDB is distributed globally via jsDelivr's CDN edge network to power metadata and save-location resolution for [Unifideck](https://github.com/mubaraknumann/unifideck).

- **Total CDN Requests**: 19.5M+ (Lifetime)
- **Monthly Requests**: ~1.6M / month
- **Total Bandwidth Served**: 10.9 TB
- **Monthly Bandwidth**: ~643 GB / month
- **CDN Rank**: #1,194 among GitHub repositories on jsDelivr

Live structured metrics are tracked daily and available via [`stats/stats.json`](https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/stats/stats.json).

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

### Save Location Data

Records may include save-game metadata, populated by `enrich_save_locations.py` from the
[Ludusavi manifest](https://github.com/mtkennerly/ludusavi-manifest):

| Field            | Type   | Description                                                              |
| ---------------- | ------ | ------------------------------------------------------------------------ |
| `save_locations` | Array  | `{ "path", "tags", "stores" }` — Windows-relevant save/config paths using Ludusavi path tokens (`<winAppData>`, `<base>`, `<storeUserId>`, …) |
| `cloud`          | Object | Native cloud-save support flags per store, e.g. `{ "gog": true, "steam": true, "epic": false }` |
| `save_source`    | String | Attribution string for the save-location data                            |

## Ubisoft Catalog

Ubisoft Connect (UPC) records owned games in two id namespaces — a legacy numeric
`install_id` and a modern product `UUID` (Algolia `appId`/`spaceId`). Unifideck reads both
from the local ownership binary and names them from two lookup tables built here by
`build_ubisoft.py` and refreshed weekly (`.github/workflows/update-ubisoft.yml`):

```
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/ubisoft/install_ids.txt
https://cdn.jsdelivr.net/gh/mubaraknumann/unifiDB@main/ubisoft/uuid_catalog.json
```

| File | Key → value | Source |
| --- | --- | --- |
| `ubisoft/install_ids.txt` | numeric `install_id` → name (`id, name` per line) | mirror of the community list [`iArtorias/ubisoft_game_ids`](https://github.com/iArtorias/ubisoft_game_ids) — covers legacy titles |
| `ubisoft/uuid_catalog.json` | `uuid` → `{ name, genre, brand, boxshot, slug, release_date }` | Ubisoft Connect's public Algolia product index — covers modern titles the community list lacks |

`uuid_catalog.json` shape: `{ "version", "updated", "count", "games": { "<uuid>": { "name", … } } }`.

## License

Game metadata content provided by [IGDB.com](https://www.igdb.com/).

Save-location data (`save_locations`, `cloud`, `save_source` fields) originates from
[PCGamingWiki](https://www.pcgamingwiki.com/), licensed
[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/), compiled by the
[Ludusavi](https://github.com/mtkennerly/ludusavi-manifest) project. This non-commercial
database redistributes that subset under the same terms.
