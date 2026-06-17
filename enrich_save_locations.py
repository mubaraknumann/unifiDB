#!/usr/bin/env python3
"""Enrich all_games.json with save-game locations from the Ludusavi manifest.

Runs in the unifiDB pipeline BETWEEN ``download_igdb_cache.py`` (which writes
``all_games.json``) and ``split_igdb_cache.py`` (which buckets it for the CDN).

The Ludusavi manifest (https://github.com/mtkennerly/ludusavi-manifest) is a
machine-readable save-path database compiled from PCGamingWiki. We match each
IGDB record to a Ludusavi entry — by embedded Steam/GOG id first, then by
normalized-title / fuzzy ``titles_match`` — and graft three fields onto the
matched record:

    "save_locations": [{"path": "<winAppData>/Foo/Saves",
                         "tags": ["save"], "stores": ["steam"]}],
    "cloud": {"gog": true, "steam": true, "epic": false},
    "save_source": "PCGamingWiki (CC BY-NC-SA 3.0) via Ludusavi manifest"

Only Windows-relevant paths are kept (the Steam Deck runs these stores' games
through Proton, i.e. a Windows prefix). ``split_igdb_cache.py`` dumps the whole
record dict, so these fields reach the CDN buckets with no change to the splitter.

Attribution: save-location data originates from PCGamingWiki, licensed
CC BY-NC-SA 3.0, compiled by the Ludusavi project. unifiDB is non-commercial.
"""
from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

from title_match import normalize_for_match, titles_match

HERE = Path(__file__).parent
ALL_GAMES_FILE = HERE / "all_games.json"
MANIFEST_URL = (
    "https://raw.githubusercontent.com/mtkennerly/"
    "ludusavi-manifest/master/data/manifest.yaml"
)
SAVE_SOURCE = "PCGamingWiki (CC BY-NC-SA 3.0) via Ludusavi manifest"

# Ludusavi `when` os values we keep (Proton runs a Windows prefix). A path with
# no `when` applies everywhere, so it is kept too.
_WINDOWS_OS = {None, "windows", "dos"}

# Skip fuzzy matching when the rarest query word still maps to more candidate
# titles than this — a guard against pathological many-thousand scans.
_FUZZY_BUCKET_CAP = 1500


