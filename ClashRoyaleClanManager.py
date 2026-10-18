#!/usr/bin/env python3
"""Clash Royale Clan Manager: fetch war history and evaluate configured rules.

Requires rule_engine.py in the same directory and requests from requirements.txt.
Usage: python ClashRoyaleClanManager.py [--cached]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from rule_engine import (
    RuleConfigurationError,
    apply_live_kick_rules,
    donation_summary,
    evaluate_clan,
)

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "config.json"
API_BASE_URL = "https://api.clashroyale.com/v1"


def load_config() -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as infile:
            config = json.load(infile)
    except FileNotFoundError:
        raise SystemExit(
            "Missing config.json. Copy config.example.json to config.json and edit it."
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load config.json: {exc}")

    if not isinstance(config, dict):
        raise SystemExit("config.json must contain a JSON object.")
    clan_tag = config.get("clan_tag")
    token = config.get("api_token")
    if (
        not isinstance(clan_tag, str)
        or not clan_tag.strip().startswith("#")
        or len(clan_tag.strip()) < 2
    ):
        raise SystemExit("config.json requires a valid clan_tag starting with #.")
    if not isinstance(token, str) or not token.strip() or token == "YOUR_API_TOKEN":
        raise SystemExit("config.json requires your Clash Royale api_token.")
    rules = config.get("rules")
    if not isinstance(rules, dict):
        raise SystemExit("config.json requires a rules object.")
    donations = config.get(
        "donations", {"enabled": False, "tracking": {"enabled": False}}
    )
    if (
        not isinstance(donations, dict)
        or type(donations.get("enabled", False)) is not bool
    ):
        raise SystemExit("config.json donations.enabled must be boolean.")
    tracking = donations.get("tracking", {})
    if (
        not isinstance(tracking, dict)
        or type(tracking.get("enabled", False)) is not bool
    ):
        raise SystemExit("config.json donations.tracking.enabled must be boolean.")
    return clan_tag.strip(), token.strip(), rules, donations


def fetch_data(clan_tag: str, token: str, endpoint: str) -> dict[str, Any]:
    # Clash Royale clan tags must be percent-encoded in the URL (including '#').
    url = f"{API_BASE_URL}/clans/{quote(clan_tag, safe='')}/{endpoint}"
    try:
        response = requests.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=30
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed fetching {endpoint}: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"API response for {endpoint} is not valid JSON") from exc
    validate_api_data(data, endpoint)
    return data


def validate_api_data(data: Any, endpoint: str) -> None:
    """Validate the two different API payload shapes."""
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response structure for {endpoint}")
    if endpoint == "currentriverrace":
        clan = data.get("clan")
        if not isinstance(clan, dict) or not isinstance(clan.get("participants"), list):
            raise RuntimeError("Current river race requires clan.participants")
    elif not isinstance(data.get("items"), list):
        raise RuntimeError(f"Unexpected response structure for {endpoint}")


def load_data(
    clan_tag: str, token: str, cached: bool
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    endpoints = (
        ("members", "members.json"),
        ("riverracelog", "riverracelog.json"),
        ("currentriverrace", "currentriverrace.json"),
    )
    for endpoint, name in endpoints:
        path = LOG_DIR / name
        if cached:
            if endpoint == "currentriverrace" and not path.exists():
                # Support caches created before this feature was introduced.
                print("Current river race: no cached snapshot available.")
                results.append(None)
                continue
            try:
                with path.open("r", encoding="utf-8") as infile:
                    data = json.load(infile)
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Cannot load cached {path}: {exc}") from exc
            validate_api_data(data, endpoint)
        else:
            print(f"Fetching {endpoint} data...")
            data = fetch_data(clan_tag, token, endpoint)
            with path.open("w", encoding="utf-8") as outfile:
                json.dump(data, outfile, indent=2)
        results.append(data)
    return results[0], results[1], results[2]


def current_race_summary(
    current_race: dict[str, Any], clan_tag: str, members: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build a live snapshot, without feeding it to disciplinary rules."""
    clan = current_race["clan"]
    if clan.get("tag") != clan_tag:
        raise RuntimeError("Current river race clan tag does not match config.json")
    entries = {
        p["tag"]: p
        for p in clan["participants"]
        if isinstance(p, dict) and isinstance(p.get("tag"), str)
    }
    summary = []
    for member in members.get("items", []):
        if not isinstance(member, dict) or not member.get("tag"):
            continue
        tag = member["tag"]
        participant = entries.get(tag)
        summary.append(
            {
                "tag": tag,
                "name": member.get("name", tag),
                "role": member.get("role"),
                "fame": participant.get("fame") if participant else None,
                "decksUsed": participant.get("decksUsed") if participant else None,
                "decksUsedToday": (
                    participant.get("decksUsedToday") if participant else None
                ),
                "record_present": participant is not None,
            }
        )
    return summary


