import os


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///printtown.db")
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
    CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
