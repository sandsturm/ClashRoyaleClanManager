# Clash Royale Clan Manager

A Python tool for managing Clash Royale clans through war performance tracking, participation analysis, and configurable promotion, demotion, warning, and kick recommendations.

## Overview

Clash Royale Clan Manager uses the official [Clash Royale API](https://developer.clashroyale.com/) to retrieve clan membership and Clan Wars II history.

The application provides:

- **Average war rank:** Average clan ranking across available historical wars.
- **Weekly war champion:** The player with the highest fame in the latest evaluated war.
- **Promotion recommendations:** Identify members who qualify for promotion to elder.
- **Demotion recommendations:** Identify elders who no longer meet the clan's requirements.
- **Kick recommendations:** Identify members who fail to meet minimum activity or performance requirements.
- **Warning recommendations:** Identify players who should receive a warning.
- **Historical data:** Store downloaded war results locally for further analysis.

Clan management recommendations are based on configurable rules. The script does not automatically promote, demote, or kick players. All decisions remain with the clan leadership.

## Requirements

- Python 3.10 or newer
- A Clash Royale API token from the [Supercell Developer Portal](https://developer.clashroyale.com/)
- Python dependencies listed in `requirements.txt`

You will also need your clan tag (starting with `#`), which can be found in Clash Royale or on [RoyaleAPI](https://royaleapi.com/).

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/sandsturm/ClashRoyaleClanManager.git
   cd ClashRoyaleClanManager
   ```

2. Create and activate a Python virtual environment (recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   On Windows, activate the environment using:

   ```powershell
   .venv\Scripts\activate
   ```

3. Install the required dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Create and configure your local `config.json` file as described below.

5. Run the script:

   ```bash
   python ClashRoyaleClanManager.py
   ```

## Configuration

Create a local configuration file from the provided template:

```bash
cp config.example.json config.json
```

Open `config.json` and replace the placeholder values with your clan tag and Clash Royale API token:

```json
{
    "clan_tag": "#YOUR_CLAN_TAG",
    "api_token": "YOUR_API_TOKEN",
    "rules": {
        "...": "See the rule configuration below"
    }
}
```

Keep the complete `rules` section from `config.example.json` and adjust the settings to your clan's preferences.

The application automatically reads the configuration file at startup. No interactive input is required.

**Security:** The `config.json` file contains your private API token and is excluded from Git through `.gitignore`. Never commit or share this file. Only `config.example.json`, containing placeholder values, should be committed.

API tokens are subject to the IP address restrictions configured in the Supercell Developer Portal.

## Clan Management Rules

Every clan manages its members differently. Some prioritize war participation, while others focus on the points earned during clan wars.

Clash Royale Clan Manager is designed to support both approaches through configurable rules.

### Rule Strategies

Each management action (promotion, demotion, warning, or kick) can use one of three strategies:

| Strategy | Description |
|---|---|
| `fame` | Evaluates players based on the points earned during clan wars. |
| `participation` | Evaluates whether players participated in consecutive clan wars. |
| `combined` | Combines fame and participation requirements using AND or OR logic. |

Strategies can be selected independently for each management action.

For example, a clan could promote players based on participation while kicking players who fail to meet a minimum fame threshold.

### Default Clan Rules

The example configuration uses the following rules:

| Action | Applies to | Requirement |
|---|---|---|
| Promotion | Members | Participate in 10 consecutive clan wars |
| Demotion | Elders | Miss 2 consecutive clan wars |
| Kick | Members | Miss the latest clan war OR earn fewer than 600 fame |
| Warning | Members | Disabled by default |

**Promotion:** Members who participate in ten consecutive clan wars qualify for promotion to elder. The number of points earned does not matter.

**Demotion:** Elders who fail to participate in two consecutive clan wars qualify for demotion to member. Poor performance alone does not trigger demotion.

**Kick:** Members who do not participate in the most recent clan war, or who earn fewer than 600 fame, qualify for a kick recommendation. Elders are explicitly excluded.

**Warning:** Warning recommendations are disabled in the default configuration but can be enabled and configured if required.

These rules are examples and can be adjusted independently to match your clan's management policies.

### Configuring Rules

Each management action has its own configuration in the `rules` section of `config.json`.

For example, the default promotion rule is:

```json
"promotion": {
    "enabled": true,
    "strategy": "participation",
    "roles": ["member"],
    "participation": {
        "consecutive_wars": 10
    },
    "fame": {
        "minimum_fame_per_week": 1600,
        "consecutive_wars": 2
    }
}
```

This configuration means:

- The promotion rule is enabled.
- Only players with the `member` role are evaluated.
- Players must participate in ten consecutive clan wars to qualify.
- The alternative fame-based rule is retained but inactive.

To use fame-based promotions instead, change:

```json
"strategy": "fame"
```

With that strategy, members must earn at least 1,600 fame in each of two consecutive wars.

### Combining Rules

The `combined` strategy evaluates both participation and fame.

For example, the default kick rule uses:

```json
"kick": {
    "enabled": true,
    "strategy": "combined",
    "roles": ["member"],
    "operator": "OR",
    "participation": {
        "consecutive_missed_wars": 1
    },
    "fame": {
        "minimum_total_fame": 600,
        "last_wars": 1
    }
}
```

The `OR` operator means a member qualifies for a kick recommendation when either condition is met:

- The member missed the latest clan war.
- The member earned fewer than 600 fame in the latest clan war.

Changing the operator to `AND` requires both conditions to be met.

### Insufficient Historical Data

Some rules require multiple consecutive wars to determine whether a player qualifies.

The application should only generate recommendations when sufficient reliable historical data is available.

Missing participation records must not automatically be interpreted as missed wars. This is particularly important for members who recently joined the clan.

All recommendations are advisory and should be reviewed by clan leadership.

## Generated Data

The script automatically creates a `logs/` directory to store downloaded Clash Royale API data, including:

- `members.json` — Current clan membership information.
- `riverracelog.json` — Historical clan war results.
- `clan-log.json` — Processed clan war history.

The entire `logs/` directory is excluded from Git through `.gitignore`. Its contents are stored locally and are not committed to the repository.

When using cached data, the corresponding JSON files must already exist.

## Development Status

The configuration structure supports three rule strategies: `fame`, `participation`, and `combined`.

**The evaluation engine is currently being extended to implement these strategies.** Until that implementation is completed, the existing fame-based evaluation remains the supported behavior.

Further improvements will focus on:

- Reliable detection of war participation and inactivity.
- Configurable rule evaluation.
- Handling incomplete historical data.
- Automated tests for management rules.
- Improved clan performance reporting.

## Disclaimer

This project is an independent community tool and is not affiliated with, endorsed by, or sponsored by Supercell.

Clash Royale and Supercell are trademarks of Supercell Oy.