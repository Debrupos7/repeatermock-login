#!/usr/bin/env python3
"""
RepeaterMock Login + Test Page Scraper via NoCaptchaAI API.

Flow:
1. Solve Cloudflare Turnstile via NoCaptchaAI API (no browser needed)
2. Login to RepeaterMock with email + password + solved token
3. Use the session cookies to scrape the test page
4. Save everything (cookies, scraped questions, logs)
"""

import asyncio
import json
import os
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

NOCAPTCHA_API_KEY = os.environ.get("NOCAPTCHA_API_KEY", "")
NOCAPTCHA_BASE = "https://api.nocaptchaai.com"
LOGIN_URL = "https://repeatermock.com/login"
LOGIN_API = "https://api.repeatermock.com/auth/login"
ME_API = "https://api.repeatermock.com/auth/me"
EMAIL = os.environ.get("RM_EMAIL", "spellingbeeanswers@gmail.com")
PASSWORD = os.environ.get("RM_PASSWORD", "BloggingJi@7")
SITEKEY = "0x4AAAAAADixxaKQ-LspbGkf"
TEST_PAGE_URL = "https://repeatermock.com/tb/test-series/ssc-cgl/test/6a0f3ef35a73de9e21cdf098/instructions"
TEST_ID = "6a0f3ef35a73de9e21cdf098"
BROWSE_PAGES = [
    ("Dashboard", "https://repeatermock.com/dashboard"),
    ("Test Series", "https://repeatermock.com/test-series"),
    ("Test Instructions", TEST_PAGE_URL),
]
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "run_log.txt"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

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

async def solve_turnstile(cli):
    section("STEP 1: Solve Cloudflare Turnstile via NoCaptchaAI")
    log("Checking NoCaptchaAI balance…")
    r = await cli.post(f"{NOCAPTCHA_BASE}/getBalance", json={"clientKey": NOCAPTCHA_API_KEY})
    log(f"  Balance: {json.dumps(r.json(), ensure_ascii=False)[:200]}")

    log("Creating Turnstile task (AntiTurnstileTaskProxyLess)…")
    r = await cli.post(f"{NOCAPTCHA_BASE}/createTask", json={
        "clientKey": NOCAPTCHA_API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": LOGIN_URL,
            "websiteKey": SITEKEY,
        }
    })
    data = r.json()
    log(f"  Response: {json.dumps(data, ensure_ascii=False)[:300]}")

    if data.get("errorId", 0) != 0:
        error = data.get("error", str(data))
        log(f"  ❌ createTask failed: {error}", "ERROR")
        if "Invalid apikey" in str(error):
            log("", "ERROR")
            log("  ╔══════════════════════════════════════════════════════╗", "ERROR")
            log("  ║  API KEY INVALID — please check:                     ║", "ERROR")
            log("  ║  1. Log into https://nocaptchaai.com dashboard       ║", "ERROR")
            log("  ║  2. Verify your email address                        ║", "ERROR")
            log("  ║  3. Copy the EXACT API key from Settings             ║", "ERROR")
            log("  ║  4. Claim the free 6000 credits                      ║", "ERROR")
            log("  ╚══════════════════════════════════════════════════════╝", "ERROR")
        return None

    task_id = data.get("taskId")
    if not task_id:
        log(f"  ❌ No taskId: {data}", "ERROR")
        return None
    log(f"  ✅ Task created: {task_id}")

    log("Polling for token…")
    start = time.time()
    for attempt in range(60):
        await asyncio.sleep(2)
        r = await cli.post(f"{NOCAPTCHA_BASE}/getTaskResult", json={
            "clientKey": NOCAPTCHA_API_KEY, "taskId": task_id,
        })
        data = r.json()
        status = data.get("status", "?")
        elapsed = time.time() - start
        if status == "ready":
            token = data.get("solution", {}).get("token", "")
            log(f"  ✅ Token ready at {elapsed:.1f}s! Length: {len(token)}")
            log(f"  Token (first 50): {token[:50]}…")
            return token
        elif status == "failed" or data.get("errorId", 0) != 0:
            log(f"  ❌ Failed at {elapsed:.1f}s: {json.dumps(data)[:200]}", "ERROR")
            return None
        if attempt % 5 == 0:
            log(f"  [{elapsed:.0f}s] status={status}…")
    log("  ❌ Timed out (120s)", "ERROR")
    return None

