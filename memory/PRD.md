# Amazon Seller Suite — Ürün ve geliştirme durumu

## Orijinal gereksinimler
Amazon satıcıları için gelir, gider, Amazon ödemeleri, bakiye ve kâr-zarar takibi.
JWT e-posta/şifre, tek mağazada çoklu pazar (US, CA, MX, UK, DE, AU vb.),
çoklu para birimi, manuel giriş ve CSV aktarımı; Türkçe açık temalı finans paneli.

## Son kullanıcı talebi
### Yeni kapsam: Sermaye & Kasa, mağaza portföyü ve ayrıntılı Excel (2026-10-06, geliştirme/test aşaması)
- Kullanıcı: her mağazaya yatırılan **net sermayeye göre ayrı hisse**; dış yatırımcı sermayesi hisseye dahil,
  borç geri ödenebilir yükümlülük olup hisse oluşturmaz. Kişisel hesap değil **şirketin kişilerle borç/alacağı**.
- Kasa/sermaye/borç seçenekleri USD ve TL (API ISO TRY). Nakit dövizleri ayrı tutulur.
- Sermaye USD karşılaştırma temeliyle paylaştırılır; TL girişte eski FX servisi işlem tarihi kuru sabitler.
  İade tarihsel ortalama sermaye maliyetini azaltır, yeni kura göre yanlış pay değişimi olmaz.
- Önceki kapanmış aylar mağaza/ay başına tek USD **nakit dışı muhasebe kaydı**; zarar negatif.
  Sonraki tarihsel değişiklikler aynı kaydı revision history ile günceller. İçinde bulunulan ay kapanmaz.
- Gerçek nakit kasası, borç/tahsilatlar ve aylık kâr kapanışları ayrıdır. Aylık kapanış banka/Amazon transferi değildir.
- Dashboard'a global mağaza/tarih filtreli USD net kâr karşılaştırma paneli.
- Rapor'a tüm mağazalar/pazarlar/kaynak döviz seçimi, sipariş detayları ve XLSX indirme.
- Yeni routes: /company (Kasa), /company/capital, /company/debts, /company/closings.
- Backend: company/{models,common,capital,treasury,closings,routes}.py, reporting.py, report_workbook.py.
- API: /api/company/people, /capital, /debts, /debts/{id}/payments, /cash, /overview,
  /closings, /closings/run, /jobs; /api/portfolio/summary, /api/reports/orders, /api/reports/excel.
- Mongo: company_people, company_capital (atomik account + entries), company_debts (atomik kalan + payments),
  company_cash, company_closings (unique user/store/period), company_jobs (unique run_id).
- İdempotent finansal yazımlar UUID request_id alır; sermaye iadesi/borç ödemesi kalan tutarı aşamaz.
  Finansal şirket geçmişi olan mağaza silinemez (409) — geçmiş kayıtlar korunur.
- Planlı iş: .emergent/crons.yml monthly-profit-close, cron `0 3 * * *` UTC;
  POST /api/company/cron/monthly-close, backend/.env WEBHOOK_CRON_SECRET. Hızlı202 + durable job + BackgroundTasks.
  Günlük tekrar tüm kapalı ayları uzlaştırır (scheduler/background loop kurulmadı).
- Cron sözleşmesi doğrulandı: yetkisiz401, valid2020.12sn, duplicate202 duplicate=true, iş completed API'den doğrulandı.
- Excel: Özet, Pazar Yerleri, Siparişler, İşlem Detayları, Amazon Ödemeleri, Rapor Bilgisi;
  gerçek .xlsx, tarih aralığı dahil tüm hareketler; 50.000 üstünde açık413, sessiz kırpma yok; formül enjeksiyonu koruması.
- Python derleme/yarn build başarılı; ana ajan Excel dosyasını openpyxl ile açtı. Tam testing agent doğrulaması bekleniyor.

