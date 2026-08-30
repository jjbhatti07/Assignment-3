
import os
from typing import Dict, List

from huggingface_hub import InferenceClient


class FinancialSentiment:
    """
    Financial sentiment analysis using Hugging Face Inference API.

    FinBERT has a maximum input length of 512 tokens, so long articles
    are divided into smaller chunks before classification.
    """

    def __init__(self):
        self.token = os.getenv("HF_TOKEN")

        if not self.token:
            raise RuntimeError(
                "HF_TOKEN is not set. "
                "Run: export HF_TOKEN='hf_...'"
            )

        self.model = "ProsusAI/finbert"

        self.client = InferenceClient(
            provider="hf-inference",
            api_key=self.token,
        )

        # Conservative size to stay safely below FinBERT's
        # 512-token maximum.
        self.chunk_words = 180

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split article text into smaller chunks.

        Word-based chunking is intentionally conservative because
        words can tokenize into multiple model tokens.
        """
        if not text:
            return []

        words = text.split()

        chunks = []

        for start in range(0, len(words), self.chunk_words):
            chunk = " ".join(words[start:start + self.chunk_words])

            if chunk.strip():
                chunks.append(chunk)

        return chunks

    def _classify_chunk(self, text: str) -> Dict[str, float]:
        """
        Send one text chunk to FinBERT and return all sentiment scores.
        """
        outputs = self.client.text_classification(
            text,
            model=self.model,
            top_k=3,
        )

        scores = {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 0.0,
        }

        for item in outputs:
            label = str(item.label).lower()
            score = float(item.score)

            if label in scores:
                scores[label] = score

        return scores

    def classify(self, text: str) -> Dict[str, object]:
        """
        Analyze an entire article.

        Each chunk is classified separately, then the sentiment
        probabilities are averaged to produce the article result.
        """
        chunks = self._chunk_text(text)

        if not chunks:
            return {
                "label": "neutral",
                "score": 0.0,
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "chunks": 0,
            }

        totals = {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 0.0,
        }

        successful_chunks = 0

        for number, chunk in enumerate(chunks, start=1):
            try:
                scores = self._classify_chunk(chunk)

                for label in totals:
                    totals[label] += scores[label]

                successful_chunks += 1

            except Exception as exc:
                print(
                    f"Warning: sentiment failed for chunk "
                    f"{number}/{len(chunks)}: {exc}"
                )

        if successful_chunks == 0:
            return {
                "label": "neutral",
                "score": 0.0,
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "chunks": 0,
            }

        averaged = {
            label: totals[label] / successful_chunks
            for label in totals
        }

        final_label = max(
            averaged,
            key=averaged.get,
        )

        return {
            "label": final_label,
            "score": round(averaged[final_label], 4),
            "positive": round(averaged["positive"], 4),
            "negative": round(averaged["negative"], 4),
            "neutral": round(averaged["neutral"], 4),
            "chunks": successful_chunks,
        }

    def analyze(self, items):
        """
        Analyze all collected news articles.
        """
        results = []

        total_items = len(items)

        for index, item in enumerate(items, start=1):
            print(
                f"[{index}/{total_items}] "
                f"Analyzing: {item.title}"
            )

            prediction = self.classify(item.content)

            results.append({
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "published": item.published,
                "sentiment": prediction["label"],
                "confidence": prediction["score"],
                "positive_score": prediction["positive"],
                "negative_score": prediction["negative"],
                "neutral_score": prediction["neutral"],
                "chunks_analyzed": prediction["chunks"],
            })

        return results


def summarize(results: list) -> dict:
    """
    Create the overall 30-news sentiment summary.

    The assignment asks us to determine whether the day's news
    indicates a good or poor environment for business and stock trading.
    """

    total = len(results)

    if total == 0:
        return {
            "total": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "positive_probability_sum": 0.0,
            "negative_probability_sum": 0.0,
            "neutral_probability_sum": 0.0,
            "sentiment_index": 0.0,
            "outlook": "NO NEWS AVAILABLE",
            "outlook_class": "mixed",
        }

    counts = {
        "POSITIVE": 0,
        "NEGATIVE": 0,
        "NEUTRAL": 0,
    }

    for result in results:
        label = str(
            result.get("sentiment", "neutral")
        ).upper()

        if label not in counts:
            label = "NEUTRAL"

        counts[label] += 1

    positive = sum(
        float(result.get("positive_score", 0.0))
        for result in results
    )

    negative = sum(
        float(result.get("negative_score", 0.0))
        for result in results
    )

    neutral = sum(
        float(result.get("neutral_score", 0.0))
        for result in results
    )

    average_positive = positive / total
    average_negative = negative / total
    average_neutral = neutral / total

    # Positive sentiment pushes the index upward.
    # Negative sentiment pushes the index downward.
    sentiment_index = average_positive - average_negative

    if (
        sentiment_index >= 0.10
        and counts["POSITIVE"] >= counts["NEGATIVE"]
    ):
        outlook = "GOOD DAY FOR BUSINESS AND STOCK TRADING"
        outlook_class = "good"

    elif (
        sentiment_index <= -0.10
        and counts["NEGATIVE"] > counts["POSITIVE"]
    ):
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
        "sentiment_index": round(sentiment_index, 4),
        "average_positive": round(average_positive, 4),
        "average_negative": round(average_negative, 4),
        "average_neutral": round(average_neutral, 4),
        "outlook": outlook,
        "outlook_class": outlook_class,
    }

