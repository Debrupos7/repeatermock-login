#!/usr/bin/env python3
"""
RepeaterMock Login via nodriver (EzSolver approach) — GitHub Actions ready.

Key fix: all page.evaluate() calls use IIFE syntax (() => { ... })() because
nodriver evaluates the expression but does NOT auto-call arrow functions
(unlike Playwright which does).
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

import nodriver as uc
import httpx

URL = "https://repeatermock.com/login"
EMAIL = os.environ.get("RM_EMAIL", "spellingbeeanswers@gmail.com")
PASSWORD = os.environ.get("RM_PASSWORD", "BloggingJi@7")
SITEKEY = "0x4AAAAAADixxaKQ-LspbGkf"
CHROME_PATH = os.environ.get("CHROME_PATH", "")
PROFILE_DIR = os.environ.get("TS_PROFILE_DIR", "/tmp/ts_profile")
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


def parse_eval(result):
    """Parse nodriver's CDP evaluate return format.
    Returns can be:
    - Primitive: returned as-is
    - Object: list of [key, {type, value}] pairs → convert to dict
    - None: returned as-is
    """
    if result is None:
        return None
    if isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, list):
        # Could be a list of [key, RemoteObject] pairs (object)
        # or a list of values (array)
        if len(result) > 0 and isinstance(result[0], list) and len(result[0]) == 2:
            # Object: [[key, {type, value}], ...]
            d = {}
            for item in result:
                if isinstance(item, list) and len(item) == 2:
                    key, val = item
                    if isinstance(val, dict) and 'value' in val:
                        d[key] = val['value']
                    else:
                        d[key] = parse_eval(val)
            return d
        # Array: [RemoteObject, ...]
        return [parse_eval(item) if isinstance(item, dict) and 'value' in item else parse_eval(item) for item in result]
    if isinstance(result, dict):
        if 'value' in result and 'type' in result:
            return result['value']
        return {k: parse_eval(v) for k, v in result.items()}
    return result


async def main():
    section("RepeaterMock Login via nodriver (EzSolver)")
    log(f"Email: {EMAIL}")
    log(f"Chrome: {CHROME_PATH}")

    # Find Chrome
    chrome = CHROME_PATH
    if not chrome or not os.path.isfile(chrome):
        for c in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome",
                  "/usr/bin/chromium-browser", "/usr/bin/chromium"]:
            if os.path.isfile(c):
                chrome = c
                break
    log(f"Using Chrome: {chrome}")

    section("STEP 1: Launch nodriver browser")
    browser = await uc.start(
        browser_executable_path=chrome,
        headless=False,
        user_data_dir=PROFILE_DIR,
        sandbox=False,
        browser_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--no-first-run",
            "--no-default-browser-check",
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Googlebot/2.1",
        ],
    )
    log("✅ Browser launched")

    try:
        section("STEP 2: Navigate to login page")
        page = await browser.get(URL)
        log("Page requested, waiting 8s…")
        await asyncio.sleep(8)

        # Use IIFE syntax: (() => { ... })()
        raw_result = await page.evaluate("""
            (() => ({
                url: window.location.href,
                title: document.title,
                bodyLen: document.body ? document.body.innerHTML.length : 0,
                hasEmailInput: !!document.querySelector('input[type=email]'),
                hasForm: !!document.querySelector('form'),
            }))()
        """)
        page_info = parse_eval(raw_result)
        log(f"Page info: {page_info}")

        if not page_info:
            log("❌ evaluate returned None", "ERROR")
            return

        log(f"  URL: {page_info.get('url')}")
        log(f"  Title: {page_info.get('title')}")
        log(f"  Body length: {page_info.get('bodyLen')}")
        log(f"  Has email input: {page_info.get('hasEmailInput')}")

        if not page_info.get("hasEmailInput"):
            log("❌ Login form not visible", "ERROR")
            return

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
            }})()
        """)
        log("Widget injected, waiting 5s…")
        await asyncio.sleep(5)

        section("STEP 4: Wait for Turnstile token")
        token = parse_eval(await page.evaluate("""
            (() => {
                if (window._tsToken) return window._tsToken;
                const inp = document.querySelector('#_ts_box [name="cf-turnstile-response"]');
                return (inp && inp.value) ? inp.value : null;
            })()
        """))

        if token:
            log(f"✅ Auto-solved! Token (first 20): {token[:20]}…")
        else:
            log("Not auto-solved, clicking widget (up to 8 attempts)…")
            for attempt in range(8):
                token = parse_eval(await page.evaluate("""
                    (() => {
                        if (window._tsToken) return window._tsToken;
                        const inp = document.querySelector('#_ts_box [name="cf-turnstile-response"]');
                        return (inp && inp.value) ? inp.value : null;
                    })()
                """))
                if token:
                    log(f"✅ Solved at attempt {attempt+1}!")
                    break

                rect = parse_eval(await page.evaluate("""
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
                """))
                if rect:
                    cx = rect["x"] + 28 + random.uniform(-3, 3)
                    cy = rect["y"] + rect["h"] / 2 + random.uniform(-3, 3)
                    log(f"  Attempt {attempt+1}: clicking iframe at ({cx:.0f}, {cy:.0f})")
                else:
                    cx = 48 + random.uniform(-3, 3)
                    cy = 52 + random.uniform(-3, 3)
                    log(f"  Attempt {attempt+1}: clicking fixed pos ({cx:.0f}, {cy:.0f})")

                await page.mouse_move(cx - 80, cy - 20)
                await asyncio.sleep(0.2)
                await page.mouse_move(cx, cy)
                await asyncio.sleep(0.1)
                await page.mouse_click(cx, cy)
                await asyncio.sleep(4)

        if not token:
            log("❌ Failed to solve Turnstile", "ERROR")
            return

        log(f"Token length: {len(token)}")

        section("STEP 5: Get cookies + submit login")
        browser_cookies = await browser.cookies.get_all()
        cookie_str = "; ".join(f"{c.name}={c.value}" for c in browser_cookies)
        log(f"Got {len(browser_cookies)} cookies")

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
            api_json = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]}
            set_cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else []

        log(f"API status: {api_status}")
        log(f"API response: {json.dumps(api_json, ensure_ascii=False)[:400]}")

        if api_status != 200 or not api_json.get("success"):
            log("❌ Login failed", "ERROR")
            return

        user = api_json.get("user", {})
        section("STEP 6: Login successful!")
        log(f"✅ User: {user.get('name')}")
        log(f"✅ Email: {user.get('email')}")
        log(f"✅ ID: {user.get('id')}")
        log(f"✅ Plan: {user.get('plan')}")

        # Build cookie list
        cookie_list = []
        for c in browser_cookies:
            ss = c.same_site if hasattr(c, "same_site") else "Lax"
            if hasattr(ss, "value"): ss = ss.value
            elif not isinstance(ss, str): ss = str(ss)
            cookie_list.append({
                "name": c.name, "value": c.value, "domain": c.domain,
                "path": c.path, "expires": c.expires if hasattr(c, "expires") else -1,
                "httpOnly": c.http_only if hasattr(c, "http_only") else False,
                "secure": c.secure if hasattr(c, "secure") else False,
                "sameSite": ss,
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
        with open(OUT / "auth_tokens.json", "w") as f:
            json.dump({"accessToken": access_token, "refreshToken": auth_cookies.get("refreshToken", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat(), "email": EMAIL}, f, indent=2)
        log(f"accessToken (first 50): {access_token[:50]}…")

        section("STEP 8: Browse 5 pages with session cookies")
        browse_results = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cli:
            for i, (name, page_url) in enumerate(BROWSE_PAGES, 1):
                log(f"--- Page {i}/{len(BROWSE_PAGES)}: {name} ---")
                try:
                    r = await cli.get(page_url, headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Cookie": cookie_header, "Referer": "https://repeatermock.com/",
                    })
                    body = r.text
                    title = body.split("<title>")[1].split("</title>")[0].strip()[:60] if "<title>" in body else ""
                    me_r = await cli.get("https://api.repeatermock.com/auth/me", headers={"Cookie": cookie_header})
                    me_ok = me_r.json().get("success", False) if me_r.headers.get("content-type","").startswith("application/json") else False
                    log(f"  {name}: status={r.status_code} len={len(body):,} title='{title}' auth={me_ok}")
                    browse_results.append({"name": name, "status": r.status_code, "len": len(body), "auth": me_ok})
                except Exception as e:
                    log(f"  ❌ {name}: {e}", "ERROR")

        section("STEP 9: Summary")
        log(f"Login: ✅ SUCCESS")
        log(f"User:  {user.get('name')} ({user.get('email')})")
        log(f"Plan:  {user.get('plan')}")
        auth_ok = sum(1 for r in browse_results if r.get("auth"))
        log(f"Pages: {len(browse_results)}/{len(BROWSE_PAGES)}  /auth/me verified: {auth_ok}")
        for r in browse_results:
            icon = "✅" if r.get("status") == 200 else "❌"
            auth = "🔒" if r.get("auth") else "🔓"
            log(f"  {icon} {auth} {r['name']:<15} status={r.get('status','ERR')} len={r.get('len',0):>7,}")
        log(f"\n🎉 ALL DONE!")

    finally:
        browser.stop()


def start_xvfb():
    import platform, subprocess
    if platform.system() != "Linux": return None
    if os.environ.get("DISPLAY"): return None
    log("Starting Xvfb…")
    proc = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x900x24"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ["DISPLAY"] = ":99"
    time.sleep(2)
    return proc


if __name__ == "__main__":
    section("RepeaterMock Login + Browse — GitHub Actions")
    log(f"Python: {sys.version.split()[0]}")
    xvfb = start_xvfb()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            asyncio.run(main())
    finally:
        if xvfb: xvfb.terminate()
