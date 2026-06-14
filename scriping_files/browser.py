"""Browser launch, routing, and profile helpers."""
import random
import time
from pathlib import Path

from playwright.sync_api import Playwright, Page, Request

from scriping_files.config import (
    BLOCK_HEAVY_RESOURCES,
    BLOCK_PAGE_REDIRECTS,
    BLOCKED_RESOURCE_TYPES,
    BROWSER_AGENTS,
    FRESH_BROWSER_PROFILE,
    NAVIGATION_TIMEOUT_MS,
    USER_DATA_DIR,
    VIEWPORT,
    build_proxy_config,
)

# Per-page state: tracks the URL we expect each page to stay on
_allowed_urls: dict = {}
_blocked_redirects: dict = {}


# ── URL / redirect helpers ─────────────────────────────────────────────────────

def _strip_fragment(url: str) -> str:
    from urllib.parse import urlparse, urlunparse
    p = urlparse(url)
    return urlunparse(p._replace(fragment=''))


def register_allowed_url(page: Page, url: str) -> None:
    _allowed_urls[page] = url
    _blocked_redirects.pop(page, None)


def pop_blocked_redirect(page: Page) -> str | None:
    return _blocked_redirects.pop(page, None)


def _is_blocked_redirect(page: Page, request: Request) -> bool:
    if not BLOCK_PAGE_REDIRECTS:
        return False
    if not request.is_navigation_request() or request.frame != page.main_frame:
        return False
    allowed = _allowed_urls.get(page)
    if allowed is None:
        return False
    return _strip_fragment(request.url) != _strip_fragment(allowed)


# ── Resource-blocking route handler ───────────────────────────────────────────

def setup_resource_blocking(page: Page) -> None:
    if not BLOCK_HEAVY_RESOURCES and not BLOCK_PAGE_REDIRECTS:
        return

    def _handler(route, request):
        if _is_blocked_redirect(page, request):
            _blocked_redirects[page] = request.url
            print(f'Blocked redirect → {request.url}')
            return route.abort()
        if BLOCK_HEAVY_RESOURCES and request.resource_type in BLOCKED_RESOURCE_TYPES:
            return route.abort()
        return route.continue_()

    page.route('**/*', _handler)


# ── Browser profile helpers ────────────────────────────────────────────────────

def destroy_browser_profile(user_data_dir: str = USER_DATA_DIR) -> None:
    root = Path(user_data_dir)
    try:
        for p in root.rglob('*'):
            if p.is_file():
                p.unlink()
        for p in sorted(root.rglob('*'), reverse=True):
            if p.is_dir():
                p.rmdir()
        root.rmdir()
        print(f'Destroyed browser profile: {user_data_dir}')
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f'Could not destroy browser profile at {user_data_dir}: {exc}')


def clear_browser_data(context) -> None:
    try:
        context.clear_cookies()
        print('Cleared browser cookies.')
    except Exception as exc:
        print(f'Could not clear browser cookies: {exc}')


# ── Launch ─────────────────────────────────────────────────────────────────────

def pick_browser_agent() -> dict:
    return random.choice(BROWSER_AGENTS)


# def launch_browser(playwright: Playwright):
#     proxy_config = build_proxy_config()
#     agent = pick_browser_agent()

#     if FRESH_BROWSER_PROFILE:
#         destroy_browser_profile()

#     print(f"Launching {'fresh ' if FRESH_BROWSER_PROFILE else ''}browser profile: {USER_DATA_DIR}")

#     context = playwright.chromium.launch_persistent_context(
#         user_data_dir=USER_DATA_DIR,
#         headless=False,
#         ignore_https_errors=True,
#         viewport=VIEWPORT,
#         user_agent=agent['userAgent'],
#         proxy=proxy_config,
#         args=['--ignore-certificate-errors'],
#     )
#     context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
#     context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
#     print(f'Browser agent: {agent["name"]}')
#     return context


import os

def launch_browser(playwright: Playwright):
    proxy_config = build_proxy_config()
    agent = pick_browser_agent()

    is_docker = os.getenv('RUNNING_IN_DOCKER', 'false').lower() == 'true'

    if FRESH_BROWSER_PROFILE:
        destroy_browser_profile()

    print(f"Launching {'fresh ' if FRESH_BROWSER_PROFILE else ''}browser profile: {USER_DATA_DIR}")

    # Docker needs headless + extra Chromium args to run without a display
    headless = is_docker
    extra_args = [
        '--ignore-certificate-errors',
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',   # use /dev/shm mounted via shm_size
        '--disable-gpu',
    ] if is_docker else ['--ignore-certificate-errors']

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=headless,
        ignore_https_errors=True,
        viewport=VIEWPORT,
        user_agent=agent['userAgent'],
        proxy=proxy_config,
        args=extra_args,
    )
    context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
    context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    print(f'Browser agent: {agent["name"]}')
    return context