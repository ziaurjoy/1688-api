import json
import re
import sys
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_HTML_FILE = 'output/html/rendered-product-907073856056.html'


def get_product_id(file_path):
    match = re.search(r'(\d+)(?=\.html$)', str(file_path))
    return match.group(1) if match else 'unknown'


def get_default_output_file(html_file):
    html_path = Path(html_file)
    html_dir = html_path.parent
    if html_dir.name == 'html':
        output_dir = html_dir.parent / 'json'
    else:
        output_dir = html_dir
    return output_dir / f'context-data-{get_product_id(html_file)}.json'


async def extract_context_script(html):
    """Extract the script block containing window.context from HTML."""
    pattern = re.compile(
        r'<script[^>]*>\s*window\.contextPath\s*=\s*"/default";[\s\S]*?</script>',
        re.IGNORECASE,
    )
    match = pattern.search(html)
    if not match:
        raise ValueError('Could not find script starting with window.contextPath = "/default";')

    script_block = match.group(0)
    script_block = re.sub(r'^<script[^>]*>', '', script_block, flags=re.IGNORECASE)
    script_block = re.sub(r'</script>$', '', script_block, flags=re.IGNORECASE)
    return script_block.strip()


async def evaluate_context_via_playwright(script):
    """Async evaluator using Playwright Async API."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('about:blank')
        await page.add_script_tag(content=script)
        context = await page.evaluate('window.context')
        await browser.close()
        return context


import concurrent.futures

def extract_context_json_sync(html_file=DEFAULT_HTML_FILE, output_file=None):
    """Synchronous wrapper safe to call from threads with an existing event loop."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            asyncio.run,
            extract_context_json(html_file, output_file)
        )
        return future.result()


async def extract_context_json(html_file=DEFAULT_HTML_FILE, output_file=None):
    """
    Extract window.context JSON from a rendered HTML file and save it.

    Args:
        html_file: Path to the rendered HTML file.
        output_file: Path where the JSON output will be saved. Auto-derived if None.

    Returns:
        Path to the saved JSON file.
    """
    html_file = str(html_file)
    if output_file is None:
        output_file = get_default_output_file(html_file)

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    html = Path(html_file).read_text(encoding='utf-8')
    script = await extract_context_script(html)
    context = await evaluate_context_via_playwright(script)

    output_file.write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding='utf-8')
    return str(output_file)


if __name__ == '__main__':

    html_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HTML_FILE
    out = asyncio.run(extract_context_json(html_file))
    print(f'Extracted context JSON: {out}')
