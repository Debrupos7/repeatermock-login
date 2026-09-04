#!/usr/bin/env python3
"""
RepeaterMock Login + Test Page Scraper via ScrapingBee API.

ScrapingBee renders the login page with stealth proxy → Turnstile solves
naturally → we extract the token → submit login → get cookies → scrape.

1000 free credits, no credit card, works from any IP (datacenter included).
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

SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY", "")
LOGIN_URL = "https://repeatermock.com/login"
LOGIN_API = "https://api.repeatermock.com/auth/login"
ME_API = "https://api.repeatermock.com/auth/me"
EMAIL = os.environ.get("RM_EMAIL", "spellingbeeanswers@gmail.com")
PASSWORD = os.environ.get("RM_PASSWORD", "BloggingJi@7")
TEST_PAGE_URL = "https://repeatermock.com/tb/test-series/ssc-cgl/test/6a0f3ef35a73de9e21cdf098/instructions"
TEST_ID = "6a0f3ef35a73de9e21cdf098"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "run_log.txt"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f: f.write(line + "\n")

def section(t):
    log(""); log("="*70); log(f"  {t}"); log("="*70)

async def solve_turnstile(cli):
    section("STEP 1: Solve Turnstile via ScrapingBee (stealth proxy)")
    log(f"API Key: {SCRAPINGBEE_API_KEY[:15]}…")
    
    for attempt in range(5):
        log(f"\n--- Attempt {attempt+1}/5 ---")
        params = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": LOGIN_URL,
            "render_js": "true",
            "wait": "20",
            "stealth_proxy": "true",
        }
        r = await cli.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=180.0)
        content = r.text
        log(f"  Page rendered: {len(content):,} bytes")
        
        for pattern in [r'name="cf-turnstile-response"[^>]*value="([^"]+)"',
                        r'value="([^"]+)"[^>]*name="cf-turnstile-response"']:
            m = re.search(pattern, content)
            if m and len(m.group(1)) > 20:
                token = m.group(1)
                log(f"  ✅ Token found! Length: {len(token)}")
                return token
        
        log(f"  ❌ No token (iframe loaded but didn't solve)")
        if attempt < 4:
            log(f"  Retrying in 3s…")
            await asyncio.sleep(3)
    
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
    }, timeout=30.0)
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

def save_cookies(set_cookies, user):
    section("STEP 3: Save cookies")
    cookie_list = []
    for sc in set_cookies:
        parts = sc.split(";")[0].split("=", 1)
        if len(parts) == 2:
            cookie_list.append({"name": parts[0].strip(), "value": parts[1].strip(),
                                "domain": ".repeatermock.com", "path": "/"})
    with open(OUTPUT_DIR / "cookies.json", "w") as f:
        json.dump({"cookies": cookie_list, "timestamp": datetime.now(timezone.utc).isoformat(),
                    "email": EMAIL, "user": user}, f, indent=2)
    with open(OUTPUT_DIR / "cookies.txt", "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookie_list:
            f.write(f".repeatermock.com\tTRUE\t/\tTRUE\t0\t{c['name']}\t{c['value']}\n")
    access_token = next((c["value"] for c in cookie_list if c["name"] == "accessToken"), "")
    with open(OUTPUT_DIR / "auth_tokens.json", "w") as f:
        json.dump({"accessToken": access_token, "timestamp": datetime.now(timezone.utc).isoformat(),
                    "email": EMAIL}, f, indent=2)
    log(f"  Saved {len(cookie_list)} cookies")
    for c in cookie_list: log(f"    - {c['name']}={c['value'][:50]}…")
    return "; ".join(f"{c['name']}={c['value']}" for c in cookie_list)

async def scrape_test_page(cli, cookie_header):
    section("STEP 4: Scrape test page")
    log(f"URL: {TEST_PAGE_URL}")
    r = await cli.get(TEST_PAGE_URL, headers={
        "Cookie": cookie_header, "User-Agent": UA, "Referer": "https://repeatermock.com/",
    }, timeout=30.0, follow_redirects=True)
    html = r.text
    log(f"  Status: {r.status_code}  Size: {len(html):,} bytes")
    log(f"  Has 'Log in' button: {'Log in' in html}")
    log(f"  Has 'question': {'question' in html.lower()}")
    
    with open(OUTPUT_DIR / "test_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  Saved: test_page.html")
    
    # Extract __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            with open(OUTPUT_DIR / "next_data.json", "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log(f"  Saved: next_data.json")
            props = data.get("props", {}).get("pageProps", {})
            log(f"  Page props: {list(props.keys())}")
        except: pass
    
    # Try API endpoints
    log(f"\n  Trying API endpoints…")
    for path in [f"/api/tests/{TEST_ID}", f"/api/tests/{TEST_ID}/answers",
                 f"/api/v1/test-series/{TEST_ID}", f"/api/v1/tests/{TEST_ID}"]:
        url = f"https://api.repeatermock.com{path}"
        try:
            r = await cli.get(url, headers={"Cookie": cookie_header, "User-Agent": UA}, timeout=15.0)
            if r.status_code == 200:
                body = r.text
                log(f"    ✅ {path}: {r.status_code} ({len(body)} bytes)")
                with open(OUTPUT_DIR / f"api_{path.replace('/','_')}.json", "w") as f:
                    f.write(body)
                if "question" in body.lower():
                    log(f"    🔥 Contains questions!")
            else:
                log(f"    {path}: {r.status_code}")
        except Exception as e:
            log(f"    {path}: {e}")
    
    # Also browse other pages
    log(f"\n  Browsing other pages…")
    for name, url in [("Dashboard", "https://repeatermock.com/dashboard"),
                       ("Test Series", "https://repeatermock.com/test-series")]:
        try:
            r = await cli.get(url, headers={"Cookie": cookie_header, "User-Agent": UA}, timeout=15.0)
            log(f"    {name}: {r.status_code} ({len(r.text):,} bytes)")
        except: pass

async def main():
    section("RepeaterMock Login + Scrape (ScrapingBee)")
    log(f"Python: {sys.version.split()[0]}")
    log(f"Email: {EMAIL}")
    log(f"Key: {SCRAPINGBEE_API_KEY[:15]}…" if SCRAPINGBEE_API_KEY else "Key: NOT SET")
    if not SCRAPINGBEE_API_KEY:
        log("❌ SCRAPINGBEE_API_KEY not set!", "ERROR")
        return
    
    async with httpx.AsyncClient(timeout=180.0) as cli:
        token = await solve_turnstile(cli)
        if not token:
            log("❌ Failed to solve Turnstile after 5 attempts", "ERROR")
            return
        
        user, set_cookies = await login(cli, token)
        if not user: return
        
        cookie_header = save_cookies(set_cookies, user)
        
        # Verify auth
        log(f"\nVerifying auth…")
        me_r = await cli.get(ME_API, headers={"Cookie": cookie_header, "User-Agent": UA}, timeout=15.0)
        me_ok = me_r.json().get("success", False)
        log(f"  Auth verified: {me_ok}")
        
        await scrape_test_page(cli, cookie_header)
        
        section("FINAL SUMMARY")
        log(f"Login: ✅ SUCCESS")
        log(f"User:  {user.get('name')} ({user.get('email')})")
        log(f"Plan:  {user.get('plan')}")
        log(f"Auth:  {'✅' if me_ok else '❌'}")
        log(f"\nFiles saved:")
        for f in sorted(OUTPUT_DIR.iterdir()):
            if f.is_file(): log(f"  {f.name} ({f.stat().st_size:,} bytes)")
        log(f"\n🎉 ALL DONE!")

if __name__ == "__main__":
    asyncio.run(main())
