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
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from rule_engine import RuleConfigurationError, evaluate_clan

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "config.json"
API_BASE_URL = "https://api.clashroyale.com/v1"


def load_config() -> tuple[str, str, dict[str, Any]]:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as infile:
            config = json.load(infile)
    except FileNotFoundError:
        raise SystemExit("Missing config.json. Copy config.example.json to config.json and edit it.")
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load config.json: {exc}")

    if not isinstance(config, dict):
        raise SystemExit("config.json must contain a JSON object.")
    clan_tag = config.get("clan_tag")
    token = config.get("api_token")
    if not isinstance(clan_tag, str) or not clan_tag.strip().startswith("#") or len(clan_tag.strip()) < 2:
        raise SystemExit("config.json requires a valid clan_tag starting with #.")
    if not isinstance(token, str) or not token.strip() or token == "YOUR_API_TOKEN":
        raise SystemExit("config.json requires your Clash Royale api_token.")
    rules = config.get("rules")
    if not isinstance(rules, dict):
        raise SystemExit("config.json requires a rules object.")
    return clan_tag.strip(), token.strip(), rules


def fetch_data(clan_tag: str, token: str, endpoint: str) -> dict[str, Any]:
    # Clash Royale clan tags must be percent-encoded in the URL (including '#').
    url = f"{API_BASE_URL}/clans/{quote(clan_tag, safe='')}/{endpoint}"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed fetching {endpoint}: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"API response for {endpoint} is not valid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RuntimeError(f"Unexpected API response structure for {endpoint}")
    return data


def load_data(clan_tag: str, token: str, cached: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for endpoint, name in (("members", "members.json"), ("riverracelog", "riverracelog.json")):
        path = LOG_DIR / name
        if cached:
            try:
                with path.open("r", encoding="utf-8") as infile:
                    data = json.load(infile)
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Cannot load cached {path}: {exc}") from exc
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise RuntimeError(f"Unexpected cached data structure in {path}")
        else:
            print(f"Fetching {endpoint} data...")
            data = fetch_data(clan_tag, token, endpoint)
            with path.open("w", encoding="utf-8") as outfile:
                json.dump(data, outfile, indent=2)
        results.append(data)
    return results[0], results[1]


def report(members: dict[str, Any], riverracelog: dict[str, Any], clan_tag: str,
           rules: dict[str, Any]) -> None:
    wars, evaluations = evaluate_clan(members, riverracelog, clan_tag, rules)

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
    print(f"\nAverage war rank: {statistics.mean(ranks):.2f}" if ranks else "\nAverage war rank: No data")

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
            print("Weekly war champion(s): " + ", ".join(
                f"{evaluations[tag]['name']} ({highest} fame)" for tag in winners
            ))
        else:
            print("Weekly war champion: No eligible player with fame data")
    else:
        print("Weekly war champion: No valid war history")

    print("\nRecommendations (advisory only):")
    for action in ("promotion", "demotion", "kick", "warning"):
        qualified = [(tag, player) for tag, player in evaluations.items()
                     if player["recommendations"][action] is True]
        unknown = [(tag, player) for tag, player in evaluations.items()
                   if player["recommendations"][action] is None]
        print(f"\n{action.capitalize()} ({len(qualified)}):")
        if not qualified:
            print("  None")
        for tag, player in qualified:
            print(f"  {player['name']} ({tag}, {player['role']})")
        if unknown:
            print(f"  Insufficient data: {', '.join(player['name'] for _, player in unknown)}")

    # Useful for manual review, using unique tags rather than names.
    print("\nWar history for players recommended for kick:")
    kick_tags = [tag for tag, player in evaluations.items()
                 if player["recommendations"]["kick"] is True]
    for tag in kick_tags:
        print(f"  {evaluations[tag]['name']} ({tag}): " + ", ".join(
            f"{war.identifier}={war.participants[tag].get('fame', '?')}"
            for war in wars if tag in war.participants
        ))

    clan_log = {
        "wars": [war.identifier for war in wars],
        "players": {tag: {
            "name": player["name"],
            "role": player["role"],
            "recommendations": player["recommendations"],
            "history": {
                war.identifier: {
                    "fame": war.participants[tag].get("fame"),
                    "decksUsed": war.participants[tag].get("decksUsed"),
                }
                for war in wars if tag in war.participants
            },
        } for tag, player in evaluations.items()},
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "clan-log.json").open("w", encoding="utf-8") as outfile:
        json.dump(clan_log, outfile, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Clash Royale clan war history")
    parser.add_argument("--cached", action="store_true", help="Use existing logs/*.json; do not call the API")
    args = parser.parse_args()
    clan_tag, token, rules = load_config()
    try:
        members, riverracelog = load_data(clan_tag, token, args.cached)
        report(members, riverracelog, clan_tag, rules)
    except (RuntimeError, OSError, RuleConfigurationError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
