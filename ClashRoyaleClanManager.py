# Clash Royale Clan Manager
# computes promotion/demotion/kick/warning lists, average war rank, and weekly war champ according to clan wars II statistics
# uses data from Supercell's Clash Royale API

import json
import requests
import statistics

from pathlib import Path

# Create logs directory if it does not exist
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Load configuration
CONFIG_FILE = BASE_DIR / "config.json"


def data_fetcher(clan_tag, token, category):
    # fetches data from API for a given category
    # categories: currentriverrace, riverracelog, warlog, members, members?limit=50, empty input for clan info etc
    
    myheaders = {} 
    myheaders['Accept'] = 'application/json'
    myheaders['authorization'] = 'Bearer '+token

    clan_tag_for_url = '%23' + clan_tag[1:]  # replace # with %23 for the http get request        
    url = "https://api.clashroyale.com/v1/clans/" + clan_tag_for_url + '/' + category

    response = requests.request("GET", url, headers=myheaders)

    return response.json()



def ClashRoyaleClanManager(clan_tag, token, data_fetched, rules):
    """Evaluate clan war performance and recommend role changes."""

    # Load previously fetched data or fetch fresh data.
    if data_fetched:
        with (LOG_DIR / "members.json").open(
            "r", encoding="utf-8"
        ) as infile:
            members = json.load(infile)

        with (LOG_DIR / "riverracelog.json").open(
            "r", encoding="utf-8"
        ) as infile:
            riverracelog = json.load(infile)
    else:
        print("Fetching members data...")
        members = data_fetcher(clan_tag, token, "members")

        with (LOG_DIR / "members.json").open(
            "w", encoding="utf-8"
        ) as outfile:
            json.dump(members, outfile)

        print("Fetching riverracelog data...")
        riverracelog = data_fetcher(
            clan_tag, token, "riverracelog"
        )

        with (LOG_DIR / "riverracelog.json").open(
            "w", encoding="utf-8"
        ) as outfile:
            json.dump(riverracelog, outfile)

    # Initialize result lists.
    promotion_list = []
    demotion_list = []
    kick_list = []
    warning_list = []
    week_champ = None

    # Initialize clan history, indexed by player tag.
    member_items = members.get("items", [])
    clan_log = {"ranks": []}

    for member in member_items:
        clan_log[member["tag"]] = {
            "name": member["name"],
            "role": member["role"],
            "fame": {}
        }

    # Order war history chronologically using integer tuples.
    weeks = sorted(
        riverracelog.get("items", []),
        key=lambda week: (
            int(week["seasonId"]),
            int(week["sectionIndex"])
        ),
        reverse=True
    )

    # Build clan history, ignoring weeks without our clan.
    valid_races = []

    for war_week in weeks:
        clan_data = next(
            (
                entry
                for entry in war_week.get("standings", [])
                if entry.get("clan", {}).get("tag") == clan_tag
            ),
            None
        )

        if clan_data is None:
            continue

        week_id = (
            f"{war_week['seasonId']}:"
            f"{war_week['sectionIndex']}"
        )
        valid_races.append(week_id)

        if clan_data.get("rank") is not None:
            clan_log["ranks"].append(clan_data["rank"])

        for participant in clan_data["clan"].get(
            "participants", []
        ):
            tag = participant["tag"]

            if tag in clan_log:
                clan_log[tag]["fame"][week_id] = (
                    participant["fame"]
                )

    # Report average rank.
    if clan_log["ranks"]:
        print(
            "Average war rank: "
            f"{statistics.mean(clan_log['ranks']):.2f}"
        )
    else:
        print("Average war rank: No data available.")

    # Calculate weekly champion.
    if valid_races:
        last_race = valid_races[0]

        week_fame = [
            (player["name"], player["fame"][last_race])
            for tag, player in clan_log.items()
            if tag != "ranks"
            and last_race in player["fame"]
        ]

        if week_fame:
            max_score = max(score for _, score in week_fame)

            champions = [
                entry
                for entry in week_fame
                if entry[1] == max_score
            ]

            week_champ = (
                champions[0]
                if len(champions) == 1
                else champions
            )
        else:
            print("No eligible players for weekly champion.")
    else:
        print("No valid clan war history available.")

    # Evaluate configurable management rules.
    if valid_races:
        promotion_rules = rules["promotion"]
        demotion_rules = rules["demotion"]
        warning_rules = rules["warning"]
        kick_rules = rules["kick"]

        promotion_weeks = promotion_rules["consecutive_weeks"]
        demotion_weeks = demotion_rules["consecutive_weeks"]
        kick_weeks = kick_rules["consecutive_weeks"]

        for tag, player in clan_log.items():
            if tag == "ranks":
                continue

            name = player["name"]
            role = player["role"]
            fame = player["fame"]

            # Warning: evaluate the most recent war.
            if valid_races[0] in fame:
                latest_score = fame[valid_races[0]]

                if latest_score < warning_rules["below_fame"]:
                    warning_list.append(
                        (name, role, latest_score)
                    )

            # Promotion: all required weeks must be present.
            if role == "member":
                recent = valid_races[:promotion_weeks]

                if (
                    len(recent) == promotion_weeks
                    and all(week in fame for week in recent)
                    and all(
                        fame[week] >= promotion_rules[
                            "minimum_fame_per_week"
                        ]
                        for week in recent
                    )
                ):
                    promotion_list.append(
                        (name, role, *(fame[w] for w in recent))
                    )

            # Demotion: elders only.
            if role == "elder":
                recent = valid_races[:demotion_weeks]

                if (
                    len(recent) == demotion_weeks
                    and all(week in fame for week in recent)
                    and all(
                        fame[week] < demotion_rules[
                            "below_fame_per_week"
                        ]
                        for week in recent
                    )
                ):
                    demotion_list.append(
                        (name, role, *(fame[w] for w in recent))
                    )

            # Kick: members only.
            if role == "member":
                recent = valid_races[:kick_weeks]

                if (
                    len(recent) == kick_weeks
                    and all(week in fame for week in recent)
                    and sum(fame[w] for w in recent)
                    < kick_rules["below_total_fame"]
                ):
                    kick_list.append(
                        (name, role, *(fame[w] for w in recent))
                    )

    # Display historical data for members on the kick list.
    print("\nFull war history of members in kick list:")

    for item in kick_list:
        name = item[0]
        # Match the original result to the member by name.
        for tag, player in clan_log.items():
            if tag != "ranks" and player["name"] == name:
                print(f"{name} ({tag}): {player['fame']}")
                break

    # Save calculated history.
    with (LOG_DIR / "clan-log.json").open(
        "w", encoding="utf-8"
    ) as outfile:
        json.dump(clan_log, outfile, indent=2)

    return (
        week_champ,
        promotion_list,
        demotion_list,
        kick_list,
        warning_list
    )

    

