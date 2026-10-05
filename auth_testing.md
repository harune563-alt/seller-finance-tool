# Custom JWT Authentication Regression Playbook

Existing authentication is preserved (7-day access token, secure HttpOnly SameSite=None cookie,
Authorization Bearer fallback). Refresh/reset endpoints were not in this feature's scope.
Use external REACT_APP_BACKEND_URL from frontend/.env for requests.
Test account credentials are in memory/test_credentials.md.

## 1. Mongo verification
- users.email unique; bcrypt hashes begin `$2b$`.
- login_attempts.identifier unique; expires_at TTL expireAfterSeconds=0.
- User-visible responses never include password hashes or ObjectIds.

## 2. API and browser
- POST /api/auth/login returns token plus secure HttpOnly access_token cookie.
- GET /api/auth/me works with cookie and with Bearer token independently.
- Valid login -> dashboard -> authenticated reload -> logout -> protected route redirects.
- Wrong credentials return generic401; on fifth failure return429 with Retry-After.
- Correct password during lockout remains429; use dedicated test identity, NOT admin.
- Set that test entry expires_at into the past in test-only DB setup; correct login succeeds.
- Successful login before reaching limit clears its counter; counter survives app reload.
- Concurrent bad attempts are counted atomically per normalized account email, independent of rotating ingress IPs.
- No wildcard credentialed CORS; allowed origin preflight200, other origins denied.
- Cross-origin cookie mutation request returns403; legitimate app origin works.
- Distinct accounts' stores, transactions, and cost-update access remain isolated.
- Cleanup test rate-limit entries; persist any new test credentials immediately.
- Preview ingress rewrites the public Origin to this app's internal cluster alias. CORS_ORIGIN_ALIASES normalizes only this exact configured alias to the public origin before CORS and the cookie guard. No wildcard or forwarded-host bypass; update environment configuration for a changed environment.