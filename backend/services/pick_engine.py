from __future__ import annotations

from collections import defaultdict
from datetime import datetime
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


def _normalize_point(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _normalize_outcome_name(value: str) -> str:
    return value.strip().lower()


def _outcome_key(outcome_name: str, outcome_point: float | None) -> tuple[str, float | None]:
    return (_normalize_outcome_name(outcome_name), _normalize_point(outcome_point))


def _compute_signal_score(ev_percent: float, book_count: int, sharp_present: bool) -> float:
    ev_component = min(max(ev_percent, 0.0), 20.0) * 4.0
    book_bonus = min(book_count, 10) * 1.5
    sharp_bonus = 5.0 if sharp_present else 0.0
    return round(min(100.0, ev_component + book_bonus + sharp_bonus), 1)


def generate_picks() -> dict[str, Any]:
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
        }

    rows = (
        OddsSnapshot.query.join(Game, Game.id == OddsSnapshot.game_id)
        .filter(
            OddsSnapshot.fetched_at == latest_fetched_at,
            Game.sport_key == SPORT_KEY,
            OddsSnapshot.market_type.in_(["h2h", "spreads", "totals"]),
        )
        .all()
    )

    market_book_groups: dict[tuple[int, str, str], list[OddsSnapshot]] = defaultdict(list)
    for row in rows:
        market_book_groups[(row.game_id, row.market_type, row.bookmaker)].append(row)

    consensus_inputs: dict[
        tuple[int, str], dict[tuple[str, float | None], list[dict[str, Any]]]
    ] = defaultdict(
        lambda: defaultdict(list)
    )

    for (game_id, market_type, sportsbook), outcomes in market_book_groups.items():
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

    total_candidates = 0
    passed_filter_rows: list[dict[str, Any]] = []

    for row in rows:
        if row.outcome_name is None or row.outcome_price in (None, 0):
            continue

        outcome_key = _outcome_key(row.outcome_name, row.outcome_point)
        market_key = (row.game_id, row.market_type)
        consensus_prob = consensus_by_market.get(market_key, {}).get(outcome_key)
        if consensus_prob is None:
            continue

        total_candidates += 1
        offered_odds = int(row.outcome_price)
        offered_decimal = american_to_decimal(offered_odds)
        ev_percent = calculate_ev_percent(consensus_prob, offered_odds)
        full_kelly = kelly_criterion(consensus_prob, offered_odds)
        quarter_kelly = min(
            kelly_fractional(consensus_prob, offered_odds, KELLY_FRACTION, KELLY_QUARTER_CAP),
            KELLY_QUARTER_CAP,
        )

        outcome_lines = consensus_inputs.get(market_key, {}).get(outcome_key, [])
        book_count = len(outcome_lines)

        if book_count < MIN_BOOKS:
            continue

        if row.market_type == "h2h" and offered_odds >= MAX_ML_PLUS:
            if book_count < LONGSHOT_MIN_BOOKS or consensus_prob < LONGSHOT_MIN_CONS_P:
                continue

        if ev_percent < MIN_EV_PERCENT:
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
    }
