# RepeaterMock Auto-Login

Automatically logs into [repeatermock.com](https://repeatermock.com) by solving
the Cloudflare Turnstile challenge using [EzSolver](https://github.com/ismoiloffS/EzSolver)
(nodriver — a real Chrome with no automation flags).

## How it works

1. Launches a real Chrome via `nodriver` (no webdriver/CDP artifacts)
2. Navigates to `https://repeatermock.com/login`
3. Injects the Turnstile widget into the real page DOM
4. Clicks the widget to solve the challenge
5. Submits the login form via the `/auth/login` API
6. Captures `accessToken`, `refreshToken`, and other session cookies
7. Browses 5-6 pages to verify the session works

## Setup

1. Set repository secrets:
   - `RM_EMAIL` — your RepeaterMock email
   - `RM_PASSWORD` — your RepeaterMock password

2. Trigger the workflow manually (Actions tab → Run workflow) or let it
   run on the 12-hour schedule.

3. Download the `repeatermock-cookies` artifact from the workflow run.

## Files

- `repeatermock_login.py` — main script
- `.github/workflows/repeatermock-login.yml` — GitHub Actions workflow
