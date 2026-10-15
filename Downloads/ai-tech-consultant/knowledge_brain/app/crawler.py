"""Polite fetching + HTML/sitemap parsing."""
import asyncio, hashlib, re, time
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
import httpx
from bs4 import BeautifulSoup
from . import config

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
UA = "KnowledgeBrainBot/1.0 (student project; polite crawler; contact: see repo README)"

class PoliteFetcher:
    """Global rate limit (one request per CRAWL_MIN_DELAY_S across all workers), bounded concurrency,
    exponential backoff on 5xx/timeouts, and honours Retry-After on 429/503."""
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None,
                 min_delay: float | None = None, retries: int | None = None):
        self.client = httpx.AsyncClient(transport=transport, headers={"User-Agent": UA},
                                        timeout=20, follow_redirects=True)
        self.min_delay = config.CRAWL_MIN_DELAY_S if min_delay is None else min_delay
        self.retries = config.CRAWL_MAX_RETRIES if retries is None else retries
        self._gate = asyncio.Lock(); self._last = 0.0

    async def _wait_turn(self) -> None:
        async with self._gate:
            gap = self._last + self.min_delay - time.monotonic()
            if gap > 0: await asyncio.sleep(gap)
            self._last = time.monotonic()

    async def get(self, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            await self._wait_turn()
            try:
                r = await self.client.get(url)
                if r.status_code in (429, 503) or r.status_code >= 500:
                    retry_after = r.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.isdigit() else min(60, 2 ** attempt)
                    await asyncio.sleep(delay if self.min_delay else 0); continue
                return r
            except httpx.HTTPError as e:
                last_exc = e; await asyncio.sleep(min(60, 2 ** attempt) if self.min_delay else 0)
        raise RuntimeError(f"giving up on {url}: {last_exc or 'server errors'}")

    async def close(self) -> None: await self.client.aclose()

def parse_sitemap(xml: str) -> tuple[dict[str, str | None], list[str]]:
    """Returns ({page_url: lastmod}, [child sitemap urls])."""
    root = ET.fromstring(xml)
    pages = {u.findtext(f"{NS}loc", "").strip(): u.findtext(f"{NS}lastmod")
             for u in root.iter(f"{NS}url") if u.findtext(f"{NS}loc")}
    subs = [s.findtext(f"{NS}loc", "").strip() for s in root.iter(f"{NS}sitemap")]
    return pages, [s for s in subs if s]

async def collect_urls(fetcher: PoliteFetcher, sitemap_url: str) -> dict[str, str | None]:
    r = await fetcher.get(sitemap_url); r.raise_for_status()
    pages, subs = parse_sitemap(r.text)
    for sub in subs:
        rr = await fetcher.get(sub); rr.raise_for_status()
        pages.update(parse_sitemap(rr.text)[0])
    return pages

_SKIP_IMG = re.compile(r"(icon|logo|avatar|sprite|emoji|badge|pixel|spacer)|\.(svg|gif)(\?|$)", re.I)

def extract_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header", "noscript", "form"]): t.decompose()
    crumbs = [a.get_text(strip=True) for a in soup.select("ol.breadcrumb li, .breadcrumb li, nav[aria-label=breadcrumb] li")]
    crumbs = [c for c in crumbs if c]
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else url)
    body = (soup.select_one(".article-body, .article-content, article, main") or soup.body or soup)
    imgs = []
    for img in body.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src or src.startswith("data:") or _SKIP_IMG.search(src): continue
        imgs.append({"src": urljoin(url, src), "alt": (img.get("alt") or "").strip()})
    text = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True))
    # Category/folder: breadcrumb if present (…, category, folder, article), else URL path fallback.
    category = crumbs[-3] if len(crumbs) >= 3 else (crumbs[0] if crumbs else None)
    folder = crumbs[-2] if len(crumbs) >= 2 else None
    return {"title": title, "text": text, "images": imgs, "category": category, "folder": folder,
            "hash": hashlib.sha256(text.encode()).hexdigest()}

def chunk_text(title: str, text: str, size: int = 900, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 > size and cur:
            chunks.append(cur); cur = cur[-overlap:] + "\n" + p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur: chunks.append(cur)
    return [f"{title}\n{c}" for c in chunks] or [title]
