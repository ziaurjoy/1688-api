

import asyncio
import json
import os
import random
import shutil
import urllib.parse
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright
from dotenv import load_dotenv
from utils import utils as utils_file
from scriping_files.config import (
    BLOCK_HEAVY_RESOURCES,
    BLOCKED_RESOURCE_TYPES,
    BODY_WAIT_TIMEOUT_MS,
    BROWSER_AGENTS,
    CAPTCHA_KEYWORDS,
    CHECK_PROXY_FIRST,
    COOKIE_FILE,
    FRESH_BROWSER_PROFILE,
    KEEP_BROWSER_OPEN,
    LOAD_1688_COOKIES,
    LOAD_SAVED_COOKIES,
    NAVIGATION_RETRIES,
    NAVIGATION_TIMEOUT_MS,
    PROXY_CHECK_URL,
    SAVE_PAGE_COOKIES,
    USER_DATA_DIR,
    VERIFICATION_CHECK_DELAY_MS,
    VIEWPORT,
)
from scriping_files.raw_cookies import RAW_1688_COOKIES

load_dotenv()

try:
    from database import db
except ModuleNotFoundError:
    import os, sys
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    from database import db

from fastapi.encoders import jsonable_encoder
from scriping_files.details_scriping_page import save_image_from_url



state_file_path="scraping_state.json"
PROCESS_RETRIES = 2
VERIFICATION_RETRIES = 1


def pick_browser_agent() -> dict:
    return random.choice(BROWSER_AGENTS)


def is_env_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_proxy_config():
    proxy_url = os.getenv("PROXY_URL")
    if not proxy_url:
        return None

    proxy = {
        "server": proxy_url,
        "bypass": "localhost,127.0.0.1",
    }
    username = os.getenv("PROXY_USERNAME")
    password = os.getenv("PROXY_PASSWORD")
    if username and password:
        proxy["username"] = username
        proxy["password"] = password
    return proxy


def destroy_browser_profile():
    try:
        shutil.rmtree(USER_DATA_DIR)
        print(f"Destroyed browser profile: {USER_DATA_DIR}")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Could not destroy browser profile at {USER_DATA_DIR}: {e}")


async def clear_browser_data(context):
    try:
        await context.clear_cookies()
        print("Cleared browser cookies.")
    except Exception as e:
        print(f"Could not clear browser cookies: {e}")


async def clear_saved_cookies():
    try:
        Path(COOKIE_FILE).unlink(missing_ok=True)
        print(f"Cleared saved cookies: {COOKIE_FILE}")
    except Exception as e:
        print(f"Could not clear saved cookies at {COOKIE_FILE}: {e}")


def normalize_cookie(cookie):
    normalized = {
        "name": cookie.get("name"),
        "value": cookie.get("value", ""),
        "path": cookie.get("path", "/"),
        "secure": bool(cookie.get("secure", False)),
        "httpOnly": bool(cookie.get("httpOnly", False)),
    }

    if cookie.get("domain"):
        normalized["domain"] = cookie["domain"]
    if cookie.get("url"):
        normalized["url"] = cookie["url"]

    expires = cookie.get("expires", cookie.get("expirationDate"))
    if expires is not None:
        normalized["expires"] = int(expires)

    same = cookie.get("sameSite")
    if isinstance(same, str):
        same = same.lower()
        if same in ("no_restriction", "none"):
            normalized["sameSite"] = "None"
        elif same == "lax":
            normalized["sameSite"] = "Lax"
        elif same == "strict":
            normalized["sameSite"] = "Strict"

    return normalized


async def set_1688_cookies(context):
    if not LOAD_1688_COOKIES:
        return

    formatted = [normalize_cookie(cookie) for cookie in RAW_1688_COOKIES if cookie.get("name")]
    if formatted:
        await context.add_cookies(formatted)
        print(f"Loaded {len(formatted)} built-in 1688 cookies.")


async def load_saved_cookies(context):
    if not LOAD_SAVED_COOKIES:
        return

    if not os.path.exists(COOKIE_FILE):
        print(f"No saved cookie file at {COOKIE_FILE}.")
        return

    try:
        cookies = load_json(COOKIE_FILE, default=[])
        formatted = [normalize_cookie(cookie) for cookie in cookies if cookie.get("name")]
        if not formatted:
            print(f"Cookie file {COOKIE_FILE} is empty.")
            return

        try:
            await context.add_cookies(formatted)
            print(f"Loaded {len(formatted)} saved cookies from {COOKIE_FILE}.")
        except Exception as e:
            print(f"Bulk add_cookies failed: {e}. Trying individually...")
            added = 0
            for cookie in formatted:
                try:
                    await context.add_cookies([cookie])
                    added += 1
                except Exception as e2:
                    print(f"Skipping cookie {cookie.get('name')} due to error: {e2}")
            print(f"Loaded {added} cookies (individual add)")
    except Exception as e:
        print(f"Cookie load error: {e}")