async def login(cli, token):
    section("STEP 2: Login to RepeaterMock")
    log(f"POST {LOGIN_API}")
    r = await cli.post(LOGIN_API, json={
        "email": EMAIL, "password": PASSWORD, "turnstileToken": token,
    }, headers={
        "Content-Type": "application/json",
        "Origin": "https://repeatermock.com",
        "Referer": "https://repeatermock.com/login",
        "User-Agent": UA,
    })
    log(f"  Status: {r.status_code}")
    try: data = r.json()
    except: data = {"raw": r.text[:500]}
    log(f"  Response: {json.dumps(data, ensure_ascii=False)[:400]}")
    set_cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else []
    if r.status_code != 200 or not data.get("success"):
        log(f"  ❌ Login failed!", "ERROR")
        return None, None
    user = data.get("user", {})
    log(f"  ✅ LOGIN SUCCESSFUL!")
    log(f"  User: {user.get('name')}  Email: {user.get('email')}  Plan: {user.get('plan')}")
    return user, set_cookies

def save_cookies(set_cookies):
    section("STEP 3: Save cookies")
    cookie_list = []
    for sc in set_cookies:
        parts = sc.split(";")[0].split("=", 1)
        if len(parts) == 2:
            name, value = parts[0].strip(), parts[1].strip()
            attrs = sc.split(";")[1:]
            domain = ".repeatermock.com"
            for a in attrs:
                if a.strip().lower().startswith("domain="):
                    domain = a.split("=", 1)[1].strip()
            cookie_list.append({
                "name": name, "value": value, "domain": domain,
                "path": "/", "httpOnly": any("httponly" in a.lower() for a in attrs),
                "secure": any("secure" in a.lower() for a in attrs), "sameSite": "Lax",
            })
    with open(OUTPUT_DIR / "cookies.json", "w") as f:
        json.dump({"cookies": cookie_list, "timestamp": datetime.now(timezone.utc).isoformat(), "email": EMAIL}, f, indent=2)
    with open(OUTPUT_DIR / "cookies.txt", "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookie_list:
            d = c["domain"]
            f.write(f"{d}\t{'TRUE' if d.startswith('.') else 'FALSE'}\t/\t{'TRUE' if c['secure'] else 'FALSE'}\t0\t{c['name']}\t{c['value']}\n")
    access_token = next((c["value"] for c in cookie_list if c["name"] == "accessToken"), "")
    refresh_token = next((c["value"] for c in cookie_list if c["name"] == "refreshToken"), "")
    with open(OUTPUT_DIR / "auth_tokens.json", "w") as f:
        json.dump({"accessToken": access_token, "refreshToken": refresh_token,
                    "timestamp": datetime.now(timezone.utc).isoformat(), "email": EMAIL}, f, indent=2)
    log(f"  Saved {len(cookie_list)} cookies")
    for c in cookie_list:
        log(f"    - {c['name']}={c['value'][:50]}…")
    return "; ".join(f"{c['name']}={c['value']}" for c in cookie_list)

async def browse_and_scrape(cli, cookie_header):
    section("STEP 4: Browse pages + scrape test page")
    results = []
    for name, url in BROWSE_PAGES:
        log(f"\n--- {name}: {url} ---")
        try:
            r = await cli.get(url, headers={
                "User-Agent": UA, "Cookie": cookie_header,
                "Referer": "https://repeatermock.com/",
            }, follow_redirects=True)
            title = r.text.split("<title>")[1].split("</title>")[0].strip()[:80] if "<title>" in r.text else ""
            log(f"  Status: {r.status_code}  Body: {len(r.text):,} bytes  Title: {title}")
            me_r = await cli.get(ME_API, headers={"Cookie": cookie_header})
            try: me_ok = me_r.json().get("success", False)
            except: me_ok = False
            log(f"  /auth/me: {me_r.status_code} success={me_ok}")
            results.append({"name": name, "url": url, "status": r.status_code, "length": len(r.text), "title": title, "auth_verified": me_ok})

            if "instructions" in url:
                log(f"  ✅ This is the test page — saving full HTML!")
                with open(OUTPUT_DIR / "test_page.html", "w", encoding="utf-8") as f:
                    f.write(r.text)
                log(f"  Saved: test_page.html ({len(r.text):,} bytes)")

                # Extract __NEXT_DATA__
                next_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
                if next_match:
                    log(f"  Found __NEXT_DATA__ — parsing…")
                    try:
                        next_data = json.loads(next_match.group(1))
                        with open(OUTPUT_DIR / "next_data.json", "w") as f:
                            json.dump(next_data, f, indent=2, ensure_ascii=False)
                        log(f"  Saved: next_data.json")
                    except: log(f"  Could not parse __NEXT_DATA__")

                # Try the API endpoint for questions
                api_url = f"https://api.repeatermock.com/api/tests/{TEST_ID}"
                log(f"  Trying API: {api_url}")
                api_r = await cli.get(api_url, headers={"Cookie": cookie_header, "User-Agent": UA, "Referer": url})
                log(f"  API status: {api_r.status_code}")
                if api_r.status_code == 200:
                    try:
                        api_data = api_r.json()
                        with open(OUTPUT_DIR / "test_api_response.json", "w") as f:
                            json.dump(api_data, f, indent=2, ensure_ascii=False)
                        log(f"  Saved: test_api_response.json")
                        api_str = json.dumps(api_data)
                        if "question" in api_str.lower():
                            log(f"  ✅ API response contains questions!")
                    except: log(f"  API returned non-JSON")

                # Also try /api/v1/test-series/{TEST_ID}
                for path in [f"/api/v1/test-series/{TEST_ID}", f"/api/tests/{TEST_ID}/answers",
                             f"/api/v1/test-series/{TEST_ID}/sections", f"/api/v1/tests/{TEST_ID}"]:
                    api_url2 = f"https://api.repeatermock.com{path}"
                    log(f"  Trying: {api_url2}")
                    api_r2 = await cli.get(api_url2, headers={"Cookie": cookie_header, "User-Agent": UA})
                    if api_r2.status_code == 200:
                        try:
                            d = api_r2.json()
                            with open(OUTPUT_DIR / f"api_{path.replace('/','_')}.json", "w") as f:
                                json.dump(d, f, indent=2, ensure_ascii=False)
                            log(f"    ✅ 200 OK — saved! ({len(json.dumps(d)):,} bytes)")
                        except: pass
                    else:
                        log(f"    {api_r2.status_code}")

        except Exception as e:
            log(f"  ❌ Error: {e}", "ERROR")
            results.append({"name": name, "url": url, "error": str(e)})
    return results

async def main():
    section("RepeaterMock Login + Test Page Scraper (NoCaptchaAI)")
    log(f"Python: {sys.version.split()[0]}")
    log(f"Email: {EMAIL}")
    log(f"Key: {NOCAPTCHA_API_KEY[:15]}…" if NOCAPTCHA_API_KEY else "Key: NOT SET")
    log(f"Test page: {TEST_PAGE_URL}")
    if not NOCAPTCHA_API_KEY:
        log("❌ NOCAPTCHA_API_KEY not set!", "ERROR")
        return
    async with httpx.AsyncClient(timeout=60.0) as cli:
        token = await solve_turnstile(cli)
        if not token: return
        user, set_cookies = await login(cli, token)
        if not user: return
        cookie_header = save_cookies(set_cookies)
        browse_results = await browse_and_scrape(cli, cookie_header)
        section("FINAL SUMMARY")
        log(f"Login: ✅ SUCCESS")
        log(f"User:  {user.get('name')} ({user.get('email')})")
        log(f"Plan:  {user.get('plan')}")
        auth_ok = sum(1 for r in browse_results if r.get("auth_verified"))
        log(f"Pages browsed: {len(browse_results)}  Auth verified: {auth_ok}/{len(browse_results)}")
        for r in browse_results:
            icon = "✅" if r.get("status") == 200 else "❌"
            auth = "🔒" if r.get("auth_verified") else "🔓"
            log(f"  {icon} {auth} {r['name']:<20} status={r.get('status','ERR')} len={r.get('length',0):>7,}")
        log(f"\nFiles saved:")
        for f in sorted(OUTPUT_DIR.iterdir()):
            if f.is_file():
                log(f"  {f.name} ({f.stat().st_size:,} bytes)")
        log(f"\n🎉 ALL DONE!")

if __name__ == "__main__":
    asyncio.run(main())
