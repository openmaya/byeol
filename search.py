import re
import time as _time
import logging
import feedparser
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import CHROMIUM_PATH, CHROMEDRIVER_PATH

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

logger = logging.getLogger(__name__)


def _create_driver():
    options = Options()
    if CHROMIUM_PATH:
        options.binary_location = CHROMIUM_PATH
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--password-store=basic")
    options.add_argument("--use-mock-keychain")
    options.add_argument("--disable-features=Translate")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
    if CHROMEDRIVER_PATH:
        service = Service(executable_path=CHROMEDRIVER_PATH)
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)


def web_search(query: str, max_results: int = 5) -> list[dict]:
    driver = _create_driver()
    results = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={query}"
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".result"))
        )
        items = driver.find_elements(By.CSS_SELECTOR, ".result")[:max_results]
        for item in items:
            try:
                title_el = item.find_element(By.CSS_SELECTOR, ".result__a")
                snippet_el = item.find_elements(By.CSS_SELECTOR, ".result__snippet")
                results.append({
                    "title": title_el.text,
                    "url": title_el.get_attribute("href"),
                    "snippet": snippet_el[0].text if snippet_el else "",
                })
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Search failed: {e}")
    finally:
        driver.quit()
    return results


def fetch_page(url: str, max_chars: int = 5000) -> str:
    if len(url) > 500:
        return "[Error: URL too long. Use a shorter, cleaner URL.]"
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text.strip()) < 50:
            title = soup.title.string if soup.title else ""
            return f"[Page title: {title}]\n[Content could not be extracted]"
        return text[:max_chars]
    except Exception as e:
        logger.warning(f"Fetch failed for {url}: {e}")
        return f"[Error loading page: {e}]"


def fetch_exchange_rate(base: str = "USD", target: str = "KRW") -> dict:
    """Fetch exchange rate from frankfurter.dev (free, no key required)."""
    try:
        resp = requests.get(
            f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={target}",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"][target]
        return {"ok": True, "base": base, "target": target, "rate": rate, "date": data.get("date", "")}
    except Exception as e:
        logger.warning(f"Exchange rate fetch failed: {e}")
        return {"ok": False, "error": str(e)}


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_rss(url: str, n: int = 3) -> list[dict]:
    """Parse RSS/Atom feed and return top n entries with title, link, summary."""
    try:
        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries[:n]:
            summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": summary[:500],
            })
        return entries
    except Exception as e:
        logger.warning(f"RSS fetch failed for {url}: {e}")
        return []