### Son güncelleme: işlem arama ve ödeme referansı (2026-10-05)
Gelir/Gider işlem kayıtlarında Order ID sorgusu; Amazon ödeme hareketlerinde filtreleme istendi.
Kullanıcı tarih aralığı, işlem türü/durum ve kısmi aramayı onayladı; ödeme tarafında
**Order ID değil, ayrı ödeme referansı** istedi.
- Gelir/Gider: Order ID kısmi/büyük-küçük harf duyarsız arama, başlangıç/bitiş ve kategori filtreleri.
- Payouts: payment_reference veya eski açıklama/not üzerinden arama; tarih ve ödeme durumu filtresi.
- Tarih/kategori bir siparişin en az bir aynı hareketinde eşleşir; siparişin bütün hareketleri korunur.
- Liste filtreleri genel P&L/bakiye özetini değiştirmez. Sipariş sonucu USD, ödeme/bakiye yerel döviz olarak kalır.
- Referans isteğe bağlı (max200), kırpılır, ödeme oluşturulurken veya sonradan düzenlenebilir; order_id ile ayrı alan.
- Sonuç sayısı, temizleme, hata/boş/yükleniyor durumları ve 20 grup/kayıtlık sunucu sayfalaması.

### Son güncelleme: otomatik kur ve USD maliyet muhasebesi (2026-10-05)
Kullanıcı CAD satış tutarı ve Amazon ödeme/bakiyesini CAD takip etmek; tüm pazarlarda
ürün/kargo/ekstra maliyetleri USD girmek ve nihai kâr/zararı USD hesaplamak istedi.
Kur seçimi sorusuna **“otomatik kur olabilir”** yanıtı verdi.
Yeni geri kazanım girişleri de USD; mevcut yerel maliyetler orijinali korunarak USD'ye türetilir.

### Önceki kapsam
Kategori seçenekleri şimdilik yalnızca `Order payments`, `Refunds`, `Service Fees`.
SKU alanını kaldır. Gelir formuna Ürün Maliyeti, Kargo Maliyeti, Ekstra Maliyet ekle.
Bu verilerden birleşik gelir, gider ve net kâr göster. Amazon Payments CSV raporları aktarılabilsin.
Önceki özel kategori yönetimi talebi bu üç sabit kategoriyle daraltıldı.

### Ek talep (2026-10-05)
- Refunds için geri alınan ürün maliyeti ve kargo claim iadesi tutarları.
- Aynı Order ID / mağaza / pazar / döviz işlemleri tek satırda birleşir.
- Sipariş bazında net kâr/zarar ve % marj; zarar açık kırmızı, kâr açık yeşil.
- ChatGPT model entegrasyonu istendi; kullanım (sohbet/rapor) ve anahtar/model soruları
  cevaplanmadı. Entegrasyon henüz yapılmadı; kullanıcının son odağı iade muhasebesi.

## Mimari
- React + Shadcn + Context API, FastAPI, Motor/MongoDB.
- `/app/backend/server.py`: auth, stores, transactions, dashboard, CSV endpoints.
- `/app/backend/finance.py`: Decimal tabanlı ortak kâr-zarar hesaplaması.
- `/app/backend/fx_service.py`: Frankfurter v2 tarihsel döviz/USD kuru, HTTP timeout/retry,
  MongoDB fx_rates önbelleği ve eşzamanlı istek kilitleri. Anahtar gerekmiyor.
- `/app/backend/usd_ledger.py`: immutable kur/snapshot, USD türetilmiş tutarlar ve yerel bakiye ayrımı.
- `/app/backend/ledger_search.py`: store/user/pazar/döviz kapsamında tam sipariş grubu arama ve ödeme sayfalama.
- `/app/frontend/src/hooks/useRecordSearch.js`: 300ms arama debounce, stale response koruması, filtre ve sayfa yönetimi.
- `components/RecordFilters.jsx`, `components/payouts/PayoutHistory.jsx`, `PaymentReferenceDialog.jsx`:
  iki listeye ortak filtre kontrolleri, ödeme referansı görünümü/düzenleme ve responsive ödeme geçmişi.
