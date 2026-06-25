#!/usr/bin/env python3
"""
Ubisoft Catalog Builder

Builds two lookup tables Unifideck uses to name owned Ubisoft games from the
local Ubisoft Connect (UPC) ``ownership`` binary, which stores entitlements in
two id forms:

* numeric **install_ids** (legacy uplay namespace, e.g. 4 = AC2), and
* product **UUIDs** (modern namespace = Algolia ``appId``/``spaceId``).

Sources (both public, no auth):

* ``ubisoft/install_ids.txt``  — mirror of the community list
  ``iArtorias/ubisoft_game_ids`` (``install_id, name`` per line). Great for
  legacy titles. Mirrored here so the plugin pulls everything from unifiDB and
  gets a weekly-refreshed copy.
* ``ubisoft/uuid_catalog.json`` — ``uuid -> {name, +metadata}`` built from
  Ubisoft Connect's own public Algolia product index. Great for modern titles
  the community list lacks (AC Origins/Odyssey, Steep, The Division, …).

Together they resolve the full owned library offline (the authenticated Ubisoft
ownership API is dead).

Stdlib only. Run from the repo root; outputs land in ``ubisoft/``.
"""

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "ubisoft"

# Ubisoft Connect's public, search-only Algolia product index (app id + key
# are lifted from UPC's own web bundle — read-only).
ALGOLIA_APP_ID = "AVCVYSEJS1"
ALGOLIA_API_KEY = "9258b782262f815cdfee54a00cf69d02"
ALGOLIA_INDEX = "products_en-us_default"
ALGOLIA_URL = (
    f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
    f"/1/indexes/{ALGOLIA_INDEX}/query"
)
IARTORIAS_URL = (
    "https://raw.githubusercontent.com/iArtorias/ubisoft_game_ids/main/UBI_GAMES.txt"
)


def fetch_algolia_catalog():
    """Page through the public Algolia product index; return all hits."""
    headers = {
        "x-algolia-api-key": ALGOLIA_API_KEY,
        "x-algolia-application-id": ALGOLIA_APP_ID,
        "content-type": "application/json",
    }
    attrs = ["title", "intlName", "spaceId", "mdmId", "genre", "brand",
             "releaseDate", "availabilities", "assets", "slug", "type"]
    hits = []
    page = 0
    while True:
        body = json.dumps({
            "query": "", "hitsPerPage": 1000, "page": page,
            "attributesToRetrieve": attrs,
        }).encode("utf-8")
        req = urllib.request.Request(ALGOLIA_URL, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        hits.extend(data.get("hits", []))
        page += 1
        if page >= data.get("nbPages", 1) or not data.get("hits"):
            break
    return hits


def build_uuid_catalog(hits):
    """uuid (appId|spaceId) -> {name, genre, brand, boxshot, slug, release_date}.

    Each product is indexed under its top-level ``spaceId`` and every
    per-platform ``appId``/``spaceId`` in ``availabilities`` — the exact values
    the ownership binary stores.
    """
    catalog = {}
    for h in hits:
        title = h.get("title") or h.get("intlName")
        if not title:
            continue
        # The index is base-games-only today (every hit is type "Game"),
        # but guard against DLC/add-ons ever appearing so the plugin's
        # catalog stays an authoritative base-game allowlist.
        ptype = h.get("type")
        if ptype and ptype.lower() != "game":
            continue
        meta = {
            "name": title,
            "type": ptype,
            "genre": h.get("genre"),
            "brand": (h.get("brand") or {}).get("title"),
            "boxshot": (h.get("assets") or {}).get("boxshot"),
            "slug": h.get("slug"),
            "release_date": h.get("releaseDate"),
        }
        keys = set()
        if h.get("spaceId"):
            keys.add(h["spaceId"])
        for a in (h.get("availabilities") or []):
            if a.get("appId"):
                keys.add(a["appId"])
            if a.get("spaceId"):
                keys.add(a["spaceId"])
        for k in keys:
            catalog.setdefault(k, meta)
    return catalog


def fetch_iartorias_text():
    """Raw ``install_id, name`` list (kept verbatim, normalised line endings)."""
    req = urllib.request.Request(
        IARTORIAS_URL, headers={"User-Agent": "unifiDB-ubisoft-builder"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


# Rows in the iArtorias list that are not ownable base/edition games:
# QC/internal builds, betas, store subscriptions, promo/company-logo
# assets, "[SECURED]" wrappers. Dropped at mirror time so the plugin's
# legacy backfill can't surface them as phantom shortcuts. Edition rows
# ("- History Edition") are deliberately NOT matched — those are games.
_NOISE_NAME_RE = re.compile(
    r"\b(internal|dev/qc|company logo|subscription|promotional|"
    r"pts|test server|closed beta|open beta)\b|\[secured\]|\[beta\]",
    re.IGNORECASE,
)


def clean_iartorias_text(text):
    """Drop non-game noise rows, keeping the ``id, name`` format verbatim."""
    kept, dropped = [], 0
    for ln in text.splitlines():
        head, _, name = ln.partition(",")
        if head.strip().isdigit() and _NOISE_NAME_RE.search(name):
            dropped += 1
            continue
        kept.append(ln)
    return "\n".join(kept), dropped


def count_install_ids(text):
    return sum(
        1 for ln in text.splitlines()
        if "," in ln and ln.split(",", 1)[0].strip().isdigit()
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    print("[Ubisoft] fetching Algolia product catalog…")
    hits = fetch_algolia_catalog()
    uuid_catalog = build_uuid_catalog(hits)
    payload = {
        "version": "1.0.0",
        "updated": now,
        "source": "Ubisoft Connect public Algolia product index",
        "products": len(hits),
        "count": len(uuid_catalog),
        "games": uuid_catalog,
    }
    (OUTPUT_DIR / "uuid_catalog.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False),
    )
    print(f"[Ubisoft] {len(hits)} products -> {len(uuid_catalog)} uuid keys")

    print("[Ubisoft] mirroring iArtorias install_id list…")
    text = fetch_iartorias_text()
    # Strip a trailing BOM/whitespace; keep the `id, name` lines verbatim so
    # the plugin's existing parser consumes it unchanged. Drop QC/internal/
    # subscription/logo noise rows that aren't ownable games.
    text = text.replace("\r\n", "\n").lstrip("﻿")
    text, dropped = clean_iartorias_text(text)
    (OUTPUT_DIR / "install_ids.txt").write_text(text)
    n_ids = count_install_ids(text)
    print(
        f"[Ubisoft] mirrored {n_ids} install_id -> name entries "
        f"({dropped} noise rows dropped)",
    )

    print(f"[OUTPUT] {OUTPUT_DIR/'uuid_catalog.json'}")
    print(f"[OUTPUT] {OUTPUT_DIR/'install_ids.txt'}")


if __name__ == "__main__":
    main()
