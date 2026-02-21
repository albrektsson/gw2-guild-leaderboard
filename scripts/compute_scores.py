#!/usr/bin/env python3
"""
compute_scores.py
Reads data/guild_log.json and produces data/leaderboard.json with two ranked lists:

  monetary_leaderboard  — ranked by gold value contributed via treasury/stash deposits
                          (net of withdrawals), priced via the GW2 trading post API
  activity_leaderboard  — ranked by flat activity points for upgrades, missions, invites
"""

import json
import requests
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT    = Path(__file__).parent.parent
DATA_FILE    = REPO_ROOT / "data" / "guild_log.json"
MEMBERS_FILE = REPO_ROOT / "data" / "guild_members.json"
OUT_FILE     = REPO_ROOT / "data" / "leaderboard.json"
NAMES_FILE   = REPO_ROOT / "data" / "item_names.json"
PRICES_FILE  = REPO_ROOT / "data" / "item_prices.json"
CONFIG_FILE  = REPO_ROOT / "config.json"

_config = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
RETENTION_DAYS    = _config.get("retention_days")    # None = all-time
LEADERBOARD_LIMIT = _config.get("leaderboard_limit", 20)

COPPER_PER_GOLD = 10000

ACTIVITY_POINTS = {
    "upgrade_queued":   15,
    "mission_started":   5,
    "invited":           5,
    "invite_accepted":   5,  # bonus when an invited member actually joins
    "daily_login":       1,  # per daily login bonus participated in
}


# ---------------------------------------------------------------------------
# Price resolution
# ---------------------------------------------------------------------------

def _batched(items, size=200):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_prices_and_names(item_ids: set) -> tuple[dict, dict]:
    """Return ({item_id: price_copper}, {item_id: name}) for all item IDs.

    Pass 1 — /v2/commerce/prices: gets sell prices for tradeable items.
    Pass 2 — /v2/items: gets names for all items + vendor_value fallback
              for anything not on the trading post.
    """
    if not item_ids:
        return {}, {}

    prices = {}
    names  = {}

    # Pass 1: trading post sell prices (no auth required)
    for batch in _batched(item_ids):
        ids_param = ",".join(str(i) for i in batch)
        resp = requests.get(
            "https://api.guildwars2.com/v2/commerce/prices",
            params={"ids": ids_param},
            timeout=15,
        )
        resp.raise_for_status()
        for entry in resp.json():
            prices[entry["id"]] = entry["sells"]["unit_price"]

    # Pass 2: item metadata — names for all items, vendor_value for untradeable
    for batch in _batched(item_ids):
        ids_param = ",".join(str(i) for i in batch)
        resp = requests.get(
            "https://api.guildwars2.com/v2/items",
            params={"ids": ids_param},
            timeout=15,
        )
        resp.raise_for_status()
        for item in resp.json():
            names[item["id"]] = item.get("name", f"Item #{item['id']}")
            if item["id"] not in prices:
                prices[item["id"]] = item.get("vendor_value", 0)

    # Ensure every requested ID has an entry (some may be unknown/bugged)
    for item_id in item_ids:
        prices.setdefault(item_id, 0)
        names.setdefault(item_id, f"Item #{item_id}")

    return prices, names


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute(entries: list, prices: dict) -> tuple[list, list]:
    """Return (monetary_leaderboard, activity_leaderboard) as ranked lists."""

    monetary = defaultdict(lambda: {
        "monetary_score": 0.0,
        "treasury_value": 0.0,
        "stash_value_deposited": 0.0,
        "stash_value_withdrawn": 0.0,
        "last_active": None,
    })
    activity = defaultdict(lambda: {
        "activity_score": 0,
        "upgrades_queued": 0,
        "missions_started": 0,
        "invites_sent": 0,
        "invites_accepted": 0,
        "daily_login_participations": 0,
        "last_active": None,
    })

    def touch(table, user, time):
        if time and (table[user]["last_active"] is None or time > table[user]["last_active"]):
            table[user]["last_active"] = time

    # Build invite map for joined cross-reference: invitee -> inviter
    invite_map = {
        e["user"]: e["invited_by"]
        for e in entries
        if e.get("type") == "invited" and e.get("user") and e.get("invited_by")
    }

    for entry in entries:
        user = entry.get("user")
        t    = entry.get("type")
        time = entry.get("time")

        if t == "treasury":
            if not user:
                continue
            item_id = entry.get("item_id", 0)
            count   = entry.get("count", 0)
            coins   = entry.get("coins", 0)
            value   = round((count * prices.get(item_id, 0) + coins) / COPPER_PER_GOLD, 2)
            monetary[user]["treasury_value"]  = round(monetary[user]["treasury_value"] + value, 2)
            monetary[user]["monetary_score"]  = round(monetary[user]["monetary_score"] + value, 2)
            touch(monetary, user, time)

        elif t == "stash":
            if not user:
                continue
            item_id   = entry.get("item_id", 0)
            count     = entry.get("count", 0)
            coins     = entry.get("coins", 0)
            operation = entry.get("operation", "deposit")
            value     = round((count * prices.get(item_id, 0) + coins) / COPPER_PER_GOLD, 2)
            if operation == "deposit":
                monetary[user]["stash_value_deposited"] = round(monetary[user]["stash_value_deposited"] + value, 2)
                monetary[user]["monetary_score"]        = round(monetary[user]["monetary_score"] + value, 2)
            elif operation == "withdraw":
                monetary[user]["stash_value_withdrawn"] = round(monetary[user]["stash_value_withdrawn"] + value, 2)
                monetary[user]["monetary_score"]        = round(monetary[user]["monetary_score"] - value, 2)
            touch(monetary, user, time)

        elif t == "upgrade":
            if not user:
                continue
            if entry.get("action") == "queued":
                activity[user]["upgrades_queued"]  += 1
                activity[user]["activity_score"]   += ACTIVITY_POINTS["upgrade_queued"]
                touch(activity, user, time)

        elif t == "mission":
            if not user:
                continue
            if entry.get("state") == "start":
                activity[user]["missions_started"] += 1
                activity[user]["activity_score"]   += ACTIVITY_POINTS["mission_started"]
                touch(activity, user, time)

        elif t == "invited":
            invited_by = entry.get("invited_by")
            if invited_by:
                activity[invited_by]["invites_sent"]   += 1
                activity[invited_by]["activity_score"] += ACTIVITY_POINTS["invited"]
                touch(activity, invited_by, time)

        elif t == "joined":
            # Credit the original inviter when their recruit actually joins
            inviter = invite_map.get(user) if user else None
            if inviter:
                activity[inviter]["invites_accepted"]  += 1
                activity[inviter]["activity_score"]    += ACTIVITY_POINTS["invite_accepted"]
                touch(activity, inviter, time)

        elif t == "influence":
            if entry.get("activity") == "daily_login":
                participants = [p for p in entry.get("participants", []) if p]
                for participant in participants:
                    activity[participant]["daily_login_participations"] += 1
                    activity[participant]["activity_score"]             += ACTIVITY_POINTS["daily_login"]
                    touch(activity, participant, time)

    def rank(table, sort_key):
        ranked = sorted(table.items(), key=lambda x: x[1][sort_key], reverse=True)
        return [{"rank": i + 1, "user": user, **stats} for i, (user, stats) in enumerate(ranked)]

    return rank(monetary, "monetary_score"), rank(activity, "activity_score")


