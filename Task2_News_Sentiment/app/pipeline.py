
import csv
import json
from pathlib import Path

from .scraper import scrape_30
from .sentiment import FinancialSentiment, summarize


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

RAW_FILE = DATA_DIR / "news_raw.json"
CSV_FILE = RESULTS_DIR / "sentiment_results.csv"
SUMMARY_FILE = RESULTS_DIR / "summary.json"


def run():
    """
    Complete Task 2 pipeline:

    1. Scrape 30 current business news articles.
    2. Run financial sentiment analysis.
    3. Save raw news.
    4. Save article-level sentiment results.
    5. Save overall summary.
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("BUSINESS NEWS SENTIMENT ANALYSIS")
    print("=" * 70)

    # ---------------------------------------------------------
    # STEP 1: SCRAPE 30 NEWS ARTICLES
    # ---------------------------------------------------------
    print("\n[1/3] Collecting 30 latest business news articles...\n")

    items = scrape_30()

    if len(items) != 30:
        raise RuntimeError(
            f"Expected 30 articles but received {len(items)}."
        )

    print(f"\nSuccessfully collected {len(items)} articles.")

    # Save raw scraped news.
    raw_data = []

    for item in items:
        raw_data.append(
            {
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "published": item.published,
                "content": item.content,
            }
        )

    RAW_FILE.write_text(
        json.dumps(raw_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # STEP 2: SENTIMENT ANALYSIS
    # ---------------------------------------------------------
    print("\n[2/3] Running financial sentiment analysis...\n")

    engine = FinancialSentiment()
    results = engine.analyze(items)

    if len(results) != 30:
        raise RuntimeError(
            f"Expected 30 sentiment results but received {len(results)}."
        )

    # ---------------------------------------------------------
    # STEP 3: SAVE RESULTS
    # ---------------------------------------------------------
    print("\n[3/3] Saving results...\n")

    # Our sentiment analyzer returns dictionaries directly,
    # so we write them directly to CSV.
    fieldnames = [
        "source",
        "title",
        "url",
        "published",
        "sentiment",
        "confidence",
        "positive_score",
        "negative_score",
        "neutral_score",
        "chunks_analyzed",
    ]

    with CSV_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(results)

    # Create overall summary.
    summary = summarize(results)

    SUMMARY_FILE.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # DISPLAY FINAL RESULT
    # ---------------------------------------------------------
    print("=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)

    print(f"Total articles : {summary['total']}")
    print(f"Positive       : {summary['positive']}")
    print(f"Negative       : {summary['negative']}")
    print(f"Neutral        : {summary['neutral']}")

    print(
        f"Sentiment index: "
        f"{summary['sentiment_index']}"
    )

    print(
        "\nOVERALL BUSINESS / TRADING OUTLOOK:"
    )

    print(
        summary["outlook"]
    )

    print("\nFiles created:")

    print(f"Raw news      : {RAW_FILE}")
    print(f"Sentiment CSV : {CSV_FILE}")
    print(f"Summary       : {SUMMARY_FILE}")

    print("=" * 70)

    return summary

