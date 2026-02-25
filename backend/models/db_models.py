from datetime import datetime

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    external_game_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    sport_key = db.Column(db.String(64), nullable=False, index=True)
    home_team = db.Column(db.String(128), nullable=False)
    away_team = db.Column(db.String(128), nullable=False)
    commence_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class OddsSnapshot(db.Model):
    __tablename__ = "odds_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, index=True)
    market_type = db.Column(db.String(32), nullable=False, index=True)
    bookmaker = db.Column(db.String(128), nullable=False)
    outcome_name = db.Column(db.String(128), nullable=True)
    outcome_price = db.Column(db.Float, nullable=True)
    outcome_point = db.Column(db.Float, nullable=True)
    source_event_updated_at = db.Column(db.DateTime, nullable=True)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    game = db.relationship("Game", backref=db.backref("odds_snapshots", lazy=True))
