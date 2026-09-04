#!/usr/bin/env python3
"""
RepeaterMock Login via Playwright + EzSolver-style Turnstile injection.

Uses vanilla Playwright (not nodriver) because nodriver can't connect to
Chrome on GitHub Actions. To bypass DisableDevtool (swiper.js), we block
the swiper.js request entirely.

The Turnstile widget is injected into the real page DOM and solved by
clicking, just like EzSolver does with nodriver.
"""

import asyncio
import json
import os
import sys
import time
import random
import warnings
from pathlib import Path
from datetime import datetime, timezone

import httpx
from playwright.async_api import async_playwright

URL = "https://repeatermock.com/login"
EMAIL = os.environ.get("RM_EMAIL", "spellingbeeanswers@gmail.com")
PASSWORD = os.environ.get("RM_PASSWORD", "BloggingJi@7")
SITEKEY = "0x4AAAAAADixxaKQ-LspbGkf"
OUT = Path(os.environ.get("OUTPUT_DIR", "./output"))
OUT.mkdir(parents=True, exist_ok=True)

BROWSE_PAGES = [
    ("Dashboard", "https://repeatermock.com/dashboard"),
    ("Test Series", "https://repeatermock.com/test-series"),
    ("Pricing", "https://repeatermock.com/pricing"),
    ("About", "https://repeatermock.com/about"),
    ("Blog", "https://repeatermock.com/blog"),
]

LOG_FILE = OUT / "run_log.txt"

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def section(title):
    log("")
    log("=" * 70)
    log(f"  {title}")
    log("=" * 70)


