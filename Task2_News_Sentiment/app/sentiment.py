from __future__ import annotations

from dataclasses import asdict, dataclass
import os

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
    chunks_analyzed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class FinancialSentiment:
    """Financial sentiment analysis using Hugging Face FinBERT."""

    def __init__(self) -> None:
        token = settings.hf_token or os.getenv("HF_TOKEN", "")
        if not token:
            raise RuntimeError(
                "HF_TOKEN is not set. Create a Hugging Face User Access Token and "
                "run 'export HF_TOKEN=hf_...' before starting the analysis."
            )

        self.client = InferenceClient(
            provider="hf-inference",
            api_key=token,
        )
        self.model = settings.hf_model
        # FinBERT has a 512-token maximum. A conservative word chunk keeps
        # each request safely below that limit for normal English news text.
        self.chunk_words = 180

    @staticmethod
    def _chunks(text: str, chunk_words: int) -> list[str]:
        words = (text or "").split()
        return [
            " ".join(words[i:i + chunk_words])
            for i in range(0, len(words), chunk_words)
            if words[i:i + chunk_words]
        ]

    def _classify_chunk(self, text: str) -> dict[str, float]:
        outputs = self.client.text_classification(
            text,
            model=self.model,
            top_k=3,
        )

        probabilities = {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 0.0,
        }

        for output in outputs:
            label = str(output.label).lower()
            if label in probabilities:
                probabilities[label] = float(output.score)

        return probabilities

    def classify(self, text: str) -> dict[str, float | str | int]:
        chunks = self._chunks(text, self.chunk_words)

        if not chunks:
            return {
                "label": "neutral",
                "score": 0.0,
                "positive_score": 0.0,
                "negative_score": 0.0,
                "neutral_score": 1.0,
                "chunks_analyzed": 0,
            }

        totals = {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 0.0,
        }
        successful = 0

        for chunk in chunks:
            try:
                scores = self._classify_chunk(chunk)
            except Exception as exc:
                print(f"Warning: failed to classify one chunk: {exc}")
                continue

            for label in totals:
                totals[label] += scores[label]
            successful += 1

        if successful == 0:
            return {
                "label": "neutral",
                "score": 0.0,
                "positive_score": 0.0,
                "negative_score": 0.0,
                "neutral_score": 1.0,
                "chunks_analyzed": 0,
            }

        averaged = {
            label: totals[label] / successful
            for label in totals
        }
        label = max(averaged, key=averaged.get)

        return {
            "label": label,
            "score": averaged[label],
            "positive_score": averaged["positive"],
            "negative_score": averaged["negative"],
            "neutral_score": averaged["neutral"],
            "chunks_analyzed": successful,
        }

    def analyze(self, items: list[NewsItem]) -> list[SentimentResult]:
        results: list[SentimentResult] = []

        for item in items:
            pred = self.classify(item.content)
            results.append(
                SentimentResult(
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    published=item.published,
                    label=str(pred["label"]).upper(),
                    score=round(float(pred["score"]), 4),
                    positive_score=round(float(pred["positive_score"]), 4),
                    negative_score=round(float(pred["negative_score"]), 4),
                    neutral_score=round(float(pred["neutral_score"]), 4),
                    chunks_analyzed=int(pred["chunks_analyzed"]),
                )
            )

        return results


def summarize(results: list[SentimentResult]) -> dict:
    total = len(results)
    counts = {
        "POSITIVE": 0,
        "NEGATIVE": 0,
        "NEUTRAL": 0,
    }

    for result in results:
        counts[result.label] = counts.get(result.label, 0) + 1

    positive = sum(result.positive_score for result in results)
    negative = sum(result.negative_score for result in results)
    neutral = sum(result.neutral_score for result in results)
    index = (positive - negative) / total if total else 0.0

    if index >= 0.10 and counts["POSITIVE"] >= counts["NEGATIVE"]:
        outlook = "GOOD DAY FOR BUSINESS AND STOCK TRADING"
        outlook_class = "good"
    elif index <= -0.10 and counts["NEGATIVE"] > counts["POSITIVE"]:
        outlook = "NOT A GOOD DAY FOR BUSINESS AND STOCK TRADING"
        outlook_class = "bad"
    else:
        outlook = "MIXED / UNCERTAIN BUSINESS AND TRADING OUTLOOK"
        outlook_class = "mixed"

    return {
        "total": total,
        "positive": counts["POSITIVE"],
        "negative": counts["NEGATIVE"],
        "neutral": counts["NEUTRAL"],
        "positive_probability_sum": round(positive, 4),
        "negative_probability_sum": round(negative, 4),
        "neutral_probability_sum": round(neutral, 4),
        "sentiment_index": round(index, 4),
        "outlook": outlook,
        "outlook_class": outlook_class,
    }
