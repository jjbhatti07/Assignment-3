from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .config import settings

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0 Safari/537.36"
)

BUSINESS_TERMS = {
    "business", "businesses", "economy", "economic", "finance", "financial",
    "market", "markets", "stocks", "stock", "psx", "investment", "investor",
    "investors", "trade", "trading", "export", "exports", "import", "imports",
    "industry", "industrial", "manufacturing", "company", "companies",
    "corporate", "tax", "taxes", "fiscal", "bank", "banks", "banking",
    "debt", "inflation", "energy", "oil", "gas", "power", "telecom",
    "technology", "startup", "startups", "retail", "agriculture", "farming",
    "food", "construction", "real estate", "property", "currency", "rupee",
    "dollar", "imf", "sbp", "fbr", "securities", "commodity", "commodities",
}

NON_BUSINESS_TERMS = {
    "cricket", "football", "soccer", "tennis", "squash", "hockey",
    "match", "matches", "innings", "wicket", "wickets", "goal", "goals",
    "tournament", "marathon", "olympics", "athlete", "athletes", "player",
    "players", "coach", "coaches", "team", "teams", "sport", "sports",
    "election", "elections", "politics", "political", "minister", "ministers",
    "president", "prime minister", "senate", "assembly", "parliament",
    "mna", "mps", "pti", "pml-n", "ppp", "imran khan", "crime", "killed",
    "killing", "murder", "police", "armed clash", "attack", "terror",
    "terrorist", "court", "judge", "judiciary", "visa denial",
}

ALLOWED_SECTIONS = {
    "business", "economy", "economic", "finance", "financial", "markets",
    "market", "money", "corporate", "industry", "industries",
}

