from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import re
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
    chunks_analyzed: int

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

        self.client = InferenceClient(api_key=token)
        self.model = settings.hf_model

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 1800) -> list[str]:
        """
        Split text into small chunks.

        1800 characters is deliberately conservative for FinBERT's
        512-token limit. Chunks are created on sentence boundaries
        where possible.
        """
        text = re.sub(r"\s+", " ", (text or "")).strip()

        if not text:
            return []

        sentences = re.split(r"(?<=[.!?])\s+", text)

        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if not sentence:
                continue

            candidate = (
                sentence
                if not current
                else f"{current} {sentence}"
            )

            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)

                # Handle one extremely long sentence.
                while len(sentence) > max_chars:
                    chunks.append(sentence[:max_chars])
                    sentence = sentence[max_chars:]

                current = sentence

        if current:
            chunks.append(current)

        return chunks

    def _classify_chunk(self, text: str) -> dict[str, float | str]:
        last_error = None

        for attempt in range(1, 4):
            try:
                outputs = self.client.text_classification(
                    text,
                    model=self.model,
                    top_k=3,
                )

                probs = {
                    str(item.label).lower(): float(item.score)
                    for item in outputs
                }

                label = max(probs, key=probs.get)

                return {
                    "label": label,
                    "score": probs[label],
                    "positive_score": probs.get("positive", 0.0),
                    "negative_score": probs.get("negative", 0.0),
                    "neutral_score": probs.get("neutral", 0.0),
                }

            except Exception as exc:
                last_error = exc

                if attempt < 3:
                    wait = 2 ** attempt
                    print(
                        f"Warning: chunk classification failed "
                        f"(attempt {attempt}/3): {exc}"
                    )
                    print(f"Retrying in {wait} seconds...")
                    time.sleep(wait)

        raise RuntimeError(
            f"Failed to classify chunk after retries: {last_error}"
        )

    def classify_article(self, text: str) -> dict:
        chunks = self._chunk_text(text)

        if not chunks:
            return {
                "label": "NEUTRAL",
                "score": 0.0,
                "positive_score": 0.0,
                "negative_score": 0.0,
                "neutral_score": 0.0,
                "chunks_analyzed": 0,
            }

        positive_scores = []
        negative_scores = []
        neutral_scores = []

        successful_chunks = 0

        for chunk in chunks:
            try:
                result = self._classify_chunk(chunk)

                positive_scores.append(
                    float(result["positive_score"])
                )
                negative_scores.append(
                    float(result["negative_score"])
                )
                neutral_scores.append(
                    float(result["neutral_score"])
                )

                successful_chunks += 1

            except Exception as exc:
                print(f"Warning: skipped one chunk: {exc}")

        if successful_chunks == 0:
            return {
                "label": "NEUTRAL",
                "score": 0.0,
                "positive_score": 0.0,
                "negative_score": 0.0,
                "neutral_score": 0.0,
                "chunks_analyzed": 0,
            }

        positive = sum(positive_scores) / successful_chunks
        negative = sum(negative_scores) / successful_chunks
        neutral = sum(neutral_scores) / successful_chunks

        probabilities = {
            "POSITIVE": positive,
            "NEGATIVE": negative,
            "NEUTRAL": neutral,
        }

        label = max(probabilities, key=probabilities.get)

        return {
            "label": label,
            "score": probabilities[label],
            "positive_score": positive,
            "negative_score": negative,
            "neutral_score": neutral,
            "chunks_analyzed": successful_chunks,
        }

    def analyze(
        self,
        items: list[NewsItem],
    ) -> list[SentimentResult]:

        results: list[SentimentResult] = []

        for i, item in enumerate(items, 1):
            print(f"[{i}/30] {item.title}")

            prediction = self.classify_article(
                item.content
            )

            results.append(
                SentimentResult(
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    published=item.published,
                    label=str(
                        prediction["label"]
                    ).upper(),
                    score=float(
                        prediction["score"]
                    ),
                    positive_score=float(
                        prediction["positive_score"]
                    ),
                    negative_score=float(
                        prediction["negative_score"]
                    ),
                    neutral_score=float(
                        prediction["neutral_score"]
                    ),
                    chunks_analyzed=int(
                        prediction["chunks_analyzed"]
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

    for result in results:
        counts[result.label] = (
            counts.get(result.label, 0) + 1
        )

    positive = sum(
        result.positive_score
        for result in results
    )

    negative = sum(
        result.negative_score
        for result in results
    )

    neutral = sum(
        result.neutral_score
        for result in results
    )

    index = (
        (positive - negative) / total
        if total
        else 0.0
    )

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
