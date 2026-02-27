import os

from flask import Blueprint, jsonify, request

from config import MAX_ML_PLUS, MIN_BOOKS, MIN_EV, MIN_SIGNAL
from models import Pick

bp = Blueprint("board", __name__)

MIN_BOOKS_SPREADS = int(os.getenv("MIN_BOOKS_SPREADS", "3"))
MIN_EV_SPREADS = float(os.getenv("MIN_EV_SPREADS", "0.01"))
MIN_BOOKS_TOTALS = int(os.getenv("MIN_BOOKS_TOTALS", "3"))
MIN_EV_TOTALS = float(os.getenv("MIN_EV_TOTALS", "0.005"))


@bp.get("/api/v1/board")
def get_board():
    min_books_arg = request.args.get("min_books")
    min_ev_arg = request.args.get("min_ev")
    min_signal_arg = request.args.get("min_signal")
    max_ml_plus = int(request.args.get("max_ml_plus", MAX_ML_PLUS))

    min_signal = float(min_signal_arg) if min_signal_arg is not None else float(MIN_SIGNAL)

    def _min_books(default_value: int) -> int:
        return int(min_books_arg) if min_books_arg is not None else int(default_value)

    def _min_ev_decimal(default_value: float) -> float:
        return float(min_ev_arg) if min_ev_arg is not None else float(default_value)

    market_filters = {
        "h2h": {
            "min_books": _min_books(MIN_BOOKS),
            "min_ev_decimal": _min_ev_decimal(MIN_EV),
            "min_signal": min_signal,
            "max_ml_plus": max_ml_plus,
        },
        "spreads": {
            "min_books": _min_books(MIN_BOOKS_SPREADS),
            "min_ev_decimal": _min_ev_decimal(MIN_EV_SPREADS),
            "min_signal": min_signal,
        },
        "totals": {
            "min_books": _min_books(MIN_BOOKS_TOTALS),
            "min_ev_decimal": _min_ev_decimal(MIN_EV_TOTALS),
            "min_signal": min_signal,
        },
    }

    for market in market_filters.values():
        market["min_ev_percent"] = market["min_ev_decimal"] * 100.0

    def _serialize_pick(pick: Pick) -> dict:
        return {
            "id": pick.id,
            "created_at": pick.created_at.isoformat() if pick.created_at else None,
            "game_id": pick.game_id,
            "sport_key": pick.sport_key,
            "commence_time": pick.commence_time.isoformat() if pick.commence_time else None,
            "home_team": pick.home_team,
            "away_team": pick.away_team,
            "market_type": pick.market_type,
            "outcome_name": pick.outcome_name,
            "outcome_point": pick.outcome_point,
            "sportsbook": pick.sportsbook,
            "offered_odds": pick.offered_odds,
            "offered_decimal": pick.offered_decimal,
            "consensus_prob": pick.consensus_prob,
            "ev_percent": pick.ev_percent,
            "kelly_fraction": pick.kelly_fraction,
            "kelly_quarter": pick.kelly_quarter,
            "book_count": pick.book_count,
            "sharp_present": pick.sharp_present,
            "signal_score": pick.signal_score,
            "status": pick.status,
        }

    board = {}
    for market_type in ("h2h", "spreads", "totals"):
        filters = market_filters[market_type]
        query = Pick.query.filter(
            Pick.market_type == market_type,
            Pick.status == "active",
            Pick.book_count >= filters["min_books"],
            Pick.ev_percent >= filters["min_ev_percent"],
            Pick.signal_score >= filters["min_signal"],
        )
        if market_type == "h2h":
            query = query.filter(Pick.offered_odds < filters["max_ml_plus"])

        picks = (
            query.order_by(Pick.signal_score.desc(), Pick.ev_percent.desc())
            .limit(5)
            .all()
        )
        board[market_type] = [_serialize_pick(p) for p in picks]

    return jsonify({"board": board, "filters": market_filters})
