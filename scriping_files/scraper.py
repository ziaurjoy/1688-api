"""
1688 product-detail scraper.

Public API
----------
scrape_details_page1688(product_id, request)  – async entry point
"""

import asyncio
import json
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
from scriping_files.extract_context_json import extract_context_json_sync

from scriping_files.browser import (
    clear_browser_data,
    destroy_browser_profile,
    launch_browser,
    pop_blocked_redirect,
    register_allowed_url,
    setup_resource_blocking,
)

from scriping_files.config import (
    BODY_WAIT_TIMEOUT_MS,
    CAPTCHA_KEYWORDS,
    CART_SELECTOR,
    CART_WAIT_TIMEOUT_MS,
    CHECK_PRODUCT_EXISTS,
    CHECK_PROXY_FIRST,
    HTML_OUTPUT_DIR,
    JSON_OUTPUT_DIR,
    KEEP_BROWSER_OPEN,
    NAVIGATION_RETRIES,
    NAVIGATION_TIMEOUT_MS,
    PRODUCT_NOT_FOUND_KEYWORDS,
    PROXY_CHECK_URL,
    VERIFICATION_CHECK_DELAY_MS,
)
from scriping_files.cookies import (
    clear_saved_cookies,
    load_saved_cookies,
    save_page_cookies,
    set_1688_cookies,
)

try:
    from database import db
except ModuleNotFoundError:
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from database import db

from scriping_files.extract_context_json import extract_context_json


# ── Custom exceptions ──────────────────────────────────────────────────────────

class VerificationPageError(Exception):
    """Raised when a CAPTCHA / login wall is detected."""


class PageRedirectBlockedError(Exception):
    def __init__(self, url: str):
        super().__init__(f'Blocked page redirect to {url}')
        self.url = url


# ── URL helpers ────────────────────────────────────────────────────────────────

def is_product_url(url: str) -> bool:
    return 'detail.1688.com/offer/' in url and url.endswith('.html')


def get_product_id(url: str) -> str:
    import re
    m = re.search(r'/offer/(\d+)\.html', url)
    return m.group(1) if m else 'unknown'


def _product_url(product_id) -> str:
    return f'https://detail.1688.com/offer/{product_id}.html'


def _html_path(url: str) -> str:
    return f'{HTML_OUTPUT_DIR}/rendered-product-{get_product_id(url)}.html'


def _json_path(url: str) -> str:
    return f'{JSON_OUTPUT_DIR}/context-data-{get_product_id(url)}.json'


# ── Page-detection helpers ─────────────────────────────────────────────────────

def _page_text(page) -> str:
    try:
        title = page.title() or ''
        url   = page.url   or ''
        body  = page.inner_text('body', timeout=5_000) or ''
        return ' '.join([title, url, body]).lower()
    except Exception:
        return ''


def is_verification_page(page) -> bool:
    text = _page_text(page)
    return any(kw.lower() in text for kw in CAPTCHA_KEYWORDS)


def has_missing_product_message(page) -> bool:
    text = _page_text(page)
    return any(kw.lower() in text for kw in PRODUCT_NOT_FOUND_KEYWORDS)


def _throw_if_verification(page) -> None:
    if VERIFICATION_CHECK_DELAY_MS > 0:
        time.sleep(VERIFICATION_CHECK_DELAY_MS / 1000)
    if is_verification_page(page):
        clear_saved_cookies()
        raise VerificationPageError()


# ── Navigation ─────────────────────────────────────────────────────────────────

def goto_page(page, url: str, label: str):
    last_err = None
    for attempt in range(1, NAVIGATION_RETRIES + 2):
        try:
            print(f'Opening {label}: {url} (attempt {attempt})')
            register_allowed_url(page, url)

            response = page.goto(url, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT_MS)
            page.wait_for_selector('body', timeout=BODY_WAIT_TIMEOUT_MS)
            _throw_if_verification(page)
            return response

        except PlaywrightTimeoutError as exc:
            last_err = exc
            if page.query_selector('body'):
                _throw_if_verification(page)
                print('Timed out but body is present – continuing.')
                return None

        except Exception as exc:
            if isinstance(exc, VerificationPageError):
                raise
            blocked = pop_blocked_redirect(page)
            if blocked:
                raise PageRedirectBlockedError(blocked) from exc
            last_err = exc
            if attempt <= NAVIGATION_RETRIES:
                print(f'Navigation failed: {exc}. Retrying in 3 s…')
                time.sleep(3)

    raise last_err


