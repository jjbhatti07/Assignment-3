# Assignment 02 — Task 2: Business News Scraper + Sentiment Analysis

This project implements the exact Task 2 requirements from the assignment PDF:

1. Scrape the latest business news from:
   - https://tribune.com.pk/business
   - https://profit.pakistantoday.com.pk/category/business
2. Collect 30 complete news articles (15 from each source by default).
3. Run Hugging Face financial sentiment analysis on all 30 articles.
4. Report positive, neutral and negative counts.
5. Compute an aggregate sentiment index and determine whether the day is good, bad, or mixed for business and stock trading.
6. Save raw news and article-level results to files and show them in a Flask dashboard.

## Why FinBERT?

The project uses `ProsusAI/finbert`, a financial sentiment model. Hugging Face's current task documentation recommends FinBERT for financial sentiment classification.

## Requirements

Python 3.10+ and internet access are required. No local Hugging Face model is downloaded; inference is sent to Hugging Face's hosted inference service, which keeps disk usage low.

## Setup (Ubuntu/Linux)

```bash
cd news-sentiment-task2
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Create a Hugging Face User Access Token, then:

```bash
export HF_TOKEN="hf_your_token_here"
```

Run the complete pipeline:

```bash
python run_analysis.py
```

Expected files:

```text
data/news_raw.json
results/sentiment_results.csv
results/summary.json
```

Start the dashboard:

```bash
python -m app.main
```

Open:

```text
http://127.0.0.1:5000
```

## How the final decision is calculated

For each article, FinBERT returns positive/negative/neutral probabilities. The program calculates:

`sentiment_index = (sum(positive probabilities) - sum(negative probabilities)) / 30`

Decision rule:

- index >= 0.10 and positive count >= negative count → GOOD DAY
- index <= -0.10 and negative count > positive count → NOT A GOOD DAY
- otherwise → MIXED / UNCERTAIN

This is a transparent academic rule for the assignment, not investment advice.

## Viva/demo flow

1. Show the two required source URLs.
2. Run `python run_analysis.py`.
3. Show that exactly 30 articles were collected.
4. Open `results/sentiment_results.csv` and explain the label + confidence for each article.
5. Open the Flask dashboard and explain the overall decision.
6. Explain that Hugging Face hosted inference is used so no large local model is stored on the 6.4 GB free disk.
