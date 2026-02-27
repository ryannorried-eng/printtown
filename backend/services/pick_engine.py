from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from config import Config
from models import Game, OddsSnapshot, Pick
from services.math_engine import (
    american_to_decimal,
    build_consensus,
    calculate_ev_percent,
    kelly_criterion,
    kelly_fractional,
    remove_vig_multiplicative,
)

SPORT_KEY = "basketball_ncaab"
MIN_EV_PERCENT = 1.0
KELLY_FRACTION = 0.25
KELLY_QUARTER_CAP = 0.05
MIN_BOOKS = int(getattr(Config, "MIN_BOOKS", 2))
MAX_ML_PLUS = int(getattr(Config, "MAX_ML_PLUS", 800))
LONGSHOT_MIN_CONS_P = float(getattr(Config, "LONGSHOT_MIN_CONS_P", 0.2))
LONGSHOT_MIN_BOOKS = int(getattr(Config, "LONGSHOT_MIN_BOOKS", 6))
SNAPSHOT_WINDOW_SECONDS = int(os.getenv("SNAPSHOT_WINDOW_SECONDS", "180"))


def _normalize_point(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _normalize_outcome_name(value: str) -> str:
    return value.strip().lower()


def _outcome_key(outcome_name: str, outcome_point: float | None) -> tuple[str, float | None]:
    return (_normalize_outcome_name(outcome_name), _normalize_point(outcome_point))


def _consensus_group_point(row: OddsSnapshot) -> float | None:
    if row.market_type in {"spreads", "totals"}:
        return _normalize_point(row.outcome_point)
    return None


def _compute_signal_score(ev_percent: float, book_count: int, sharp_present: bool) -> float:
    ev_component = min(max(ev_percent, 0.0), 20.0) * 4.0
    book_bonus = min(book_count, 10) * 1.5
    sharp_bonus = 5.0 if sharp_present else 0.0
    return round(min(100.0, ev_component + book_bonus + sharp_bonus), 1)


def generate_picks() -> dict[str, Any]:
    debug_rejects = {
        "no_consensus": 0,
        "min_books": 0,
        "longshot_guard": 0,
        "min_ev": 0,
        "other": 0,
    }
    debug_samples: list[dict[str, Any]] = []

    latest_fetched_at = (
        OddsSnapshot.query.filter(OddsSnapshot.market_type.in_(["h2h", "spreads", "totals"]))
        .with_entities(OddsSnapshot.fetched_at)
        .order_by(OddsSnapshot.fetched_at.desc())
        .limit(1)
        .scalar()
    )

    if latest_fetched_at is None:
        return {
            "total_candidates": 0,
            "passed_filter": 0,
            "deduped_kept": 0,
            "upserted": 0,
            "kept_by_market": {"h2h": 0, "spreads": 0, "totals": 0},
            "debug_counts": {
                "rows_in_window": 0,
                "by_book_groups": 0,
                "devigged_groups": 0,
                "consensus_markets": 0,
                "consensus_outcomes": 0,
                "offered_lines": 0,
            },
            "debug_rejects": debug_rejects,
            "debug_samples": debug_samples,
        }

    rows = (
        OddsSnapshot.query.join(Game, Game.id == OddsSnapshot.game_id)
        .filter(
            OddsSnapshot.fetched_at >= (latest_fetched_at - timedelta(seconds=SNAPSHOT_WINDOW_SECONDS)),
            Game.sport_key == SPORT_KEY,
            OddsSnapshot.market_type.in_(["h2h", "spreads", "totals"]),
        )
        .all()
    )

    offered = [
        {
            "snapshot": row,
            "market_key": (row.game_id, row.market_type),
            "outcome_key": _outcome_key(row.outcome_name, row.outcome_point)
            if row.outcome_name is not None
            else None,
        }
        for row in rows
    ]

    market_book_groups: dict[tuple[int, str, str, datetime, float | None], list[OddsSnapshot]] = defaultdict(list)
    for row in rows:
        market_book_groups[
            (row.game_id, row.market_type, row.bookmaker, row.fetched_at, _consensus_group_point(row))
        ].append(row)

    consensus_inputs: dict[
        tuple[int, str], dict[tuple[str, float | None], list[dict[str, Any]]]
    ] = defaultdict(
        lambda: defaultdict(list)
    )

    devigged_groups = 0
    for (game_id, market_type, sportsbook, _fetched_at, _group_point), outcomes in market_book_groups.items():
        if len(outcomes) < 2:
            continue
        devig_payload: list[dict[str, Any]] = []
        for o in outcomes:
            if o.outcome_name is None or o.outcome_price in (None, 0):
                continue
            devig_payload.append(
                {
                    "name": o.outcome_name,
                    "point": _normalize_point(o.outcome_point),
                    "american_odds": int(o.outcome_price),
                }
            )
        if len(devig_payload) < 2:
            continue
        try:
            devigged = remove_vig_multiplicative(devig_payload)
        except ValueError:
            continue
        devigged_groups += 1
        for entry in devigged:
            key = _outcome_key(entry["name"], entry.get("point"))
            consensus_inputs[(game_id, market_type)][key].append(
                {
                    "sportsbook": sportsbook,
                    "devigged_prob": entry["devigged_prob"],
                }
            )

    consensus_by_market: dict[tuple[int, str], dict[tuple[str, float | None], float]] = {}
    for market_key, by_outcome in consensus_inputs.items():
        consensus_by_market[market_key] = {}
        for outcome_key, lines in by_outcome.items():
            if not lines:
                continue
            try:
                consensus_by_market[market_key][outcome_key] = build_consensus(lines)
            except ValueError:
                continue

    debug_counts = {
        "rows_in_window": len(rows),
        "by_book_groups": len(market_book_groups),
        "devigged_groups": devigged_groups,
        "consensus_markets": len(consensus_by_market),
        "consensus_outcomes": sum(len(v) for v in consensus_by_market.values()),
        "offered_lines": len(offered),
    }

    total_candidates = 0
    passed_filter_rows: list[dict[str, Any]] = []

    for offer in offered:
        row = offer["snapshot"]
        if offer["outcome_key"] is None or row.outcome_price in (None, 0):
            continue

        outcome_key = offer["outcome_key"]
        market_key = offer["market_key"]
        consensus_prob = consensus_by_market.get(market_key, {}).get(outcome_key)
        offered_odds = int(row.outcome_price)
        outcome_lines = consensus_inputs.get(market_key, {}).get(outcome_key, [])
        book_count = len(outcome_lines)
        ev_percent = calculate_ev_percent(consensus_prob, offered_odds) if consensus_prob is not None else None

        if len(debug_samples) < 10:
            debug_samples.append(
                {
                    "market_type": row.market_type,
                    "outcome_name": row.outcome_name,
                    "point": _normalize_point(row.outcome_point),
                    "offered_odds": offered_odds,
                    "consensus_prob": consensus_prob,
                    "ev_percent": ev_percent,
                    "book_count": book_count,
                }
            )

        if consensus_prob is None:
            debug_rejects["no_consensus"] += 1
            continue

        total_candidates += 1
        offered_decimal = american_to_decimal(offered_odds)
        ev_percent = calculate_ev_percent(consensus_prob, offered_odds)
        full_kelly = kelly_criterion(consensus_prob, offered_odds)
        quarter_kelly = min(
            kelly_fractional(consensus_prob, offered_odds, KELLY_FRACTION, KELLY_QUARTER_CAP),
            KELLY_QUARTER_CAP,
        )

        if book_count < MIN_BOOKS:
            debug_rejects["min_books"] += 1
            continue

        if row.market_type == "h2h" and offered_odds >= MAX_ML_PLUS:
            if book_count < LONGSHOT_MIN_BOOKS or consensus_prob < LONGSHOT_MIN_CONS_P:
                debug_rejects["longshot_guard"] += 1
                continue

        if ev_percent < MIN_EV_PERCENT:
            debug_rejects["min_ev"] += 1
            continue

        sharp_present = any("pinnacle" in x["sportsbook"].lower() for x in outcome_lines)
        effective_ev = min(ev_percent, 8.0)
        signal_score = _compute_signal_score(effective_ev, book_count, sharp_present)

        game = row.game
        passed_filter_rows.append(
            {
                "game_id": row.game_id,
                "sport_key": game.sport_key,
                "commence_time": game.commence_time,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "market_type": row.market_type,
                "outcome_name": row.outcome_name,
                "outcome_point": _normalize_point(row.outcome_point),
                "sportsbook": row.bookmaker,
                "offered_odds": offered_odds,
                "offered_decimal": offered_decimal,
                "consensus_prob": consensus_prob,
                "ev_percent": ev_percent,
                "kelly_fraction": full_kelly,
                "kelly_quarter": quarter_kelly,
                "book_count": book_count,
                "sharp_present": sharp_present,
                "signal_score": signal_score,
                "status": "active",
            }
        )

    deduped: dict[tuple[int, str, str, float | None], dict[str, Any]] = {}
    for row in passed_filter_rows:
        dedupe_key = (
            row["game_id"],
            row["market_type"],
            row["outcome_name"],
            row["outcome_point"],
        )
        current = deduped.get(dedupe_key)
        if current is None or row["ev_percent"] > current["ev_percent"]:
            deduped[dedupe_key] = row

    upserted = 0
    for row in deduped.values():
        existing = Pick.query.filter_by(
            game_id=row["game_id"],
            market_type=row["market_type"],
            outcome_name=row["outcome_name"],
            outcome_point=row["outcome_point"],
            sportsbook=row["sportsbook"],
        ).first()

        if existing is None:
            existing = Pick(**row)
            existing.created_at = datetime.utcnow()
            db_session = Pick.query.session
            db_session.add(existing)
        else:
            for key, value in row.items():
                setattr(existing, key, value)
        upserted += 1

    Pick.query.session.commit()

    kept_by_market = {"h2h": 0, "spreads": 0, "totals": 0}

    for row in deduped.values():
        if row["market_type"] in kept_by_market:
            kept_by_market[row["market_type"]] += 1

    return {
        "total_candidates": total_candidates,
        "passed_filter": len(passed_filter_rows),
        "deduped_kept": len(deduped),
        "upserted": upserted,
        "kept_by_market": kept_by_market,
        "debug_counts": debug_counts,
        "debug_rejects": debug_rejects,
        "debug_samples": debug_samples,
    }
