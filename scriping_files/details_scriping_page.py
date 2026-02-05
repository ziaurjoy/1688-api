import os
import json
import asyncio
import random
import requests
from urllib.parse import urlparse
from playwright.async_api import async_playwright


try:
    from database import db
except ModuleNotFoundError:
    import os, sys
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    from database import db

from fastapi.encoders import jsonable_encoder

def save_image_from_url(image_url: str, save_dir: str = "downloads"):
    """
    Download an image from a URL and save it locally.

    :param image_url: Direct image URL
    :param save_dir: Folder where the image will be saved
    :return: Full path of saved image
    """

    # Create directory if not exists
    os.makedirs(save_dir, exist_ok=True)

    # Extract image name from URL
    parsed_url = urlparse(image_url)
    filename = os.path.basename(parsed_url.path)

    if not filename:
        raise ValueError("Cannot determine image filename from URL")

    file_path = os.path.join(save_dir, filename)

    # Download image
    response = requests.get(image_url, timeout=15)
    response.raise_for_status()

    # Save image
    with open(file_path, "wb") as f:
        f.write(response.content)

    return file_path

# ---------------------------
# JSON Utilities
# ---------------------------


async def extract_categories(page):

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

def product_id_exists(file_path: str, value: str) -> bool:
    """
    Check if a value exists in file
    """
    value = value.strip()

    if not value:
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return value in (line.strip() for line in f)
    except FileNotFoundError:
        return False


def append_product_id_value(file_path: str, value: str) -> None:
    """
    Append a value to file if it does not already exist
    """
    value = value.strip()

    if not value:
        return

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(value + "\n")

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





# ---------------------------
# Detail Page Parser
# ---------------------------


async def extract_product_reviews(page):
    """
    Extract product reviews section from 1688 product detail page
    """
    try:
        await page.wait_for_selector("#productEvaluation")

        rating = await page.locator(
            "#productEvaluation .header-label-desc em.hl >> nth=0"
        ).inner_text()

        positive_rate = await page.locator(
            "#productEvaluation .header-label-desc em.hl >> nth=1"
        ).inner_text()

        total_reviews = await page.locator(
            "#productEvaluation .header-label-desc .brackets"
        ).get_attribute("data-value")

        data = {
            "summary": {
                "rating": rating.strip(),
                "total_reviews": int(total_reviews) if total_reviews else None,
                "positive_rate": positive_rate.strip()
            }
        }

        return data
    except Exception:
        data = {
            "summary": {
                "rating": "0.0",
                "total_reviews": 0,
                "positive_rate": "0%"
            }
        }
        return data


async def extract_product_attributes(page):
    """
    Extract product attributes from 1688 product detail page
    :param page: playwright.async_api.Page
    :return: dict
    """

    await page.wait_for_selector("#productAttributes")

    # Expand all attributes if collapsed
    expand_btn = page.locator(
        "#productAttributes .collapse-footer button"
    )
    if await expand_btn.count() > 0:
        await expand_btn.click()
        # await page.wait_for_timeout(500)

    attributes = {}

    rows = page.locator(
        "#productAttributes .ant-descriptions-row"
    )
    row_count = await rows.count()

    for i in range(row_count):
        row = rows.nth(i)

        labels = row.locator(".ant-descriptions-item-label")
        values = row.locator(".ant-descriptions-item-content .field-value")

        label_count = await labels.count()
        value_count = await values.count()

        # Pair labels and values safely
        for j in range(min(label_count, value_count)):
            key = (await labels.nth(j).inner_text()).strip()
            value = (await values.nth(j).inner_text()).strip()
            attributes[key] = value

    return attributes


async def extract_product_packing(page):
    """
    Extract product packaging information from 1688 product detail page
    :param page: playwright.async_api.Page
    :return: list[dict]
    """

    await page.wait_for_selector("#productPackInfo")

    packing_list = []

    rows = page.locator(
        "#productPackInfo tbody tr"
    )
    row_count = await rows.count()

    for i in range(row_count):
        row = rows.nth(i)
        cols = row.locator("td")

        packing_list.append({
            "color": (await cols.nth(0).inner_text()).strip(),
            "size": (await cols.nth(1).inner_text()).strip() if await cols.count() > 1 else None,
            "weight_g": (await cols.nth(2).inner_text()).strip() if await cols.count() > 2 else None,
        })

    return packing_list