async def save_page_cookies(context):
    if not SAVE_PAGE_COOKIES:
        return

    try:
        cookies = await context.cookies()
        Path(COOKIE_FILE).parent.mkdir(parents=True, exist_ok=True)
        save_json(COOKIE_FILE, cookies)
        print(f"Saved {len(cookies)} page cookies to {COOKIE_FILE}")
    except Exception as e:
        print(f"Error saving cookies: {e}")


async def setup_resource_blocking(page):
    if not BLOCK_HEAVY_RESOURCES:
        return

    async def route_handler(route, request):
        if request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        await route.continue_()

    await page.route("**/*", route_handler)


async def page_text(page) -> str:
    try:
        title = await page.title() or ""
        url = page.url or ""
        body = await page.inner_text("body", timeout=5_000) or ""
        return " ".join([title, url, body]).lower()
    except Exception:
        return ""


async def is_verification_page(page) -> bool:
    text = await page_text(page)
    return any(keyword.lower() in text for keyword in CAPTCHA_KEYWORDS)


async def throw_if_verification_page(page):
    if VERIFICATION_CHECK_DELAY_MS > 0:
        await asyncio.sleep(VERIFICATION_CHECK_DELAY_MS / 1000)
    if await is_verification_page(page):
        await clear_saved_cookies()
        raise VerificationPageError()


async def goto_page(page, url: str, label: str):
    last_error = None
    for attempt in range(1, NAVIGATION_RETRIES + 2):
        try:
            print(f"Opening {label}: {url} (attempt {attempt})")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            await page.wait_for_selector("body", timeout=BODY_WAIT_TIMEOUT_MS)
            await throw_if_verification_page(page)
            return response
        except PlaywrightTimeoutError as e:
            last_error = e
            if await page.query_selector("body"):
                await throw_if_verification_page(page)
                print("Timed out but body is present. Continuing.")
                return None
        except Exception as e:
            if isinstance(e, VerificationPageError):
                raise
            last_error = e
            if attempt <= NAVIGATION_RETRIES:
                print(f"Navigation failed: {e}. Retrying in 3 s...")
                await asyncio.sleep(3)

    raise last_error


async def check_proxy(page):
    if not CHECK_PROXY_FIRST:
        return

    print("Checking proxy...")
    await goto_page(page, PROXY_CHECK_URL, "proxy check")
    location = (await page.inner_text("body", timeout=10_000)).strip().replace("\n", " ")
    print(f"Proxy location: {location}")


class VerificationPageError(Exception):
    """Raised when 1688 returns a CAPTCHA or login verification page."""


async def new_configured_page(context):
    page = await context.new_page()
    await page.set_extra_http_headers({"accept-language": "zh-CN,zh;q=0.9,en;q=0.8"})
    await setup_resource_blocking(page)
    return page


async def process_item_with_retries(context, searching_key, browser, requests):
    last_error = None
    verification_retries_used = 0

    for attempt in range(1, PROCESS_RETRIES + 2):
        page = await new_configured_page(context)
        try:
            if attempt == 1:
                await check_proxy(page)
            await process_item(page, searching_key, browser, context, requests)
            return
        except VerificationPageError as e:
            last_error = e
            if verification_retries_used < VERIFICATION_RETRIES:
                verification_retries_used += 1
                print(f"Verification page appeared. Closing page and retrying once for {searching_key}.")
                await clear_browser_data(context)
                await asyncio.sleep(5 + random.randint(3, 10))
                continue
            raise
        except Exception as e:
            last_error = e
            print(f"Process attempt {attempt} failed for {searching_key}: {e}")
            if attempt <= PROCESS_RETRIES:
                await asyncio.sleep(5 + random.randint(3, 10))
            else:
                raise last_error
        finally:
            try:
                await page.close()
            except Exception as e:
                print(f"Error closing retry page: {e}")

    if last_error:
        raise last_error


def load_state(file_path="scraping_state.json"):
    default_state = {
        "max_pages": 5,
        "current_page": 1,
        "last_page": 0,
        "current_url": "",
        "last_url": ""
    }
    return load_json(file_path, default=default_state)


def save_state(state, file_path="scraping_state.json"):
    save_json(file_path, state)


def load_json(file_path: str, default=None):
    if default is None:
        default = []

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return default

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def init_product_file(file_path="collected_product_data.json"):
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)


