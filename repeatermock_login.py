#!/usr/bin/env python3
"""
RepeaterMock Login + Browse Script (GitHub Actions ready)
==========================================================

1. Solves Cloudflare Turnstile on the REAL repeatermock.com/login page
   using nodriver (EzSolver approach).
2. Submits the login form and captures session cookies.
3. Browses 5-6 pages of the website using the obtained cookies to verify
   the session is valid.
4. Prints detailed, timestamped logs throughout — no buffering.

Designed to run in GitHub Actions with xvfb-run.
"""

import asyncio
import json
import os
import sys
import time
import warnings
import random
from pathlib import Path
from datetime import datetime, timezone

import nodriver as uc
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
URL = "https://repeatermock.com/login"
EMAIL = os.environ.get("RM_EMAIL", "spellingbeeanswers@gmail.com")
PASSWORD = os.environ.get("RM_PASSWORD", "BloggingJi@7")
SITEKEY = "0x4AAAAAADixxaKQ-LspbGkf"

CHROME_PATH = os.environ.get(
    "CHROME_PATH",
    "/home/z/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
)
PROFILE_DIR = os.environ.get("TS_PROFILE_DIR", "/tmp/ts_profile")
OUT = Path(os.environ.get("OUTPUT_DIR", "/home/z/my-project/download"))
OUT.mkdir(parents=True, exist_ok=True)

