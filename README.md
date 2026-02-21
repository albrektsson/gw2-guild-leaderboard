# GW2 Guild Leaderboard

A static GitHub Pages leaderboard for Guild Wars 2 guild contributions. GitHub Actions polls the GW2 API daily, commits the data to the repo, and deploys the site automatically.

## Setup

**1. Repository secrets** — Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `GW2_API_KEY` | Guild leader's API key (scope: `guilds`) |
| `GW2_GUILD_ID` | Your guild's UUID |

**Finding your guild ID:**

```bash
export GW2_API_KEY="your-api-key-here"

# Search by name (no key required)
curl "https://api.guildwars2.com/v2/guild/search?name=Your+Guild+Name"

# List guilds you lead
curl -H "Authorization: Bearer $GW2_API_KEY" "https://api.guildwars2.com/v2/account"

# Confirm the right ID
curl -H "Authorization: Bearer $GW2_API_KEY" "https://api.guildwars2.com/v2/guild/YOUR_GUILD_ID"
```

**2. Enable GitHub Pages** — Settings → Pages → Source: **GitHub Actions**

**3. First run** — Actions → Update GW2 Leaderboard → Run workflow

## Configuration

Edit `config.json` at the repo root:

```json
{
  "retention_days": null,
  "leaderboard_limit": 20
}
```

- `retention_days` — only count contributions from the last N days (`null` = all-time). Old entries are trimmed from `guild_log.json` automatically; history is preserved in git.
- `leaderboard_limit` — max members shown per board.

## Local dev

```bash
pip install requests

export GW2_GUILD_ID="your-guild-uuid"
export GW2_API_KEY="your-leader-api-key"

python scripts/fetch_log.py
python scripts/compute_scores.py

python -m http.server 8080
```
