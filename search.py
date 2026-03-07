import time as _time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import CHROMIUM_PATH, CHROMEDRIVER_PATH

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
    driver = _create_driver()
    try:
        if len(url) > 500:
            return "[Error: URL too long. Use a shorter, cleaner URL.]"

        driver.get(url)
        # Wait for body to appear
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        # Extra wait for JS-heavy SPAs to render content
        _time.sleep(3)

        # Try to get meaningful text
        text = driver.find_element(By.TAG_NAME, "body").text

        # If body text is too short, the page is likely JS-rendered
        # Try waiting longer and retry
        if len(text.strip()) < 100:
            _time.sleep(5)
            text = driver.find_element(By.TAG_NAME, "body").text

        # Still empty? Return page title + whatever we have
        if len(text.strip()) < 50:
            title = driver.title or ""
            return f"[Page title: {title}]\n[Content could not be fully loaded - JS-heavy site]\n{text}"

        return text[:max_chars]
    except Exception as e:
        logger.warning(f"Fetch failed for {url}: {e}")
        return f"[Error loading page: {e}]"
    finally:
        driver.quit()