- `/app/frontend/src/hooks/useFxQuote.js`, `components/FxStatus.jsx`: canlı kur önizleme, kaynak/tarih,
  yerel bakiye listesi ve eksik kur uyarıları.
- `/app/backend/amazon_csv.py`: Amazon CSV tür/tarih/tutar eşleme ve satır hataları.
- `/app/backend/auth_security.py`: MongoDB atomik hatalı giriş sayacı, 5 denemede 15dk kilit.
- `/app/backend/proxy_origin.py`: yalnızca ortamda tanımlı tam ingress Origin eşlemesi;
  wildcard veya forwarded-host tabanlı güven atlaması yok.
- `components/transactions/*`: manuel form, CSV, maliyet/iade düzenleme, sipariş grupları.
- `lib/orderFinance.js`: kuruş bazında sipariş toplama; `hooks/useFormMarketplace.js`: geçerli pazar seçimi.
- MongoDB: users, stores, transactions; payouts da type=payout transaction olarak tutulur.
- Ek koleksiyon: fx_rates (source/base/quote/requested_date unique index).
- Transaction ek alanları: cost_currency, fx {base/quote/rate/requested_date/rate_date/source/fetched_at},
  amount_usd, usd_costs, fx_status. Legacy orijinaller okunurken değiştirilmez.
- GET `/api/fx/to-usd?currency=CAD&date=YYYY-MM-DD` authenticated; dış servise yalnızca tarih/döviz gider.
- GET `/api/transactions/search`: view=orders|payouts, store_id, marketplace, currency, search,
  category, start_date/end_date, outcome=all|profit|loss, page/page_size. Response items/total/page/page_size/total_pages.
- PATCH `/api/payouts/{id}/reference`: yalnızca kullanıcıya ait payout payment_reference alanını günceller.
- Summary yeni sözleşmesi: currency=USD, source_currency=ALL veya native filtre,
  native_balances[{currency,amazon_balance,payouts_received}], incomplete_count/fx_errors.
  Eski üst-seviye amazon_balance/payouts_received yerine yerel döviz dizisi kullanılır.
- Mevcut JWT/çerez sözleşmesi korundu, hesap bazlı giriş kilidi eklendi; credentials `/app/memory/test_credentials.md`.
- Ortam URL ve DB bağlantıları .env üzerinden; API `/api` öneki kullanır.

## Muhasebe kuralları
- Order payments gelir; Refunds ve Service Fees gider (pozitif CSV ters kayıtları gideri azaltır).
- Gelir kaydına bağlı üç ek maliyet yalnızca bir kez giderlere eklenir.
- Refunds kaydındaki product_cost_recovery/shipping_cost_recovery gideri azaltır, yeni satış geliri değildir.
- Aynı siparişin eski maliyetleri tekrar yazılmaz; geri kazanımlar bunları azaltır.
- Sipariş marjı = net / Order payments tutarı × 100. Satış yoksa yüzde tanımsız (—).
- Net kâr (USD) = gelirin USD karşılığı − iadeler/hizmet ücretleri/diğer geçmiş giderlerin USD karşılığı
  − USD maliyetler + USD ürün/kargo geri kazanımları. Her kayıt kendi işlem tarihindeki sabit kuru kullanır.
- CSV `total` satırdaki Amazon ücretlerinden sonraki tutardır; bileşen ücretleri yeniden düşülmez.
- Kişisel ürün/kargo/ekstra maliyet Amazon bakiyesinden düşmez. Bankada statülü payout gelir değildir.
- Gelir/iade/hizmet ücreti/ödeme tutarları pazarın yerel para biriminde saklanır.
- Tüm pazarlardaki yeni ürün/kargo/ekstra maliyet ve geri kazanım girişleri USD.
- Dövizler kur olmadan toplanmaz; P&L ve grafik/rapor/USD CSV çıktısı USD konsolide edilir.
  Kaynak döviz filtresi, hangi kayıtların alınacağını seçer; çıktı para birimini değiştirmez.