def save_json(file_path: str, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def save_last_page(url: str, file_path="lastvisit.txt"):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(url)


# ---------------------------
# Product Card Parser
# ---------------------------


async def parse_categories(page):

    item_name = await page.locator("#productTitle h1").inner_text()
    item_name = item_name.strip()

    breadcrumbs = await page.locator(".breadcrumb a").all_inner_texts()

    # Clean
    breadcrumbs = [b.strip() for b in breadcrumbs if b.strip()]

    category = breadcrumbs[1] if len(breadcrumbs) > 1 else ""
    subcategory = breadcrumbs[2] if len(breadcrumbs) > 2 else ""

    data = {
        "category": category,
        "sub_category": subcategory,
        "item_name": item_name
    }
    return data


async def parse_product_card(card, requests):
    async def qs(selector, attr=None):
        el = await card.query_selector(selector)
        if not el:
            return None
        return await el.get_attribute(attr) if attr else (await el.inner_text()).strip()

    href = await card.get_attribute("href")

    # Offer ID
    offer_id = None
    if href:
        if "offer/" in href:
            offer_id = href.split("offer/")[-1].split(".")[0]
        else:
            q = parse_qs(urlparse(href).query)
            offer_id = q.get("a", [None])[0]

    # Price
    currency = await qs(".price-wrap .symbol")
    amount = await qs(".price-wrap .number")
    unit = await qs(".price-wrap .unit")

    overseas_price_el = await card.query_selector(".overseas-price")
    overseas_price = (
        (await overseas_price_el.inner_text()).replace("≈", "").strip()
        if overseas_price_el else None
    )

    return {

        "offer_id": offer_id,
        "title": await qs(".offer-title"),
        "url": href,
        "image": save_image_from_url(await qs("img.main-img", attr="src"), f"{utils_file.get_project_url(requests)}assets/images/product_images"),
        "price": {
            "currency": currency,
            "amount": amount,
            "unit": unit,
            "overseas": overseas_price
        },
        "rating": await qs(".star-level-text"),
        "sold": await qs(".sale-amount-wrap"),
        "promotion": await qs(".promotion-tags"),
        "moq": await qs(".overseas-begin-quantity-wrap"),
        "seller_icon": await qs(".overseas-seller-icon", attr="src"),
        "is_ad": "cardui-adOffer" in (await card.get_attribute("class") or "")
    }


# ---------------------------
# Pagination
# ---------------------------

# ...existing code...

async def click_next_page(page):
    next_btn = page.locator(".fui-arrow.fui-next")

    # Update state
    page_url = page.url
    state_file_path = "scraping_state.json"

    state = load_state(state_file_path)

    # Safely get current page, default to 1 if not found
    try:
        current_page_text = await page.locator(".fui-current").inner_text()
        state["current_page"] = int(current_page_text) if current_page_text else 1
    except Exception:
        state["current_page"] = 1

    state["current_url"] = page_url

    # Safely get max pages, default to 5 if not found
    try:
        max_pages_text = await page.locator(".fui-paging-num").inner_text()
        if max_pages_text:
            state["max_pages"] = int(max_pages_text)
    except Exception:
        pass

    save_state(state, state_file_path)

    current_page_before = state["current_page"]

    if not await next_btn.count():
        return {"has_next": False, "page": page}

    class_name = await next_btn.get_attribute("class")
    if "disabled" in class_name:
        return {"has_next": False, "page": page}

    try:
        await next_btn.scroll_into_view_if_needed()

        await next_btn.click()
        await page.wait_for_load_state("networkidle")

        # Verify the page actually advanced
        try:
            new_current_page_text = await page.locator(".fui-current").inner_text()
            new_current_page = int(new_current_page_text) if new_current_page_text else current_page_before
            if new_current_page != current_page_before + 1:
                print(f"Page did not advance correctly: expected {current_page_before + 1}, got {new_current_page}")
                return {"has_next": False, "page": page}
        except Exception as e:
            print(f"Error verifying page advance: {e}")
            return {"has_next": False, "page": page}

        # Update state with new page
        state["current_page"] = new_current_page
        state["current_url"] = page.url
        save_state(state, state_file_path)

        return {"has_next": True, "page": page}
    except Exception as e:
        print(f"Error clicking next page: {e}")
        return {"has_next": False, "page": page}


async def extract_products_from_page(page, browser, context, requests):

    state = load_state(state_file_path)
    current_page = state["current_page"]
    max_pages = state["max_pages"]

    while current_page <= max_pages:

        state = load_state(state_file_path)
        current_page = state["current_page"]
        max_pages = state["max_pages"]
        for attempt in range(3):
            try:
                await page.wait_for_selector("a.i18n-card-wrap", timeout=30000)
                break
            except Exception as e:
                print(f"Attempt {attempt + 1} failed to load selector for page {current_page}: {e}")
                await throw_if_verification_page(page)
                if attempt < 2:
                    await asyncio.sleep(5 + random.randint(5, 10))
                else:
                    raise e

        cards = await page.query_selector_all("a.i18n-card-wrap")

        for card in cards:
            product = await parse_product_card(card, requests)
            product_id = product.get("offer_id")

            query = {
                "$or": [
                    {"offer_id": {"$regex": product_id, "$options": "i"}},
                ]
            }

            total = await db.products.count_documents(query)
            if total > 0:
                print(f"Product with offer_id {product_id} already exists. Skipping.")
                continue

            product_name = await page.locator("#alisearch-input").input_value()
            product.update({"product_name": product_name})
            # product.update(await parse_categories(page))
            data = jsonable_encoder(product)
            if product:
                await db.products.insert_one(data)

        # Add random delay to mimic human behavior
        await asyncio.sleep(random.randint(2, 5))

        after_click = await click_next_page(page)

        print("Has next page:", after_click.get("has_next"))
        if not after_click.get("has_next"):
            print("No more pages")
            break

        page = after_click.get("page")
        # Reload state after page change
        state = load_state(state_file_path)
        current_page = state["current_page"]

    if current_page > max_pages:
        print("Reached max page limit")

async def process_item(page, searching_key, browser, context, requests):
    searching_key_encoded = urllib.parse.quote(searching_key)
    url = f"https://s.1688.com/selloffer/offer_search.htm?charset=utf8&keywords={searching_key_encoded}"
    try:
        await goto_page(page, url, "search results")
        await extract_products_from_page(page, browser, context, requests)

    except Exception as e:
        print(f"Error processing item {searching_key}: {e}")
        raise




async def playwright_main(searching_key, requests):
    browser = None
    context = None
    verification_hit = False

    async with async_playwright() as p:
        playwright_endpoint = os.getenv("PLAYWRIGHT_ENDPOINT")
        try:
            browser_agent = pick_browser_agent()
            proxy = build_proxy_config()

            if playwright_endpoint:
                print(f"Connecting to Playwright server at: {playwright_endpoint}")
                browser = await p.chromium.connect(playwright_endpoint, timeout=NAVIGATION_TIMEOUT_MS)
                context_options = {
                    "ignore_https_errors": True,
                    "viewport": VIEWPORT,
                    "user_agent": browser_agent["userAgent"],
                }
                if proxy:
                    context_options["proxy"] = proxy
                context = await browser.new_context(**context_options)
            else:
                if FRESH_BROWSER_PROFILE:
                    destroy_browser_profile()

                is_docker = is_env_enabled("RUNNING_IN_DOCKER")
                headless = is_env_enabled("PLAYWRIGHT_HEADLESS", default=is_docker)
                launch_args = [
                    "--ignore-certificate-errors",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ] if is_docker else ["--ignore-certificate-errors"]

                print(f"Launching browser profile: {USER_DATA_DIR} headless={headless}")
                context_options = {
                    "user_data_dir": USER_DATA_DIR,
                    "headless": headless,
                    "ignore_https_errors": True,
                    "viewport": VIEWPORT,
                    "user_agent": browser_agent["userAgent"],
                    "args": launch_args,
                }
                if proxy:
                    context_options["proxy"] = proxy
                context = await p.chromium.launch_persistent_context(**context_options)

            context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
            context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
            print(f'Browser agent: {browser_agent["name"]}')

            await load_saved_cookies(context)
            await set_1688_cookies(context)

            await process_item_with_retries(context, searching_key, browser, requests)
            await save_page_cookies(context)

            print(f"\n{'='*50}")
            print("Collection Complete!")
            print(f"Output cookies saved to: {COOKIE_FILE}")
            print(f"{'='*50}")
        except Exception as e:
            verification_hit = isinstance(e, VerificationPageError)
            raise
        finally:
            if verification_hit and context:
                await clear_browser_data(context)
            if context and (not KEEP_BROWSER_OPEN or verification_hit):
                try:
                    await context.close()
                except Exception as e:
                    print(f"Error closing context: {e}")
            if browser and (not KEEP_BROWSER_OPEN or verification_hit):
                try:
                    await browser.close()
                except Exception as e:
                    print(f"Error closing browser: {e}")
            if verification_hit:
                destroy_browser_profile()



# if __name__ == "__main__":
#     init_product_file()
#     asyncio.run(playwright_main("laptop"))
