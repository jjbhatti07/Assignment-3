from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import time

from huggingface_hub import InferenceClient

from .config import settings
from .scraper import NewsItem


@dataclass
class SentimentResult:
    source: str
    title: str
    url: str
    published: str
    label: str
    score: float
    positive_score: float
    negative_score: float
    neutral_score: float

    def to_dict(self) -> dict:
        return asdict(self)


class FinancialSentiment:
    def __init__(self) -> None:
        token = settings.hf_token or os.getenv("HF_TOKEN", "")

        if not token:
            raise RuntimeError(
                "HF_TOKEN is not set. Run:\n"
                "export HF_TOKEN='hf_...'"
            )

        self.client = InferenceClient(
            api_key=token
        )

        self.model = settings.hf_model

    def classify(self, text: str) -> dict[str, float | str]:
        # Keep input reasonably sized for FinBERT.
        text = (text or "").strip()

        if not text:
            return {
                "label": "neutral",
                "score": 0.0,
                "positive_score": 0.0,
                "negative_score": 0.0,
                "neutral_score": 0.0,
            }

        # Retry transient Hugging Face gateway/time-out errors.
        last_error = None

        for attempt in range(1, 4):
            try:
                outputs = self.client.text_classification(
                    text[:12000],
                    model=self.model,
                    top_k=3,
                )

                probs = {
                    str(x.label).lower(): float(x.score)
                    for x in outputs
                }

                label = max(
                    probs,
                    key=probs.get,
                )

                return {
                    "label": label,
                    "score": probs[label],
                    "positive_score": probs.get(
                        "positive", 0.0
                    ),
                    "negative_score": probs.get(
                        "negative", 0.0
                    ),
                    "neutral_score": probs.get(
                        "neutral", 0.0
                    ),
                }

            except Exception as exc:
                last_error = exc

                if attempt < 3:
                    wait = 2 ** attempt
                    print(
                        f"Warning: sentiment request failed "
                        f"(attempt {attempt}/3): {exc}"
                    )
                    print(
                        f"Retrying in {wait} seconds..."
                    )
                    time.sleep(wait)

        # Don't crash the whole 30-article assignment
        # because of one transient inference failure.
        print(
            f"Warning: failed to classify one article after retries: "
            f"{last_error}"
        )

        return {
            "label": "neutral",
            "score": 0.0,
            "positive_score": 0.0,
            "negative_score": 0.0,
            "neutral_score": 0.0,
        }

    def analyze(
        self,
        items: list[NewsItem],
    ) -> list[SentimentResult]:

        results: list[SentimentResult] = []

        for i, item in enumerate(items, 1):
            print(
                f"[{i}/{len(items)}] {item.title}"
            )

            pred = self.classify(
                item.content
            )

            results.append(
                SentimentResult(
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    published=item.published,
                    label=str(
                        pred["label"]
                    ).upper(),
                    score=float(
                        pred["score"]
                    ),
                    positive_score=float(
                        pred["positive_score"]
                    ),
                    negative_score=float(
                        pred["negative_score"]
                    ),
                    neutral_score=float(
                        pred["neutral_score"]
                    ),
                )
            )

        return results


def summarize(
    results: list[SentimentResult],
) -> dict:

    total = len(results)

    counts = {
        "POSITIVE": 0,
        "NEGATIVE": 0,
        "NEUTRAL": 0,
    }

    for r in results:
        counts[r.label] = (
            counts.get(r.label, 0) + 1
        )

    positive = sum(
        r.positive_score
        for r in results
    )

    negative = sum(
        r.negative_score
        for r in results
    )

    neutral = sum(
        r.neutral_score
        for r in results
    )

    index = (
        (positive - negative) / total
        if total
        else 0.0
    )

    if (
        index >= 0.10
        and counts["POSITIVE"] >= counts["NEGATIVE"]
    ):
        outlook = (
            "GOOD DAY FOR BUSINESS AND STOCK TRADING"
        )
        outlook_class = "good"

    elif (
        index <= -0.10
        and counts["NEGATIVE"] > counts["POSITIVE"]
    ):
        outlook = (
            "NOT A GOOD DAY FOR BUSINESS AND STOCK TRADING"
        )
        outlook_class = "bad"

    else:
        outlook = (
            "MIXED / UNCERTAIN BUSINESS AND TRADING OUTLOOK"
        )
        outlook_class = "mixed"

    return {
        "total": total,
        "positive": counts["POSITIVE"],
        "negative": counts["NEGATIVE"],
        "neutral": counts["NEUTRAL"],
        "positive_probability_sum": round(
            positive, 4
        ),
        "negative_probability_sum": round(
            negative, 4
        ),
        "neutral_probability_sum": round(
            neutral, 4
        ),
        "sentiment_index": round(
            index, 4
        ),
        "outlook": outlook,
        "outlook_class": outlook_class,
    }
