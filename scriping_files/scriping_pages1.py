import asyncio
import json
import os
import random
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright

from fastapi.encoders import jsonable_encoder
# from app.database import db
from database import db

# from scriping_files.scriping_pages import process_item

state_file_path="scraping_state.json"


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

async def parse_product_card(card):
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
        "image": await qs("img.main-img", attr="src"),
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
    print('========')
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


async def extract_products_from_page(page):

    state = load_state(state_file_path)
    current_page = state["current_page"]
    max_pages = state["max_pages"]

    while current_page <= max_pages:
        print(f"Scraping page {current_page}")

        state = load_state(state_file_path)
        current_page = state["current_page"]
        max_pages = state["max_pages"]

        for attempt in range(3):
            try:
                await page.wait_for_selector("a.i18n-card-wrap", timeout=30000)
                # break
                continue
            except Exception as e:
                print(f"Attempt {attempt + 1} failed to load selector for page {current_page}: {e}")
                if attempt < 2:
                    await asyncio.sleep(5 + random.randint(5, 10))
                else:
                    raise e
        page_url = page.url

        cards = await page.query_selector_all("a.i18n-card-wrap")
        print("Cards found:", len(cards))

        products = []
        for card in cards:
            product = await parse_product_card(card)
            product.update(await parse_categories(page))
            print('=============',product)
            if product:
                result = await db.products.insert_one(product)
                # products.append(product)

        # stored_data = load_json(product_file_path)

        # record = {
        #     # "category": category_name,
        #     # "subcategory": sub_category_name,
        #     # "item": item_name,
        #     "page_url": page_url,
        #     "page": current_page,
        #     "products": products
        # }

        # data = jsonable_encoder(record)

        # # Insert is async with Motor, so await the result and return the new id
        # result = await db.products.insert_one(data)

        # stored_data.append(record)
        # save_json(product_file_path, stored_data)

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



async def process_item(page, searching_key):
    url = f"https://s.1688.com/selloffer/offer_search.htm?charset=utf8&keywords={searching_key}"
    for attempt in range(3):
        try:
            await page.goto(url, timeout=60000)
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {searching_key}: {e}")
            if attempt < 2:
                await asyncio.sleep(10 + random.randint(5, 15))
            else:
                raise e

    await extract_products_from_page(page)



# https://s.1688.com/selloffer/offer_search.htm?charset=utf8&keywords=大码针织衫
async def playwright_main(searching_key):

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # viewport={"width": 1280, "height": 720}
        )

        # Load cookies from file next to this module so relative paths work the same regardless of cwd
        try:
            cookie_file = os.path.join(os.path.dirname(__file__), "cookie.json")
            with open(cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            formatted = []
            for c in cookies:
                # Playwright accepts either a `url` OR a `domain`+`path`. Using `url` is simpler and more reliable.
                domain = c.get("domain")
                path = c.get("path", "/") or "/"

                cookie = {
                    "name": c.get("name"),
                    "value": c.get("value", ""),
                    "path": path,
                    "secure": c.get("secure", False),
                    "httpOnly": c.get("httpOnly", False),
                }

                # Prefer building a full URL so Playwright will apply the cookie to navigations
                if domain:
                    # remove leading dot if present
                    host = domain.lstrip('.')
                    cookie["url"] = f"https://{host}{path}"
                elif c.get("url"):
                    cookie["url"] = c.get("url")

                # expirationDate from some exports is in seconds since epoch
                if "expirationDate" in c:
                    try:
                        cookie["expires"] = int(c["expirationDate"])
                    except Exception:
                        pass

                if c.get("sameSite") == "no_restriction":
                    cookie["sameSite"] = "None"
                elif "sameSite" in c:
                    cookie["sameSite"] = c.get("sameSite")

                formatted.append(cookie)

            if formatted:
                await context.add_cookies(formatted)
                print(f"Loaded {len(formatted)} cookies")

                # Debug: show the cookies currently in the context
                current = await context.cookies()
                print("Context cookies after load:", current)
            else:
                print("No cookies found to load")

        except FileNotFoundError:
            print(f"Cookie file not found: {cookie_file}")
        except Exception as e:
            print("Cookie load error:", e)
        print('=====')
        page = await context.new_page()


                # await process_item(page, category_name, subcategory_name, item, _link)
        await process_item(page, searching_key)
        print("hhh")


            # state_file_path = "scraping_state.json"
            # state = load_state(state_file_path)
            # state["current_page"] = 1
            # state["current_url"] = ""
            # state["max_pages"] = 5
            # save_state(state, state_file_path)

            # Delay between items
        await asyncio.sleep(random.randint(5, 10))




        print("Scraping finished. Browser will remain open.")

        # Save cookies to cookie.json
        cookies = await context.cookies()
        with open("cookie.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=4, ensure_ascii=False)


        await asyncio.Event().wait()

