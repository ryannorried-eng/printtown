import argparse
import time
from datetime import datetime, timezone

from app import create_app
from services.odds_service import fetch_and_store_all
from services.pick_engine import generate_picks

INTERVAL_SECONDS = 300


def run_cycle() -> None:
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"[{started_at}] refresh cycle started")
    odds = fetch_and_store_all()
    picks = generate_picks()
    finished_at = datetime.now(timezone.utc).isoformat()
    print(
        f"[{finished_at}] refresh cycle finished "
        f"odds_total={odds.get('total_rows', 0)} "
        f"h2h={odds.get('market_counts', {}).get('h2h', 0)} "
        f"spreads={odds.get('market_counts', {}).get('spreads', 0)} "
        f"totals={odds.get('market_counts', {}).get('totals', 0)} "
        f"picks_total_candidates={picks.get('total_candidates', 0)} "
        f"picks_passed={picks.get('passed_filter', 0)} "
        f"picks_kept={picks.get('deduped_kept', 0)} "
        f"picks_upserted={picks.get('upserted', 0)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PrintTown worker")
    parser.add_argument("--once", action="store_true", help="Run one refresh cycle")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.once:
            run_cycle()
            return

        while True:
            run_cycle()
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
