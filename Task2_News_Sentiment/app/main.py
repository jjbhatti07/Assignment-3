from __future__ import annotations

import csv
import json
from pathlib import Path

from flask import Flask, render_template

app = Flask(__name__)
ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "results" / "summary.json"
RESULTS = ROOT / "results" / "sentiment_results.csv"


def load_summary() -> dict:
    if SUMMARY.exists():
        return json.loads(SUMMARY.read_text(encoding="utf-8"))
    return {
        "total": 0,
        "positive": 0,
        "negative": 0,
        "neutral": 0,
        "sentiment_index": 0,
        "outlook": "Run the analysis first",
        "outlook_class": "mixed",
    }


def load_rows() -> list[dict]:
    if not RESULTS.exists():
        return []
    with RESULTS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@app.route("/")
def index():
    return render_template("index.html", summary=load_summary(), rows=load_rows())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