async def extract_product_variants(page):
    """
    Extract full SKU matrix dynamically: click each color variant and get only its sizes.
    """
    try:
        sku_matrix = []

        # --- Step 1: Get all color/style buttons ---
        color_buttons = page.locator(".transverse-filter .sku-filter-button")
        color_count = await color_buttons.count()

        print(f"Found {color_count} color variants")

        for i in range(color_count):
            try:
                # Re-query color buttons in case DOM changed
                color_buttons = page.locator(".transverse-filter .sku-filter-button")
                btn = color_buttons.nth(i)

                # Click color to load sizes
                await btn.click()
                await page.wait_for_timeout(500)  # Wait for DOM to update

                color_variant = {
                    "color_name": "",
                    "image": "",
                    "active": False,
                    "sizes": []
                }

                # Extract color info
                try:
                    color_variant["color_name"] = (await btn.locator(".label-name").inner_text()).strip()
                except Exception:
                    pass

                try:
                    img_el = btn.locator("img")
                    if await img_el.count() > 0:
                        # color_variant["image"] = await img_el.get_attribute("src")
                        color_variant_images = await img_el.get_attribute("src")
                        # Save image locally
                        if color_variant_images:
                            try:
                                color_variant["image"] = save_image_from_url(color_variant_images, save_dir="assets/images/variant_images")
                            except Exception:
                                pass
                except Exception:
                    pass

                try:
                    class_attr = await btn.get_attribute("class")
                    color_variant["active"] = "active" in (class_attr or "").split()
                except Exception:
                    pass

                # --- Step 2: Extract sizes for this color ---
                try:
                    size_container = page.locator(".expand-view-list")
                    size_items = size_container.locator(".expand-view-item")
                    size_count = await size_items.count()

                    print(f"  Color {i+1}: '{color_variant['color_name']}' has {size_count} sizes")

                    for j in range(size_count):
                        try:
                            size_item = size_items.nth(j)

                            size_name = ""
                            price = ""
                            stock = ""

                            # Get size name
                            try:
                                size_label = size_item.locator(".item-label")
                                if await size_label.count() > 0:
                                    size_name = (await size_label.inner_text()).strip()
                            except Exception:
                                pass

                            # Get price and stock
                            price_stock_spans = size_item.locator(".item-price-stock")
                            price_stock_count = await price_stock_spans.count()

                            if price_stock_count > 0:
                                try:
                                    price = (await price_stock_spans.nth(0).inner_text()).strip()
                                except Exception:
                                    pass

                            if price_stock_count > 1:
                                try:
                                    stock = (await price_stock_spans.nth(1).inner_text()).strip()
                                    # Clean up stock text - remove extra whitespace
                                    stock = " ".join(stock.split())
                                except Exception:
                                    pass

                            size_data = {
                                "size_name": size_name,
                                "price": price,
                                "stock": stock,
                            }

                            color_variant["sizes"].append(size_data)

                        except Exception as e:
                            print(f"    Error extracting size {j}: {e}")
                            continue

                except Exception as e:
                    print(f"  Error extracting sizes for color {i}: {e}")

                sku_matrix.append(color_variant)

            except Exception as e:
                print(f"Error processing color variant {i}: {e}")
                continue

        return sku_matrix

    except Exception as e:
        print(f"Error in extract_product_variants: {e}")
        return []


async def extract_product_description(page):
    """
    Extract product description and price description from 1688 product detail page
    """
    await page.wait_for_selector(".price-indication")

    description = {
        "images": [],
        "html": None,
        "price_desc": {}
    }

    # --------------------------------
    # Extract description images
    # --------------------------------
    detail_component = page.locator("#description")
    imgs = detail_component.locator("img")

    for i in range(await imgs.count()):
        src = await imgs.nth(i).get_attribute("src")
        if src:
            local_file_path = save_image_from_url(src, save_dir="assets/images/description_images")
            description["images"].append(local_file_path)


    # --------------------------------
    # Extract price description
    # --------------------------------
    price_desc_root = page.locator(".price-desc")

    # Get all dt and dl inside price-desc (in DOM order)
    nodes = price_desc_root.locator(":scope > dt, :scope > dl")
    node_count = await nodes.count()

    current_title = None

    for i in range(node_count):
        node = nodes.nth(i)
        tag = await node.evaluate("el => el.tagName.toLowerCase()")

        text = (await node.inner_text()).strip()
        if not text:
            continue

        if tag == "dt":
            current_title = text
            description["price_desc"][current_title] = []
        elif tag == "dl" and current_title:
            description["price_desc"][current_title].append(text)

    return description


async def extract_product_title_and_cart(page):
    """
    Extract productTitle and cartScrollBar data from 1688 product page
    :param page: playwright.async_api.Page
    :return: dict
    """

    await page.wait_for_selector("#productTitle")
    # await page.wait_for_selector("#cartScrollBar", timeout=15000)

    data = {
        "productTitle": {},
        "cart": {}
    }

    # -------------------------
    # PRODUCT TITLE
    # -------------------------

    title_root = page.locator("#productTitle")

    title_h1 = title_root.locator("h1")
    rating_el = title_root.locator(".hl")
    reviews_el = title_root.locator(".brackets")
    sales_el = title_root.locator(".trade-info em.hl")

    data["productTitle"] = {
        "title": (await title_h1.first.inner_text()).strip() if await title_h1.count() else "",
        "rating": (await rating_el.first.inner_text()).strip() if await rating_el.count() else "0.0",
        "reviews": (await reviews_el.first.inner_text()).strip() if await reviews_el.count() else "0",
        "total_sales": (await sales_el.nth(1).inner_text()).strip() if await sales_el.count() > 1 else "0",
    }

    # -------------------------
    # CART SCROLL BAR
    # -------------------------
    cart = page.locator("#cartScrollBar")

    # ---- Price ----
    prices = cart.locator("#mainPrice .price-info span")
    price_values = [await prices.nth(i).inner_text() for i in range(await prices.count())]

    data["cart"]["price_range"] = "".join(price_values)
    data["cart"]["min_order"] = (await cart.locator("#mainPrice").inner_text()).strip()

    # ---- Services ----
    services = cart.locator("#mainServices .service-item-link")
    data["cart"]["services"] = [
        (await services.nth(i).inner_text()).strip()
        for i in range(await services.count())
    ]

    # ---- Shipping ----
    data["cart"]["shipping_from"] = (
        await cart.locator("#shippingServices .location").inner_text()
    ).strip()

    # -------------------------
    # SKU SELECTION
    # -------------------------
    skus = []

    sizes = cart.locator("#skuSelection .expand-view-item")

    for i in range(await sizes.count()):
        size = sizes.nth(i)

        skus.append({
            "size": (await size.locator(".item-label").inner_text()).strip(),
            "price": (await size.locator(".item-price-stock").first.inner_text()).strip(),
            "stock": (await size.locator(".item-price-stock").nth(1).inner_text()).strip(),
        })

    data["cart"]["skus"] = skus

    return data


