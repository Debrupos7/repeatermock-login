"""Minimal Chrome + nodriver test."""
import asyncio
import os
import nodriver as uc

CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome-stable")

async def test():
    print(f"Chrome path: {CHROME}")
    print("Launching Chrome via nodriver…")
    browser = await uc.start(
        browser_executable_path=CHROME,
        headless=False,
        sandbox=False,
        browser_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    print("Browser launched!")
    page = await browser.get("about:blank")
    await asyncio.sleep(2)
    title = await page.evaluate("document.title")
    print(f"Page title: '{title}'")
    browser.stop()
    print("Test PASSED!")

asyncio.run(test())