async def main():
    section("RepeaterMock Login via Playwright + EzSolver injection")
    log(f"Email: {EMAIL}")
    log(f"Output: {OUT}")

    async with async_playwright() as p:
        section("STEP 1: Launch Chromium (headless, block swiper.js)")
        browser = await p.chromium.launch(
            channel="chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        # Block swiper.js (contains DisableDevtool which hides the form)
        await ctx.route("**/swiper.js", lambda route: route.abort())
        log("✅ Browser launched, swiper.js blocked")

        page = await ctx.new_page()

        section("STEP 2: Navigate to login page")
        log(f"URL: {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        try:
            await page.wait_for_selector("input[type=email]", timeout=15000)
            log("✅ Login form is visible!")
        except:
            log("❌ Login form not visible", "ERROR")
            html = await page.content()
            log(f"Page HTML length: {len(html)}")
            log(f"First 300 chars: {html[:300]}")
            await browser.close()
            return

        await page.wait_for_timeout(3000)
        ts_type = await page.evaluate("() => typeof window.turnstile")
        log(f"window.turnstile type: {ts_type}")

        section("STEP 3: Inject Turnstile widget (EzSolver style)")
        await page.evaluate(f"""
            (() => {{
                if (document.getElementById('_ts_box')) return;
                window._tsToken = null;
                const wrap = document.createElement('div');
                wrap.id = '_ts_box';
                wrap.style = 'position:fixed;top:20px;left:20px;z-index:2147483647;background:white;';
                document.body.appendChild(wrap);
                window._tsLoad = function () {{
                    turnstile.render('#_ts_box', {{
                        sitekey: '{SITEKEY}',
                        callback: function(token) {{ window._tsToken = token; }}
                    }});
                }};
                const s = document.createElement('script');
                s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=_tsLoad&render=explicit';
                s.async = true;
                document.head.appendChild(s);
            }})();
        """)
        log("Widget injected, waiting 5s for initialization…")
        await page.wait_for_timeout(5000)

        section("STEP 4: Wait for Turnstile token")
        token = await page.evaluate("""
            (() => {
                if (window._tsToken) return window._tsToken;
                const inp = document.querySelector('#_ts_box [name="cf-turnstile-response"]');
                return (inp && inp.value) ? inp.value : null;
            })()
        """)

        if token:
            log(f"✅ Auto-solved! Token (first 20): {token[:20]}…")
        else:
            log("Not auto-solved. Waiting + clicking (up to 10 attempts)…")
            for attempt in range(10):
                # Check for token first (maybe it auto-solved)
                token = await page.evaluate("""
                    (() => {
                        if (window._tsToken) return window._tsToken;
                        const inp = document.querySelector('#_ts_box [name="cf-turnstile-response"]');
                        return (inp && inp.value) ? inp.value : null;
                    })()
                """)
                if token:
                    log(f"✅ Solved at attempt {attempt+1}! Token (first 20): {token[:20]}…")
                    break

                log(f"  Attempt {attempt+1}/10: clicking widget…")
                rect = await page.evaluate("""
                    (() => {
                        for (const f of document.querySelectorAll('iframe')) {
                            const src = f.src || '';
                            if (!src.includes('challenges.cloudflare.com')) continue;
                            const r = f.getBoundingClientRect();
                            if (r.width > 50 && r.height > 20)
                                return {x: r.x, y: r.y, w: r.width, h: r.height};
                        }
                        return null;
                    })()
                """)
                if rect:
                    cx = rect["x"] + 28 + random.uniform(-3, 3)
                    cy = rect["y"] + rect["h"] / 2 + random.uniform(-3, 3)
                    log(f"    iframe at ({cx:.0f}, {cy:.0f}) size={rect['w']:.0f}x{rect['h']:.0f}")
                else:
                    cx = 48 + random.uniform(-3, 3)
                    cy = 52 + random.uniform(-3, 3)
                    log(f"    no iframe, fixed pos ({cx:.0f}, {cy:.0f})")

                await page.mouse.move(cx - 80, cy - 20)
                await page.wait_for_timeout(200)
                await page.mouse.move(cx, cy)
                await page.wait_for_timeout(100)
                await page.mouse.click(cx, cy)
                await page.wait_for_timeout(5000)  # wait 5s between attempts

                # Check for errors in the widget
                widget_state = await page.evaluate("""
                    (() => {
                        const box = document.getElementById('_ts_box');
                        if (!box) return 'no box';
                        const iframe = box.querySelector('iframe');
                        const inp = box.querySelector('[name="cf-turnstile-response"]');
                        return {
                            hasIframe: !!iframe,
                            iframeSrc: iframe ? iframe.src.slice(0, 80) : null,
                            tokenValue: inp ? inp.value.slice(0, 20) : null,
                            boxHTML: box.innerHTML.slice(0, 200),
                        };
                    })()
                """)
                log(f"    widget state: {widget_state}")

        if not token:
            log("❌ Failed to solve Turnstile after 5 attempts", "ERROR")
            await browser.close()
            return

        log(f"Token length: {len(token)}")

        section("STEP 5: Get cookies + submit login")
        cookies = await ctx.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        log(f"Got {len(cookies)} cookies from browser")

        log("Calling POST /auth/login…")
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                "https://api.repeatermock.com/auth/login",
                json={"email": EMAIL, "password": PASSWORD, "turnstileToken": token},
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://repeatermock.com",
                    "Referer": "https://repeatermock.com/login",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Cookie": cookie_str,
                },
            )
            api_status = r.status_code
            try:
                api_json = r.json()
            except:
                api_json = {"raw": r.text[:500]}
            set_cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else []

        log(f"API status: {api_status}")
        log(f"API response: {json.dumps(api_json, ensure_ascii=False)[:400]}")
        log(f"Set-Cookie headers: {len(set_cookies)}")

        if api_status != 200 or not api_json.get("success"):
            log(f"❌ Login failed", "ERROR")
            await browser.close()
            return

        user = api_json.get("user", {})
        section("STEP 6: Login successful!")
        log(f"✅ User: {user.get('name')}")
        log(f"✅ Email: {user.get('email')}")
        log(f"✅ ID: {user.get('id')}")
        log(f"✅ Plan: {user.get('plan')}")

        # Build cookie list
        cookie_list = []
        for c in cookies:
            cookie_list.append({
                "name": c["name"], "value": c["value"],
                "domain": c["domain"], "path": c.get("path", "/"),
                "expires": c.get("expires", -1),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": c.get("sameSite", "Lax"),
            })
        for sc in set_cookies:
            parts = sc.split(";")[0].split("=", 1)
            if len(parts) == 2 and not any(c["name"] == parts[0].strip() for c in cookie_list):
                cookie_list.append({
                    "name": parts[0].strip(), "value": parts[1].strip(),
                    "domain": ".repeatermock.com", "path": "/",
                    "expires": -1, "httpOnly": True, "secure": True, "sameSite": "Lax",
                })

        auth_cookies = {c["name"]: c["value"] for c in cookie_list}
        cookie_header = "; ".join(f"{k}={v}" for k, v in auth_cookies.items())

        section("STEP 7: Save cookies")
        with open(OUT / "cookies.json", "w") as f:
            json.dump({"cookies": cookie_list, "timestamp": datetime.now(timezone.utc).isoformat(),
                        "email": EMAIL, "user": user}, f, indent=2)
        with open(OUT / "cookies.txt", "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookie_list:
                d = c["domain"]
                f.write(f"{d}\t{'TRUE' if d.startswith('.') else 'FALSE'}\t{c.get('path','/')}\t"
                        f"{'TRUE' if c.get('secure') else 'FALSE'}\t{int(c.get('expires',0) or 0)}\t{c['name']}\t{c['value']}\n")
        access_token = auth_cookies.get("accessToken", "")
        refresh_token = auth_cookies.get("refreshToken", "")
        with open(OUT / "auth_tokens.json", "w") as f:
            json.dump({"accessToken": access_token, "refreshToken": refresh_token,
                        "timestamp": datetime.now(timezone.utc).isoformat(), "email": EMAIL}, f, indent=2)
        log(f"Saved cookies.json, cookies.txt, auth_tokens.json")
        log(f"accessToken (first 50): {access_token[:50]}…")

        section("STEP 8: Browse 5-6 pages with session cookies")
        browse_results = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cli:
            for i, (name, page_url) in enumerate(BROWSE_PAGES, 1):
                log("")
                log(f"--- Page {i}/{len(BROWSE_PAGES)}: {name} ---")
                log(f"  GET {page_url}")
                try:
                    r = await cli.get(page_url, headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Cookie": cookie_header,
                        "Referer": "https://repeatermock.com/",
                    })
                    status = r.status_code
                    body = r.text
                    title = ""
                    if "<title>" in body:
                        title = body.split("<title>")[1].split("</title>")[0].strip()[:80]
                    has_login = "Log in" in body
                    has_email = EMAIL in body
                    log(f"  Status: {status}")
                    log(f"  Body: {len(body):,} bytes")
                    log(f"  Title: {title}")
                    log(f"  Has 'Log in' button: {has_login}")
                    log(f"  Has user email: {has_email}")

                    me_r = await cli.get("https://api.repeatermock.com/auth/me", headers={"Cookie": cookie_header})
                    try:
                        me_j = me_r.json()
                        me_ok = me_j.get("success", False)
                    except:
                        me_ok = False
                    log(f"  /auth/me: {me_r.status_code} success={me_ok}")

                    browse_results.append({"name": name, "url": page_url, "status": status,
                                           "body_length": len(body), "title": title,
                                           "auth_me_success": me_ok})
                except Exception as e:
                    log(f"  ❌ Error: {e}", "ERROR")
                    browse_results.append({"name": name, "url": page_url, "error": str(e)})

        section("STEP 9: Summary")
        log(f"Login: ✅ SUCCESS")
        log(f"User:  {user.get('name')} ({user.get('email')})")
        log(f"Plan:  {user.get('plan')}")
        log(f"Pages browsed: {len(browse_results)}/{len(BROWSE_PAGES)}")
        auth_ok = sum(1 for r in browse_results if r.get("auth_me_success"))
        log(f"/auth/me verified: {auth_ok}/{len(browse_results)}")
        for r in browse_results:
            icon = "✅" if r.get("status") == 200 else "❌"
            auth = "🔒" if r.get("auth_me_success") else "🔓"
            log(f"  {icon} {auth} {r['name']:<15} status={r.get('status','ERR')} len={r.get('body_length',0):>7,}")

        log(f"\n🎉 ALL DONE!")
        await browser.close()


if __name__ == "__main__":
    section("RepeaterMock Login + Browse — GitHub Actions")
    log(f"Python: {sys.version.split()[0]}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        asyncio.run(main())