- Amazon bakiyesi ve Bankada ödemeleri döviz başına ayrı gösterilir; USD maliyetlerden etkilenmez.
- Eski maliyetin cost_currency alanı yoksa orijinal transaction.currency varsayılır;
  usd_costs ayrıca hesaplanır. USD olarak açıkça düzenlenince eski değerler original_costs arşivinde korunur.
- Kur kayda sabittir. Sonraki maliyet düzenlemeleri, okumalar veya kaynak kur değişiklikleri eski kârı yeniden değerlemez.
- Frankfurter referans kuru Amazon'un/bankanın gerçek ödeme kuru değildir. Kaynak ve kur tarihi görünür.
- Gelecek tarihli finans kaydı için kur uydurulmaz; kur alınamazsa kayıt/CSV aktarımı gerçekleşmez.
- Önceden kayıtlı kur çevrimdışı çalışır; eski eksik kurda P&L toplamları null (UI —), yerel bakiye yine kullanılabilir.
- Geçmiş kategoriler/kayıtlar silinmez, eksik maliyet alanları sıfırdır.

## Durum ve öncelikler
### P0 — FBA/PPC takibi + özel kategoriler (2026-10-07, tamamlandı)
- Yeni `transaction_categories` koleksiyonu: mağaza-bazlı CRUD, archived flag, ilk GET/POST'ta otomatik seed.
- Varsayılan seed: 3 Genel (Order payments / Refunds / Service Fees) + 5 FBA + 2 PPC (10 kategori).
- Transaction modeline opsiyonel alanlar: section (general/fba/ppc), campaign_name, ad_type, asin_sku, clicks, impressions, orders_count.
- validate_transaction: hem legacy hem custom kategorileri doğrular; PPC alanları yalnız section=ppc'de izinli; arşivli kategoriye yeni kayıt engeli.
- /api/categories CRUD (GET/POST/PUT/DELETE) — PUT ile isim değişimi tüm ilgili transactions'ı da cascade günceller.
- Yeni UI: /settings/categories (CRUD + arşivle), /fba (KPI+form+liste), /ppc (CTR/ACoS + günlük/tekil mod toggle + kampanya metrikleri).
- Transactions formu artık API'den gelen custom kategorileri de dropdown'da gösteriyor.
- Backend testleri: 20 yeni + 21 regresyon pytest tamam (iteration_7.json). Frontend testleri: tüm E2E akışlar geçti (iteration_8.json). Küçük bir useCategories.byType sentinel bug'ı testing agent tarafından bulundu ve düzeltildi.

