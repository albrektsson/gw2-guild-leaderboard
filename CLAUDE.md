# GW2 Guild Leaderboard — Claude Context

Zero-infrastructure guild leaderboard for Guild Wars 2. GitHub Actions polls the GW2 API daily, commits JSON data to the repo (the "database"), and deploys a static GitHub Pages site.

## Architecture

```
GitHub Actions (workflow_dispatch + daily cron: 06:00 UTC)
  → scripts/fetch_log.py
      fetches GET /v2/guild/{id}/log?since={last_id}
      fetches GET /v2/guild/{id}/members
      writes  data/guild_log.json   (appends entries, trims if retention_days set)
      writes  data/guild_members.json (current member snapshot)
  → scripts/compute_scores.py
      reads   data/guild_log.json + data/guild_members.json + config.json
      fetches /v2/commerce/prices and /v2/items for all item_ids
      writes  data/leaderboard.json   (two ranked boards)
      writes  data/item_names.json    (item_id → name)
      writes  data/item_prices.json   (item_id → price in copper)
  → git commit && git push
  → GitHub Pages deploys via actions/deploy-pages
```

## File map

| File | Purpose |
|------|---------|
| `index.html` | Frontend — two-tab leaderboard (Monetary / Activity), member detail modal |
| `scripts/fetch_log.py` | Fetches log entries + current members, writes data files |
| `scripts/compute_scores.py` | Computes scores, fetches item prices/names, writes output files |
| `config.json` | User-editable settings: `retention_days`, `leaderboard_limit` |
| `.github/workflows/update.yml` | CI pipeline — fetch → compute → commit → deploy |
| `data/guild_log.json` | Accumulated log entries with `last_id` cursor |
| `data/guild_members.json` | Current guild member snapshot (refreshed every run) |
| `data/leaderboard.json` | Computed output served to frontend |
| `data/item_names.json` | Item ID → name lookup for modal timeline |
| `data/item_prices.json` | Item ID → copper price lookup for modal timeline |

## Leaderboards

Two separate ranked lists in `leaderboard.json`:

**monetary_leaderboard** — ranked by gold value contributed via treasury/stash deposits (net of withdrawals). Each item priced at TP sell price, falling back to vendor value for untradeable items.

**activity_leaderboard** — ranked by flat activity points:

```python
ACTIVITY_POINTS = {
    "upgrade_queued":   15,
    "mission_started":   5,
    "invited":           5,
    "invite_accepted":   5,  # credited to inviter when recruit joins
    "daily_login":       1,  # per influence/daily_login participation
}
```

Both boards are filtered to current guild members only (ex-members excluded).

## Data schemas

### data/guild_log.json
```json
{
  "last_id": 9794,
  "updated_at": "2026-02-21T06:00:00Z",
  "entries": [
    { "id": 9794, "time": "...", "type": "treasury", "user": "Player.1234", "item_id": 43319, "count": 250 }
  ]
}
```

### data/leaderboard.json
```json
{
  "updated_at": "...",
  "total_entries": 312,
  "retention_days": null,
  "leaderboard_limit": 20,
  "monetary_leaderboard": [
    { "rank": 1, "user": "Player.1234", "monetary_score": 125.50,
      "treasury_value": 80.25, "stash_value_deposited": 55.00, "stash_value_withdrawn": 9.75,
      "last_active": "..." }
  ],
  "activity_leaderboard": [
    { "rank": 1, "user": "Player.1234", "activity_score": 85,
      "upgrades_queued": 3, "missions_started": 2, "invites_sent": 5,
      "invites_accepted": 4, "daily_login_participations": 12, "last_active": "..." }
  ],
  "activity_scoring": { "upgrade_queued": 15, "..." : "..." }
}
```

## GW2 API

- **Guild log:** `GET /v2/guild/{id}/log?since={last_id}` — requires guild leader key with `guilds` scope
- **Members:** `GET /v2/guild/{id}/members` — same auth
- **Item prices:** `GET /v2/commerce/prices?ids=...` — public, bulk up to 200
- **Item details:** `GET /v2/items?ids=...` — public, bulk up to 200

### Tracked log event types

| type | Tracked | Notes |
|------|---------|-------|
| `treasury` | ✅ monetary | item_id + count → gold value |
| `stash` | ✅ monetary | deposit/withdraw, item_id + count + coins → gold value |
| `upgrade` | ✅ activity | action == "queued" only |
| `mission` | ✅ activity | state == "start" only |
| `invited` | ✅ activity | credits invited_by |
| `joined` | ✅ activity | credits original inviter via invite_map |
| `influence` | ✅ activity | activity == "daily_login", credits each participant |
| `kick` | ❌ | not tracked |
| `rank_change` | ❌ | not tracked |
| `motd` | ❌ | not tracked |

## Frontend

- Two tabs: **Monetary** (gold values) and **Activity** (flat points)
- Click any member row → modal showing their full log timeline
- Modal lazy-fetches `guild_log.json`, `item_names.json`, `item_prices.json` (cached after first open)
- Each timeline entry shows item name, count, and gold value where applicable

## Configuration (config.json)

```json
{
  "retention_days": null,
  "leaderboard_limit": 20
}
```

`retention_days` trims `guild_log.json` entries older than N days on each fetch run. The `last_id` cursor is preserved so trimming never causes re-fetching. Git history retains all data.

## Local dev

```bash
pip install requests
export GW2_GUILD_ID="your-guild-uuid"
export GW2_API_KEY="your-leader-api-key"
python scripts/fetch_log.py
python scripts/compute_scores.py
python -m http.server 8080
```

To test scoring without credentials, write fake entries into `data/guild_log.json` and run `compute_scores.py` directly — it only needs the API for item prices.
