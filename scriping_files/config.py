import os
import re
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool) -> bool:
    val = os.getenv(name)
    return default if val is None else val.lower() in {'1', 'true', 'yes', 'on'}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ''))
    except (ValueError, TypeError):
        return default


def _str(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, '').strip()
    return val or default


# ── Server ─────────────────────────────────────────────────────────────────────
APP_HOST = _str('APP_HOST', '0.0.0.0')
APP_PORT = _int('APP_PORT', 8000)

# ── Proxy ──────────────────────────────────────────────────────────────────────
PROXY_CHECK_URL = _str('PROXY_CHECK_URL', 'https://ip.oxylabs.io/location')
PROXY_URL       = _str('PROXY_URL') or _str('PROXY_SERVER')
PROXY_USERNAME  = _str('PROXY_USERNAME')
PROXY_PASSWORD  = _str('PROXY_PASSWORD')

# ── Paths ──────────────────────────────────────────────────────────────────────
USER_DATA_DIR   = _str('USER_DATA_DIR', './.playwright-profile')
OUTPUT_DIR      = _str('OUTPUT_DIR', './output')
HTML_OUTPUT_DIR = f'{OUTPUT_DIR}/html'
JSON_OUTPUT_DIR = f'{OUTPUT_DIR}/json'
COOKIE_FILE     = _str('COOKIE_FILE', f'{OUTPUT_DIR}/cookies/1688-cookies.json')

# ── Browser ────────────────────────────────────────────────────────────────────
VIEWPORT = {'width': 1080, 'height': 1024}
BROWSER_AGENTS = [
    {
        'name': 'Chrome Windows',
        'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    },
    {
        'name': 'Chrome macOS',
        'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    },
    {
        'name': 'Edge Windows',
        'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
    },
    {
        'name': 'Chrome Linux',
        'userAgent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    },
]

# ── Timeouts & retries ─────────────────────────────────────────────────────────
NAVIGATION_TIMEOUT_MS      = _int('NAVIGATION_TIMEOUT_MS', 120_000)
BODY_WAIT_TIMEOUT_MS       = _int('BODY_WAIT_TIMEOUT_MS', 30_000)
NAVIGATION_RETRIES         = _int('NAVIGATION_RETRIES', 1)
CART_WAIT_TIMEOUT_MS       = 60_000
VERIFICATION_CHECK_DELAY_MS = _int('VERIFICATION_CHECK_DELAY_MS', 1_000)

# ── Feature flags ──────────────────────────────────────────────────────────────
CHECK_PROXY_FIRST       = _flag('CHECK_PROXY_FIRST', True)
CHECK_PRODUCT_EXISTS    = _flag('CHECK_PRODUCT_EXISTS', True)
LOAD_1688_COOKIES       = _flag('LOAD_1688_COOKIES', False)
LOAD_SAVED_COOKIES      = _flag('LOAD_SAVED_COOKIES', True)
SAVE_PAGE_COOKIES       = _flag('SAVE_PAGE_COOKIES', True)
KEEP_BROWSER_OPEN       = _flag('KEEP_BROWSER_OPEN', False)
FRESH_BROWSER_PROFILE   = _flag('FRESH_BROWSER_PROFILE', False)
BLOCK_PAGE_REDIRECTS    = _flag('BLOCK_PAGE_REDIRECTS', True)
BLOCK_HEAVY_RESOURCES   = _flag('BLOCK_HEAVY_RESOURCES', True)
BLOCKED_RESOURCE_TYPES  = {'font', 'image', 'media'}

# ── Detection keywords ─────────────────────────────────────────────────────────
CAPTCHA_KEYWORDS = [
    'captcha',
    'Captcha Interception',
    'login.taobao.com',
    'login.1688.com',
]
PRODUCT_NOT_FOUND_KEYWORDS = [
    '404', 'not found',
    '商品不存在', '商品已下架', '商品已经下架',
    '该商品不存在', '宝贝不存在', '页面不存在', '很抱歉',
]

# ── Selectors ──────────────────────────────────────────────────────────────────
CART_SELECTOR = 'div#cart[data-module="od_cart_sider"][data-spm="cart"]'


# ── Proxy builder ──────────────────────────────────────────────────────────────
def build_proxy_config() -> dict:
    if not PROXY_URL:
        raise ValueError('Missing PROXY_URL in .env or environment.')

    raw = PROXY_URL if re.match(r'^[a-z]+://', PROXY_URL, re.I) else f'http://{PROXY_URL}'
    parsed = urlparse(raw)
    username = PROXY_USERNAME or parsed.username
    password = PROXY_PASSWORD or parsed.password

    netloc = parsed.hostname or ''
    if parsed.port:
        netloc = f'{netloc}:{parsed.port}'
    server_url = urlunparse(parsed._replace(netloc=netloc))

    proxy: dict = {'server': server_url}
    if username and password:
        proxy['username'] = username
        proxy['password'] = password
    return proxy