### P0 — Tamamlandı ve doğrulandı (2026-10-05)
- Üç kategori, SKU kaldırma, maliyet giriş/düzenleme ve birleşik gelir/gider/net kâr özeti.
- Refunds ürün maliyeti geri kazanımı ve kargo claim geri ödemesi; sonradan düzenleme.
- Sipariş bazında tek satır, net tutar ve % marj, yeşil/kırmızı görünüm, detay açma ve alt kayıt silme.
- CSV önizleme, bilinmeyen/hatalı satır bildirimi ve tekrar yükleme koruması (5 MB / 10.000 satır sınırı).
- Mağaza/pazar seçim tutarlılığı, dropdown görünürlüğü ve açık validasyon.
- USD/CAD/EUR vb. ayrı özetler; Dashboard/Report/Payouts aynı muhasebe hesabını kullanır.
- 5 hatalı girişte hesap bazlı 15dk kilit, açık CORS origin ve ingress alias normalizasyonu.
- Backend 20/20 test, normal çerezli frontend akışları ve 320/768/1024/1440 görünüm doğrulaması.
### P0 — Otomatik USD muhasebe tamamlandı ve doğrulandı (2026-10-05)
- Gerçek Frankfurter v2 entegrasyonu, 12 para birimi, tarihsel/hafta sonu kur bilgisi, kalıcı snapshot/cache.
- CAD/native gelir ve iade; tüm pazarlarda USD maliyet/geri kazanım; USD sipariş marjı ve konsolide rapor.
- Dashboard/Transactions/Payouts orijinal CAD ve diğer döviz bakiyelerini ayrı gösteriyor.
- Maliyet düzenlemede USD değerleri, CSV ithalatta kur snapshot'ı ve idempotency korunuyor.
- Kur hatasında yanlış sıfır/1:1 dönüşüm yok; eski orijinaller korunuyor.
- 33/33 backend test + frontend akışları geçti. Key-spread uyarısı giderildi; silme ve 320px ek doğrulama geçti.
### P1 — Sonraki
- ChatGPT entegrasyonu için kullanım/model/anahtar seçimi bekleniyor.
- Kullanıcının gerçek Amazon CSV örneğiyle bölgesel rapor uyumluluğunu doğrulama.
- Kullanıcının gerçek CAD Amazon CSV'siyle kabul kontrolü.
- İsteğe bağlı kayıtlı filtreler (ör. bekleyen CAD ödemeleri / bu ay iade alan siparişler).
### P2 — Gelecek
- Özel kategori yönetimi (yeniden istenirse), bütçe/maliyet trend analizi.
- Amazon rezerv ve ödeme mutabakatı.
- Claim takibi: beklemede / onaylandı / ödendi; geri ödeme tarihine göre raporlama.
- Çok yüksek veri hacminde Mongo aggregation tabanlı arama/gruplama optimizasyonu (mevcut geçmiş görünümü
  artık sunucuda sayfalı ve 500/10.000 kayıt sınırından bağımsız; sipariş adayları sunucuda gruplandırılıyor).
- Amazon/banka gerçek ödeme kuru ile referans kur arasındaki gerçekleşmiş kur farkı takibi.

## Son tamamlanan çalışma — Faz A: Amazon import idempotency + tarih koruma (2026-10-08)
- Yeni `backend/reconciliation.py`: tarih-içermeyen stabil `event_fingerprint` (marketplace+order_id+type+sku+quantity+tutar+currency+description+satır sırası), satır sınıflandırma (new/existing_unchanged/existing_updated/date_changed/possible_duplicate/conflict), legacy backfill yardımcıları.
- `transactions` kayıtlarına eklemeli alanlar: `original_transaction_date` (değişmez), `latest_amazon_reported_date`, `first_seen_at`, `last_seen_at`, `date_changed`. Startup'ta idempotent backfill + eski CSV kayıtlarına event fingerprint backfill.
- `amazon_csv.py` parser'ı artık opsiyonel `sku`, `quantity`, `amazon_txn_id` alanlarını da çıkarıyor (yalnızca reconciliation için; mevcut akış değişmedi).
- Yeni koleksiyonlar: `amazon_date_history` (tarih değişikliği denetimi), `amazon_import_batches` (audit-only import geçmişi), `amazon_orders` (Marketplace+Order ID canonical sipariş kaydı, unique index).
- `/api/transactions/import` aynı sözleşmeyle staging/reconciliation uyguluyor: aynı dosya N kez → aynı toplamlar; örtüşen raporlarda mükerrer yok; Amazon tarihi değişirse orijinal tarih korunur, latest ayrı yazılır, history tutulur. GET `/api/transactions/import/history` ve `/api/transactions/date-history` eklendi.
- CSV import dialogu: reconciliation özeti (yeni/değişmemiş/tarih değişimi/güncellenen/olası mükerrer/çakışma/etkilenen sipariş), tarih değişimi uyarısı, satır durum rozetleri, "Son İçe Aktarmalar" listesi. Mevcut önizleme/commit UX'i korundu.
- Doğrulama: testing agent 25/25 backend testi geçti (TEST 1-2-3-4-6 senaryoları + finans regresyonu). MOCK yok.
- Sıradaki fazlar: Faz B (SellerFlash yükleyici — sol menüde ayrı sayfa, .csv/.xlsx/.xls[xlrd==1.2.0]), Faz C (staging UI genişletme, Unmatched SellerFlash, cost priority, kullanıcı başına Reporting Date Mode).

