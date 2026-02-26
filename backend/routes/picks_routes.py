from flask import Blueprint, jsonify, request

from models import Pick

picks_bp = Blueprint("picks", __name__)


@picks_bp.get("/api/v1/picks")
def get_picks():
    sport_key = request.args.get("sport_key", "basketball_ncaab")
    min_ev = float(request.args.get("min_ev", 1.0))
    min_signal = float(request.args.get("min_signal", 40.0))

    picks = (
        Pick.query.filter(
            Pick.sport_key == sport_key,
            Pick.ev_percent >= min_ev,
            Pick.signal_score >= min_signal,
            Pick.status == "active",
        )
        .order_by(Pick.signal_score.desc(), Pick.ev_percent.desc())
        .all()
    )

    return jsonify(
        [
            {
                "id": p.id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "game_id": p.game_id,
                "sport_key": p.sport_key,
                "commence_time": p.commence_time.isoformat() if p.commence_time else None,
                "home_team": p.home_team,
                "away_team": p.away_team,
                "market_type": p.market_type,
                "outcome_name": p.outcome_name,
                "outcome_point": p.outcome_point,
                "sportsbook": p.sportsbook,
                "offered_odds": p.offered_odds,
                "offered_decimal": p.offered_decimal,
                "consensus_prob": p.consensus_prob,
                "ev_percent": p.ev_percent,
                "kelly_fraction": p.kelly_fraction,
                "kelly_quarter": p.kelly_quarter,
                "book_count": p.book_count,
                "sharp_present": p.sharp_present,
                "signal_score": p.signal_score,
                "status": p.status,
            }
            for p in picks
        ]
    )
