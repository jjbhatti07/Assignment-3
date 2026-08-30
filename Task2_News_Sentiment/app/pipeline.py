from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .scraper import scrape_30
from .sentiment import FinancialSentiment, summarize


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"

DATA_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)


def run() -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat()

    print("[1/3] Collecting 30 latest business news articles...")
    items = scrape_30()

    print(f"Successfully collected {len(items)} articles.")

    (DATA_DIR / "news_raw.json").write_text(
        json.dumps(
            [x.to_dict() for x in items],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n[2/3] Running financial sentiment analysis...")
    engine = FinancialSentiment()
    results = engine.analyze(items)

    print("\n[3/3] Saving results...")

    summary = summarize(results)
    summary["fetched_at"] = fetched_at

    csv_path = RESULTS_DIR / "sentiment_results.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(results[0].to_dict().keys())

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for row in results:
            writer.writerow(row.to_dict())

    (RESULTS_DIR / "summary.json").write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return summary