def fetch_manifest(url: str = MANIFEST_URL) -> dict:
    """Download + parse the Ludusavi manifest YAML."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "unifiDB-enrich/1.0", "Accept-Encoding": "gzip"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    data = yaml.safe_load(raw.decode("utf-8", "replace"))
    if not isinstance(data, dict):
        raise ValueError("manifest did not parse to a mapping")
    return data


def extract_save_data(entry: dict) -> dict | None:
    """Pull windows-relevant save_locations + cloud flags from one entry.

    Returns ``None`` when the entry has no usable Windows save/config path.
    """
    if not isinstance(entry, dict):
        return None
    locations: list[dict] = []
    for path, meta in (entry.get("files") or {}).items():
        if not isinstance(meta, dict):
            continue
        tags = meta.get("tags") or []
        # Skip pure backup markers; keep save (primary) and config (fallback).
        if tags and "save" not in tags and "config" not in tags:
            continue
        whens = meta.get("when") or []
        windows_ok = (not whens) or any(
            (w or {}).get("os") in _WINDOWS_OS for w in whens
        )
        if not windows_ok:
            continue
        stores = sorted({(w or {}).get("store") for w in whens if (w or {}).get("store")})
        locations.append({
            "path": path,
            "tags": list(tags) if tags else ["save"],
            "stores": stores,
        })
    if not locations:
        return None
    cloud = {
        k: bool(v)
        for k, v in (entry.get("cloud") or {}).items()
        if k in ("gog", "steam", "epic", "uplay", "origin", "battlenet")
    }
    out = {"save_locations": locations, "save_source": SAVE_SOURCE}
    if cloud:
        out["cloud"] = cloud
    return out


class LudusaviIndex:
    """Lookup of Ludusavi entries by store id and by normalized title."""

    def __init__(self, manifest: dict) -> None:
        self.by_steam: dict[str, dict] = {}
        self.by_gog: dict[str, dict] = {}
        self.by_norm: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        self.word_index: dict[str, set[str]] = defaultdict(set)
        for title, entry in manifest.items():
            if not isinstance(entry, dict):
                continue
            ids = entry.get("id") or {}
            for key in ("steam",):
                if ids.get(key):
                    self.by_steam[str(ids[key])] = entry
            for sid in ids.get("steamExtra") or []:
                self.by_steam.setdefault(str(sid), entry)
            if ids.get("gog"):
                self.by_gog[str(ids["gog"])] = entry
            for gid in ids.get("gogExtra") or []:
                self.by_gog.setdefault(str(gid), entry)
            norm = normalize_for_match(title)
            if not norm:
                continue
            self.by_norm[norm].append((title, entry))
            for word in set(norm.split()):
                self.word_index[word].add(norm)

    def match(self, name: str, ext_ids: list[dict]) -> tuple[dict | None, str]:
        """Return (entry, how) for an IGDB record. how ∈ id|exact|fuzzy|''."""
        # 1) embedded store id (highest confidence)
        for ext in ext_ids or []:
            store, uid = ext.get("store"), ext.get("uid")
            if not uid:
                continue
            if store == "steam" and str(uid) in self.by_steam:
                return self.by_steam[str(uid)], "id"
            if store == "gog" and str(uid) in self.by_gog:
                return self.by_gog[str(uid)], "id"
        # 2) exact normalized title
        norm = normalize_for_match(name or "")
        if not norm:
            return None, ""
        if norm in self.by_norm:
            return self.by_norm[norm][0][1], "exact"
        # 3) fuzzy, pruned to the RAREST shared word so the scan stays bounded
        # (common words like "the"/"of" pull thousands of candidates — a true
        # titles_match always shares the rarest word). Skip single-word and
        # pathological buckets to keep the bulk pipeline fast.
        words = [w for w in norm.split() if len(w) > 1]
        if len(words) < 2:
            return None, ""
        rarest = min(words, key=lambda w: len(self.word_index.get(w, ())))
        bucket = self.word_index.get(rarest, set())
        if len(bucket) > _FUZZY_BUCKET_CAP:
            return None, ""
        for cn in bucket:
            for cand_title, entry in self.by_norm[cn]:
                if titles_match(name, cand_title):
                    return entry, "fuzzy"
        return None, ""


def enrich_games(games: list, index: LudusaviIndex) -> dict:
    """Mutate ``games`` in place, attaching save data. Returns stats."""
    stats = {"total": len(games), "id": 0, "exact": 0, "fuzzy": 0, "with_saves": 0}
    save_cache: dict[int, dict | None] = {}
    for game in games:
        entry, how = index.match(game.get("name", ""), game.get("external_ids") or [])
        if entry is None:
            continue
        key = id(entry)
        if key not in save_cache:
            save_cache[key] = extract_save_data(entry)
        data = save_cache[key]
        if not data:
            continue
        game.update(data)
        stats[how] += 1
        stats["with_saves"] += 1
    return stats


def main() -> int:
    if not ALL_GAMES_FILE.exists():
        print(f"[ERROR] {ALL_GAMES_FILE.name} not found — run download_igdb_cache.py first")
        return 1
    print("[LUDUSAVI] downloading manifest...")
    manifest = fetch_manifest()
    print(f"[LUDUSAVI] {len(manifest)} entries; building index...")
    index = LudusaviIndex(manifest)
    print("[LOAD] reading all_games.json...")
    with open(ALL_GAMES_FILE) as f:
        games = json.load(f)
    print(f"[ENRICH] matching {len(games):,} IGDB records...")
    stats = enrich_games(games, index)
    print("[WRITE] saving all_games.json...")
    with open(ALL_GAMES_FILE, "w") as f:
        json.dump(games, f, ensure_ascii=False, separators=(",", ":"))
    print(
        f"[DONE] {stats['with_saves']:,}/{stats['total']:,} games enriched "
        f"(id={stats['id']:,} exact={stats['exact']:,} fuzzy={stats['fuzzy']:,})",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
