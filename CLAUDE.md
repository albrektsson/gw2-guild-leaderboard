# GW2 Guild Leaderboard — Claude Context

This file gives Claude CLI the context needed to resume work on this project without re-explaining anything.

## What this project does

A zero-infrastructure guild leaderboard for Guild Wars 2. GitHub Actions polls the GW2 guild log API daily, accumulates events into a committed JSON file (the "database"), computes per-member contribution scores, and serves everything as a static GitHub Pages site.

## Architecture

```
GitHub Actions (daily cron: 06:00 UTC)
  → scripts/fetch_log.py
      reads  data/guild_log.json → extracts last_id cursor
      calls  GET /v2/guild/{id}/log?since={last_id}
      writes data/guild_log.json (appends new entries, updates last_id)
  → scripts/compute_scores.py
      reads  data/guild_log.json
      writes data/leaderboard.json (ranked members + scoring metadata)
  → git commit && git push
  → GitHub Pages auto-serves index.html, which fetches data/leaderboard.json at runtime
```

Persistence model: **the repo is the database**. `data/guild_log.json` accumulates all historical entries. The `last_id` field is the polling cursor — every run fetches only events newer than this ID.

## File map

| File | Purpose |
|------|---------|
| `index.html` | GitHub Pages frontend — loads `data/leaderboard.json` via `fetch()`, renders ranked table |
| `scripts/fetch_log.py` | Fetches new GW2 log entries, merges into `data/guild_log.json` |
| `scripts/compute_scores.py` | Reads log entries, outputs `data/leaderboard.json` |
| `.github/workflows/update.yml` | Daily cron workflow; also supports `workflow_dispatch` for manual runs |
| `data/guild_log.json` | Persisted log store — **committed to repo**, never gitignored |
| `data/leaderboard.json` | Computed scores — **committed to repo**, served directly to the frontend |

## GW2 API details

- **Endpoint:** `GET https://api.guildwars2.com/v2/guild/{guild_id}/log`
- **Auth:** `Authorization: Bearer {api_key}` — must be the **guild leader's** API key with `guilds` scope
- **Pagination:** `?since={id}` — returns only entries with id > since. No backward pagination.
- **Limit:** ~100 events per type per response. Daily polling is sufficient for normal guild activity.
- **Required secrets:** `GW2_GUILD_ID`, `GW2_API_KEY` (set in GitHub repo Settings → Secrets → Actions)

### Log event types and fields

| type | Relevant fields | Currently tracked |
|------|----------------|-------------------|
| `treasury` | `user`, `item_id`, `count` | ✅ deposit count |
| `stash` | `user`, `operation` (deposit/withdraw), `item_id`, `count` | ✅ deposit/withdrawal count |
| `upgrade` | `user`, `action` (queued/completed/cancelled), `upgrade_id` | ✅ queued count |
| `mission` | `user` (only on start), `state` (start/success/fail/cancel), `influence` | ✅ started count |
| `invited` | `user` (invitee), `invited_by` | ✅ invites sent |
| `joined` | `user` | ❌ not yet tracked |
| `kick` | `user`, `kicked_by` | ❌ not yet tracked |
| `rank_change` | `user`, `changed_by`, `old_rank`, `new_rank` | ❌ not yet tracked |
| `motd` | `user` | ❌ not yet tracked |
| `gifted` / `daily_login` | `participants`, `total_participants` | ❌ legacy influence, not yet tracked |

## Current scoring weights

Defined in `scripts/compute_scores.py` in the `POINTS` dict:

```python
POINTS = {
    "treasury_deposit": 10,
    "stash_deposit":     5,
    "stash_withdrawal": -2,
    "upgrade_queued":   15,
    "mission_started":  20,
    "invited":           5,
}
```

## Data schemas

### data/guild_log.json
```json
{
  "last_id": 4821,
  "updated_at": "2026-02-21T06:00:00Z",
  "entries": [
    {
      "id": 4821,
      "time": "2026-02-21T05:30:00Z",
      "type": "treasury",
      "user": "SomeMember.1234",
      "item_id": 19721,
      "count": 250
    }
  ]
}
```

### data/leaderboard.json
```json
{
  "updated_at": "2026-02-21T06:00:00Z",
  "total_entries": 312,
  "scoring": { "treasury_deposit": 10, "...": "..." },
  "leaderboard": [
    {
      "rank": 1,
      "user": "SomeMember.1234",
      "score": 420,
      "treasury_deposits": 12,
      "stash_deposits": 8,
      "stash_withdrawals": 2,
      "upgrades_queued": 3,
      "missions_started": 5,
      "invites_sent": 1,
      "last_active": "2026-02-21T05:30:00Z"
    }
  ]
}
```

## Planned / suggested next steps

These were discussed but not yet implemented. Pick up from any of these:

### Higher priority
- **Item value weighting for treasury/stash** — cross-reference deposited `item_id` with `GET /v2/commerce/prices` to weight contributions by gold value instead of flat count. This is the biggest scoring quality improvement.
- **`gifted` / `daily_login` influence tracking** — these events have a `participants` array of account names; currently ignored.
- **Track `joined` events** — useful for measuring member retention alongside `invited`.

### Medium priority
- **Weekly/monthly leaderboard views** — filter `entries` by `time` field on the compute side and expose multiple timeframe views in `leaderboard.json`.
- **Per-member detail pages** — currently the frontend shows aggregate stats only. Could add a drilldown showing a member's activity timeline.
- **Rank history** — store a daily snapshot of rankings to show rank movement over time (up/down arrows).

### Lower priority / nice-to-have
- **`/v2/guild/:id/members`** integration — cross-reference log users with current member list to flag contributions from members who have since left.
- **Upgrade name resolution** — `upgrade_id` can be resolved via `GET /v2/guild/upgrades` to show what was built, not just a count.
- **Frontend improvements** — search/filter by member name, sortable columns, mobile layout improvements.

## Local dev / testing

```bash
# Install dependency
pip install requests

# Set env vars locally
export GW2_GUILD_ID="your-guild-uuid"
export GW2_API_KEY="your-leader-api-key"

# Run the pipeline manually
python scripts/fetch_log.py
python scripts/compute_scores.py

# Preview the page locally
python -m http.server 8080
# then open http://localhost:8080
```

To test scoring logic without a real API key, write fake entries directly into `data/guild_log.json` (see the schema above) and run `compute_scores.py` directly — it doesn't need credentials.
