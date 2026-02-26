import os


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///instance/printtown.db")
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
    CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# ==============================
# PRINTTOWN PICK QUALITY SETTINGS
# ==============================

import os

MIN_EV = float(os.getenv("MIN_EV", "0.02"))
MIN_SIGNAL = float(os.getenv("MIN_SIGNAL", "55"))
MIN_BOOKS = int(os.getenv("MIN_BOOKS", "4"))

# Moneyline longshot guardrails
MAX_ML_PLUS = int(os.getenv("MAX_ML_PLUS", "600"))
LONGSHOT_MIN_CONS_P = float(os.getenv("LONGSHOT_MIN_CONS_P", "0.12"))
LONGSHOT_MIN_BOOKS = int(os.getenv("LONGSHOT_MIN_BOOKS", "6"))

# Optional scoring cap
EV_CAP = float(os.getenv("EV_CAP", "0.08"))

