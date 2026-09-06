# RepeaterMock Auto-Login

Automatically logs into [repeatermock.com](https://repeatermock.com) by solving Cloudflare Turnstile using residential proxy rendering APIs. Runs on GitHub Actions — no local machine needed.

**Status: ✅ PROVEN WORKING** (GitHub Action Run #33916072971)

## How It Works

Cloudflare Turnstile blocks datacenter IPs (GitHub Actions, AWS, etc.). This script uses scraping APIs that render the login page on **their servers** using **residential proxy IPs** that Cloudflare trusts. The Turnstile widget solves naturally, we extract the token, and submit it to the login API.

## Free Providers (pick any one, all use residential proxies)

| Provider | Free Credits | Credits per Login | Logins/month | Sign Up |
|---|---|---|---|---|
| **BrightData** ⭐ | 5,000/month | 1 | ~5,000 | https://brightdata.com/ |
| **ZenRows** | 5,000/month | 25 (JS+premium) | ~200 | https://www.zenrows.com/ |
| **ScrapingBee** | 1,000/month | 1 | ~330 | https://www.scrapingbee.com/ |

All three are **free, no credit card required**. BrightData gives the most free credits.

## Setup (2 minutes)

1. **Sign up** for any provider above (free, no card)
2. **Add GitHub secrets** (Settings → Secrets → Actions):
   - `BRIGHTDATA_TOKEN` OR `ZENROWS_API_KEY` OR `SCRAPINGBEE_API_KEY`
   - `RM_EMAIL` — your RepeaterMock email
   - `RM_PASSWORD` — your RepeaterMock password
3. **Run the workflow** (Actions tab → Run workflow)
4. **Download artifacts** (cookies.json, auth_tokens.json)

## Cookie Caching (Save Credits)

The `refreshToken` lasts days/weeks. After the first login (costs 1 credit), use it to get new access tokens without solving Turnstile again:

```python
response = requests.post("https://api.repeatermock.com/auth/refresh",
    headers={"Cookie": f"refreshToken={refresh_token}"})
new_access_token = response.json()["accessToken"]
# Cost: 0 credits!
```

## Files

- `repeatermock_login.py` — Multi-provider login script
- `.github/workflows/repeatermock-login.yml` — GitHub Actions workflow

## Links

- Repo: https://github.com/Debrupos7/repeatermock-login
- Proof: https://github.com/Debrupos7/repeatermock-login/actions/runs/33916072971
- BrightData: https://brightdata.com/
- ZenRows: https://www.zenrows.com/
- ScrapingBee: https://www.scrapingbee.com/

## License

Educational purposes only.
