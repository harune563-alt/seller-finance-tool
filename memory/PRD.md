# PRD — Seller Finance Tool (Amazon Seller Suite)

## Original Problem Statement
Import and run existing project from GitHub (repo: harune563-alt/seller-finance-tool, branch `emergent-latest-20261011`). No rebuild, no redesign, no business-logic changes. Restore runtime, verify preview login (admin@amzsuite.com / admin123) and Dashboard load. Preserve all modules: Amazon Payments CSV import, SellerFlash reconciliation, Amazon Orders/Fulfillment Import, FBA Tracking, FIFO costing, FBA lot CSV/XLSX import, low-stock alerts, store-filtered Dashboard, Income/Expense, Profit/Loss, Cash Flow (Nakit Akışı), PPC modules.

## Architecture
- Frontend: React (craco) on port 3000, REACT_APP_BACKEND_URL from frontend/.env
- Backend: FastAPI (uvicorn) on 0.0.0.0:8001, all routes under /api
- DB: MongoDB via MONGO_URL / DB_NAME (backend/.env)
- Auth: JWT (JWT_SECRET), bcrypt password hashing, login lockout (LOGIN_MAX_ATTEMPTS / LOGIN_LOCKOUT_SECONDS)
- FX: Frankfurter v2 (FRANKFURTER_BASE_URL=https://api.frankfurter.dev/v2, FX_TIMEOUT_SECONDS)
- CORS: explicit origins only (CORS_ORIGINS), optional Origin alias middleware (CORS_ORIGIN_ALIASES)
- Webhook cron: WEBHOOK_CRON_SECRET (company monthly-close)

## User Personas
- Amazon seller (admin) tracking multi-marketplace P/L, cash flow, FBA stock, PPC

## Implemented / Restored (2026-10-11)
- Checked out branch emergent-latest-20261011 (commit 08894ae) exactly as-is; no source changes
- frontend/.env: restored current preview URL (af22bc1a-...); repo had stale amz-finance-suite URL
- backend/.env: added missing runtime vars — JWT_SECRET, WEBHOOK_CRON_SECRET, CORS_ORIGINS (explicit preview origin), CORS_ORIGIN_ALIASES={}, LOGIN_MAX_ATTEMPTS=5, LOGIN_LOCKOUT_SECONDS=900, FRANKFURTER_BASE_URL (v2), FX_TIMEOUT_SECONDS=10, ADMIN_EMAIL/ADMIN_PASSWORD defaults
- Dependencies: venv already satisfied pinned requirements; installed missing reportlab, xlrd (bumped 1.2.0→2.0.2), openpyxl; yarn install completed
- Verified: backend/frontend RUNNING; admin seeded; POST /api/auth/login 200; /api/auth/me 200; /api/dashboard/summary 200; /api/stores 200; browser login → Dashboard loads (empty state, fresh DB)

## Notes
- This pod has a FRESH MongoDB (no previous app data; old environment data not migrated)
- Broad regression suite intentionally not run per user instruction

## Backlog
- P0: none — ready for next development task
- P1/P2: per user's next feature requests