try:
    with CONFIG_FILE.open("r", encoding="utf-8") as infile:
        config = json.load(infile)
        # Load rules
        rules = config["rules"]

        for action in ("promotion", "demotion", "kick"):
            weeks = rules[action]["consecutive_weeks"]

            if type(weeks) is not int or weeks < 1:
                raise SystemExit(
                    f"Invalid consecutive_weeks for {action}: {weeks}"
                )

        thresholds = {
            "promotion": "minimum_fame_per_week",
            "demotion": "below_fame_per_week",
            "warning": "below_fame",
            "kick": "below_total_fame",
        }

        for action, field in thresholds.items():
            value = rules[action][field]

            if type(value) is not int or value < 0:
                raise SystemExit(
                    f"Invalid {action}.{field}: {value}"
                )

except FileNotFoundError:
    raise SystemExit(
        "Configuration file not found. "
        "Copy config.example.json to config.json "
        "and enter your clan tag and API token."
    )
except json.JSONDecodeError as exc:
    raise SystemExit(f"Invalid JSON in config.json: {exc}")

clan_tag = config.get("clan_tag", "").strip()
token = config.get("api_token", "").strip()

if not clan_tag.startswith("#") or len(clan_tag) < 2:
    raise SystemExit("Invalid clan tag in config.json.")

# set to True to compute the output from the local files 
data_fetched = True

week_champ, promotion_list, demotion_list, kick_list, warning_list = (
    ClashRoyaleClanManager(clan_tag, token, data_fetched, rules)
)

print(f"Week champ: {week_champ} \nPromote: {promotion_list} \nDemote: {demotion_list} \nKick: {kick_list} \nwarning list: {warning_list}")