## Doğrulama geçmişi
- Önceki `/app/test_reports/iteration_1.json`: backend başarılı; UI akışlarında seçim/validasyon eksiklikleri.
- `/app/test_reports/iteration_2.json`: backend 11/11 regresyon geçti; frontend login doğrulandı.
  Radix form içindeki boş native-select değişimi sonrası pazar boşalması bulundu; türetilmiş
  geçerli pazar ve boş değişimleri filtreleme düzeltmesi uygulandı ve tarayıcıda doğrulandı.
- Aynı raporun auth deneme sınırı ve wildcard CORS bulguları için Mongo kilit ve açık origin eklendi.
- `/app/test_reports/iteration_3.json`: çekirdek finans akışları geçti; yeni güvenlik katmanında ingress IP
  değişimi ve Origin dönüşümü bulundu. Raporun açık bulguları sonraki self-testte çözüldü.
- Hesap sayacı `account:{email}` ile kararlı hale getirildi. Ingress iç alias'ı CORS öncesi
  sadece tanımlı public origin'e çevriliyor. Ortam değişirse `.env` CORS_ORIGINS ve CORS_ORIGIN_ALIASES
  yeni ortama göre güncellenmeli; varsayılan `{}` alias config doğrudan originli ortamlarda kullanılabilir.
- Son kanıt: `/app/test_reports/final_verification.json`, `/app/test_reports/pytest/final_backend_retest.xml` (20 geçti),
  `/app/test_reports/final-orders-verified.jpg`, `/app/test_reports/finance-build.log` (başarılı derleme).
- Gerçek çerezli tarayıcıda mağaza/işlem oluşturma, iade düzenleme, tek alt işlem silme, Dashboard/Report eşleşmesi geçti.
- Test örneği: 1000 gelir − (400 ürün +100 kargo +20 ekstra +1000 iade +20 ücret −400 ürün iadesi −80 kargo iadesi)
  = −60 net ve −%6. Kargo geri kazanımı100 yapılınca −40; ücret silinince −20.
- CSV ikinci önizlemede 3 tekrar, ekleme kapalı. Aynı ID DE/FR EUR altında iki ayrı satır;
  USD/CAD ayrı seçilir, farklı dövizler aynı görünümde toplanmaz. Boş Order ID kayıtları birleşmez.
- İşlemler, rapor, dashboard ve payout ekranlarında 320/768/1024/1440 genişliklerde sayfa taşması yok.
- Son konsolda Recharts boyut / Select kontrol uyarısı yok; login öncesi beklenen auth/me401 ve platform overlay abort kayıtları var.
- VERIFY_* ve iteration3 TEST_I3_* mağazaları temizlendi; önceki kullanıcı mağazaları korundu.
- API/entegrasyon MOCK yok. ChatGPT bağlı değil; henüz gerçek Amazon rapor dosyasıyla kullanıcı kabul testi yapılmadı.
- **En yeni doğrulama:** `/app/test_reports/iteration_4.json`,
  `/app/test_reports/pytest/pytest_results_iter4_backend_full.xml` (33/33), `/app/test_reports/fx-build.log`.
- `/app/backend/tests/test_fx_usd_workflows.py`: 10 gerçek API test; `/app/backend/tests/test_fx_failure_modes_unit.py`:
  3 izole birim testi yalnızca hata senaryolarını taklit eder. Uygulamadaki FX API gerçek, MOCK entegrasyon yok.
- 2025-01-15 gerçek kur: 1 CAD=0.69634 USD. 100CAD gelir−(20+5+3)USD maliyet=41.63USD net.
  20CAD iade, 12USD geri kazanım, 5CAD fee ile36.22USD net; 50CAD Bankada sonrası25CAD bakiye.
