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
- 2026-10-11 Login fix: user preview is the alias origin https://fba-finance-hub.preview.emergentagent.com; it was missing from backend CORS_ORIGINS → browser blocked the login preflight (no request ever reached backend). Env-only fix: added alias origin to CORS_ORIGINS, restarted backend. Verified in real browser on the alias URL: login 200 → Dashboard loads.

## Unified PPC Module (2026-10-11)
- /ppc single page (nav "PPC Reklam"; /ppc-attribution redirects). Tabs: Genel Bakış, Kayıtları, ASIN/Kampanya Dağılımı, Amazon Payments Mutabakatı
- Merged old PpcAttribution page + SectionLedger(ppc) (legacy manual financial ad ledger kept embedded in Mutabakat tab with warning)
- Attribution fields added: ppc_category, ad_type, notes; ASIN→SKU lookup from fba_lots (/api/ppc/asin-lookup); PPC report CSV/XLSX import (/api/ppc/attributions/import-file, idempotent upsert)
- Statuses: reconciled, partially_reconciled, pending_match, financial_only, ppc_only, unmatched; overview adds allocated/unallocated, clicks, impressions, orders, CTR, ASIN/campaign filters
- Amazon Payments CSV: normalized type matching, advertising keywords → category "Advertising" / classification PPC_ADVERTISING_EXPENSE, raw_transaction_type kept, no Order ID needed; unknown types → diagnostics.review_required (not booked, rest of file continues)
- Focused tests: backend/tests/test_ppc_unified.py 8/8 pass

## FBA Deletion Consistency Fix (2026-10-11)
- Root cause: DELETE /api/transactions/{id} and bulk-delete removed transactions but never reversed FIFO allocations → lots stayed depleted, Manual FBA Sale saw insufficient stock after order disappeared
- fba.py: reverse_fba_order (restores quantities to original lots, marks allocations reversed, audits) + cleanup_deleted_fba_sales (reverses when no FBA-fulfillment tx remains on the order); reallocate_order refactored to reuse it
- server.py: single + bulk transaction delete now trigger cleanup for any deleted row with an order_id
- New DELETE /api/fba/lots/{lot_id}: 409 "Bu lot aktif FBA satışlarında kullanılıyor..." when active allocations exist; deletes normally otherwise
- Cash flow purchase/inbound records untouched; lots never auto-deleted on sale deletion
- Tests: iteration_14 4/4 pass (main scenario, partial-order, lot guard, bulk delete)

## FBA Takibi UI Düzeltmesi (2026-10-11)
- Manuel FBA Kayıtları sekmesindeki ikinci (alt) manuel giriş formu kaldırıldı; yalnızca kayıt listesi/özet kaldı (SectionLedger'a showForm prop'u eklendi, varsayılan true)
- Kategori alanı üstteki Manuel FBA Satışı formuna taşındı (FBA bölüm kategorileri, varsayılan "FBA Satış"); backend ManualSaleIn artık category + currency kabul ediyor
- Satış Tutarı alanı CAD: label/placeholder CAD, payload currency="CAD"; backend attach_usd ile USD'ye çeviriyor (doğrulandı: CAD 41.00 → USD 28.81)
- CAD tutarı USD FIFO maliyetiyle karışmasın diye formdaki "Tahmini Net Kâr" satırı kaldırıldı

## Backlog
- P0: none — ready for next development task
- P1/P2: per user's next feature requests

## Import (2026-10-12)
- Branch emergent-latest-20261011 (HEAD f7147b1) restored as-is; backend/.env + frontend/.env recreated for preview https://2574333c-5d19-403c-ac30-f56cb9acfdb3.preview.emergentagent.com (new JWT/WEBHOOK secrets, fresh DB). Browser login + Dashboard verified.
