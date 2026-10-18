# Clash Royale Clan Manager

A Python tool for tracking Clash Royale clan wars, monitoring donations, and generating configurable promotion, demotion, warning, and kick recommendations.

## Overview

The application uses the official [Clash Royale API](https://developer.clashroyale.com/) to retrieve current clan members, completed river races, and the current river race.

It reports:

- Average clan rank across available completed wars.
- Weekly war champion(s), based on fame in the latest completed war.
- Promotion, demotion, warning, and kick recommendations based on configurable rules.
- Live fame and deck usage during the current river race.
- Current donations, a donation ranking, and locally collected donation snapshots.

**Recommendations are advisory only.** The script never automatically changes clan roles or removes players.

## Requirements

- Python 3.10 or newer.
- An API token from the [Supercell Developer Portal](https://developer.clashroyale.com/), authorized for your IP address.
- Your clan tag (beginning with `#`), which you can find in the game or on [RoyaleAPI](https://royaleapi.com/).
- Dependencies listed in `requirements.txt`.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/sandsturm/ClashRoyaleClanManager.git
   cd ClashRoyaleClanManager
   ```

2. Create and activate a virtual environment (recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   On Windows, activate it with `.venv\Scripts\activate`.

3. Install the dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Configure the clan tag, API token, and rules as described below.

5. Run the application:

   ```bash
   python ClashRoyaleClanManager.py
   ```

## Configuration

Copy the example configuration and edit your local file:

```bash
cp config.example.json config.json
```

Replace the placeholder `clan_tag` and `api_token` values with your own. Keep the complete `rules` section from `config.example.json`; it controls how each recommendation is calculated. For example:

```json
{
  "clan_tag": "#YOUR_CLAN_TAG",
  "api_token": "YOUR_API_TOKEN",
  "rules": {
    "...": "Use the full rules object from config.example.json"
  }
}
```

This abbreviated example is illustrative, **not** a complete usable configuration.

**Security:** `config.json` includes your private API token and must remain excluded from Git using `.gitignore`. Only commit `config.example.json` with placeholder credentials. If a real token has been committed publicly, revoke it and create a replacement.

## Clan management rules

Each action (promotion, demotion, kick, warning) can be enabled or disabled and can use an independent strategy:

| Strategy | Meaning |
| --- | --- |
| `fame` | Evaluate points earned in clan wars. |
| `participation` | Evaluate whether a player used war decks in consecutive wars. |
| `combined` | Combine participation and fame conditions using `AND` or `OR`. |

The provided example configuration reflects these clan policies:

| Action | Eligible players | Rule |
| --- | --- | --- |
| **Promotion** | Members | Participate in **10 consecutive completed wars**. |
| **Demotion** | Elders | Miss **2 consecutive completed wars**. |
| **Kick** | Members only | During an active war day: **0 participation OR fewer than 600 fame** in the current war. |
| **Warning** | Members | Disabled by default. |

For example, the kick rule can be expressed as:

```json
"kick": {
  "enabled": true,
  "strategy": "combined",
  "roles": ["member"],
  "operator": "OR",
  "participation": { "consecutive_missed_wars": 1 },
  "fame": { "minimum_total_fame": 600, "last_wars": 1 }
}
```

The full example configuration also retains inactive fame-based alternatives for promotion and demotion. Changing a strategy activates the corresponding settings without changing Python code.

### What “Insufficient data” means

The rule engine uses three evaluation results: **qualifies**, **does not qualify**, and **unknown** (`null` in JSON). An unknown result is printed as *Insufficient data* and is **not** a recommendation to take action.

This can happen when there are too few historical wars, a player is missing from a required participant list, or the necessary fame/deck information is absent. A missing player record is **not automatically treated as zero participation**, because that player may have joined recently.

## Current river race and Monday reviews

The application retrieves both completed history (`/riverracelog`) and the live race (`/currentriverrace`). They are used differently.

**Monday morning — kick review:** If the current race reports `periodType: "warDay"`, **kick recommendations use the live current-race snapshot**. Members with zero decks used or fewer than 600 fame meet the configured default kick rule; elders and leaders are excluded. These recommendations can change before the war ends, so run a **fresh API fetch** before reviewing them.

**Monday afternoon — promotion/demotion review:** Once a war has finished and is available in `/riverracelog`, promotion and demotion use the **completed war history**. The ongoing race never counts toward their consecutive-war requirements. Run the script again after the API has updated the completed history.

Outside `warDay`, kick evaluation falls back to completed-war history. The decision is based on the API's `periodType`, not the local day or clock.

Live race reporting also prints each current member's fame and decks used. For example:

```text
Current river race (live snapshot; warDay):
  Used for kick evaluations only; promotions/demotions use completed wars.
  player1 (#LLLLLL10C): 2250 fame, 15 decks used
  illyrian (#Y8PLCIJ"J): 0 fame, 0 decks used
```

*Illustrative values.* If a current player has no participant record, that player's activity is classified as unknown rather than assumed to be zero.

**Caution:** A live kick result is a pre-close recommendation, not a final war result. An API delay or incomplete participant history should be reviewed before a player is removed.

## Donation tracking

Donation tracking is **informational** and does not currently affect promotion, demotion, warning, or kick decisions. It is intended to support future leadership and co-leader reviews.

The script reads `donations` and `donationsReceived` from the current clan-members API response. Optionally, it records timestamped snapshots in `logs/donations-history.json`, indexed by player tag.

Add a top-level `donations` section to `config.json`:

```json
"donations": {
  "enabled": true,
  "tracking": { "enabled": true },
  "evaluation": {
    "enabled": false,
    "co_leader": {
      "minimum_average_weekly_donations": 200,
      "minimum_weeks_observed": 8
    }
  }
}
```

The co-leader settings above are **reserved for a future feature**; no automated co-leader assessment is implemented yet. The values are illustrative, not enforced thresholds.

Snapshots are saved **only after a fresh API fetch** when tracking is enabled. Cached runs do not add a new observation. Donation counters can reset; the engine detects decreases across recorded observations, but it does **not** yet calculate reliable full-week donation totals or averages. Regular data collection will be necessary before historical donation-based evaluation is meaningful.

## Running the script

Fetch fresh API data and update donation tracking:

```bash
python ClashRoyaleClanManager.py
```

Use locally saved responses without calling the API:

```bash
python ClashRoyaleClanManager.py --cached
```

**Use a fresh run for Monday decisions.** `--cached` may contain stale current-race data and should be used primarily for debugging or repeatable analysis.

Cached mode supports older caches without `currentriverrace.json`: it prints that the live snapshot is unavailable and continues using completed-war data.

## Generated data

The script creates a local `logs/` directory for downloaded API responses and derived reports:

| File | Purpose |
| --- | --- |
| `members.json` | Current clan member data and donation counters. |
| `riverracelog.json` | Completed clan war history. |
| `currentriverrace.json` | Most recently fetched live river race. |
| `clan-log.json` | Calculated recommendations and player war histories. |
| `donations-history.json` | Timestamped donation snapshots when enabled. |

The entire `logs/` directory should be ignored by Git. Cached mode generally requires the saved member and completed-war files; the current-race cache is optional.

## Development and testing

The rules are evaluated by `rule_engine.py`, while `ClashRoyaleClanManager.py` handles API access, caching, reporting, and donation snapshots.

Run the automated tests with:

```bash
python -m unittest discover -s tests -v
```

Before acting on recommendations, consider the limitations of historical membership data: the API does not necessarily show whether someone was a member during every past race. The tool intentionally treats missing records as unknown.

## Disclaimer

This is an independent community project and is not affiliated with, endorsed by, or sponsored by Supercell. Clash Royale and Supercell are trademarks of Supercell Oy.