@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    published: str = ""
    content: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class NewsScraper:
    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.request_timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.8",
            }
        )

    def fetch(self, url: str) -> str:
        response = self.session.get(
            url,
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        response.encoding = response.encoding or response.apparent_encoding or "utf-8"
        return response.text

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _normalise_url(url: str) -> str:
        p = urlparse(url)
        return urlunparse(
            (p.scheme, p.netloc, p.path.rstrip("/"), "", "", "")
        )

    @staticmethod
    def _same_domain(url: str, base_url: str) -> bool:
        a = urlparse(url).netloc.lower().split(":")[0]
        b = urlparse(base_url).netloc.lower().split(":")[0]
        return a == b or a.endswith("." + b) or b.endswith("." + a)

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        value = value.strip()
        if not value:
            return None

        candidates = [
            value.replace("Z", "+00:00"),
            value,
        ]

        for candidate in candidates:
            try:
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                pass

        for fmt in (
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        return None

    @classmethod
    def _is_recent(cls, published: str, max_age_days: int) -> bool:
        dt = cls._parse_date(published)
        if dt is None:
            return False
        now = datetime.now(timezone.utc)
        return now - timedelta(days=max_age_days) <= dt <= now + timedelta(days=1)

    @classmethod
    def _business_score(cls, title: str, section: str) -> int:
        text = f"{section} {title}".lower()

        section_parts = {
            p.strip() for p in re.split(r"[,/|>]+", section.lower()) if p.strip()
        }

        score = 0
        if any(any(k == part or k in part for part in section_parts) for k in ALLOWED_SECTIONS):
            score += 5

        score += sum(1 for term in BUSINESS_TERMS if term in text)
        score -= sum(2 for term in NON_BUSINESS_TERMS if term in text)

        return score

    @classmethod
    def _is_business_article(cls, title: str, section: str, source: str) -> bool:
        if len(title) < 15:
            return False

        lower_title = title.lower()

        # Hard rejection for clearly unrelated content.
        if any(term in lower_title for term in NON_BUSINESS_TERMS):
            # Permit a few terms when a clearly business/finance term is also present.
            business_present = any(term in lower_title for term in BUSINESS_TERMS)
            if not business_present:
                return False

        # Structured articleSection is the strongest signal.
        normalized_section = section.lower()
        if normalized_section:
            if any(k in normalized_section for k in ALLOWED_SECTIONS):
                return True

            # A known non-business section should be rejected.
            if any(k in normalized_section for k in {
                "sports", "sport", "pakistan", "world", "entertainment",
                "life & style", "lifestyle", "opinion", "blogs",
            }):
                return False

        return cls._business_score(title, section) >= 2

    @staticmethod
    def _json_ld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []

        for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = node.string or node.get_text()
            if not raw.strip():
                continue

            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            values: list[Any] = []
            if isinstance(parsed, dict):
                values.append(parsed)
                graph = parsed.get("@graph")
                if isinstance(graph, list):
                    values.extend(graph)
            elif isinstance(parsed, list):
                values.extend(parsed)

            objects.extend(x for x in values if isinstance(x, dict))

        return objects

    def _listing_links(
        self,
        html: str,
        base_url: str,
        source: str,
        limit: int,
    ) -> list[NewsItem]:
        soup = BeautifulSoup(html, "html.parser")

        # Prefer main/article content over navigation/header links.
        containers = []
        for selector in ("main", "article", "[role='main']", ".site-main", ".content"):
            found = soup.select_one(selector)
            if found is not None:
                containers.append(found)

        roots = containers or [soup]

        candidates: list[NewsItem] = []
        seen: set[str] = set()

        for root in roots:
            for a in root.find_all("a", href=True):
                title = self._clean(a.get_text(" ", strip=True))
                href = (a.get("href") or "").strip()

                if not title or not href:
                    continue

                url = self._normalise_url(urljoin(base_url, href))

                if not url.startswith(("http://", "https://")):
                    continue
                if not self._same_domain(url, base_url):
                    continue
                if url in seen:
                    continue

                path = urlparse(url).path.lower()

                if source == "Profit Pakistan Today":
                    is_article_url = bool(
                        re.search(r"/\d{4}/\d{2}/\d{2}/[^/]+", path)
                    )
                else:
                    is_article_url = "/story/" in path or "/business/" in path

                if not is_article_url:
                    continue

                if any(
                    blocked in path
                    for blocked in (
                        "/tag/", "/category/", "/author/", "/search",
                        "/page/", "/feed", "/wp-json/", "/subscribe",
                        "/login", "/about/", "/contact/"
                    )
                ):
                    continue

                if len(title) < 15:
                    continue

                seen.add(url)
                candidates.append(
                    NewsItem(
                        source=source,
                        title=title,
                        url=url,
                    )
                )

                if len(candidates) >= limit:
                    return candidates

        return candidates

    def _extract_article(self, item: NewsItem) -> tuple[NewsItem, str]:
        html = self.fetch(item.url)
        soup = BeautifulSoup(html, "html.parser")
        objects = self._json_ld_objects(soup)

        section = ""

        # First pass: structured Article JSON-LD.
        for obj in objects:
            types = obj.get("@type", "")
            types = types if isinstance(types, list) else [types]

            if not any(
                str(t).lower() in {"article", "newsarticle", "reportagearticle"}
                for t in types
            ):
                continue

            headline = self._clean(str(obj.get("headline", "")))
            if len(headline) >= 15:
                item.title = headline

            item.published = self._clean(
                str(
                    obj.get("datePublished")
                    or obj.get("dateCreated")
                    or ""
                )
            )

            raw_section = obj.get("articleSection", "")
            if isinstance(raw_section, list):
                section = " ".join(str(x) for x in raw_section)
            else:
                section = self._clean(str(raw_section))

            body = obj.get("articleBody", "")
            if isinstance(body, str):
                body = self._clean(body)
                if len(body) >= 120:
                    item.content = body
                    return item, section

        # Fallback metadata.
        time_tag = soup.find("time")
        if time_tag and not item.published:
            item.published = self._clean(
                time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
            )

        if not item.published:
            for attrs in (
                {"property": "article:published_time"},
                {"name": "pubdate"},
                {"name": "date"},
            ):
                meta = soup.find("meta", attrs=attrs)
                if meta:
                    item.published = self._clean(meta.get("content", ""))
                    if item.published:
                        break

        if not section:
            meta_section = soup.find("meta", attrs={"property": "article:section"})
            if meta_section:
                section = self._clean(meta_section.get("content", ""))

        for tag in soup(
            ["script", "style", "noscript", "svg", "nav", "footer",
             "header", "form", "aside"]
        ):
            tag.decompose()

        title_node = soup.find("h1")
        if title_node:
            title = self._clean(title_node.get_text(" ", strip=True))
            if len(title) >= 15:
                item.title = title

        selectors = [
            "[itemprop='articleBody']",
            ".story-detail",
            ".story-detail-content",
            ".story-detail__content",
            ".detail-content",
            ".entry-content",
            ".single-post-content",
            ".article-content",
            ".post-content",
            ".article-body",
            "article",
            "main",
        ]

        best = ""
        for selector in selectors:
            root = soup.select_one(selector)
            if root is None:
                continue

            paragraphs = []
            for p in root.find_all(["p", "li"]):
                text = self._clean(p.get_text(" ", strip=True))
                if len(text) >= 25:
                    paragraphs.append(text)

            candidate = self._clean(" ".join(paragraphs))
            if len(candidate) > len(best):
                best = candidate

        if not best:
            paragraphs = []
            for p in soup.find_all("p"):
                text = self._clean(p.get_text(" ", strip=True))
                if len(text) >= 25:
                    paragraphs.append(text)
            best = self._clean(" ".join(paragraphs))

        item.content = best
        return item, section

    @staticmethod
    def _page_urls(listing_url: str, page: int) -> list[str]:
        if page == 1:
            return [listing_url]

        parsed = urlparse(listing_url)
        base_path = parsed.path.rstrip("/")

        urls = [
            urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    f"{base_path}/page/{page}",
                    "",
                    parsed.query,
                    "",
                )
            )
        ]

        # Some Tribune pages use ?page=N.
        query = parsed.query
        extra = f"{query}&page={page}" if query else f"page={page}"
        urls.append(
            urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    "",
                    extra,
                    "",
                )
            )
        )

        return urls

    def scrape_source(
        self,
        listing_url: str,
        source: str,
        limit: int,
        max_pages: int = 8,
        max_age_days: int = 30,
    ) -> list[NewsItem]:
        results: list[NewsItem] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()

        for page in range(1, max_pages + 1):
            html = None

            for page_url in self._page_urls(listing_url, page):
                try:
                    html = self.fetch(page_url)
                    break
                except requests.RequestException:
                    continue

            if html is None:
                continue

            candidates = self._listing_links(
                html,
                listing_url,
                source,
                limit * 8,
            )

            for candidate in candidates:
                if candidate.url in seen_urls:
                    continue

                seen_urls.add(candidate.url)

                try:
                    full, section = self._extract_article(candidate)
                except (requests.RequestException, ValueError):
                    continue
                finally:
                    time.sleep(0.15)

                if not self._is_recent(full.published, max_age_days):
                    continue

                if not self._is_business_article(
                    full.title,
                    section,
                    source,
                ):
                    continue

                if len(full.content) < 120:
                    continue

                key = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    full.title.lower(),
                ).strip()

                if key in seen_titles:
                    continue

                seen_titles.add(key)
                results.append(full)

                if len(results) >= limit:
                    return results

        return results