# Pages to browse after login (to verify the session works)
BROWSE_PAGES = [
    ("Dashboard", "https://repeatermock.com/dashboard"),
    ("Test Series", "https://repeatermock.com/test-series"),
    ("Pricing", "https://repeatermock.com/pricing"),
    ("About", "https://repeatermock.com/about"),
    ("Blog", "https://repeatermock.com/blog"),
    ("Settings", "https://repeatermock.com/settings"),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = OUT / "run_log.txt"


def log(msg: str, level: str = "INFO") -> None:
    """Print a timestamped log line and append to file. No buffering."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def section(title: str) -> None:
    log("")
    log("=" * 70)
    log(f"  {title}")
    log("=" * 70)


# ---------------------------------------------------------------------------
# Core: Solve Turnstile + Login
# ---------------------------------------------------------------------------
async def solve_and_login() -> dict:
    section("STEP 1: Launch nodriver browser (real Chrome, no automation flags)")
    log(f"Chrome path: {CHROME_PATH}")
    log(f"Profile dir: {PROFILE_DIR}")
    log(f"Email: {EMAIL}")

    browser = await uc.start(
        browser_executable_path=CHROME_PATH,
        headless=False,  # needs Xvfb on servers
        user_data_dir=PROFILE_DIR,
        sandbox=False,
        browser_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    log("✅ Browser launched")

    # Set a Googlebot-ish UA via CDP to bypass DisableDevtool (swiper.js).
    # We can't use nodriver's user_agent param (it breaks Chrome on some systems).
    # The UA includes "Googlebot" which makes DisableDevtool skip its checks.
    try:
        page_temp = await browser.get("about:blank")
        await page_temp.send(
            uc.cdp.network.set_user_agent_override(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Googlebot/2.1"
            )
        )
        log("✅ Set Googlebot UA via CDP")
    except Exception as e:
        log(f"⚠️ Could not set UA via CDP: {e}", "WARN")

    try:
        section("STEP 2: Navigate to the real login page")
        log(f"URL: {URL}")
        page = await browser.get(URL)
        await asyncio.sleep(5)
        log("✅ Page loaded")

        # Debug: check page state
        page_info = await page.evaluate("""
            () => ({
                url: window.location.href,
                title: document.title,
                bodyLen: document.body ? document.body.innerHTML.length : 0,
                bodyText: document.body ? document.body.innerText.slice(0, 300) : "",
                hasEmailInput: !!document.querySelector('input[type=email]'),
                hasPasswordInput: !!document.querySelector('input[type=password]'),
                hasForm: !!document.querySelector('form'),
                scripts: Array.from(document.querySelectorAll('script[src]')).map(s => s.src).slice(0, 5),
            })
        """)
        log(f"  URL: {page_info.get('url') if page_info else 'None'}")
        log(f"  Title: {page_info.get('title') if page_info else 'None'}")
        log(f"  Body length: {page_info.get('bodyLen') if page_info else 'None'}")
        log(f"  Body text (first 200): {(page_info.get('bodyText') or '')[:200]}")
        log(f"  Has email input: {page_info.get('hasEmailInput') if page_info else 'None'}")
        log(f"  Has password input: {page_info.get('hasPasswordInput') if page_info else 'None'}")
        log(f"  Has form: {page_info.get('hasForm') if page_info else 'None'}")

        # Save page HTML for debugging
        try:
            html = await page.evaluate("() => document.documentElement.outerHTML")
            with open(OUT / "page_debug.html", "w") as f:
                f.write(html or "")
            log(f"  Saved HTML to page_debug.html")
        except Exception as e:
            log(f"  Could not save HTML: {e}")

        form_visible = page_info.get('hasEmailInput') if page_info else False
        if not form_visible:
            log("❌ Form not visible — page may have detected automation", "ERROR")
            # Try waiting longer and rechecking
            log("  Waiting 10s and rechecking…")
            await asyncio.sleep(10)
            form_visible = await page.evaluate(
                "() => !!document.querySelector('input[type=email]')"
            )
            log(f"  Form visible after 10s: {form_visible}")
            if not form_visible:
                return {"success": False, "error": "form not visible"}

        section("STEP 3: Inject Turnstile widget into the real page")
        await page.evaluate(f"""
            (() => {{
                if (document.getElementById('_ts_box')) return;
                window._tsToken = null;
                const wrap = document.createElement('div');
                wrap.id = '_ts_box';
                wrap.style = 'position:fixed;top:20px;left:20px;z-index:2147483647;';
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
        log("Widget div + api.js injected")
        await asyncio.sleep(5)
        log("Waiting 5s for widget to initialize…")

        section("STEP 4: Wait for Turnstile token (auto-solve or click)")
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
            log("Not auto-solved, attempting to click the widget…")
            for attempt in range(5):
                log(f"  Click attempt {attempt + 1}/5")
                rect_json = await page.evaluate("""
                    JSON.stringify((() => {
                        for (const f of document.querySelectorAll('iframe')) {
                            const src = f.src || f.getAttribute('src') || '';
                            if (!src.includes('challenges.cloudflare.com')) continue;
                            const r = f.getBoundingClientRect();
                            if (r.width > 50 && r.height > 20) return {x:r.x, y:r.y, w:r.width, h:r.height};
                        }
                        return null;
                    })())
                """)
                if rect_json and rect_json != "null":
                    rect = json.loads(rect_json)
                    cx = rect["x"] + 28 + random.uniform(-3, 3)
                    cy = rect["y"] + rect["h"] / 2 + random.uniform(-3, 3)
                    log(f"    iframe found at ({cx:.0f}, {cy:.0f})")
                else:
                    cx = 20 + 28 + random.uniform(-3, 3)
                    cy = 20 + 32 + random.uniform(-3, 3)
                    log(f"    iframe not found, clicking fixed pos ({cx:.0f}, {cy:.0f})")

                await page.mouse_move(cx - 80, cy - 20)
                await asyncio.sleep(0.2)
                await page.mouse_move(cx, cy)
                await asyncio.sleep(0.1)
                await page.mouse_click(cx, cy)
                await asyncio.sleep(3)

                token = await page.evaluate("""
                    (() => {
                        if (window._tsToken) return window._tsToken;
                        const inp = document.querySelector('#_ts_box [name="cf-turnstile-response"]');
                        return (inp && inp.value) ? inp.value : null;
                    })()
                """)
                if token:
                    log(f"✅ Solved after click! Token (first 20): {token[:20]}…")
                    break
                else:
                    log("    Still no token, retrying…")

        if not token:
            log("❌ Failed to solve Turnstile after 5 attempts", "ERROR")
            return {"success": False, "error": "turnstile not solved"}

        log(f"Token length: {len(token)}")

        section("STEP 5: Extract browser cookies")
        browser_cookies = await browser.cookies.get_all()
        cookie_str = "; ".join(f"{c.name}={c.value}" for c in browser_cookies)
        log(f"Got {len(browser_cookies)} cookies from browser")
        for c in browser_cookies:
            log(f"  - {c.name}={c.value[:40]}… (domain={c.domain})")

        section("STEP 6: Submit login via API (same IP as solver)")
        log(f"POST https://api.repeatermock.com/auth/login")
        log(f"  email: {EMAIL}")
        log(f"  password: {'*' * (len(PASSWORD) - 2)}{PASSWORD[-2:]}")
        log(f"  turnstileToken: {token[:30]}…")

        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                "https://api.repeatermock.com/auth/login",
                json={
                    "email": EMAIL,
                    "password": PASSWORD,
                    "turnstileToken": token,
                },
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://repeatermock.com",
                    "Referer": "https://repeatermock.com/login",
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
                    ),
                    "Cookie": cookie_str,
                },
            )
            api_status = r.status_code
            try:
                api_json = r.json()
            except Exception:
                api_json = {"raw": r.text[:500]}
            set_cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else []

        log(f"API response status: {api_status}")
        log(f"API response body: {json.dumps(api_json, ensure_ascii=False)[:400]}")
        log(f"Set-Cookie headers: {len(set_cookies)}")
        for sc in set_cookies:
            log(f"  {sc[:120]}…")

        if api_status != 200 or not api_json.get("success"):
            log(f"❌ Login failed: {api_json}", "ERROR")
            return {"success": False, "error": "login API failed", "api": api_json}

        user = api_json.get("user", {})
        section("STEP 7: Login successful!")
        log(f"✅ User ID:    {user.get('id')}")
        log(f"✅ Name:       {user.get('name')}")
        log(f"✅ Email:      {user.get('email')}")
        log(f"✅ Plan:       {user.get('plan')}")
        log(f"✅ TOTP:       {user.get('totpEnabled')}")

        # Build cookie list
        cookie_list = []
        for c in browser_cookies:
            same_site = c.same_site if hasattr(c, "same_site") else "Lax"
            if hasattr(same_site, "value"):
                same_site = same_site.value
            elif not isinstance(same_site, str):
                same_site = str(same_site)
            cookie_list.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "expires": c.expires if hasattr(c, "expires") else -1,
                "httpOnly": c.http_only if hasattr(c, "http_only") else False,
                "secure": c.secure if hasattr(c, "secure") else False,
                "sameSite": same_site,
            })

        # Merge Set-Cookie headers (accessToken, refreshToken, totpVerified)
        for sc in set_cookies:
            parts = sc.split(";")[0].split("=", 1)
            if len(parts) == 2:
                name = parts[0].strip()
                value = parts[1].strip()
                if not any(c["name"] == name for c in cookie_list):
                    cookie_list.append({
                        "name": name,
                        "value": value,
                        "domain": ".repeatermock.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    })

        # Build a clean cookie header for HTTP requests
        auth_cookies = {c["name"]: c["value"] for c in cookie_list}
        cookie_header = "; ".join(f"{k}={v}" for k, v in auth_cookies.items())

        section("STEP 8: Save cookies")
        cookies_data = {
            "cookies": cookie_list,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "email": EMAIL,
            "user": user,
        }
        with open(OUT / "cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies_data, f, indent=2, ensure_ascii=False)

        with open(OUT / "cookies.txt", "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookie_list:
                domain = c["domain"]
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure") else "FALSE"
                expires = int(c.get("expires", 0))
                if expires == -1:
                    expires = 0
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{c['name']}\t{c['value']}\n")

        access_token = auth_cookies.get("accessToken", "")
        refresh_token = auth_cookies.get("refreshToken", "")
        with open(OUT / "auth_tokens.json", "w", encoding="utf-8") as f:
            json.dump({
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "email": EMAIL,
            }, f, indent=2)

        log(f"Saved: cookies.json ({len(cookie_list)} cookies)")
        log(f"Saved: cookies.txt (Netscape format)")
        log(f"Saved: auth_tokens.json")
        log(f"accessToken (first 50): {access_token[:50]}…")

        # -----------------------------------------------------------------
        # STEP 9: Browse 5-6 pages with the obtained cookies
        # -----------------------------------------------------------------
        section("STEP 9: Browse 5-6 pages with session cookies")

        browse_results = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cli:
            for i, (name, page_url) in enumerate(BROWSE_PAGES, 1):
                log("")
                log(f"--- Page {i}/{len(BROWSE_PAGES)}: {name} ---")
                log(f"  GET {page_url}")
                try:
                    r = await cli.get(
                        page_url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
                            ),
                            "Cookie": cookie_header,
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Referer": "https://repeatermock.com/",
                        },
                    )
                    status = r.status_code
                    final_url = str(r.url)
                    body = r.text
                    body_len = len(body)

                    # Extract <title>
                    title = ""
                    if "<title>" in body:
                        title = body.split("<title>")[1].split("</title>")[0].strip()[:100]

                    # Check for auth indicators
                    has_login_button = "Log in" in body or "/login" in body
                    has_dashboard = "dashboard" in body.lower()
                    has_user_email = EMAIL in body
                    has_logout = "logout" in body.lower() or "log out" in body.lower()

                    log(f"  Status: {status}")
                    log(f"  Final URL: {final_url}")
                    log(f"  Body length: {body_len:,} bytes")
                    log(f"  Title: {title}")
                    log(f"  Has 'Log in' button: {has_login_button}")
                    log(f"  Has 'dashboard' reference: {has_dashboard}")
                    log(f"  Has user email in body: {has_user_email}")
                    log(f"  Has logout link: {has_logout}")

                    # Also try calling /auth/me to verify session
                    me_resp = await cli.get(
                        "https://api.repeatermock.com/auth/me",
                        headers={"Cookie": cookie_header},
                    )
                    me_status = me_resp.status_code
                    try:
                        me_json = me_resp.json()
                        me_success = me_json.get("success", False)
                        me_email = me_json.get("user", {}).get("email", "")
                    except Exception:
                        me_json = {}
                        me_success = False
                        me_email = ""
                    log(f"  /auth/me: status={me_status} success={me_success} email={me_email}")

                    browse_results.append({
                        "name": name,
                        "url": page_url,
                        "status": status,
                        "final_url": final_url,
                        "body_length": body_len,
                        "title": title,
                        "has_login_button": has_login_button,
                        "has_dashboard": has_dashboard,
                        "has_user_email": has_user_email,
                        "has_logout": has_logout,
                        "auth_me_status": me_status,
                        "auth_me_success": me_success,
                    })

                except Exception as e:
                    log(f"  ❌ Error: {e}", "ERROR")
                    browse_results.append({
                        "name": name,
                        "url": page_url,
                        "error": str(e),
                    })

        # -----------------------------------------------------------------
        # STEP 10: Summary
        # -----------------------------------------------------------------
        section("STEP 10: Final Summary")

        successful_pages = sum(1 for r in browse_results if r.get("status") == 200)
        auth_verified = sum(1 for r in browse_results if r.get("auth_me_success"))

        log(f"Login: ✅ SUCCESS")
        log(f"User:  {user.get('name')} ({user.get('email')})")
        log(f"Plan:  {user.get('plan')}")
        log(f"")
        log(f"Pages browsed: {len(browse_results)}/{len(BROWSE_PAGES)}")
        log(f"  Successful (HTTP 200): {successful_pages}")
        log(f"  /auth/me verified:     {auth_verified}")
        log(f"")
        log(f"Browse results:")
        for r in browse_results:
            status_icon = "✅" if r.get("status") == 200 else "❌"
            auth_icon = "🔒" if r.get("auth_me_success") else "🔓"
            log(
                f"  {status_icon} {auth_icon} {r['name']:<15} "
                f"status={r.get('status', 'ERR')} "
                f"len={r.get('body_length', 0):>7,} "
                f"title='{r.get('title', '')[:40]}'"
            )

        log(f"")
        log(f"Files saved:")
        for f in sorted(OUT.iterdir()):
            if f.is_file():
                log(f"  {f}  ({f.stat().st_size:,} bytes)")

        return {
            "success": True,
            "user": user,
            "cookies": cookie_list,
            "browse_results": browse_results,
        }

    finally:
        browser.stop()


def start_xvfb_if_needed():
    import platform
    import subprocess
    if platform.system() != "Linux":
        return None
    if os.environ.get("DISPLAY"):
        return None
    log("No DISPLAY set, starting Xvfb …")
    proc = subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x900x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = ":99"
    time.sleep(2)
    return proc


if __name__ == "__main__":
    section("RepeaterMock Login + Browse — GitHub Actions run")
    log(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    log(f"Python: {sys.version.split()[0]}")
    log(f"Working dir: {os.getcwd()}")
    log(f"Output dir: {OUT}")

    xvfb = start_xvfb_if_needed()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = asyncio.run(solve_and_login())
        if not result.get("success"):
            log(f"\n❌ FAILED: {result.get('error')}", "ERROR")
            sys.exit(1)
        else:
            log(f"\n🎉 ALL DONE — login + browse complete!")
    finally:
        if xvfb:
            xvfb.terminate()
