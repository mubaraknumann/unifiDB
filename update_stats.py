#!/usr/bin/env python3
"""
update_stats.py
Fetches live jsDelivr CDN usage statistics for mubaraknumann/unifiDB,
updates stats/stats.json, and generates dynamic endpoint badge files for shields.io.
Zero third-party dependencies (uses standard library urllib).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO_OWNER = "mubaraknumann"
REPO_NAME = "unifiDB"
STATS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats")


def fetch_jsdelivr_stats(period: str) -> dict:
    url = f"https://data.jsdelivr.com/v1/stats/packages/gh/{REPO_OWNER}/{REPO_NAME}?period={period}"
    headers = {
        "User-Agent": f"{REPO_NAME}-Stats-Collector/1.0 (+https://github.com/{REPO_OWNER}/{REPO_NAME})"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"Error fetching stats for period '{period}': {e}", file=sys.stderr)
        raise


def format_compact_number(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B".rstrip("0").rstrip(".")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def format_bytes_si(b: int) -> str:
    tb = b / 1_000_000_000_000
    gb = b / 1_000_000_000
    mb = b / 1_000_000
    if tb >= 1.0:
        return f"{tb:.1f} TB"
    if gb >= 1.0:
        return f"{gb:.1f} GB"
    if mb >= 1.0:
        return f"{mb:.1f} MB"
    return f"{b} B"


def make_shield_endpoint(label: str, message: str, color: str = "blue") -> dict:
    return {
        "schemaVersion": 1,
        "label": label,
        "message": message,
        "color": color,
    }


def main():
    print(f"Fetching CDN statistics for {REPO_OWNER}/{REPO_NAME}...")
    month_data = fetch_jsdelivr_stats("month")
    year_data = fetch_jsdelivr_stats("year")

    hits_month = month_data.get("hits", {}).get("total", 0)
    hits_year = year_data.get("hits", {}).get("total", 0)
    bw_month = month_data.get("bandwidth", {}).get("total", 0)
    bw_year = year_data.get("bandwidth", {}).get("total", 0)

    rank_hits = month_data.get("hits", {}).get("rank")
    rank_hits_gh = month_data.get("hits", {}).get("typeRank")
    rank_bw = month_data.get("bandwidth", {}).get("rank")
    rank_bw_gh = month_data.get("bandwidth", {}).get("typeRank")

    hits_month_str = format_compact_number(hits_month)
    hits_total_str = format_compact_number(hits_year)
    bw_month_str = format_bytes_si(bw_month)
    bw_total_str = format_bytes_si(bw_year)

    print(f"  Monthly Hits:      {hits_month:,} ({hits_month_str})")
    print(f"  Total (Year) Hits: {hits_year:,} ({hits_total_str})")
    print(f"  Monthly Bandwidth: {bw_month:,} B ({bw_month_str})")
    print(f"  Total Bandwidth:   {bw_year:,} B ({bw_total_str})")

    os.makedirs(STATS_DIR, exist_ok=True)

    # Detailed statistics JSON
    stats_data = {
        "schemaVersion": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "package": f"gh/{REPO_OWNER}/{REPO_NAME}",
        "cdn": "jsDelivr",
        "metrics": {
            "hits": {
                "monthly": hits_month,
                "monthly_formatted": hits_month_str,
                "total": hits_year,
                "total_formatted": hits_total_str,
                "rank_overall": rank_hits,
                "rank_github": rank_hits_gh,
            },
            "bandwidth": {
                "monthly_bytes": bw_month,
                "monthly_formatted": bw_month_str,
                "total_bytes": bw_year,
                "total_formatted": bw_total_str,
                "rank_overall": rank_bw,
                "rank_github": rank_bw_gh,
            },
        },
    }

    with open(os.path.join(STATS_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats_data, f, indent=2)

    # Shields.io custom endpoint badge JSON files
    endpoints = {
        "hits_total.json": make_shield_endpoint("total cdn hits", hits_total_str, "blue"),
        "hits_month.json": make_shield_endpoint("monthly cdn hits", f"{hits_month_str}/mo", "blue"),
        "bandwidth_total.json": make_shield_endpoint("total bandwidth", bw_total_str, "informational"),
        "bandwidth_month.json": make_shield_endpoint("monthly bandwidth", f"{bw_month_str}/mo", "informational"),
    }

    for filename, payload in endpoints.items():
        with open(os.path.join(STATS_DIR, filename), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    print(f"Successfully updated all stats files in {STATS_DIR}/")


if __name__ == "__main__":
    main()