def scrape_30() -> list[NewsItem]:
    per_source = max(
        1,
        settings.total_articles // 2,
        settings.per_source,
    )

    scraper = NewsScraper()

    # Tribune Business.
    tribune = scraper.scrape_source(
        "https://tribune.com.pk/business",
        "Express Tribune",
        per_source,
        max_pages=8,
        max_age_days=30,
    )

    # Profit's business page is the primary source. Its page includes
    # a recent "Latest News" section as well as older curated posts;
    # article dates are therefore validated after opening each article.
    profit = scraper.scrape_source(
        "https://profit.pakistantoday.com.pk/category/business",
        "Profit Pakistan Today",
        per_source,
        max_pages=8,
        max_age_days=30,
    )

    # If the business page does not yield enough recent articles, use
    # Profit's economy/business-news sections as an additional pool,
    # while keeping the same source label.
    if len(profit) < per_source:
        for fallback_url in (
            "https://profit.pakistantoday.com.pk/category/economy",
            "https://profit.pakistantoday.com.pk/category/world-business-news",
        ):
            needed = per_source - len(profit)
            if needed <= 0:
                break

            extra = scraper.scrape_source(
                fallback_url,
                "Profit Pakistan Today",
                needed,
                max_pages=8,
                max_age_days=30,
            )

            known = {x.url for x in profit}
            for item in extra:
                if item.url not in known:
                    profit.append(item)
                    known.add(item.url)

    if len(tribune) < per_source or len(profit) < per_source:
        raise RuntimeError(
            "Could not collect 15 recent business articles from each "
            f"required source. Tribune={len(tribune)}, Profit={len(profit)}. "
            "The scraper intentionally rejects old and non-business articles."
        )

    items = tribune[:per_source] + profit[:per_source]

    # Final safety checks.
    unique_urls = {item.url for item in items}
    if len(items) != settings.total_articles or len(unique_urls) != len(items):
        raise RuntimeError(
            f"Expected {settings.total_articles} unique articles, "
            f"but collected {len(items)}."
        )

    return items
