from datetime import datetime
from typing import Any

import requests
from flask import current_app

from models import Game, OddsSnapshot, db

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"


def fetch_odds(sport_key: str, market_type: str) -> list[dict[str, Any]]:
    api_key = current_app.config.get("ODDS_API_KEY")
    if not api_key:
        raise ValueError("ODDS_API_KEY is not configured")

    response = requests.get(
        f"{ODDS_API_BASE_URL}/sports/{sport_key}/odds",
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": market_type,
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Unexpected odds payload format")
    return payload


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def store_odds_snapshot(odds_data: list[dict[str, Any]], market_type: str) -> int:
    rows_inserted = 0

    for event in odds_data:
        external_game_id = event.get("id")
        if not external_game_id:
            continue

        game = Game.query.filter_by(external_game_id=external_game_id).first()
        if game is None:
            game = Game(
                external_game_id=external_game_id,
                sport_key=event.get("sport_key", "unknown"),
                home_team=event.get("home_team", "Unknown Home"),
                away_team=event.get("away_team", "Unknown Away"),
                commence_time=_parse_iso_datetime(event.get("commence_time")),
            )
            db.session.add(game)
            db.session.flush()

        source_updated_at = _parse_iso_datetime(event.get("last_update"))

        for bookmaker in event.get("bookmakers", []):
            bookmaker_title = bookmaker.get("title", "Unknown Book")
            markets = bookmaker.get("markets", [])
            for market in markets:
                if market.get("key") != market_type:
                    continue
                for outcome in market.get("outcomes", []):
                    snapshot = OddsSnapshot(
                        game_id=game.id,
                        market_type=market_type,
                        bookmaker=bookmaker_title,
                        outcome_name=outcome.get("name"),
                        outcome_price=outcome.get("price"),
                        outcome_point=outcome.get("point"),
                        source_event_updated_at=source_updated_at,
                    )
                    db.session.add(snapshot)
                    rows_inserted += 1

    db.session.commit()
    return rows_inserted


def fetch_and_store_all() -> dict[str, Any]:
    sport_key = "basketball_ncaab"
    markets = ["h2h", "spreads", "totals"]

    total_rows = 0
    market_counts: dict[str, int] = {}

    for market in markets:
        odds_data = fetch_odds(sport_key=sport_key, market_type=market)
        inserted = store_odds_snapshot(odds_data=odds_data, market_type=market)
        market_counts[market] = inserted
        total_rows += inserted

    return {
        "sport_key": sport_key,
        "market_counts": market_counts,
        "total_rows": total_rows,
        "fetched_at": datetime.utcnow().isoformat(),
    }
