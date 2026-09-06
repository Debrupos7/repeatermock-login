# RepeaterMock Auto-Login + Scraper

Automatically logs into [repeatermock.com](https://repeatermock.com), bypasses Cloudflare Turnstile CAPTCHA, obtains session cookies, and scrapes test pages (questions, answers, solutions) — all running on GitHub Actions with zero local infrastructure.

**Status: ✅ PROVEN WORKING** — Successfully tested on GitHub Actions (Run #33916072971)

---

## ⚠️ IMPORTANT: What Actually Worked

**ScrapingBee** with `stealth_proxy=true` is the **ONLY** service that successfully solved Cloudflare Turnstile and produced a working login.

| Service | Did it work? | Explanation |
|---------|-------------|-------------|
| **ScrapingBee** (`stealth_proxy=true`) | **✅ YES — PROVEN** | Uses residential proxy IPs that Cloudflare trusts. Turnstile solves naturally. Token submitted to login API → cookies obtained. **GitHub Action Run #33916072971 succeeded.** |
| **Scrapfly** (`asp=true`, `country=in`) | **❌ NO** | Tested 10+ times. The Turnstile iframe loads but the token is **never populated**. An earlier "breakthrough" was a false positive — a 147-char string that matched the regex but was NOT a real token (real tokens are 500+ chars). After fixing extraction, Scrapfly failed 10/10 attempts. |
| **NoCaptchaAI API** | **❌ NO** | API key rejected ("Invalid apikey"). Free credits not activated on the account. |
| **Direct Playwright/nodriver** on GitHub Actions | **❌ NO** | Azure datacenter IP → Cloudflare refuses to render Turnstile widget. |
| **Theyka/Turnstile-Solver** (route interception) | **❌ NO** | Token solved but rejected by siteverify (synthetic page detected). |

**Bottom line: You need a ScrapingBee API key for this to work.**

---

## How It Works

### The Problem

RepeaterMock uses Cloudflare Turnstile CAPTCHA on its login page. Turnstile checks:
1. **IP reputation** — datacenter IPs (AWS, Azure, GCP) are flagged as high-risk
2. **Browser fingerprint** — headless browsers are detected
3. **Behavioral signals** — mouse movement, timing

When running on GitHub Actions (Azure datacenter IP), Cloudflare loads the page but **refuses to issue a Turnstile token** — the widget stays empty forever.

### The Solution: ScrapingBee Stealth Proxy

[ScrapingBee](https://www.scrapingbee.com/) renders the login page on **their servers** using **residential proxy IPs**. Cloudflare sees a residential IP → allows Turnstile to solve → we extract the token → submit it to the login API.

```
GitHub Actions (Azure IP)          ScrapingBee (Residential IP)        RepeaterMock
       │                                    │                              │
       │  1. "Render this page"             │                              │
       │───────────────────────────────────▶│                              │
       │                                    │  2. Load page + stealth      │
       │                                    │─────────────────────────────▶│
       │                                    │                              │
       │                                    │  3. Turnstile SOLVES ✅      │
       │                                    │◀─────────────────────────────│
       │  4. Returns HTML with token        │                              │
       │◀───────────────────────────────────│                              │
       │                                    │                              │
       │  5. POST token + email + password  │                              │
       │─────────────────────────────────────────────────────────────────▶│
       │                                    │                              │
       │  6. Returns accessToken + refreshToken                             │
       │◀─────────────────────────────────────────────────────────────────│
       │                                    │                              │
       │  7. Use cookies to scrape pages    │                              │
       │─────────────────────────────────────────────────────────────────▶│
       │  8. Returns test questions/answers                                │
       │◀─────────────────────────────────────────────────────────────────│
```

The token works from any IP because Cloudflare's `siteverify` validates the token against the IP that **solved** it (ScrapingBee's residential IP), not the IP that **submits** it (GitHub Actions).

### Step-by-Step Logic

**Step 1: Solve Turnstile via ScrapingBee**
```python
# Ask ScrapingBee to render the login page with residential proxy
response = httpx.get("https://app.scrapingbee.com/api/v1/", params={
    "api_key": SCRAPINGBEE_API_KEY,
    "url": "https://repeatermock.com/login",
    "render_js": "true",        # Execute JavaScript (Turnstile widget)
    "wait": "20",                # Wait 20 seconds for Turnstile to solve
    "stealth_proxy": "true",    # CRITICAL: Use residential proxy
})

# Extract token from the hidden input in the returned HTML
# <input type="hidden" name="cf-turnstile-response" value="1.abc123...xyz">
token = re.search(r'name="cf-turnstile-response"[^>]*value="([^"]+)"', response.text).group(1)
```

**Step 2: Login to RepeaterMock (IMMEDIATELY — token expires in 300s)**
```python
response = httpx.post("https://api.repeatermock.com/auth/login", json={
    "email": EMAIL,
    "password": PASSWORD,
    "turnstileToken": token,
})

# Set-Cookie headers contain:
# accessToken=eyJhbGciOiJIUzI1NiIs...  (JWT, expires in 15 min)
# refreshToken=b5def785971d54fc...      (lasts days/weeks)
# totpVerified=1
```

**Step 3: Save Cookies**
- `cookies.json` — Full JSON
- `cookies.txt` — Netscape format for curl
- `auth_tokens.json` — Just accessToken + refreshToken

**Step 4: Scrape Pages**
```python
# Browse any authenticated page
response = httpx.get(TEST_PAGE_URL, headers={"Cookie": cookie_header})

# Also try API endpoints for structured data
response = httpx.get(f"https://api.repeatermock.com/api/tests/{TEST_ID}",
                     headers={"Cookie": cookie_header})
```

**Step 5: Cookie Refresh (Save API Credits)**
```python
# The accessToken expires in 15 min, but refreshToken lasts much longer.
# Use it to get a new accessToken WITHOUT solving Turnstile again:
response = httpx.post("https://api.repeatermock.com/auth/refresh",
                      headers={"Cookie": f"refreshToken={refresh_token}"})
new_access_token = response.json()["accessToken"]
# Cost: 0 ScrapingBee credits!
```

---

## Setup Guide

### Prerequisites
- GitHub account
- [ScrapingBee](https://www.scrapingbee.com/) API key (free: 1,000 calls/month, no credit card)
- RepeaterMock email + password

### Steps

1. **Fork/clone this repo:**
   ```bash
   git clone https://github.com/Debrupos7/repeatermock-login.git
   ```

2. **Get ScrapingBee API key:**
   - Go to https://www.scrapingbee.com/
   - Sign up (free, no credit card)
   - Copy API key from dashboard

3. **Add GitHub secrets** (Settings → Secrets → Actions):
   | Secret | Value |
   |---|---|
   | `SCRAPINGBEE_API_KEY` | Your ScrapingBee key |
   | `RM_EMAIL` | RepeaterMock email |
   | `RM_PASSWORD` | RepeaterMock password |

4. **Run the workflow:**
   - Actions tab → "RepeaterMock Login + Scrape" → Run workflow
   - Wait ~60 seconds
   - Download artifact

5. **Use the cookies:**
   ```bash
   curl --cookie cookies.txt https://api.repeatermock.com/auth/me
   ```

---

## Repository Structure

```
repeatermock-login/
├── .github/workflows/
│   └── repeatermock-login.yml    # GitHub Actions workflow (runs every 12h or manual)
├── repeatermock_login.py         # Main script (ScrapingBee + login + scrape)
└── README.md                     # This file
```

### `repeatermock_login.py` does:
1. Calls ScrapingBee to render login page → extracts Turnstile token (retries 5x)
2. Submits token + credentials to `/auth/login` API
3. Saves cookies (accessToken, refreshToken)
4. Scrapes the test page (HTML + API endpoints)
5. Browses Dashboard + Test Series pages
6. Saves everything to output directory

### Workflow `.github/workflows/repeatermock-login.yml`:
- Runs on `ubuntu-latest`
- Only dependency: `httpx` (no browser!)
- Triggers: manual (`workflow_dispatch`) or every 12 hours (`cron`)
- Uploads all output as downloadable artifact

---

## Cookie Caching (Save API Credits)

| Run Type | ScrapingBee Credits Used | How |
|---|---|---|
| First login | ~3 credits | Solve Turnstile → login → save refreshToken |
| Subsequent logins | **0 credits** | Use refreshToken → get new accessToken via `/auth/refresh` |

```python
# Load saved refresh token
refresh_token = json.load(open("auth_tokens.json"))["refreshToken"]

# Get new access token (NO Turnstile needed!)
response = requests.post("https://api.repeatermock.com/auth/refresh",
    headers={"Cookie": f"refreshToken={refresh_token}"})
new_access_token = response.json()["accessToken"]
```

With caching: 1,000 free ScrapingBee credits = **~330 initial logins** + unlimited refreshes.

---

## Scraping Questions/Answers/Solutions

### Free test pages
```
URL: https://repeatermock.com/tb/test-series/ssc-cgl/test/{TEST_ID}/instructions
```

### Pro test pages
```
URL: https://repeatermock.com/tb-pro/test-series/ssc-cgl/test/{TEST_ID}/attempt
```
Requires a Pro plan account.

### Method 1: Scrape HTML + extract __NEXT_DATA__
```python
response = requests.get(TEST_PAGE_URL, headers={"Cookie": cookie_header})
# Extract Next.js server data (contains questions/answers)
next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      response.text, re.DOTALL)
data = json.loads(next_data.group(1))
questions = data["props"]["pageProps"]
```

### Method 2: Use API endpoints
```python
# Get test details
requests.get(f"https://api.repeatermock.com/api/tests/{TEST_ID}",
             headers={"Cookie": cookie_header})

# Get answers
requests.get(f"https://api.repeatermock.com/api/tests/{TEST_ID}/answers",
             headers={"Cookie": cookie_header})
```

---

## All Approaches Tried

| # | Approach | Worked? | Why |
|---|---|---|---|
| 1 | **ScrapingBee** (stealth_proxy=true) | **✅** | Residential IP → Turnstile solves → valid token |
| 2 | Theyka/Turnstile-Solver (route interception) | ❌ | Token rejected by siteverify (synthetic page) |
| 3 | Direct Playwright on GitHub Actions | ❌ | Datacenter IP → Turnstile never solves |
| 4 | nodriver (EzSolver) on GitHub Actions | ❌ | Datacenter IP + Chrome launch issues |
| 5 | Camoufox (Firefox stealth) | ❌ | Token solved but rejected by siteverify |
| 6 | NoCaptchaAI API (6000 free) | ❌ | API key rejected — credits not activated |
| 7 | Scrapfly (asp=true, country=in) | ❌ | Turnstile iframe loads but token never populates |
| 8 | FlareSolverr | ❌ | Deprecated, Cloudflare monitors it |
| 9 | Google OAuth | ❌ | Google bot detection blocks automation |
| 10 | Render deployment (AWS) | ❌ | Same datacenter IP issue |
| 11 | Free proxy lists | ❌ | All datacenter proxies blocked |
| 12 | Cloudflare Workers | ❌ | Can't solve Turnstile from Workers |

---

## API Reference

### ScrapingBee
```
GET https://app.scrapingbee.com/api/v1/
```
| Param | Value | Description |
|---|---|---|
| `api_key` | YOUR_KEY | Authentication |
| `url` | https://repeatermock.com/login | Page to render |
| `render_js` | true | Execute JavaScript |
| `wait` | 20 | Wait 20s for Turnstile |
| `stealth_proxy` | true | **CRITICAL** — residential proxy |

### RepeaterMock
| Endpoint | Method | Description |
|---|---|---|
| `POST /auth/login` | POST | Login (email + password + turnstileToken) |
| `GET /auth/me` | GET | Verify auth + user profile |
| `POST /auth/refresh` | POST | Refresh accessToken |
| `GET /api/tests/{id}` | GET | Get test details |
| `GET /api/tests/{id}/answers` | GET | Get answers |

Base URL: `https://api.repeatermock.com`

---

## Cost Analysis

| Service | Free Tier | Cost per Login | Total Logins |
|---|---|---|---|
| **ScrapingBee** | 1,000 calls/month | ~3 calls (with retries) | ~330/month |
| With cookie caching | — | 0 (use refreshToken) | Unlimited refreshes |

---

## Troubleshooting

**"No token found"** — Turnstile didn't solve (~40% failure rate per attempt). Script retries 5x.

**"Captcha verification failed"** — Token expired before submission. Script submits immediately after extraction.

**"Monthly API calls limit reached"** — ScrapingBee free tier exhausted. Create new account or wait for monthly reset.

---

## Links

- **Repo:** https://github.com/Debrupos7/repeatermock-login
- **Proof it worked:** https://github.com/Debrupos7/repeatermock-login/actions/runs/33916072971
- **ScrapingBee:** https://www.scrapingbee.com/
- **RepeaterMock:** https://repeatermock.com
- **Turnstile-Solver (failed):** https://github.com/Theyka/Turnstile-Solver
- **EzSolver (failed on GHA):** https://github.com/ismoiloffS/EzSolver
- **NoCaptchaAI (failed):** https://nocaptchaai.com
- **Scrapfly (failed):** https://scrapfly.io
- **Monid API (research):** https://api.monid.ai

---

## License

Educational purposes only. Use responsibly.