async def parse_product_details(page):
    """Extract product details from 1688 product detail page"""

    # try:
    data = {
        "extract_product_reviews": await extract_product_reviews(page),
        "extract_product_attributes": await extract_product_attributes(page),
        "extract_product_packing": await extract_product_packing(page),
        "extract_product_description": await extract_product_description(page),
        "extract_product_title_and_cart": await extract_product_title_and_cart(page),
        "extract_product_variants": await extract_product_variants(page),
        "extract_categories": await extract_categories(page),
    }

    return data


# ---------------------------
# Product Detail Collector
# ---------------------------

async def collect_product_details(page, url, product_id, browser, context):
    """Collect details for a single product"""

    try:
        print(f"Fetching details from: {url}")
        await page.goto(url)

        details = await parse_product_details(page)
        print('=====details', details)
        await db.products.update_one(
            {"offer_id": product_id},
            {"$set": {"details": details}},
            upsert=True
        )
        await context.close()
        await browser.close()


    except Exception as e:
        print(f"✗ Failed after 3 attempts for {url}")
        await context.close()
        await browser.close()







# ---------------------------
# Playwright Main
# ---------------------------

async def playwright_main_details(details_link, product_id):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # Load cookies if available
        try:
            # with open("cookie.json", "r", encoding="utf-8") as f:
            #     cookies = json.load(f)
            cookie_file = os.path.join(os.path.dirname(__file__), "cookie.json")
            # if os.path.exists(cookie_file):
            with open(cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            formatted = []
            for c in cookies:
                try:
                    cookie = {
                        "name": c.get("name"),
                        "value": c.get("value", ""),
                        "domain": c.get("domain"),
                        "path": c.get("path", "/"),
                        "secure": bool(c.get("secure", False)),
                        "httpOnly": bool(c.get("httpOnly", False))
                    }

                    # Normalize expiration to integer seconds if provided
                    if "expirationDate" in c and c.get("expirationDate") is not None:
                        cookie["expires"] = int(c["expirationDate"])

                    # Normalize sameSite values. Accept common variants and skip None.
                    same = c.get("sameSite")
                    if isinstance(same, str):
                        s = same.lower()
                        if s in ("no_restriction", "none"):
                            cookie["sameSite"] = "None"
                        elif s == "lax":
                            cookie["sameSite"] = "Lax"
                        elif s == "strict":
                            cookie["sameSite"] = "Strict"

                    formatted.append(cookie)
                except Exception as e:
                    print(f"Skipping invalid cookie {c.get('name')}: {e}")

            # Try to add cookies in bulk; if that fails, add them one-by-one to isolate bad cookies
            try:
                await context.add_cookies(formatted)
                print(f"Loaded {len(formatted)} cookies")
            except Exception as e:
                print(f"Bulk add_cookies failed: {e}. Trying individually...")
                added = 0
                for c in formatted:
                    try:
                        await context.add_cookies([c])
                        added += 1
                    except Exception as e2:
                        print(f"Skipping cookie {c.get('name')} due to error: {e2}")
                print(f"Loaded {added} cookies (individual add)")

        except Exception as e:
            print(f"Cookie load error: {e}")

        page = await context.new_page()

        # await process_item(page, searching_key, browser, context)
        await collect_product_details(page, details_link, product_id, browser, context)

        # Collect details for each product
        success_count = 0
        failed_count = 0

        # Save cookies
        try:
            cookies = await context.cookies()
            with open("cookie.json", "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=4, ensure_ascii=False)
            print(f"\nUpdated cookies saved")
        except Exception as e:
            print(f"Error saving cookies: {e}")

        await browser.close()

        print(f"\n{'='*50}")
        print(f"Collection Complete!")
        print(f"Successfully collected: {success_count}")
        print(f"Failed: {failed_count}")
        print(f"Total: {success_count + failed_count}")
        print(f"Output saved to: product_details.json")
        print(f"{'='*50}")




