# GW2 Guild Leaderboard

A GitHub Pages site that tracks guild member contributions using the Guild Wars 2 API.
Updated automatically every day via GitHub Actions.

## Setup

### 1. Repository secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `GW2_API_KEY` | Guild leader's GW2 API key (scope: `guilds`) |
| `GW2_GUILD_ID` | Your guild's UUID (see below) |

#### Finding your guild ID

Search by exact guild name (no API key required):

```bash
curl "https://api.guildwars2.com/v2/guild/search?name=Your+Guild+Name"
# ["xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"]
```

Or list all guilds your API key has leader access to:

```bash
export GW2_API_KEY="your-api-key-here"

curl -H "Authorization: Bearer $GW2_API_KEY" \
  "https://api.guildwars2.com/v2/account"
# Look for the "guilds" and "guild_leader" arrays in the response
```

Then fetch the guild name to confirm the right ID:

```bash
curl -H "Authorization: Bearer $GW2_API_KEY" \
  "https://api.guildwars2.com/v2/guild/YOUR_GUILD_ID"
# {"id":"...","name":"Your Guild Name", ...}
```

### 2. Enable GitHub Pages

Go to **Settings → Pages** and set the source to **GitHub Actions**.

### 3. First run

Trigger the workflow manually from **Actions → Update GW2 Leaderboard → Run workflow**.
This fetches the initial log snapshot and deploys the leaderboard.

After that, it runs automatically every day at 06:00 UTC.

## How it works

```
GitHub Actions (daily cron)
  → fetch_log.py      reads last_id from data/guild_log.json
                      fetches ?since=last_id from GW2 API
                      appends new entries, updates last_id
  → compute_scores.py reads all entries, computes per-member scores
                      writes data/leaderboard.json
  → git commit & push
  → GitHub Pages serves index.html which fetches data/leaderboard.json
```

## Scoring (POC)

| Action | Points |
|--------|--------|
| Treasury deposit | +10 |
| Stash deposit | +5 |
| Stash withdrawal | -2 |
| Upgrade queued | +15 |
| Mission started | +20 |
| Member invited | +5 |

Adjust weights in `scripts/compute_scores.py`.
