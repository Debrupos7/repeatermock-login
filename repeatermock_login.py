#!/usr/bin/env python3
"""
RepeaterMock Login + Test Page Scraper — Multi-provider Turnstile solver.

Supports multiple CAPTCHA solving APIs (try whichever has a key set):
1. NSLSolver  — 100 free, no card, simplest API (POST /solve, synchronous)
2. NoCaptchaAI — 6000 free (if credits activated)
3. CapSolver   — paid but reliable

Flow:
1. Solve Cloudflare Turnstile via whichever API key is available
2. Login to RepeaterMock with email + password + solved token
3. Use session cookies to scrape the test page
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

# ─── Config ──────────────────────────────────────────────────────────────────
LOGIN_URL = "https://repeatermock.com/login"
LOGIN_API = "https://api.repeatermock.com/auth/login"
ME_API = "https://api.repeatermock.com/auth/me"
EMAIL = os.environ.get("RM_EMAIL", "spellingbeeanswers@gmail.com")
PASSWORD = os.environ.get("RM_PASSWORD", "BloggingJi@7")
SITEKEY = "0x4AAAAAADixxaKQ-LspbGkf"
TEST_PAGE_URL = "https://repeatermock.com/tb/test-series/ssc-cgl/test/6a0f3ef35a73de9e21cdf098/instructions"
TEST_ID = "6a0f3ef35a73de9e21cdf098"

# CAPTCHA solver keys (set whichever you have)
NSL_API_KEY = os.environ.get("NSL_API_KEY", "")
NOCAPTCHA_API_KEY = os.environ.get("NOCAPTCHA_API_KEY", "")
CAPSOLVER_API_KEY = os.environ.get("CAPSOLVER_API_KEY", "")

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

# ─── Provider 1: NSLSolver (100 free, synchronous, simplest) ────────────────
async def solve_with_nslsolver(cli):
    log("Using NSLSolver (100 free requests, no card needed)")
    log(f"  API Key: {NSL_API_KEY[:15]}…")
    log(f"  POST https://api.nslsolver.com/solve")
    log(f"  type=turnstile, site_key={SITEKEY}, url={LOGIN_URL}")

    r = await cli.post("https://api.nslsolver.com/solve", json={
        "type": "turnstile",
        "site_key": SITEKEY,
        "url": LOGIN_URL,
    }, headers={
        "Content-Type": "application/json",
        "X-API-Key": NSL_API_KEY,
    }, timeout=120.0)

    data = r.json()
    log(f"  Response: {json.dumps(data, ensure_ascii=False)[:300]}")

    if data.get("token"):
        token = data["token"]
        log(f"  ✅ Token solved! Length: {len(token)}")
        log(f"  Token (first 50): {token[:50]}…")
        return token
    elif data.get("error"):
        log(f"  ❌ NSLSolver error: {data['error']}", "ERROR")
        return None
    else:
        log(f"  ❌ Unexpected response: {data}", "ERROR")
        return None

# ─── Provider 2: NoCaptchaAI (6000 free if activated) ───────────────────────
async def solve_with_nocaptcha(cli):
    log("Using NoCaptchaAI")
    log(f"  API Key: {NOCAPTCHA_API_KEY[:15]}…")

    # Check balance
    r = await cli.post("https://api.nocaptchaai.com/getBalance",
                       json={"clientKey": NOCAPTCHA_API_KEY})
    log(f"  Balance: {json.dumps(r.json(), ensure_ascii=False)[:200]}")

    # Create task
    r = await cli.post("https://api.nocaptchaai.com/createTask", json={
        "clientKey": NOCAPTCHA_API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": LOGIN_URL,
            "websiteKey": SITEKEY,
        }
    })
    data = r.json()
    log(f"  createTask: {json.dumps(data, ensure_ascii=False)[:300]}")

    if data.get("errorId", 0) != 0:
        log(f"  ❌ NoCaptchaAI failed: {data.get('error', data)}", "ERROR")
        return None

    task_id = data.get("taskId")
    if not task_id:
        log(f"  ❌ No taskId", "ERROR")
        return None

    log(f"  Task ID: {task_id}, polling…")
    start = time.time()
    for attempt in range(60):
        await asyncio.sleep(2)
        r = await cli.post("https://api.nocaptchaai.com/getTaskResult", json={
            "clientKey": NOCAPTCHA_API_KEY, "taskId": task_id,
        })
        data = r.json()
        status = data.get("status", "?")
        elapsed = time.time() - start
        if status == "ready":
            token = data.get("solution", {}).get("token", "")
            log(f"  ✅ Token ready at {elapsed:.1f}s! Length: {len(token)}")
            return token
        elif status == "failed" or data.get("errorId", 0) != 0:
            log(f"  ❌ Failed: {json.dumps(data)[:200]}", "ERROR")
            return None
        if attempt % 5 == 0:
            log(f"  [{elapsed:.0f}s] status={status}…")
    log("  ❌ Timed out", "ERROR")
    return None

# ─── Provider 3: CapSolver ───────────────────────────────────────────────────
async def solve_with_capsolver(cli):
    log("Using CapSolver")
    log(f"  API Key: {CAPSOLVER_API_KEY[:15]}…")

    r = await cli.post("https://api.capsolver.com/createTask", json={
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": LOGIN_URL,
            "websiteKey": SITEKEY,
        }
    })
    data = r.json()
    log(f"  createTask: {json.dumps(data, ensure_ascii=False)[:300]}")

    if data.get("errorId", 0) != 0:
        log(f"  ❌ CapSolver failed: {data.get('errorDescription', data)}", "ERROR")
        return None

    task_id = data.get("taskId")
    if not task_id:
        log(f"  ❌ No taskId", "ERROR")
        return None

    log(f"  Task ID: {task_id}, polling…")
    start = time.time()
    for attempt in range(60):
        await asyncio.sleep(3)
        r = await cli.post("https://api.capsolver.com/getTaskResult", json={
            "clientKey": CAPSOLVER_API_KEY, "taskId": task_id,
        })
        data = r.json()
        status = data.get("status", "?")
        elapsed = time.time() - start
        if status == "ready":
            token = data.get("solution", {}).get("token", "")
            log(f"  ✅ Token ready at {elapsed:.1f}s! Length: {len(token)}")
            return token
        elif status == "failed" or data.get("errorId", 0) != 0:
            log(f"  ❌ Failed: {json.dumps(data)[:200]}", "ERROR")
            return None
        if attempt % 5 == 0:
            log(f"  [{elapsed:.0f}s] status={status}…")
    log("  ❌ Timed out", "ERROR")
    return None

# ─── Solve Turnstile (tries each provider) ──────────────────────────────────
async def solve_turnstile(cli):
    section("STEP 1: Solve Cloudflare Turnstile")

    providers = []
    if NSL_API_KEY:
        providers.append(("NSLSolver", solve_with_nslsolver))
    if NOCAPTCHA_API_KEY:
        providers.append(("NoCaptchaAI", solve_with_nocaptcha))
    if CAPSOLVER_API_KEY:
        providers.append(("CapSolver", solve_with_capsolver))

    if not providers:
        log("❌ No CAPTCHA solver API key set!", "ERROR")
        log("", "ERROR")
        log("Set at least ONE of these environment variables:", "ERROR")
        log("  NSL_API_KEY        — Sign up at https://nslsolver.com (100 free, no card)", "ERROR")
        log("  NOCAPTCHA_API_KEY  — Sign up at https://nocaptchaai.com (6000 free)", "ERROR")
        log("  CAPSOLVER_API_KEY  — Sign up at https://capsolver.com", "ERROR")
        return None

    log(f"Available providers: {[p[0] for p in providers]}")
    log(f"Site key: {SITEKEY}")
    log(f"Login URL: {LOGIN_URL}")

    for name, solver in providers:
        log(f"\n--- Trying {name} ---")
        try:
            token = await solver(cli)
            if token:
                log(f"\n✅ Turnstile solved via {name}!")
                return token
            else:
                log(f"{name} failed, trying next provider…", "WARN")
        except Exception as e:
            log(f"{name} error: {e}", "WARN")
            continue

    log("\n❌ All providers failed!", "ERROR")
    return None

# ─── Login ───────────────────────────────────────────────────────────────────
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

# ─── Save cookies ────────────────────────────────────────────────────────────
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
                "name": name, "value": value, "domain": domain, "path": "/",
                "httpOnly": any("httponly" in a.lower() for a in attrs),
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

# ─── Browse + scrape ─────────────────────────────────────────────────────────
async def browse_and_scrape(cli, cookie_header):
    section("STEP 4: Browse pages + scrape test page")
    results = []
    for name, url in BROWSE_PAGES:
        log(f"\n--- {name}: {url} ---")
        try:
            r = await cli.get(url, headers={
                "User-Agent": UA, "Cookie": cookie_header, "Referer": "https://repeatermock.com/",
            }, follow_redirects=True)
            title = r.text.split("<title>")[1].split("</title>")[0].strip()[:80] if "<title>" in r.text else ""
            log(f"  Status: {r.status_code}  Body: {len(r.text):,} bytes  Title: {title}")
            me_r = await cli.get(ME_API, headers={"Cookie": cookie_header})
            try: me_ok = me_r.json().get("success", False)
            except: me_ok = False
            log(f"  /auth/me: {me_r.status_code} success={me_ok}")
            results.append({"name": name, "url": url, "status": r.status_code, "length": len(r.text), "title": title, "auth_verified": me_ok})

            if "instructions" in url:
                log(f"  ✅ Test page — saving full HTML!")
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
                    except: pass

                # Try API endpoints for questions
                for path in [f"/api/tests/{TEST_ID}", f"/api/tests/{TEST_ID}/answers",
                             f"/api/v1/test-series/{TEST_ID}", f"/api/v1/tests/{TEST_ID}"]:
                    api_url = f"https://api.repeatermock.com{path}"
                    log(f"  Trying: {api_url}")
                    api_r = await cli.get(api_url, headers={"Cookie": cookie_header, "User-Agent": UA})
                    if api_r.status_code == 200:
                        try:
                            d = api_r.json()
                            fname = f"api_{path.replace('/','_')}.json"
                            with open(OUTPUT_DIR / fname, "w") as f:
                                json.dump(d, f, indent=2, ensure_ascii=False)
                            log(f"    ✅ 200 OK — saved {fname} ({len(json.dumps(d)):,} bytes)")
                            if "question" in json.dumps(d).lower():
                                log(f"    🔥 Contains questions!")
                        except: pass
                    else:
                        log(f"    {api_r.status_code}")
        except Exception as e:
            log(f"  ❌ Error: {e}", "ERROR")
    return results

# ─── Main ────────────────────────────────────────────────────────────────────
async def main():
    section("RepeaterMock Login + Test Page Scraper (Multi-provider)")
    log(f"Python: {sys.version.split()[0]}")
    log(f"Email: {EMAIL}")
    log(f"Test page: {TEST_PAGE_URL}")
    log(f"Providers: NSL={'✅' if NSL_API_KEY else '❌'} NoCaptcha={'✅' if NOCAPTCHA_API_KEY else '❌'} CapSolver={'✅' if CAPSOLVER_API_KEY else '❌'}")

    if not any([NSL_API_KEY, NOCAPTCHA_API_KEY, CAPSOLVER_API_KEY]):
        log("❌ No API key set! Set one of: NSL_API_KEY, NOCAPTCHA_API_KEY, CAPSOLVER_API_KEY", "ERROR")
        return

    async with httpx.AsyncClient(timeout=120.0) as cli:
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
