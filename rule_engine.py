"""Configurable, conservative Clash Royale clan-war recommendation engine.

No network access or file I/O. A missing per-player war record is UNKNOWN, not
non-participation. Donation statistics are advisory and never affect war rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class RuleConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class War:
    season_id: int
    section_index: int
    participants: Mapping[str, Mapping[str, Any]]

    @property
    def identifier(self) -> str:
        return f"{self.season_id}:{self.section_index}"


def build_wars(riverracelog: Mapping[str, Any], clan_tag: str) -> list[War]:
    """Return descending history of races with a matching clan standing.

    NOTE: Presence in a participant list does not prove that a missing current
    member belonged to the clan in that war. Unknowns remain unknown.
    """
    wars = {}
    for item in riverracelog.get("items", []):
        try:
            season, section = int(item["seasonId"]), int(item["sectionIndex"])
        except (KeyError, TypeError, ValueError):
            continue
        standing = next(
            (
                s
                for s in item.get("standings", [])
                if s.get("clan", {}).get("tag") == clan_tag
            ),
            None,
        )
        if standing is None:
            continue
        entries = standing.get("clan", {}).get("participants", [])
        players = {p["tag"]: p for p in entries if isinstance(p, dict) and p.get("tag")}
        wars[(season, section)] = War(season, section, players)
    return [wars[k] for k in sorted(wars, reverse=True)]


def _positive_int(value: Any, key: str) -> int:
    if type(value) is not int or value < 1:
        raise RuleConfigurationError(f"{key} must be a positive integer")
    return value


def _nonnegative_int(value: Any, key: str) -> int:
    if type(value) is not int or value < 0:
        raise RuleConfigurationError(f"{key} must be a nonnegative integer")
    return value


def validate_rules(rules: Mapping[str, Any]) -> None:
    for action in ("promotion", "demotion", "kick", "warning"):
        rule = rules.get(action)
        if not isinstance(rule, dict):
            raise RuleConfigurationError(f"rules.{action} must be an object")
        if type(rule.get("enabled")) is not bool:
            raise RuleConfigurationError(f"rules.{action}.enabled must be boolean")
        if not rule["enabled"]:
            continue
        strategy = rule.get("strategy")
        if strategy not in ("fame", "participation", "combined"):
            raise RuleConfigurationError(f"Invalid {action} strategy: {strategy}")
        if not isinstance(rule.get("roles"), list) or not all(
            isinstance(x, str) for x in rule["roles"]
        ):
            raise RuleConfigurationError(
                f"rules.{action}.roles must be a list of role strings"
            )
        if strategy == "combined" and rule.get("operator") not in ("AND", "OR"):
            raise RuleConfigurationError(f"rules.{action}.operator must be AND or OR")
        if strategy in ("fame", "combined"):
            f = rule.get("fame", {})
            if action == "promotion":
                _nonnegative_int(
                    f.get("minimum_fame_per_week"),
                    f"{action}.fame.minimum_fame_per_week",
                )
                _positive_int(
                    f.get("consecutive_wars"), f"{action}.fame.consecutive_wars"
                )
            elif action == "demotion":
                _nonnegative_int(
                    f.get("below_fame_per_week"), f"{action}.fame.below_fame_per_week"
                )
                _positive_int(
                    f.get("consecutive_wars"), f"{action}.fame.consecutive_wars"
                )
            elif action == "kick":
                _nonnegative_int(
                    f.get("minimum_total_fame"), f"{action}.fame.minimum_total_fame"
                )
                _positive_int(f.get("last_wars"), f"{action}.fame.last_wars")
            else:
                _nonnegative_int(f.get("below_fame"), f"{action}.fame.below_fame")
                _positive_int(f.get("last_wars"), f"{action}.fame.last_wars")
        if strategy in ("participation", "combined"):
            p = rule.get("participation", {})
            key = (
                "consecutive_wars"
                if action == "promotion"
                else "consecutive_missed_wars"
            )
            _positive_int(p.get(key), f"{action}.participation.{key}")


def _records(wars: Sequence[War], tag: str, count: int):
    if len(wars) < count:
        return None
    recent = [war.participants.get(tag) for war in wars[:count]]
    if any(record is None for record in recent):
        return None
    return recent


def _participation(record: Mapping[str, Any]) -> bool | None:
    # Data source may lack decksUsed; do not infer inactivity from fame.
    value = record.get("decksUsed")
    if type(value) is not int or value < 0:
        return None
    return value > 0


def _fame(record: Mapping[str, Any]) -> int | None:
    value = record.get("fame")
    if type(value) is not int or value < 0:
        return None
    return value


def _strategy_check(
    action: str, kind: str, tag: str, wars: Sequence[War], rule: Mapping[str, Any]
) -> bool | None:
    if kind == "participation":
        opts = rule["participation"]
        count = (
            opts["consecutive_wars"]
            if action == "promotion"
            else opts["consecutive_missed_wars"]
        )
        recs = _records(wars, tag, count)
        if recs is None:
            return None
        values = [_participation(record) for record in recs]
        if action == "promotion":
            return _all_known(values, True)
        return _all_known(values, False)

    opts = rule["fame"]
    count = (
        opts["consecutive_wars"]
        if action in ("promotion", "demotion")
        else opts["last_wars"]
    )
    recs = _records(wars, tag, count)
    if recs is None:
        return None
    values = [_fame(record) for record in recs]
    if any(value is None for value in values):
        return None
    if action == "promotion":
        return all(value >= opts["minimum_fame_per_week"] for value in values)
    if action == "demotion":
        return all(value < opts["below_fame_per_week"] for value in values)
    if action == "kick":
        return sum(values) < opts["minimum_total_fame"]
    return (
        sum(values) < opts["below_fame"]
    )  # If last_wars > 1, threshold applies to total.


def _all_known(values: Sequence[bool | None], target: bool) -> bool | None:
    # Known counterexample => False even when other data unknown.
    if any(value is (not target) for value in values):
        return False
    if any(value is None for value in values):
        return None
    return True


def _combine(left: bool | None, right: bool | None, operator: str) -> bool | None:
    if operator == "OR":
        return (
            True
            if left is True or right is True
            else (None if None in (left, right) else False)
        )
    return (
        False
        if left is False or right is False
        else (None if None in (left, right) else True)
    )


def evaluate_member(
    tag: str, role: str, wars: Sequence[War], rules: Mapping[str, Any]
) -> dict[str, bool | None]:
    """True=recommend, False=no action, None=insufficient evidence."""
    output: dict[str, bool | None] = {}
    for action in ("promotion", "demotion", "kick", "warning"):
        rule = rules[action]
        if not rule["enabled"] or role not in rule["roles"]:
            output[action] = False
            continue
        strategy = rule["strategy"]
        if strategy == "combined":
            part = _strategy_check(action, "participation", tag, wars, rule)
            fame = _strategy_check(action, "fame", tag, wars, rule)
            output[action] = _combine(part, fame, rule["operator"])
        else:
            output[action] = _strategy_check(action, strategy, tag, wars, rule)
    # Disciplinary recommendation takes precedence over promotion.
    if output["kick"] is True:
        output["promotion"] = False
        output["warning"] = False
    return output


def evaluate_clan(
    members: Mapping[str, Any],
    riverracelog: Mapping[str, Any],
    clan_tag: str,
    rules: Mapping[str, Any],
):
    validate_rules(rules)
    wars = build_wars(riverracelog, clan_tag)
    results = {}
    for member in members.get("items", []):
        tag = member.get("tag")
        if not tag:
            continue
        results[tag] = {
            "name": member.get("name", tag),
            "role": member.get("role", "unknown"),
            "recommendations": evaluate_member(
                tag, member.get("role", "unknown"), wars, rules
            ),
        }
    return wars, results


def donation_summary(
    members: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] = (),
) -> dict[str, dict[str, Any]]:
    """Report donation observations without making disciplinary recommendations.

    Historical samples must be captured on fresh API calls, never replayed from
    cached responses. A decreasing counter flags a reset (or counter anomaly);
    it does not imply negative donations or a known full-week total.
    """
    samples_by_tag: dict[str, list[tuple[str, int]]] = {}
    for snapshot in history:
        timestamp = snapshot.get("timestamp")
        players = snapshot.get("players")
        if not isinstance(timestamp, str) or not isinstance(players, dict):
            continue
        for tag, data in players.items():
            if not isinstance(data, dict):
                continue
            amount = data.get("donations")
            if isinstance(tag, str) and type(amount) is int and amount >= 0:
                samples_by_tag.setdefault(tag, []).append((timestamp, amount))

    results: dict[str, dict[str, Any]] = {}
    for member in members.get("items", []):
        if not isinstance(member, dict) or not member.get("tag"):
            continue
        tag = member["tag"]
        current = member.get("donations")
        received = member.get("donationsReceived")
        if type(current) is not int or current < 0:
            current = None
        if type(received) is not int or received < 0:
            received = None
        samples = sorted(samples_by_tag.get(tag, []), key=lambda pair: pair[0])
        resets = sum(b < a for (_, a), (_, b) in zip(samples, samples[1:]))
        results[tag] = {
            "name": member.get("name", tag),
            "donations": current,
            "donations_received": received,
            "observations": len(samples),
            "observed_resets": resets,
            "first_observed": samples[0][0] if samples else None,
            "last_observed": samples[-1][0] if samples else None,
            "highest_observed_counter": max((n for _, n in samples), default=None),
        }
    return results