def _ensure_product_page(page, product_url: str, label: str = 'product page', max_attempts: int = 2):
    for attempt in range(1, max_attempts + 1):
        response = goto_page(page, product_url, label)
        if is_product_url(page.url):
            return response
        if attempt < max_attempts:
            print('Not on product page – retrying…')
    raise RuntimeError(f'Could not reach product page after {max_attempts} attempts.')


# ── Scrape steps ───────────────────────────────────────────────────────────────

def _check_proxy(page) -> None:
    if not CHECK_PROXY_FIRST:
        return
    print('Checking proxy…')
    goto_page(page, PROXY_CHECK_URL, 'proxy check')
    location = page.inner_text('body', timeout=10_000).strip().replace('\n', ' ')
    print(f'Proxy location: {location}')


def _check_product_exists(page, product_url: str) -> None:
    if not CHECK_PRODUCT_EXISTS:
        return
    response = _ensure_product_page(page, product_url, 'product existence check')
    if response and response.status >= 400:
        raise RuntimeError(f'Product unavailable – HTTP {response.status}')
    if has_missing_product_message(page):
        raise RuntimeError('Product page is missing or has been removed.')
    print('Product page confirmed to exist.')


def _open_product_page(page, product_url: str, already_loaded: bool = False) -> None:
    if not already_loaded or not is_product_url(page.url):
        _ensure_product_page(page, product_url)
    print('Waiting for cart module…')
    page.wait_for_selector(CART_SELECTOR, timeout=CART_WAIT_TIMEOUT_MS)
    print('Product page fully loaded.')


def _save_html(page, product_url: str) -> str:
    html = page.content()
    out  = _html_path(product_url)
    Path(HTML_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(out).write_text(html, encoding='utf-8')
    print(f'Saved HTML → {out}')
    return out


# ── Sync core ──────────────────────────────────────────────────────────────────

def _scrape_sync(product_id) -> dict:
    product_url       = _product_url(product_id)
    verification_hit  = False

    with sync_playwright() as pw:
        context = launch_browser(pw)
        page    = context.new_page()
        page.set_extra_http_headers({'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8'})
        setup_resource_blocking(page)

        try:
            load_saved_cookies(page)
            set_1688_cookies(page)
            _check_proxy(page)
            _check_product_exists(page, product_url)
            _open_product_page(page, product_url)

            html_path = _save_html(page, product_url)
            save_page_cookies(page, product_url)

            # Extract structured JSON from rendered HTML
            Path(JSON_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
            # json_out  = extract_context_json(html_path, _json_path(product_url))
            # json_out  = asyncio.run(extract_context_json(html_path, _json_path(product_url)))
            json_out = extract_context_json_sync(html_path, _json_path(product_url))
            json_data = None

            if json_out and Path(json_out).exists():
                with open(json_out, encoding='utf-8') as fh:
                    json_data = json.load(fh)
                Path(json_out).unlink(missing_ok=True)   # keep only DB copy
                print(f'Extracted & cleaned up: {json_out}')

            return {
                'product_id': product_id,
                'cookies':    page.context.cookies([product_url]),
                'html_path':  html_path,
                'json_data':  json_data,
            }

        except Exception as exc:
            verification_hit = isinstance(exc, VerificationPageError)
            print(f'Scraper error: {exc}')
            raise

        finally:
            if verification_hit:
                clear_browser_data(context)
            if not KEEP_BROWSER_OPEN or verification_hit:
                context.close()
                print('Browser closed.')
            if verification_hit:
                destroy_browser_profile()


# ── DB persistence ─────────────────────────────────────────────────────────────

async def _save_to_db(product_id, cookies, html_path: str, json_data) -> None:
    doc = {
        'offer_id':   str(product_id),
        'is_details_page': True,
        'details':    json_data.get("result", {}) if json_data else {},
        'url':        _product_url(product_id),
        'scraped_at': time.time(),
        'status':     'success',
    }
    result = await db.products.update_one(
        {'offer_id': str(product_id)},
        {'$set': doc},
        upsert=True,
    )
    print(f'✓ DB upsert complete: offer_id={product_id}')
    return result


# ── Public async entry point ───────────────────────────────────────────────────

async def scrape_details_page1688(product_id, request=None):
    """
    Run the synchronous Playwright scraper in a thread pool so it never
    blocks the asyncio event loop, then persist results via Motor (async).
    """



    result = await asyncio.to_thread(_scrape_sync, product_id)
    if result:
        await _save_to_db(
            result['product_id'],
            result.get('cookies'),
            result.get('html_path'),
            result.get('json_data'),
        )
    return result
