from app.pipeline import run

if __name__ == "__main__":
    summary = run()
    print("\n=== TASK 2 RESULTS ===")
    for key in ["total", "positive", "negative", "neutral", "sentiment_index", "outlook"]:
        print(f"{key}: {summary[key]}")