- Test ajanı CAD/native bakiye, USD maliyet, rapor/kur hatası/durum değişimi ve 390/768/1024/1440 ekranlarını geçti.
- Ana ajan son kontrolü: kayıtlı test store içindeki Service Fees UI üzerinden silindi;
  USD net kâr amount_usd kadar, CAD bakiye native amount kadar arttı; key-spread konsol uyarısı yok.
  Transactions/Dashboard/Payouts/Report320px taşma kontrolü geçti.
- Son UI kanıtı: `/root/.emergent/automation_output/20261005_163352/console_20261005_163352.log`;
  `/app/test_reports/fx-smoke.jpg`. `TEST_UI_FX_007cb7` geçici test mağazası temizlendi.
- Frankfurter config: FRANKFURTER_BASE_URL ve FX_TIMEOUT_SECONDS backend/.env; httpx dependency requirements'ta.

## Son tamamlanan çalışma — filtreler/referans (2026-10-05)
- Arama/kategori/tarih/pagination backend ve iki liste UI tamamlandı; tek bir sipariş asla sayfalara bölünmez.
- Kâr/zarar filtresi sayfalama öncesi tam USD sipariş sonucuna uygulanır; regex karakterleri literal aranır.
- Referans ekleme/düzenleme/temizleme, eski not araması, kullanıcı/pazar/mağaza ayrımı doğrulandı.
- Mağaza/pazar/kaynak para birimi değişince yeni liste filtreleri reset; kayıt düzenleme/silmede arama korunur.
- Payout geçmişi uzun referanslarda taşmayan responsive satırlara ayrıldı.
- Menüye tıklanamaması RCA: top-right Sonner başarı bildirimi marketplace düğmesini kapatıyordu.
  DOM elementFromPoint ile yeniden üretildi, App.js Toaster bottom-right'a alındı ve aktif bildirim varken tek tıklama doğrulandı.
- `/app/test_reports/iteration_5.json`: 11 yeni API testi +11 finans regresyon testi geçti. Agentın belirsiz bıraktığı
  pazar filtresi reseti ana ajan tarafından CA→ALL, currency ve store değişimlerinde doğrulandı.
- Son frontend self-test: ödeme arama+tarih+durum resetleri, menü erişimi ve iki sayfada320px taşma kontrolü geçti.
- 390/768/1024/1440 görüntüler testing agent tarafından geçti; final build uyarısız başarılı.
- Kanıtlar: `/app/test_reports/history_filters_final_verification.json`, `/app/test_reports/history-filters-build.log`,
  `/app/test_reports/pytest/pytest_results_iter5_backend.xml`, `/app/test_reports/pytest/pytest_results_iter5_regression.xml`,
  `/root/.emergent/automation_output/20261005_181730/console_20261005_181730.log`.
- TEST_FILTER_* test verileri temizlendi, mevcut kullanıcı kayıtlarına dokunulmadı. Oluşturulan regresyon test hesabı
  test_credentials.md dosyasında kayıtlı. Bu çalışma ek entegrasyon veya MOCK API içermez.

## Son tamamlanan çalışma — Cari hesap ekstresi ve kasa etkisi (2026-10-07)
- Yeni `company_current_entries` koleksiyonu: cari kişi, borç/alacak yönü, tutar, tarih, mağaza, açıklama, kasa etkisi (`none/in/out`) ve gerçekleşme durumu (`pending/completed`).
- Yeni API: `GET/POST/PUT/DELETE /api/company/current-accounts` ve toplu silme; kişi/para birimi/mağaza filtresi, idempotent request_id ve cari bazında toplam borç/alacak/net bakiye.
- Cari ekstre hareketlerinde tarih sıralı `balance_after` gösterimi; tamamlanmış kasa giriş/çıkışları Company Overview ledger ve kasa bakiyesine tek kaynaktan yansıyor.
- `Sermaye & Kasa → Borç & Alacak` varsayılan ekranı Cari Hesap Ekstresi oldu. Mevcut `company_debts` sistemi ve kayıtları silinmeden `Eski Borç/Alacak Kayıtları` sekmesinde korunuyor.
- Cari hareketli kişiler silinmeye karşı korunuyor. Yeni formda `Kasa etkisi yok / Kasaya giriş / Kasadan çıkış` ve `Bekliyor / Gerçekleşti` seçimleri bulunuyor.
- Backend: iteration_9 ile 21/21 test geçti; mevcut şirket finansı regresyonları 13/13 geçti. Frontend: cari oluşturma, kasa etkisi, filtre, düzenleme/silme, legacy sekmesi ve 390/768/1440 responsive kontrolleri geçti.


