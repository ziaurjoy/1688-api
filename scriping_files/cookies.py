"""Cookie load / save / normalise helpers."""
import json
from pathlib import Path

from scriping_files.config import (
    COOKIE_FILE,
    LOAD_1688_COOKIES,
    LOAD_SAVED_COOKIES,
    SAVE_PAGE_COOKIES,
)
from scriping_files.raw_cookies import RAW_1688_COOKIES


# ── Normalisation ──────────────────────────────────────────────────────────────

def _normalize_same_site(value: str | None) -> str | None:
    return {'no_restriction': 'None', 'lax': 'Lax', 'strict': 'Strict'}.get(value or '')


def normalize_cookie(cookie: dict) -> dict:
    """Convert a browser-extension-exported cookie to Playwright format."""
    result: dict = {
        'name':     cookie['name'],
        'value':    cookie['value'],
        'path':     cookie['path'],
        'httpOnly': cookie.get('httpOnly', False),
        'secure':   cookie.get('secure', False),
    }
    if not cookie.get('session') and cookie.get('expirationDate') is not None:
        result['expires'] = int(cookie['expirationDate'])

    same_site = _normalize_same_site(cookie.get('sameSite'))
    if same_site:
        result['sameSite'] = same_site

    if cookie.get('hostOnly'):
        result['url'] = f"https://{cookie['domain']}{cookie['path']}"
    else:
        result['domain'] = cookie['domain']
    return result


def to_playwright_cookie(cookie: dict) -> dict:
    """Convert a saved-cookie dict to the shape Playwright's add_cookies expects."""
    result: dict = {
        'name':     cookie['name'],
        'value':    cookie['value'],
        'path':     cookie.get('path', '/'),
        'httpOnly': cookie.get('httpOnly', False),
        'secure':   cookie.get('secure', False),
    }
    if cookie.get('domain') and not cookie.get('url'):
        result['domain'] = cookie['domain']
    if cookie.get('url'):
        result['url'] = cookie['url']
    if cookie.get('expires') is not None:
        result['expires'] = int(cookie['expires'])
    if cookie.get('sameSite'):
        result['sameSite'] = cookie['sameSite']
    return result


# ── Page-level helpers ─────────────────────────────────────────────────────────

def set_1688_cookies(page) -> None:
    if not LOAD_1688_COOKIES:
        return
    cookies = [normalize_cookie(c) for c in RAW_1688_COOKIES]
    page.context.add_cookies(cookies)
    print(f'Loaded {len(cookies)} built-in 1688 cookies.')


def load_saved_cookies(page) -> None:
    if not LOAD_SAVED_COOKIES:
        return
    try:
        cookies = json.loads(Path(COOKIE_FILE).read_text(encoding='utf-8'))
    except FileNotFoundError:
        print(f'No saved cookie file at {COOKIE_FILE}.')
        return
    except Exception as exc:
        raise RuntimeError(f'Could not load saved cookies from {COOKIE_FILE}: {exc}') from exc

    if not cookies:
        print(f'Cookie file {COOKIE_FILE} is empty.')
        return

    page.context.add_cookies([to_playwright_cookie(c) for c in cookies])
    print(f'Loaded {len(cookies)} saved cookies from {COOKIE_FILE}.')


def save_page_cookies(page, product_url: str) -> None:
    if not SAVE_PAGE_COOKIES:
        return
    cookies = page.context.cookies([product_url])
    path = Path(COOKIE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved {len(cookies)} page cookies → {COOKIE_FILE}')


def clear_saved_cookies() -> None:
    try:
        Path(COOKIE_FILE).unlink(missing_ok=True)
        print(f'Cleared saved cookies: {COOKIE_FILE}')
    except Exception as exc:
        print(f'Could not clear saved cookies at {COOKIE_FILE}: {exc}')
