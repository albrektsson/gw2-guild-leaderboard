#!/usr/bin/env python3
"""
fetch_log.py
Fetches new entries from the GW2 guild log API and appends them to data/guild_log.json.
Uses the stored last_id as a cursor to only fetch new events.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# --- Config ---
GUILD_ID = os.environ["GW2_GUILD_ID"]
API_KEY  = os.environ["GW2_API_KEY"]

REPO_ROOT     = Path(__file__).parent.parent
DATA_FILE     = REPO_ROOT / "data" / "guild_log.json"
MEMBERS_FILE  = REPO_ROOT / "data" / "guild_members.json"
GUILD_FILE    = REPO_ROOT / "data" / "guild_info.json"
EMBLEM_FILE   = REPO_ROOT / "data" / "guild_emblem.svg"
CONFIG_FILE   = REPO_ROOT / "config.json"

_config = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
RETENTION_DAYS = _config.get("retention_days")  # None = keep all

BASE_URL = f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/log"
HEADERS  = {"Authorization": f"Bearer {API_KEY}"}


def load_existing() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"last_id": 0, "updated_at": None, "entries": []}


def fetch_guild_info() -> dict:
    response = requests.get(
        f"https://api.guildwars2.com/v2/guild/{GUILD_ID}",
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return {"id": data["id"], "name": data["name"], "tag": data.get("tag", "")}


def fetch_members() -> list:
    response = requests.get(
        f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members",
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def fetch_new_entries(since: int) -> list:
    params = {}
    if since > 0:
        params["since"] = since

    response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def main():
    # Fetch guild info (name, tag) — rarely changes but cheap to refresh
    print("Fetching guild info...")
    guild_info = fetch_guild_info()
    with open(GUILD_FILE, "w") as f:
        json.dump(guild_info, f, indent=2)
    print(f"  {guild_info['name']} [{guild_info['tag']}]")

    # Fetch and cache guild emblem SVG from third-party renderer
    try:
        emblem_resp = requests.get(
            f"https://guilds.gw2w2w.com/guilds/{guild_info['name']}.svg",
            timeout=10,
        )
        if emblem_resp.ok and "svg" in emblem_resp.headers.get("content-type", ""):
            EMBLEM_FILE.write_bytes(emblem_resp.content)
            print("  Emblem SVG saved.")
        else:
            print("  Emblem fetch returned unexpected response, skipping.")
    except Exception as e:
        print(f"  Emblem fetch failed ({e}), skipping.")

    # Always refresh the member list — membership changes independently of the log
    print("Fetching current guild members...")
    members = fetch_members()
    MEMBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMBERS_FILE, "w") as f:
        json.dump(members, f, indent=2)
    print(f"  Saved {len(members)} members.")

    print("Loading existing log data...")
    data = load_existing()
    last_id = data.get("last_id", 0)
    print(f"  Current cursor: last_id={last_id}, existing entries={len(data['entries'])}")

    print(f"Fetching new entries from GW2 API (since={last_id})...")
    new_entries = fetch_new_entries(since=last_id)
    print(f"  Got {len(new_entries)} new entries")

    if not new_entries:
        print("No new log entries.")
        return

    # Merge and deduplicate by id (API guarantees uniqueness within guild)
    existing_ids = {e["id"] for e in data["entries"]}
    added = [e for e in new_entries if e["id"] not in existing_ids]
    print(f"  {len(added)} entries after dedup")

    if not added:
        print("All fetched entries already stored.")
        return

    data["entries"].extend(added)
    data["last_id"] = max(e["id"] for e in data["entries"])
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    if RETENTION_DAYS is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        before = len(data["entries"])
        data["entries"] = [e for e in data["entries"] if e.get("time", "") >= cutoff]
        trimmed = before - len(data["entries"])
        if trimmed:
            print(f"  Trimmed {trimmed} entries older than {RETENTION_DAYS} days.")

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved. New last_id={data['last_id']}, total entries={len(data['entries'])}")


if __name__ == "__main__":
    main()
