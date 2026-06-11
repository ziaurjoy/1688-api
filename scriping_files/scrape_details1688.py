import json
import os
import random
import re
import sys
import time
import asyncio
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

from playwright.sync_api import Playwright, TimeoutError as PlaywrightTimeoutError, sync_playwright

from scriping_files.extract_context_json import extract_context_json

load_dotenv()

# Import database
try:
    from database import db
except ModuleNotFoundError:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    from database import db


def env_flag(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


def env_number(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_string(name, default=None):
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def build_proxy_config():
    if not PROXY_URL:
        raise ValueError('Missing PROXY_URL in .env or environment.')

    proxy_input = PROXY_URL if re.match(r'^[a-z]+://', PROXY_URL, re.I) else f'http://{PROXY_URL}'
    parsed = urlparse(proxy_input)
    username = PROXY_USERNAME or parsed.username
    password = PROXY_PASSWORD or parsed.password

    netloc = parsed.hostname or ''
    if parsed.port:
        netloc = f'{netloc}:{parsed.port}'
    proxy_url = parsed._replace(netloc=netloc)

    proxy = {'server': urlunparse(proxy_url)}
    if username and password:
        proxy['username'] = username
        proxy['password'] = password
    return proxy


PROXY_CHECK_URL = os.getenv('PROXY_CHECK_URL', 'https://ip.oxylabs.io/location')
PROXY_URL = env_string('PROXY_URL', env_string('PROXY_SERVER'))
PROXY_USERNAME = env_string('PROXY_USERNAME')
PROXY_PASSWORD = env_string('PROXY_PASSWORD')
USER_DATA_DIR = os.getenv('USER_DATA_DIR', './.playwright-profile')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', './output')
HTML_OUTPUT_DIR = f'{OUTPUT_DIR}/html'
JSON_OUTPUT_DIR = f'{OUTPUT_DIR}/json'
COOKIE_FILE = env_string('COOKIE_FILE', f'{OUTPUT_DIR}/cookies/1688-cookies.json')
VIEWPORT = {'width': 1080, 'height': 1024}
NAVIGATION_TIMEOUT_MS = env_number('NAVIGATION_TIMEOUT_MS', 120_000)
BODY_WAIT_TIMEOUT_MS = env_number('BODY_WAIT_TIMEOUT_MS', 30_000)
NAVIGATION_RETRIES = env_number('NAVIGATION_RETRIES', 1)
CART_SELECTOR = 'div#cart[data-module="od_cart_sider"][data-spm="cart"]'
CART_WAIT_TIMEOUT_MS = 60_000
VERIFICATION_CHECK_DELAY_MS = env_number('VERIFICATION_CHECK_DELAY_MS', 1000)
CHECK_PROXY_FIRST = env_flag('CHECK_PROXY_FIRST', True)
CHECK_PRODUCT_EXISTS = env_flag('CHECK_PRODUCT_EXISTS', True)
LOAD_1688_COOKIES = env_flag('LOAD_1688_COOKIES', False)
LOAD_SAVED_COOKIES = env_flag('LOAD_SAVED_COOKIES', True)
SAVE_PAGE_COOKIES = env_flag('SAVE_PAGE_COOKIES', True)
KEEP_BROWSER_OPEN = env_flag('KEEP_BROWSER_OPEN', False)
FRESH_BROWSER_PROFILE = env_flag('FRESH_BROWSER_PROFILE', False)
BLOCK_PAGE_REDIRECTS = env_flag('BLOCK_PAGE_REDIRECTS', True)
BLOCK_HEAVY_RESOURCES = env_flag('BLOCK_HEAVY_RESOURCES', True)
BLOCKED_RESOURCE_TYPES = {'font', 'image', 'media'}

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

CAPTCHA_KEYWORDS = [
    'captcha',
    'Captcha Interception',
    'login.taobao.com',
    'login.1688.com',
]
PRODUCT_NOT_FOUND_KEYWORDS = [
    '404',
    'not found',
    '商品不存在',
    '商品已下架',
    '商品已经下架',
    '该商品不存在',
    '宝贝不存在',
    '页面不存在',
    '很抱歉',
]

RAW_1688_COOKIES = [
    {
        'domain': '.1688.com',
        'expirationDate': 1778749280.784412,
        'hostOnly': False,
        'httpOnly': False,
        'name': '_m_h5_tk',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '9b90acb5863f0b0cfe2d50b302b3937b_1778751440791',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778749280.784494,
        'hostOnly': False,
        'httpOnly': False,
        'name': '_m_h5_tk_enc',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'da0f1a842a5889ee0069acd52ae5de69',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779003081,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'xlly_s',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '1',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1813303883.127476,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'cna',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'SWiMIqG/W3wCAXELZgVzvuPi',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.715307,
        'hostOnly': False,
        'httpOnly': True,
        'name': 'cookie2',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '18adf575146f5435c5a66da37fa1d2ee',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.715839,
        'hostOnly': False,
        'httpOnly': False,
        'name': 't',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'ddccf769621d12fbf46ce4179a8153eb',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716126,
        'hostOnly': False,
        'httpOnly': False,
        'name': '_tb_token_',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '450e1e78b540',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.71506,
        'hostOnly': False,
        'httpOnly': True,
        'name': 'cookie1',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'UNiMia4%2FJ%2BfBleKQWpIkgFo1cUie6NhUgfIoSoHYnIU%3D',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.715605,
        'hostOnly': False,
        'httpOnly': True,
        'name': 'cookie17',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'UUpjN48sA%2BVtHmLHKA%3D%3D',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.715724,
        'hostOnly': False,
        'httpOnly': True,
        'name': 'sgcookie',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'E100MOmrpf7CDRtjAFe6gbapCSEBKvwWhhfzqOudgwp72ur6NVprvq%2FC2%2FlbnF9trtRlSyTAwdxYlp%2FuRzJJ1KmwPXQ16%2B31M1XdCJLzZX3paic%3D',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716406,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'sg',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '157',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716519,
        'hostOnly': False,
        'httpOnly': True,
        'name': 'csg',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'd383df83',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1810280127.716608,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'lid',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '16887116043041',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716692,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'unb',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '2221601455665',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716771,
        'hostOnly': False,
        'httpOnly': True,
        'name': 'uc4',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'id4=0%40U2gp9xpBdhg79J0Iw5tqnKR8ioNW3HPu&nk4=0%40UO%2B6ZP9KzwMUMzBrzSDEGyowRH90ccGbAQ%3D%3D',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716856,
        'hostOnly': False,
        'httpOnly': False,
        'name': '_nk_',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': '16887116043041',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.716937,
        'hostOnly': False,
        'httpOnly': False,
        'name': '__cn_logon__',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': 'true',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1779348927.717102,
        'hostOnly': False,
        'httpOnly': False,
        'name': '__cn_logon_id__',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': '16887116043041',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1813304127.717197,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'ali_apache_track',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': 'c_mid=b2b-2221601455665c2084|c_lid=16887116043041|c_ms=1',
    },
    {
        'domain': '.1688.com',
        'hostOnly': False,
        'httpOnly': False,
        'name': 'ali_apache_tracktmp',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': True,
        'value': 'c_w_signed=Y',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778816127.71749,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'last_mid',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'b2b-2221601455665c2084',
    },
    {
        'domain': '.1688.com',
        'hostOnly': False,
        'httpOnly': False,
        'name': '_csrf_token',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': True,
        'value': '1778744128279',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1813304163.189786,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'taklid',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': '05171a44882345e7a52b192d40dfb04b',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778830565,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'oversearegion',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': 'GLOBAL',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778830565,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'overseaRegionName',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': 'EN%2FUSD',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778830565,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'oversealanguage',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': 'en',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778830565,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'overseacurrency',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': 'USD',
    },
    {
        'domain': 'detail.1688.com',
        'hostOnly': True,
        'httpOnly': True,
        'name': 'JSESSIONID',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': True,
        'session': True,
        'value': '5AB6ABA1241D74F1B7C4B1286A5A3FFB',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1778830565,
        'hostOnly': False,
        'httpOnly': False,
        'name': '_user_vitals_session_data_',
        'path': '/',
        'sameSite': 'unspecified',
        'secure': False,
        'session': False,
        'value': '{"user_line_track":true,"ul_session_id":"duxmugk70wl","last_page_id":"detail.1688.com%2F84no9ur6gon"}',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1794296171,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'isg',
        'path': '/product_data',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'BK2teOkzuwmghV_lJSv-1OorvE8nCuHc-RSOeO-y6cSzZs0Yt1rxPskUiKAffmU',
    },
    {
        'domain': '.1688.com',
        'expirationDate': 1794296167,
        'hostOnly': False,
        'httpOnly': False,
        'name': 'tfstk',
        'path': '/',
        'sameSite': 'no_restriction',
        'secure': True,
        'session': False,
        'value': 'gLvrY1sQU9YXB1uMbhXE_QABzDBRP9u1rp_CxHxhVaboJ0IhLUTctgj3KoA2-EC5rTiLTJ-Fkub3E94cogIatwjlxIreXEWB8HnRxwYH8wOSGAtJ29Bn5pksC3BrUpIwU94BmTIIWrxWCAtJ29Ez-cOmCXyJqE2utwYhnZjRj943KwmViGshK8f3ES4ckMXhK_XHmsjhY8qlK6m2mZIhKwYhKmWckMXh-eXnNkRWOSSGZ0O2B8ptNs1PS3b4Ke9Vq_PJqZy3KK5NaN2CuJ2H3g-d89TaEA7DNBv5nL00btx9GUjVQYzO4IxNEg8KB8BkjnAhaplQXwd2mC12MuidJK-DEBxYz2WycUpNEduzFi6AP1AMqqNV0IxW3s9i7J5JiUdOTpgjBTO6fpCMEYzOl1Ieu1Or788G4RadmqkkpQz3T_jA0Niq0Fk49lC96x309WCc7i7s2aFL9_b10Niq0WFdiisV50QR.',
    },
]


class VerificationPageError(Exception):
    pass


class PageRedirectBlockedError(Exception):
    def __init__(self, url):
        super().__init__(f'Blocked page redirect to {url}')
        self.url = url


allowed_main_frame_urls = {}
blocked_main_frame_redirects = {}


def is_product_url(url: str) -> bool:
    return 'detail.1688.com/offer/' in url and url.endswith('.html')


def get_product_id(url: str) -> str:
    match = re.search(r'/offer/(\d+)\.html', url)
    return match.group(1) if match else 'unknown'


def get_html_output_path(url: str) -> str:
    return f'{HTML_OUTPUT_DIR}/rendered-product-{get_product_id(url)}.html'


def get_json_output_path(url: str) -> str:
    return f'{JSON_OUTPUT_DIR}/context-data-{get_product_id(url)}.json'


def pick_browser_agent() -> dict:
    return random.choice(BROWSER_AGENTS)


def normalize_url_for_redirect_check(url: str) -> str:
    parsed = urlparse(url)
    parsed = parsed._replace(fragment='')
    return urlunparse(parsed)


def normalize_same_site(same_site):
    if same_site == 'no_restriction':
        return 'None'
    if same_site == 'lax':
        return 'Lax'
    if same_site == 'strict':
        return 'Strict'
    return None


def normalize_cookie(cookie):
    normalized = {
        'name': cookie['name'],
        'value': cookie['value'],
        'path': cookie['path'],
        'httpOnly': cookie.get('httpOnly', False),
        'secure': cookie.get('secure', False),
    }

    if not cookie.get('session') and cookie.get('expirationDate') is not None:
        normalized['expires'] = int(cookie['expirationDate'])

    same_site = normalize_same_site(cookie.get('sameSite'))
    if same_site:
        normalized['sameSite'] = same_site

    if cookie.get('hostOnly'):
        normalized['url'] = f"https://{cookie['domain']}{cookie['path']}"
    else:
        normalized['domain'] = cookie['domain']

    return normalized


def to_playwright_cookie(cookie):
    normalized = {
        'name': cookie['name'],
        'value': cookie['value'],
        'path': cookie.get('path', '/'),
        'httpOnly': cookie.get('httpOnly', False),
        'secure': cookie.get('secure', False),
    }

    if cookie.get('domain') and not cookie.get('url'):
        normalized['domain'] = cookie['domain']
    if cookie.get('url'):
        normalized['url'] = cookie['url']

    if cookie.get('expires') is not None:
        normalized['expires'] = int(cookie['expires'])

    if cookie.get('sameSite'):
        normalized['sameSite'] = cookie['sameSite']

    return normalized


def is_blocked_page_redirect(page, request):
    if not BLOCK_PAGE_REDIRECTS or not request.is_navigation_request() or request.frame != page.main_frame:
        return False

    allowed_url = allowed_main_frame_urls.get(page)
    if allowed_url is None:
        return False

    return normalize_url_for_redirect_check(request.url) != normalize_url_for_redirect_check(allowed_url)


def goto_page(page, url, label):
    last_error = None

    for attempt in range(1, NAVIGATION_RETRIES + 2):
        try:
            print(f'Opening {label}: {url} (attempt {attempt})')
            allowed_main_frame_urls[page] = url
            blocked_main_frame_redirects.pop(page, None)

            response = page.goto(url, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT_MS)
            page.wait_for_selector('body', timeout=BODY_WAIT_TIMEOUT_MS)
            throw_if_verification_page(page)
            return response
        except PlaywrightTimeoutError as timeout_error:
            last_error = timeout_error
            if page.query_selector('body'):
                throw_if_verification_page(page)
                print('Navigation timed out, but page body is available. Continuing with current page.')
                return None
        except Exception as error:
            if isinstance(error, VerificationPageError):
                raise
            blocked_redirect_url = blocked_main_frame_redirects.get(page)
            if blocked_redirect_url:
                raise PageRedirectBlockedError(blocked_redirect_url)

            last_error = error
            if attempt <= NAVIGATION_RETRIES:
                print(f'Navigation failed: {error}. Retrying...')
                time.sleep(3)

    raise last_error


def is_verification_page(page):
    try:
        title = page.title() or ''
        url = page.url or ''
        body_text = page.inner_text('body', timeout=5_000) or ''
        page_text = ' '.join([title, url, body_text]).lower()
        return any(keyword.lower() in page_text for keyword in CAPTCHA_KEYWORDS)
    except Exception:
        return False


def has_missing_product_message(page):
    try:
        title = page.title() or ''
        url = page.url or ''
        body_text = page.inner_text('body', timeout=5_000) or ''
        page_text = ' '.join([title, url, body_text]).lower()
        return any(keyword.lower() in page_text for keyword in PRODUCT_NOT_FOUND_KEYWORDS)
    except Exception:
        return False


def clear_saved_cookies():
    try:
        Path(COOKIE_FILE).unlink(missing_ok=True)
        print(f'Cleared saved cookies: {COOKIE_FILE}')
    except Exception as error:
        print(f'Could not clear saved cookies at {COOKIE_FILE}: {error}')


def throw_if_verification_page(page):
    if VERIFICATION_CHECK_DELAY_MS > 0:
        time.sleep(VERIFICATION_CHECK_DELAY_MS / 1000)

    if not is_verification_page(page):
        return

    clear_saved_cookies()
    raise VerificationPageError()


def ensure_product_page_loaded(page, product_url, label='product page', max_attempts=2):
    for attempt in range(1, max_attempts + 1):
        response = goto_page(page, product_url, label)
        if is_product_url(page.url):
            return response
        if attempt < max_attempts:
            print('Returning to the product page after verification...')

    raise RuntimeError(f'Could not reach product page after {max_attempts} attempts.')


def setup_resource_blocking(page):
    if not BLOCK_HEAVY_RESOURCES and not BLOCK_PAGE_REDIRECTS:
        return

    def route_handler(route, request):
        if BLOCK_PAGE_REDIRECTS and is_blocked_page_redirect(page, request):
            blocked_main_frame_redirects[page] = request.url
            print(f'Blocked page redirect: {request.url}')
            return route.abort()

        if BLOCK_HEAVY_RESOURCES and request.resource_type in BLOCKED_RESOURCE_TYPES:
            return route.abort()

        return route.continue_()

    page.route('**/*', route_handler)


def set_1688_cookies(page):
    if not LOAD_1688_COOKIES:
        return

    cookies = [normalize_cookie(cookie) for cookie in RAW_1688_COOKIES]
    page.context.add_cookies(cookies)
    print(f'Loaded {len(cookies)} 1688 cookies.')


def load_saved_cookies(page):
    if not LOAD_SAVED_COOKIES:
        return

    try:
        cookies = json.loads(Path(COOKIE_FILE).read_text(encoding='utf-8'))
    except FileNotFoundError:
        print(f'No saved cookie file found at {COOKIE_FILE}.')
        return
    except Exception as error:
        raise RuntimeError(f'Could not load saved cookies from {COOKIE_FILE}: {error}')

    if not cookies:
        print(f'No saved cookies to load from {COOKIE_FILE}.')
        return

    page.context.add_cookies([to_playwright_cookie(cookie) for cookie in cookies])
    print(f'Loaded {len(cookies)} saved cookies from {COOKIE_FILE}.')


def save_page_cookies(page, product_url):
    if not SAVE_PAGE_COOKIES:
        return

    cookies = page.context.cookies([product_url])
    Path(COOKIE_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(COOKIE_FILE).write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved {len(cookies)} page cookies: {COOKIE_FILE}')


def check_proxy(page):
    if not CHECK_PROXY_FIRST:
        return

    print('Checking proxy connection...')
    goto_page(page, PROXY_CHECK_URL, 'proxy check')
    proxy_location = page.inner_text('body', timeout=10_000).strip().replace('\n', ' ').replace('\r', ' ')
    print(f'Proxy check result: {proxy_location}')


def check_product_page_exists(page, product_url):
    if not CHECK_PRODUCT_EXISTS:
        return

    response = ensure_product_page_loaded(page, product_url, 'product existence check')
    if response and response.status >= 400:
        raise RuntimeError(f'Product page does not exist or is unavailable. HTTP status: {response.status}')

    if has_missing_product_message(page):
        raise RuntimeError('Product page appears to be missing, removed, or unavailable.')

    print('Product page exists.')


def open_product_page(page, product_url, already_loaded=False):
    if not already_loaded or not is_product_url(page.url):
        ensure_product_page_loaded(page, product_url)

    print('Waiting for product cart module...')
    page.wait_for_selector(CART_SELECTOR, timeout=CART_WAIT_TIMEOUT_MS)
    print('Product page loaded.')


def save_rendered_html(page, product_url):
    html = page.content()
    output_path = get_html_output_path(product_url)
    Path(HTML_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding='utf-8')
    print(f'Saved rendered HTML: {output_path}')
    return output_path


def clear_browser_data(context):
    try:
        context.clear_cookies()
        print('Cleared browser cookies.')
    except Exception as error:
        print(f'Could not clear browser cookies: {error}')


def destroy_browser_profile(user_data_dir):
    try:
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        for path in Path(user_data_dir).glob('**/*'):
            if path.is_file():
                path.unlink()
        for path in sorted(Path(user_data_dir).glob('**/*'), reverse=True):
            if path.is_dir():
                path.rmdir()
        Path(user_data_dir).rmdir()
        print(f'Destroyed browser profile: {user_data_dir}')
    except FileNotFoundError:
        pass
    except Exception as error:
        print(f'Could not destroy browser profile at {user_data_dir}: {error}')


def launch_browser(playwright: Playwright):
    proxy_config = build_proxy_config()
    browser_agent = pick_browser_agent()
    if FRESH_BROWSER_PROFILE:
        destroy_browser_profile(USER_DATA_DIR)

    print(
        f"{'Launching fresh browser profile' if FRESH_BROWSER_PROFILE else 'Launching browser profile'}: {USER_DATA_DIR}"
    )

    options = {
        'headless': False,
        'ignore_https_errors': True,
        'user_data_dir': USER_DATA_DIR,
        'viewport': VIEWPORT,
        'user_agent': browser_agent['userAgent'],
        'proxy': proxy_config,
        'args': ['--ignore-certificate-errors'],
    }

    context = playwright.chromium.launch_persistent_context(**options)
    context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
    context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    print(f'Using browser agent: {browser_agent["name"]}')
    return context


async def save_to_database(product_id, cookies, html_path, json_data):
    """
    Save scraped product data to MongoDB database
    """
    try:
        cookies_data = json.loads(json.dumps(cookies)) if cookies else []

        # Prepare document for database (use `details` key to match other scrapers)
        product_data = {
            "offer_id": str(product_id),
            "details": json_data,
            "url": f"https://detail.1688.com/offer/{product_id}.html",
            "scraped_at": time.time(),
            "status": "success"
        }

        # Update or insert product in database
        result = await db.products.update_one(
            {"offer_id": str(product_id)},
            {"$set": product_data},
            upsert=True
        )

        print(f"✓ Saved to database: offer_id={product_id}")
        return result
    except Exception as error:
        print(f"✗ Failed to save to database: {error}")
        raise



def _scrape_details_page1688_sync(product_id, request):
    product_url = f"https://detail.1688.com/offer/{product_id}.html"
    html_path = None
    json_path = None
    json_data = None
    cookies = None
    verification_detected = False

    with sync_playwright() as playwright:
        context = launch_browser(playwright)
        page = context.new_page()
        page.set_extra_http_headers({'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8'})
        setup_resource_blocking(page)

        try:
            load_saved_cookies(page)
            set_1688_cookies(page)
            check_proxy(page)
            # check_product_page_exists(page)
            open_product_page(page, product_url)
            html_path = save_rendered_html(page, product_url)
            cookies = page.context.cookies([product_url])
            save_page_cookies(page, product_url)

            # Extract context JSON
            if html_path:
                Path(JSON_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
                json_path = extract_context_json(html_path, get_json_output_path(product_url))
                print(f'Extracted context JSON: {json_path}')

                # Read JSON data from extracted file
                if json_path and Path(json_path).exists():
                    with open(json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)

                # Return scraped data to caller (async wrapper will persist to DB)
                # Delete JSON file (keep only in database)
                try:
                    Path(json_path).unlink(missing_ok=True)
                    print(f'Cleaned up: {json_path}')
                except Exception:
                    pass

                return {
                    'product_id': product_id,
                    'cookies': cookies,
                    'html_path': html_path,
                    'json_data': json_data,
                }

        except Exception as error:
            verification_detected = isinstance(error, VerificationPageError)
            print(f'Scraper failed: {error}')
            raise
        finally:
            if verification_detected:
                clear_browser_data(context)

            if not KEEP_BROWSER_OPEN or verification_detected:
                context.close()
                print('Browser context closed.')

            if verification_detected:
                destroy_browser_profile(USER_DATA_DIR)


async def scrape_details_page1688(product_id, request):
    """Async wrapper that runs the synchronous Playwright scraper in a background thread.
    This avoids using the sync Playwright API in the main asyncio event loop.
    The sync scraper returns scraped data which we persist here in the main loop.
    """
    try:
        result = await asyncio.to_thread(_scrape_details_page1688_sync, product_id, request)
        if result:
            # Persist to DB in the main async loop (Motor expects this)
            await save_to_database(result['product_id'], result.get('cookies'), result.get('html_path'), result.get('json_data'))
            return result
    except Exception:
        # Re-raise to let callers handle logging/HTTP errors
        raise
