# RepeaterMock Auto-Login + Scraper

Automatically logs into [repeatermock.com](https://repeatermock.com), bypasses Cloudflare Turnstile CAPTCHA, obtains session cookies, and scrapes test pages — all running on GitHub Actions with **zero local infrastructure**.

**Status: ✅ WORKING — Proven on GitHub Actions with ZenRows (Run #34011335116) and ScrapingBee (Run #33916072971)**

---

## Quick Start (3 minutes)

### Step 1: Get a free API key

Sign up for **any one** of these (all free, no credit card):

| Provider | Free Credits | Cost per Login | Total Logins | Sign Up |
|---|---|---|---|---|
| **ZenRows** ⭐ | 5,000/month | 25 credits | ~200/month | https://www.zenrows.com/ |
| **ScrapingBee** | 1,000/month | 1 credit | ~330/month | https://www.scrapingbee.com/ |
| **BrightData** | 5,000/month | 1 credit | ~5,000/month | https://brightdata.com/ |

**Recommendation:** ZenRows is the best balance — 5,000 free credits, uses residential proxies, and is proven working.

### Step 2: Fork this repo

```bash
git clone https://github.com/Debrupos7/repeatermock-login.git
cd repeatermock-login
```

Or fork via GitHub: https://github.com/Debrupos7/repeatermock-login/fork

### Step 3: Add secrets

Go to your forked repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret Name | Value | Required? |
|---|---|---|
| `ZENROWS_API_KEY` | Your ZenRows API key | ✅ (recommended) |
| `SCRAPINGBEE_API_KEY` | Your ScrapingBee API key | Optional (alternative) |
| `BRIGHTDATA_TOKEN` | Your BrightData token + zone | Optional (alternative) |
| `RM_EMAIL` | Your RepeaterMock email | ✅ |
| `RM_PASSWORD` | Your RepeaterMock password | ✅ |

You only need **one** of the three API keys. ZenRows is recommended.

### Step 4: Run the workflow

1. Go to your repo → **Actions** tab
2. Select **"RepeaterMock Login"** workflow
3. Click **"Run workflow"**
4. Wait ~80 seconds
5. Click on the completed run → scroll down to **Artifacts**
6. Download `repeatermock-output`

### Step 5: Use the cookies

The downloaded artifact contains:

```
output/
├── cookies.json         # Full cookie jar (JSON)
├── cookies.txt          # Netscape format for curl
├── auth_tokens.json     # Just accessToken + refreshToken
└── run_log.txt          # Full timestamped log
```

```bash
# Use cookies with curl
curl --cookie cookies.txt https://api.repeatermock.com/auth/me

# Or use the access token directly
curl -H "Cookie: accessToken=eyJhbGci..." https://api.repeatermock.com/auth/me
```

---

## How It Works

### The Problem

RepeaterMock.com uses **Cloudflare Turnstile** CAPTCHA on its login page. Turnstile checks:

1. **IP reputation** — Datacenter IPs (AWS, Azure, GCP, GitHub Actions) are flagged as high-risk
2. **Browser fingerprint** — Headless browsers are detected via `navigator.webdriver`, CDP artifacts
3. **Behavioral signals** — Mouse movement, click patterns, timing

When running on GitHub Actions (Azure datacenter IP), Cloudflare loads the page but **refuses to issue a Turnstile token** — the widget iframe stays empty (0 width, 0 height) forever.

### The Solution: Residential Proxy Rendering APIs

[**ZenRows**](https://www.zenrows.com/) (and ScrapingBee) render the login page on **their servers** using **residential proxy IPs** (real ISP IPs from homes/mobile devices). Cloudflare sees a residential IP → allows the Turnstile widget to solve → the token is populated in the hidden `<input name="cf-turnstile-response">` field → the API returns the fully rendered HTML with the token.

```
GitHub Actions (Azure IP)              ZenRows (Residential IP)           RepeaterMock
       │                                       │                               │
       │  1. "Render this page for me"         │                               │
       │──────────────────────────────────────▶│                               │
       │                                       │  2. Load page + premium proxy │
       │                                       │──────────────────────────────▶│
       │                                       │                               │
       │                                       │  3. Turnstile SOLVES ✅       │
       │                                       │◀──────────────────────────────│
       │  4. Returns HTML with token           │                               │
       │◀──────────────────────────────────────│                               │
       │                                       │                               │
       │  5. POST token + email + password     │                               │
       │─────────────────────────────────────────────────────────────────────▶│
       │                                       │                               │
       │  6. Returns accessToken + refreshToken│                               │
       │◀─────────────────────────────────────────────────────────────────────│
       │                                       │                               │
       │  7. Use cookies to browse/scrape      │                               │
       │─────────────────────────────────────────────────────────────────────▶│
```

The token works from any IP because Cloudflare's `siteverify` validates the token against the IP that **solved** it (ZenRows' residential IP), not the IP that **submits** it (GitHub Actions).

### ZenRows API Parameters

```python
response = httpx.get("https://api.zenrows.com/v1/", params={
    "url": "https://repeatermock.com/login",
    "apikey": ZENROWS_API_KEY,
    "js_render": "true",        # Execute JavaScript (Turnstile widget)
    "premium_proxy": "true",    # CRITICAL: Use residential proxy
    "wait": "25000",            # Wait 25s for Turnstile to solve
})
```

### Turnstile Token Extraction

The token is in a hidden input in the returned HTML:

```html
<input type="hidden" name="cf-turnstile-response" value="1.abc123...xyz">
```

```python
import re
match = re.search(r'name="cf-turnstile-response"[^>]*value="([^"]+)"', response.text)
token = match.group(1)  # The Turnstile token (500-800+ chars)
```

### Login API Call

```python
response = httpx.post("https://api.repeatermock.com/auth/login", json={
    "email": "your@email.com",
    "password": "yourpassword",
    "turnstileToken": token,
}, headers={
    "Content-Type": "application/json",
    "Origin": "https://repeatermock.com",
    "Referer": "https://repeatermock.com/login",
})

# Set-Cookie headers contain:
# accessToken=eyJhbGciOiJIUzI1NiIs...  (JWT, expires in 15 min)
# refreshToken=411ee7b2fff110...         (lasts 30 days)
# totpVerified=1
```

---

## Cookie Caching (Save API Credits)

The `accessToken` expires after **15 minutes**, but the `refreshToken` lasts **30 days**. After the first login (costs 25 ZenRows credits), use the refresh token to get new access tokens without solving Turnstile again:

```python
import httpx

# Load saved refresh token
refresh_token = json.load(open("auth_tokens.json"))["refreshToken"]

# Get new access token (NO Turnstile needed!)
response = httpx.post("https://api.repeatermock.com/auth/refresh", headers={
    "Cookie": f"refreshToken={refresh_token}"
})
new_access_token = response.headers.get("set-cookie", "").split("accessToken=")[1].split(";")[0]

# Use the new access token
response = httpx.get("https://api.repeatermock.com/auth/me", headers={
    "Cookie": f"accessToken={new_access_token}; refreshToken={refresh_token}"
})
print(response.json())  # {"success": true, "user": {...}}
```

**Cost comparison:**

| Method | ZenRows Credits | When to Use |
|---|---|---|
| Full login (Turnstile solve) | 25 | First time, or when refreshToken expires |
| Token refresh | 0 | Every subsequent time (within 30 days) |

With caching: 5,000 free credits = **200 initial logins** + unlimited refreshes for 30 days each.

---

## Scraping Test Pages

### Using cookies to browse authenticated pages

```python
import httpx

cookie_header = "accessToken=eyJhbGci...; refreshToken=411ee7b2...; totpVerified=1"

# Browse dashboard
response = httpx.get("https://repeatermock.com/dashboard",
    headers={"Cookie": cookie_header})

# Browse test series
response = httpx.get("https://repeatermock.com/test-series",
    headers={"Cookie": cookie_header})

# Browse specific test page
response = httpx.get(
    "https://repeatermock.com/tb/test-series/ssc-cgl/test/6a0f3ef35a73de9e21cdf098/instructions",
    headers={"Cookie": cookie_header})
```

### RepeaterMock API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `POST /auth/login` | POST | Login (email + password + turnstileToken) |
| `GET /auth/me` | GET | Verify auth + get user profile |
| `POST /auth/refresh` | POST | Refresh accessToken using refreshToken |
| `GET /api/v2/test-series/{slug}` | GET | Get test series info + sections |
| `GET /api/v2/test-series/{id}/sections/{sectionId}/tests` | GET | Get list of tests |
| `POST /api/v2/attempts/{testId}/start` | POST | Start a test attempt → returns questions |
| `POST /api/v2/attempts/{attemptId}/submit` | POST | Submit answers |
| `GET /api/v2/attempts/{attemptId}/result` | GET | Get results + solutions |

**Base URL:** `https://api.repeatermock.com`

### Example: Get test series data

```python
# Get all test series
response = httpx.get("https://api.repeatermock.com/api/v2/test-series/ssc-selection-post",
    headers={"Cookie": cookie_header})

# Get tests in a section
response = httpx.get(
    "https://api.repeatermock.com/api/v2/test-series/5214/sections/1649/tests?limit=30&offset=0",
    headers={"Cookie": cookie_header})

# Each test has: id, title, isFree, duration, questionCount, totalMark
```

---

## Repository Structure

```
repeatermock-login/
├── .github/
│   └── workflows/
│       └── repeatermock-login.yml    # GitHub Actions workflow
├── repeatermock_login.py             # Main script (multi-provider)
└── README.md                         # This file
```

### `repeatermock_login.py`

The main script that:
1. Tries each provider in order: BrightData → ZenRows → ScrapingBee
2. Renders the login page via the provider's API (residential proxy)
3. Extracts the Turnstile token from the rendered HTML
4. Submits the token + credentials to RepeaterMock's login API
5. Saves cookies (accessToken, refreshToken)
6. Browses Dashboard, Test Series, and Test pages to verify auth
7. Saves everything to the output directory

### `.github/workflows/repeatermock-login.yml`

- Runs on `ubuntu-latest`
- Only dependency: `httpx` (no browser!)
- Triggers: manual (`workflow_dispatch`) or every 12 hours (`cron: "0 */12 * * *"`)
- Uploads all output as a downloadable artifact

---

## All Approaches Tested

| # | Approach | Worked? | Why |
|---|---|---|---|
| 1 | **ZenRows** (premium_proxy + js_render) | **✅** | Residential IP → Turnstile solves → valid token. **GitHub Action #34011335116** |
| 2 | **ScrapingBee** (stealth_proxy) | **✅** | Residential IP → Turnstile solves → valid token. **GitHub Action #33916072971** |
| 3 | **BrightData** (Web Unlocker) | Not tested | Requires zone name from dashboard. 5,000 free credits. |
| 4 | Theyka/Turnstile-Solver (route interception) | ❌ | Token rejected by siteverify (synthetic page detected) |
| 5 | EzSolver/nodriver on GitHub Actions | ❌ | Azure datacenter IP → Turnstile iframe never renders |
| 6 | NoCaptchaAI API (6000 free) | ❌ | API key rejected — free credits not activated |
| 7 | Scrapfly (asp=true) | ❌ | Turnstile iframe loads but token never populates |
| 8 | Webshare datacenter proxies | ❌ | Datacenter IP (Leaseweb) → Cloudflare blocks Turnstile |
| 9 | FlareSolverr | ❌ | Deprecated, Cloudflare monitors it |
| 10 | Google OAuth | ❌ | Google bot detection blocks automated login |
| 11 | Render deployment (AWS) | ❌ | Same datacenter IP issue |
| 12 | Direct Playwright on GitHub Actions | ❌ | Azure datacenter IP → Turnstile never solves |

**Key finding:** The IP reputation is the critical factor. Only **residential proxy IPs** (used by ZenRows/ScrapingBee) pass Cloudflare's Turnstile. Datacenter IPs (Webshare, AWS, Azure, GitHub Actions) are all blocked.

---

## Troubleshooting

### "No token found" / "Hidden input exists but no token"

Turnstile didn't solve on that attempt. This happens ~30-40% of the time per attempt (residential proxy IPs vary — some are flagged, some aren't). The script retries up to 10 times. If all fail:
- Wait a few minutes and try again
- The residential proxy pool rotates — some IPs have better reputation

### "Monthly API calls limit reached" (ScrapingBee)

ScrapingBee free tier exhausted (1,000 calls). Options:
- Wait for monthly reset (1st of each month)
- Use ZenRows instead (5,000 free credits)
- Create a new account with a different email

### "Captcha verification failed"

Token expired before submission (tokens expire after 300 seconds). The script submits immediately after extraction, so this is rare. If it happens, just retry.

### "session_expired" / "Invalid or expired refresh token"

The refreshToken has expired (after 30 days). Run the full login workflow again to get a fresh one.

### BrightData: "zone not found"

BrightData requires a **zone name** in addition to the API token. To get it:
1. Log into https://brightdata.com/ dashboard
2. Go to Web Access → Create API → Web Unlocker
3. The zone name is shown in the Overview tab
4. Set `BRIGHTDATA_TOKEN` secret as: `your_token:your_zone_name`

---

## Cost Analysis

| Provider | Free Tier | Cost per Login | Logins per Month | With Cookie Caching |
|---|---|---|---|---|
| **ZenRows** | 5,000 credits | 25 credits | ~200 | 200 initial + unlimited refreshes |
| **ScrapingBee** | 1,000 calls | 1 call | ~330 | 330 initial + unlimited refreshes |
| **BrightData** | 5,000 credits | 1 credit | ~5,000 | 5,000 initial + unlimited refreshes |

---

## Links

### Repositories
- **Main repo:** https://github.com/Debrupos7/repeatermock-login

### API Providers
- **ZenRows:** https://www.zenrows.com/ (5,000 free credits, proven working)
- **ScrapingBee:** https://www.scrapingbee.com/ (1,000 free credits, proven working)
- **BrightData:** https://brightdata.com/ (5,000 free credits)

### Proof It Works
- **ZenRows success:** https://github.com/Debrupos7/repeatermock-login/actions/runs/34011335116
- **ScrapingBee success:** https://github.com/Debrupos7/repeatermock-login/actions/runs/33916072971

### Target Site
- **RepeaterMock:** https://repeatermock.com
- **Login page:** https://repeatermock.com/login
- **Login API:** https://api.repeatermock.com/auth/login
- **Turnstile sitekey:** `0x4AAAAAADixxaKQ-LspbGkf`

### Turnstile Solver Repos Researched
- Theyka/Turnstile-Solver: https://github.com/Theyka/Turnstile-Solver
- ismoiloffS/EzSolver: https://github.com/ismoiloffS/EzSolver
- sarperavci/CloudflareBypassForScraping: https://github.com/sarperavci/CloudflareBypassForScraping
- 1837620622/cloudflare-bypass-2026: https://github.com/1837620622/cloudflare-bypass-2026

---

## License

Educational purposes only. Use responsibly and in accordance with the target site's Terms of Service.
