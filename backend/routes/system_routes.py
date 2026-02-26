from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from models import OddsSnapshot, db
from services.odds_service import fetch_and_store_all
from services.pick_engine import generate_picks

system_bp = Blueprint("system", __name__)


@system_bp.get("/api/v1/health")
def health_check():
    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    latest_snapshot = OddsSnapshot.query.order_by(OddsSnapshot.fetched_at.desc()).first()

    return jsonify(
        {
            "status": "ok" if db_ok else "degraded",
            "db_ok": db_ok,
            "odds_key_present": bool(current_app.config.get("ODDS_API_KEY")),
            "last_fetch_time": latest_snapshot.fetched_at.isoformat() if latest_snapshot else None,
        }
    )


@system_bp.post("/api/v1/refresh")
def refresh_odds():
    odds_result = fetch_and_store_all()
    picks_result = generate_picks()
    return jsonify({"status": "ok", "odds": odds_result, "picks": picks_result})