def filter_to_members(leaderboard: list, current_members: set) -> list:
    """Remove ex-members and re-rank the remaining entries."""
    filtered = [e for e in leaderboard if e["user"] in current_members]
    for i, entry in enumerate(filtered):
        entry["rank"] = i + 1
    return filtered


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not DATA_FILE.exists():
        print("No guild_log.json found. Run fetch_log.py first.")
        return

    with open(DATA_FILE) as f:
        data = json.load(f)

    entries = data.get("entries", [])

    if RETENTION_DAYS is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        cutoff_str = cutoff.isoformat()
        entries = [e for e in entries if e.get("time", "") >= cutoff_str]
        print(f"Retention filter: last {RETENTION_DAYS} days → {len(entries)} entries.")
    else:
        print(f"Retention: all-time → {len(entries)} entries.")

    # Collect item IDs that need pricing
    item_ids = {
        e["item_id"]
        for e in entries
        if e.get("type") in ("treasury", "stash") and e.get("item_id")
    }
    # Load current member list for filtering
    if MEMBERS_FILE.exists():
        with open(MEMBERS_FILE) as f:
            members_data = json.load(f)
        current_members = {m["name"] for m in members_data}
        print(f"Loaded {len(current_members)} current guild members.")
    else:
        current_members = None
        print("Warning: guild_members.json not found — run fetch_log.py first. Skipping member filter.")

    print(f"Fetching prices and names for {len(item_ids)} unique items...")
    prices, names = fetch_prices_and_names(item_ids)

    # Write item names and prices as static lookup files for the frontend
    with open(NAMES_FILE, "w") as f:
        json.dump(names, f)
    with open(PRICES_FILE, "w") as f:
        json.dump(prices, f)
    print(f"Item names and prices written ({len(names)} entries).")

    monetary_lb, activity_lb = compute(entries, prices)

    if current_members is not None:
        monetary_lb = filter_to_members(monetary_lb, current_members)
        activity_lb = filter_to_members(activity_lb, current_members)
        print(f"After member filter: {len(monetary_lb)} monetary, {len(activity_lb)} activity entries.")

    monetary_lb = monetary_lb[:LEADERBOARD_LIMIT]
    activity_lb = activity_lb[:LEADERBOARD_LIMIT]
    print(f"Leaderboard limit: top {LEADERBOARD_LIMIT}.")

    out = {
        "updated_at": data.get("updated_at"),
        "total_entries": len(entries),
        "retention_days": RETENTION_DAYS,
        "leaderboard_limit": LEADERBOARD_LIMIT,
        "monetary_leaderboard": monetary_lb,
        "activity_leaderboard": activity_lb,
        "activity_scoring": ACTIVITY_POINTS,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Monetary leaderboard — {len(monetary_lb)} members:")
    for e in monetary_lb[:5]:
        print(f"  #{e['rank']} {e['user']}: {e['monetary_score']:.2f}g")

    print(f"Activity leaderboard — {len(activity_lb)} members:")
    for e in activity_lb[:5]:
        print(f"  #{e['rank']} {e['user']}: {e['activity_score']} pts")


if __name__ == "__main__":
    main()