## Son tamamlanan çalışma — Cari vade, toplu işlemler, mutabakat ve raporlar (2026-10-07)
- Cari hareketlere `due_date` ve uygulama içi `due_status` eklendi: vadesi olan, vadesi yaklaşan (7 gün), vadesi geçen ve gerçekleşen rozetleri/filtreleri.
- `/api/company/current-accounts/bulk-complete` ve mevcut bulk-delete ile seçili hareketleri topluca gerçekleşti yapma veya silme; tekrar gerçekleşti çağrısı idempotent.
- Kasa ekranında Cari Kasa Mutabakatı bölümü: gerçekleşmiş cari giriş/çıkışları ayrı listeler, tarih/para birimi filtreleri ve döviz bazında giriş-çıkış-net dönem toplamları.
- Cari rapor endpointleri: `/api/company/current-accounts/report/excel` ve `/pdf`; kişi, para birimi ve tarih aralığı filtreli XLSX/PDF çıktıları. PDF fontu için güvenli fallback eklendi.
- Frontend Cari Ekstre: vade alanı, vade filtresi, toplu seçim, toplu gerçekleşti/sil, Excel/PDF indirme ve rapor filtreleri.
- Doğrulama: iteration_10 ile 14/14 yeni test + 8/8 cari regresyon geçti; son idempotency/fallback düzeltmesi sonrası 14/14 test tekrar geçti. Frontend tüm akışlar ve 390/768/1440 responsive kontrolleri geçti.


## Son tamamlanan çalışma — Runtime ortam restorasyonu ve doğrulama (2026-10-09, continuation)
- Yeni container'da eksik `backend/.env`, `frontend/.env` ve `memory/test_credentials.md` yeniden oluşturuldu: MONGO_URL (local MongoDB), DB_NAME=amazon_seller_suite, güvenli üretilmiş JWT/WEBHOOK_CRON secret'ları, auth kilidi (5 deneme/900sn), Frankfurter v2, explicit CORS origin = yeni preview URL (https://d475802d-d8ad-42a5-8683-782b6f0e8c23.preview.emergentagent.com), REACT_APP_BACKEND_URL aynı URL.
- Uygulama kaynak kodu, Amazon Payments CSV mantığı, idempotency/tarih koruma, SellerFlash maliyet import/reconciliation, auth, raporlar ve finans hesaplamaları DEĞİŞTİRİLMEDİ; hiçbir kullanıcı verisi değiştirilmedi.
- Doğrulama: backend testing agent 18/18 test geçti (servis durumu, MongoDB 19 koleksiyon, env, CORS eşleşmesi, login/session, dashboard/stores, TRY/USD FX, Amazon CSV idempotency + tarih koruma regresyonu, SellerFlash endpoint kayıtları). Frontend testing agent 9/9 geçti (login, dashboard, navigasyon: İşlemler/Amazon Ödemeleri/Mağazalar/Sermaye & Kasa/SellerFlash sayfası, CSV İçe Aktar dialog yapısı, 390px ve 1920px taşmasız responsive, konsol/CORS temiz, session kalıcılığı, logout→login yönlendirmesi).
- Test dosyaları: /app/continuation_runtime_test.py, /app/continuation_regression_test.py. MOCK yok. Açık sorun yok.
