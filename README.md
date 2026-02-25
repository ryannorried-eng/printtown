# PrintTown (Phase 1A)

## Backend local run

```bash
cd backend
export ODDS_API_KEY=your_api_key_here
# optional env vars
export DATABASE_URL=sqlite:///printtown.db
export CORS_ORIGIN=http://localhost:3000
export FLASK_SECRET_KEY=change-me

pip install -r requirements.txt
python app.py
```

In a second terminal:

```bash
cd backend
curl http://127.0.0.1:5000/api/v1/health
curl -X POST http://127.0.0.1:5000/api/v1/refresh
pytest -q
```
