from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .config import settings

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0 Safari/537.36"
)


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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _same_domain(url: str, base_url: str) -> bool:
        a = urlparse(url).netloc.lower().split(":")[0]
        b = urlparse(base_url).netloc.lower().split(":")[0]
        return a == b or a.endswith("." + b) or b.endswith("." + a)

    @staticmethod
    def _normalise_url(url: str) -> str:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))

    @staticmethod
    def _is_probable_article(url: str, title: str, source: str) -> bool:
        path = urlparse(url).path.lower()
        title = title.strip()
        if len(title) < 15:
            return False
        blocked = (
            "/tag/",
            "/category/",
            "/author/",
            "/search",
            "/page/",
            "/archives",
            "/feed",
            "/wp-json",
            "/subscribe",
            "/login",
            "/about",
            "/contact",
        )
        if any(x in path for x in blocked):
            return False
        if source == "Profit Pakistan Today":
            # Profit article URLs are date-based, e.g. /2026/08/28/article-title
            return bool(re.search(r"/\d{4}/\d{2}/\d{2}/[^/]+", path))
        # Tribune uses story-like URLs inside /business or section paths.
        return "/business" in path or "/story/" in path or len(path.strip("/").split("/")) >= 2

    def _listing_links(self, html: str, base_url: str, source: str, limit: int) -> list[NewsItem]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[NewsItem] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            title = self._clean(a.get_text(" ", strip=True))
            href = (a.get("href") or "").strip()
            if not href:
                continue
            url = self._normalise_url(urljoin(base_url, href))
            if not url.startswith(("http://", "https://")):
                continue
            if not self._same_domain(url, base_url):
                continue
            if url in seen:
                continue
            if not self._is_probable_article(url, title, source):
                continue
            seen.add(url)
            candidates.append(NewsItem(source=source, title=title, url=url))
            if len(candidates) >= limit:
                break

        return candidates

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
            if isinstance(parsed, dict):
                objects.append(parsed)
            elif isinstance(parsed, list):
                objects.extend(x for x in parsed if isinstance(x, dict))
            elif isinstance(parsed, dict) and isinstance(parsed.get("@graph"), list):
                objects.extend(x for x in parsed["@graph"] if isinstance(x, dict))
        # Expand @graph from objects collected above.
        expanded: list[dict[str, Any]] = []
        for obj in objects:
            expanded.append(obj)
            graph = obj.get("@graph")
            if isinstance(graph, list):
                expanded.extend(x for x in graph if isinstance(x, dict))
        return expanded

    def _extract_article(self, item: NewsItem) -> NewsItem:
        html = self.fetch(item.url)
        soup = BeautifulSoup(html, "html.parser")
        json_objects = self._json_ld_objects(soup)

        # Structured data is more stable than CSS selectors on both sites.
        for obj in json_objects:
            obj_type = obj.get("@type", "")
            types = obj_type if isinstance(obj_type, list) else [obj_type]
            if any(str(t).lower() in {"article", "newsarticle", "reportagearticle"} for t in types):
                headline = self._clean(str(obj.get("headline", "")))
                if len(headline) >= 15:
                    item.title = headline
                published = obj.get("datePublished") or obj.get("dateCreated") or ""
                item.published = self._clean(str(published))
                body = obj.get("articleBody") or ""
                if isinstance(body, str) and len(self._clean(body)) >= 120:
                    item.content = self._clean(body)
                    return item

        # Remove obvious non-content elements.
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside"]):
            tag.decompose()

        title_node = soup.find("h1")
        if title_node:
            extracted_title = self._clean(title_node.get_text(" ", strip=True))
            if len(extracted_title) >= 15:
                item.title = extracted_title

        time_tag = soup.find("time")
        if time_tag:
            item.published = self._clean(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
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

        content_selectors = [
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
        roots = [soup.select_one(selector) for selector in content_selectors]
        roots = [r for r in roots if r is not None]

        best = ""
        for root in roots:
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
        return item

    def _page_url(self, listing_url: str, page: int) -> str:
        if page == 1:
            return listing_url
        parsed = urlparse(listing_url)
        query = parse_qs(parsed.query)
        query["page"] = [str(page)]
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query, doseq=True), parsed.fragment))

    def scrape_source(self, listing_url: str, source: str, limit: int, max_pages: int = 6) -> list[NewsItem]:
        results: list[NewsItem] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()

        for page in range(1, max_pages + 1):
            page_url = self._page_url(listing_url, page)
            try:
                html = self.fetch(page_url)
            except requests.RequestException:
                continue

            candidates = self._listing_links(html, page_url, source, limit * 4)
            if not candidates:
                # If pagination has ended, there is nothing more useful to try.
                if page > 1:
                    break
                continue

            for item in candidates:
                if len(results) >= limit:
                    return results
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                try:
                    full = self._extract_article(item)
                except (requests.RequestException, ValueError):
                    continue
                finally:
                    time.sleep(0.2)

                if len(full.content) < 120:
                    continue
                key = re.sub(r"[^a-z0-9]+", " ", full.title.lower()).strip()
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                results.append(full)

        return results


def scrape_30() -> list[NewsItem]:
    per_source = max(1, settings.total_articles // 2)
    scraper = NewsScraper()

    tribune = scraper.scrape_source(settings.tribune_url, "Express Tribune", per_source)
    profit = scraper.scrape_source(settings.profit_url, "Profit Pakistan Today", per_source)

    items = tribune + profit
    if len(items) < settings.total_articles:
        raise RuntimeError(
            f"Only {len(items)} complete articles were collected "
            f"({len(tribune)} from Express Tribune, {len(profit)} from Profit Pakistan Today). "
            f"The assignment requires {settings.total_articles}. "
            "Check internet access, site availability, or increase MAX_PAGES in scraper.py."
        )
    return items[: settings.total_articles]
