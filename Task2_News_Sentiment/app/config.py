from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    tribune_url: str = os.getenv("TRIBUNE_URL", "https://tribune.com.pk/business")
    profit_url: str = os.getenv("PROFIT_URL", "https://profit.pakistantoday.com.pk/category/business")
    hf_model: str = os.getenv("HF_MODEL", "ProsusAI/finbert")
    hf_token: str = os.getenv("HF_TOKEN", "")
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    per_source: int = int(os.getenv("PER_SOURCE", "15"))
    total_articles: int = int(os.getenv("TOTAL_ARTICLES", "30"))


settings = Settings()
