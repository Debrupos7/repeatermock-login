"""Minimal Chrome + nodriver test."""
import asyncio
import nodriver as uc

async def test():
    print("Launching Chrome via nodriver…")
    browser = await uc.start(
        browser_executable_path="/usr/bin/google-chrome-stable",
        headless=False,
        sandbox=False,
        browser_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    print("Browser launched, getting about:blank…")
    page = await browser.get("about:blank")
    await asyncio.sleep(2)
    title = await page.evaluate("document.title")
    print(f"Page title: '{title}'")
    ua = await page.evaluate("navigator.userAgent")
    print(f"User-Agent: {ua}")
    browser.stop()
    print("Test passed!")

asyncio.run(test())
