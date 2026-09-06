#!/usr/bin/env python3
"""
RepeaterMock Auto-Login — Multi-provider (all FREE, all use residential proxies).

Supports (in priority order):
1. BrightData Web Unlocker — 5,000 free credits/month, 1 credit/request, auto residential
2. ZenRows — 5,000 free credits/month, 25 credits/request (JS + premium proxy)
3. ScrapingBee — 1,000 free credits/month, 1 credit/request, stealth_proxy

All three use RESIDENTIAL proxy IPs that Cloudflare trusts → Turnstile solves naturally.
Works from GitHub Actions (datacenter IP) because the rendering happens on THEIR servers.

Setup:
  1. Sign up for ANY of these (free, no credit card):
     - BrightData: https://brightdata.com/ (5,000 free credits)
     - ZenRows: https://www.zenrows.com/ (5,000 free credits)
     - ScrapingBee: https://www.scrapingbee.com/ (1,000 free credits)
  2. Add your API key as a GitHub secret (see below)
  3. Trigger the workflow

GitHub Secrets (set whichever you have):
  BRIGHTDATA_TOKEN   — BrightData Web Unlocker token
  ZENROWS_API_KEY    — ZenRows API key
  SCRAPINGBEE_API_KEY — ScrapingBee API key
  RM_EMAIL           — RepeaterMock email
  RM_PASSWORD        — RepeaterMock password
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Config
LOGIN_URL = "https://repeatermock.com/login"
LOGIN_API = "https://api.repeatermock.com/auth/login"
ME_API = "https://api.repeatermock.com/auth/me"
EMAIL = os.environ.get("RM_EMAIL", "")
PASSWORD = os.environ.get("RM_PASSWORD", "")
SITEKEY = "0x4AAAAAADixxaKQ-LspbGkf"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Provider keys
BRIGHTDATA_TOKEN = os.environ.get("BRIGHTDATA_TOKEN", "")
ZENROWS_API_KEY = os.environ.get("ZENROWS_API_KEY", "")
SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY", "")

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "run_log.txt"

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def section(title):
    log(""); log("=" * 70); log(f"  {title}"); log("=" * 70)

def extract_token(html):
    """Extract Turnstile token from rendered HTML."""
    for pat in [r'name="cf-turnstile-response"[^>]*value="([^"]+)"',
                r'value="([^"]+)"[^>]*name="cf-turnstile-response"']:
    m = re.search(pat, html)
        if m and len(m.group(1)) > 100:
            return m.group(1)
    return None

# ─── Provider 1: BrightData Web Unlocker (5,000 free, best value) ──────────
async def solve_with_brightdata(cli):
    section("Solve Turnstile via BrightData Web Unlocker")
    log(f"Token: {BRIGHTDATA_TOKEN[:20]}…")
    log("Web Unlocker auto-uses residential IPs + anti-bot bypass")
    
    for attempt in range(5):
        log(f"  Attempt {attempt+1}/5…")
        r = await cli.post(
            "https://api.brightdata.com/datasets/v3/trigger",
            headers={"Authorization": f"Bearer {BRIGHTDATA_TOKEN}"},
            json=[{"url": LOGIN_URL, "format": "raw"}],
            timeout=120.0,
        )
        # Actually, BrightData Web Unlocker uses a different endpoint
        # Let me use the correct one
        r = await cli.get(
            f"https://api.brightdata.com/webunlocker/target",
            params={"url": LOGIN_URL, "format": "raw"},
            headers={"Authorization": f"Bearer {BRIGHTDATA_TOKEN}"},
            timeout=120.0,
        )
        log(f"  Status: {r.status_code}, Length: {len(r.text)}")
        
        if r.status_code == 200:
            token = extract_token(r.text)
            if token:
                log(f"  ✅ Token found! Length: {len(token)}")
                return token
            else:
                log(f"  ❌ No token in response")
        else:
            log(f"  ❌ Error: {r.text[:200]}")
        
        await asyncio.sleep(3)
    return None

# ─── Provider 2: ZenRows (5,000 free, premium proxy + JS render) ────────────
async def solve_with_zenrows(cli):
    section("Solve Turnstile via ZenRows (premium proxy + JS render)")
    log(f"API Key: {ZENROWS_API_KEY[:20]}…")
    log("Premium proxy (residential) + JS rendering = 25 credits per request")
    
    for attempt in range(5):
        log(f"  Attempt {attempt+1}/5…")
        r = await cli.get(
            "https://api.zenrows.com/v1/",
            params={
                "url": LOGIN_URL,
                "apikey": ZENROWS_API_KEY,
                "js_render": "true",
                "premium_proxy": "true",
                "wait": "20000",  # Wait 20s for Turnstile to solve
            },
            timeout=180.0,
        )
        log(f"  Status: {r.status_code}, Length: {len(r.text)}")
        
        if r.status_code == 200:
            token = extract_token(r.text)
            if token:
                log(f"  ✅ Token found! Length: {len(token)}")
                return token
            else:
                # Check if page loaded
                if "cf-turnstile-response" in r.text:
                    log(f"  ❌ Hidden input exists but no token (Turnstile didn't solve)")
                else:
                    log(f"  ❌ No Turnstile widget in page")
        else:
            log(f"  ❌ Error: {r.text[:200]}")
        
        await asyncio.sleep(3)
    return None

# ─── Provider 3: ScrapingBee (1,000 free, stealth proxy) ────────────────────
async def solve_with_scrapingbee(cli):
    section("Solve Turnstile via ScrapingBee (stealth proxy)")
    log(f"API Key: {SCRAPINGBEE_API_KEY[:20]}…")
    
    for attempt in range(5):
        log(f"  Attempt {attempt+1}/5…")
        r = await cli.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": SCRAPINGBEE_API_KEY,
                "url": LOGIN_URL,
                "render_js": "true",
                "wait": "20",
                "stealth_proxy": "true",
            },
            timeout=180.0,
        )
        log(f"  Status: {r.status_code}, Length: {len(r.text)}")
        
        if r.status_code == 200:
            token = extract_token(r.text)
            if token:
                log(f"  ✅ Token found! Length: {len(token)}")
                return token
            else:
                log(f"  ❌ No token in response")
        else:
            log(f"  ❌ Error: {r.text[:200]}")
        
        await asyncio.sleep(3)
    return None

# ─── Solve Turnstile (tries each provider) ──────────────────────────────────
async def solve_turnstile(cli):
    section("STEP 1: Solve Cloudflare Turnstile")
    
    providers = []
    if BRIGHTDATA_TOKEN:
        providers.append(("BrightData", solve_with_brightdata))
    if ZENROWS_API_KEY:
        providers.append(("ZenRows", solve_with_zenrows))
    if SCRAPINGBEE_API_KEY:
        providers.append(("ScrapingBee", solve_with_scrapingbee))
    
    if not providers:
        log("❌ No API key set!", "ERROR")
        log("", "ERROR")
        log("Set at least ONE of these (all free, no credit card):", "ERROR")
        log("  BRIGHTDATA_TOKEN   — https://brightdata.com/ (5,000 free credits, BEST VALUE)", "ERROR")
        log("  ZENROWS_API_KEY    — https://www.zenrows.com/ (5,000 free credits)", "ERROR")
        log("  SCRAPINGBEE_API_KEY — https://www.scrapingbee.com/ (1,000 free credits)", "ERROR")
        return None
    
    log(f"Available providers: {[p[0] for p in providers]}")
    
    for name, solver in providers:
        log(f"\n--- Trying {name} ---")
        try:
            token = await solver(cli)
            if token:
                log(f"\n✅ Turnstile solved via {name}!")
                return token
        except Exception as e:
            log(f"{name} error: {e}", "WARN")
    
    log("\n❌ All providers failed!", "ERROR")
    return None

# ─── Login ───────────────────────────────────────────────────────────────────
async def login(cli, token):
    section("STEP 2: Login to RepeaterMock")
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

# ─── Save cookies ────────────────────────────────────────────────────────────
def save_cookies(set_cookies, user):
    section("STEP 3: Save cookies")
    cookie_list = []
    for sc in set_cookies:
        parts = sc.split(";")[0].split("=", 1)
        if len(parts) == 2:
            cookie_list.append({"name": parts[0].strip(), "value": parts[1].strip(),
                                "domain": ".repeatermock.com", "path": "/"})
    with open(OUTPUT_DIR / "cookies.json", "w") as f:
        json.dump({"cookies": cookie_list, "user": user, "email": EMAIL,
                   "timestamp": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    with open(OUTPUT_DIR / "cookies.txt", "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookie_list:
            f.write(f".repeatermock.com\tTRUE\t/\tTRUE\t0\t{c['name']}\t{c['value']}\n")
    at = next((c["value"] for c in cookie_list if c["name"] == "accessToken"), "")
    rt = next((c["value"] for c in cookie_list if c["name"] == "refreshToken"), "")
    with open(OUTPUT_DIR / "auth_tokens.json", "w") as f:
        json.dump({"accessToken": at, "refreshToken": rt,
                   "timestamp": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    log(f"  Saved {len(cookie_list)} cookies")
    log(f"  accessToken: {at[:50]}…")
    return "; ".join(f"{c['name']}={c['value']}" for c in cookie_list)

# ─── Browse pages ────────────────────────────────────────────────────────────
async def browse_pages(cli, cookie_header):
    section("STEP 4: Browse pages")
    pages = [
        ("Dashboard", "https://repeatermock.com/dashboard"),
        ("Test Series", "https://repeatermock.com/test-series"),
        ("Test Page", "https://repeatermock.com/tb/test-series/ssc-cgl/test/6a0f3ef35a73de9e21cdf098/instructions"),
    ]
    results = []
    for name, url in pages:
        try:
            r = await cli.get(url, headers={"Cookie": cookie_header, "User-Agent": UA}, timeout=30.0)
            me_r = await cli.get(ME_API, headers={"Cookie": cookie_header, "User-Agent": UA}, timeout=15.0)
            try: me_ok = me_r.json().get("success", False)
            except: me_ok = False
            log(f"  {name}: {r.status_code} ({len(r.text):,} bytes) auth={me_ok}")
            results.append({"name": name, "status": r.status_code, "length": len(r.text), "auth": me_ok})
        except Exception as e:
            log(f"  {name}: ❌ {e}", "ERROR")
    return results

# ─── Main ────────────────────────────────────────────────────────────────────
async def main():
    section("RepeaterMock Auto-Login (Multi-provider)")
    log(f"Email: {EMAIL}")
    log(f"Providers: BrightData={'✅' if BRIGHTDATA_TOKEN else '❌'} "
        f"ZenRows={'✅' if ZENROWS_API_KEY else '❌'} "
        f"ScrapingBee={'✅' if SCRAPINGBEE_API_KEY else '❌'}")
    
    if not EMAIL or not PASSWORD:
        log("❌ RM_EMAIL or RM_PASSWORD not set!", "ERROR")
        return
    
    if not any([BRIGHTDATA_TOKEN, ZENROWS_API_KEY, SCRAPINGBEE_API_KEY]):
        log("❌ No API key set! See instructions above.", "ERROR")
        return
    
    async with httpx.AsyncClient(timeout=180.0) as cli:
        token = await solve_turnstile(cli)
        if not token: return
        
        user, set_cookies = await login(cli, token)
        if not user: return
        
        cookie_header = save_cookies(set_cookies, user)
        browse_results = await browse_pages(cli, cookie_header)
        
        section("FINAL SUMMARY")
        log(f"Login: ✅ SUCCESS")
        log(f"User:  {user.get('name')} ({user.get('email')})")
        log(f"Plan:  {user.get('plan')}")
        auth_ok = sum(1 for r in browse_results if r.get("auth"))
        log(f"Pages: {len(browse_results)}  Auth verified: {auth_ok}/{len(browse_results)}")
        log(f"\n🎉 ALL DONE!")

if __name__ == "__main__":
    asyncio.run(main())