def update_donation_history(
    members: dict[str, Any], fresh_data: bool
) -> list[dict[str, Any]]:
    """Persist fresh donation snapshots; cached runs never manufacture new data."""
    path = LOG_DIR / "donations-history.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as infile:
            history = json.load(infile)
        if not isinstance(history, list):
            raise RuntimeError("Donation history must contain a JSON list")
    else:
        history = []
    if not fresh_data:
        return history

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "players": {
            m["tag"]: {
                "name": m.get("name", m["tag"]),
                "donations": m.get("donations"),
                "donationsReceived": m.get("donationsReceived"),
            }
            for m in members.get("items", [])
            if isinstance(m, dict) and m.get("tag")
        },
    }
    history.append(snapshot)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as outfile:
        json.dump(history, outfile, ensure_ascii=False, indent=2)
    temporary.replace(path)
    return history


def report(
    members: dict[str, Any],
    riverracelog: dict[str, Any],
    clan_tag: str,
    rules: dict[str, Any],
    donation_history: list[dict[str, Any]] | None = None,
    current_race: dict[str, Any] | None = None,
) -> None:
    wars, evaluations = evaluate_clan(members, riverracelog, clan_tag, rules)
    live_kick_evaluation = False
    if current_race is not None:
        live_kick_evaluation = apply_live_kick_rules(
            evaluations, current_race, clan_tag, rules
        )

    # Use only clan standings corresponding to the evaluated war IDs.
    war_ids = {war.identifier for war in wars}
    ranks = []
    for item in riverracelog.get("items", []):
        try:
            identifier = f"{int(item['seasonId'])}:{int(item['sectionIndex'])}"
        except (KeyError, TypeError, ValueError):
            continue
        if identifier not in war_ids:
            continue
        for standing in item.get("standings", []):
            if standing.get("clan", {}).get("tag") == clan_tag:
                rank = standing.get("rank")
                if type(rank) is int and rank > 0:
                    ranks.append(rank)
                break
    print(
        f"\nAverage war rank: {statistics.mean(ranks):.2f}"
        if ranks
        else "\nAverage war rank: No data"
    )

    if wars:
        latest = wars[0]
        scores = [
            (tag, record["fame"])
            for tag, record in latest.participants.items()
            if tag in evaluations and type(record.get("fame")) is int
        ]
        if scores:
            highest = max(score for _, score in scores)
            winners = [tag for tag, score in scores if score == highest]
            print(f"Latest war: {latest.identifier}")
            print(
                "Weekly war champion(s): "
                + ", ".join(
                    f"{evaluations[tag]['name']} ({highest} fame)" for tag in winners
                )
            )
        else:
            print("Weekly war champion: No eligible player with fame data")
    else:
        print("Weekly war champion: No valid war history")

    # Live race is used for kick decisions on warDay only.
    live_summary = None
    if current_race is not None:
        live_summary = current_race_summary(current_race, clan_tag, members)
        print(
            f"\nCurrent river race (live snapshot; {current_race.get('periodType', 'unknown')}):"
        )
        if live_kick_evaluation:
            print(
                "  Used for kick evaluations only; promotions/demotions use completed wars."
            )
        else:
            print("  Not used for rule evaluations (not an active warDay).")
        for player in sorted(
            live_summary,
            key=lambda p: (p["fame"] is None, -(p["fame"] or 0), p["name"]),
        ):
            if not player["record_present"]:
                details = "no participant record (unknown)"
            else:
                fame = player["fame"] if player["fame"] is not None else "unknown"
                decks = (
                    player["decksUsed"]
                    if player["decksUsed"] is not None
                    else "unknown"
                )
                details = f"{fame} fame, {decks} decks used"
            print(f"  {player['name']} ({player['tag']}): {details}")
    else:
        print(
            "\nCurrent river race: snapshot unavailable (not included in recommendations)."
        )

    print("\nRecommendations (advisory only):")
    if live_kick_evaluation:
        print("  Kick: live warDay snapshot; promotion/demotion: completed wars.")
        print("  During an active war, kick results can still change before war ends.")
    else:
        print("  Kick, promotion and demotion: completed-war history.")
    for action in ("promotion", "demotion", "kick", "warning"):
        qualified = [
            (tag, player)
            for tag, player in evaluations.items()
            if player["recommendations"][action] is True
        ]
        unknown = [
            (tag, player)
            for tag, player in evaluations.items()
            if player["recommendations"][action] is None
        ]
        print(f"\n{action.capitalize()} ({len(qualified)}):")
        if not qualified:
            print("  None")
        for tag, player in qualified:
            print(f"  {player['name']} ({tag}, {player['role']})")
        if unknown:
            print(
                f"  Insufficient data: {', '.join(player['name'] for _, player in unknown)}"
            )

    if donation_history is not None:
        donation_data = donation_summary(members, donation_history)
        print("\nDonations (current API counters; not disciplinary criteria):")
        ranked = sorted(
            donation_data.items(),
            key=lambda row: (row[1]["donations"] is None, -(row[1]["donations"] or 0)),
        )
        for tag, item in ranked:
            donated = "unknown" if item["donations"] is None else str(item["donations"])
            print(
                f"  {item['name']} ({tag}): {donated} donated; "
                f"{item['observations']} snapshot(s)"
            )

    # Useful for manual review, using unique tags rather than names.
    print("\nWar history for players recommended for kick:")
    kick_tags = [
        tag
        for tag, player in evaluations.items()
        if player["recommendations"]["kick"] is True
    ]
    for tag in kick_tags:
        print(
            f"  {evaluations[tag]['name']} ({tag}): "
            + ", ".join(
                f"{war.identifier}={war.participants[tag].get('fame', '?')}"
                for war in wars
                if tag in war.participants
            )
        )

    clan_log = {
        "kick_evaluation_source": (
            "current_war" if live_kick_evaluation else "completed_wars"
        ),
        "current_race": (
            {
                "periodType": current_race.get("periodType"),
                "sectionIndex": current_race.get("sectionIndex"),
                "players": {p["tag"]: p for p in live_summary},
            }
            if current_race is not None
            else None
        ),
        "wars": [war.identifier for war in wars],
        "players": {
            tag: {
                "name": player["name"],
                "role": player["role"],
                "recommendations": player["recommendations"],
                "history": {
                    war.identifier: {
                        "fame": war.participants[tag].get("fame"),
                        "decksUsed": war.participants[tag].get("decksUsed"),
                    }
                    for war in wars
                    if tag in war.participants
                },
            }
            for tag, player in evaluations.items()
        },
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "clan-log.json").open("w", encoding="utf-8") as outfile:
        json.dump(clan_log, outfile, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Clash Royale clan war history"
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use existing logs/*.json; do not call the API",
    )
    args = parser.parse_args()
    clan_tag, token, rules, donations = load_config()
    try:
        members, riverracelog, current_race = load_data(clan_tag, token, args.cached)
        history = None
        if donations.get("enabled", False):
            history = update_donation_history(
                members,
                fresh_data=(
                    not args.cached
                    and donations.get("tracking", {}).get("enabled", False)
                ),
            )
        report(members, riverracelog, clan_tag, rules, history, current_race)
    except (RuntimeError, OSError, RuleConfigurationError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
