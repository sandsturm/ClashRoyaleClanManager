# Clash Royale Clan Manager

## Overview

A short script that computes statistics based on Clan Wars II weekly performance for a clan in Clash Royale.

Requires:
1. the clan's tag (starting with #). Can be found (for example) here: https://royaleapi.com/?lang=en 
2. a token from supercell's API for Clash Royale: https://developer.clashroyale.com/#/
   the token can be associated with a number of IPs

Computes:
1. average war rank
2. weekly war champ (member with the most fame in the past war)

3. promotion/demotion/warning/kick lists to which members are added with the following rules:
    - promotion rule: two consecutive weeks of at least 1600 fame in war
    - demotion rule (elders): less than 1600 for two consecutive weeks 
    - warning rule: less than losing all attacks in 3/4 days in the last war 
    - kick rule: total score for two consecutive weeks is less than 2800. The thresshold can be achieved by losing all attacks in 3/4 (1200) and 4/4 (1600) days.

Decisions on clan updates can be made according to the four lists. The script also prints a full war history for all members in the kick list.

## Clan Management Rules

Promotion, demotion, warning, and kick recommendations are controlled through the `rules` section of `config.json`.

| Rule | Default | Description |
|---|---|---|
| Promotion | 1,600 fame per week, 2 consecutive weeks | Recommend promoting a member to elder |
| Demotion | Below 1,600 fame per week, 2 consecutive weeks | Recommend demoting an elder |
| Warning | Below 1,200 fame in the latest war | Recommend warning a player |
| Kick | Below 2,800 total fame across 2 consecutive weeks | Recommend removing a member |

Thresholds and the number of consecutive weeks can be adjusted independently.

**Insufficient data:** Recommendations requiring multiple weeks are generated only when all required war records are available for the player. Missing participation records are not automatically treated as zero fame.

These recommendations are informational only. The script does not automatically change clan membership or roles.

The application evaluates completed war history returned by the Clash Royale API and does not independently verify whether a participant deliberately skipped an attack.


Feel free to update the rules according to your preferences!

## Requirements

- Python 3.10 or newer
- A Clash Royale API token from [Supercell Developer Portal](https://developer.clashroyale.com/)
- Python dependencies listed in `requirements.txt`

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

3. Install the required dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Configure the Clash Royale API token and clan tag as described in the configuration instructions.

5. Run the script:

   ```bash
   python ClashRoyaleClanManager.py
   ```

## Configuration

Before running the application, create a local configuration file from the provided template:

```bash
cp config.example.json config.json
```

Edit `config.json` and enter your Clash Royale clan tag and API token:

```json
{
    "clan_tag": "#YOUR_CLAN_TAG",
    "api_token": "YOUR_API_TOKEN"
}
```

You can obtain an API token from the [Supercell Developer Portal](https://developer.clashroyale.com/).

The application automatically reads the configuration file at startup. No interactive input is required.

**Security:** The `config.json` file contains your private API token and is excluded from Git through `.gitignore`. Never commit or share this file. Only `config.example.json`, containing placeholder values, should be committed.

## Generated Data

The script automatically creates a `logs/` directory to store downloaded Clash Royale API data, including `members.json` and `riverracelog.json`.

The entire `logs/` directory is excluded from Git through `.gitignore`. Its contents are stored locally and are not committed to the repository.

When using cached data, the corresponding JSON files must already exist.
