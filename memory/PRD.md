# Amazon Seller Suite — Ürün ve geliştirme durumu

## Orijinal gereksinimler
Amazon satıcıları için gelir, gider, Amazon ödemeleri, bakiye ve kâr-zarar takibi.
JWT e-posta/şifre, tek mağazada çoklu pazar (US, CA, MX, UK, DE, AU vb.),
çoklu para birimi, manuel giriş ve CSV aktarımı; Türkçe açık temalı finans paneli.

## Son kullanıcı talebi
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
- `/app/backend/amazon_csv.py`: Amazon CSV tür/tarih/tutar eşleme ve satır hataları.
- `/app/backend/auth_security.py`: MongoDB atomik hatalı giriş sayacı, 5 denemede 15dk kilit.
- `/app/backend/proxy_origin.py`: yalnızca ortamda tanımlı tam ingress Origin eşlemesi;
  wildcard veya forwarded-host tabanlı güven atlaması yok.
- `components/transactions/*`: manuel form, CSV, maliyet/iade düzenleme, sipariş grupları.
- `lib/orderFinance.js`: kuruş bazında sipariş toplama; `hooks/useFormMarketplace.js`: geçerli pazar seçimi.
- MongoDB: users, stores, transactions; payouts da type=payout transaction olarak tutulur.
- Mevcut JWT/çerez sözleşmesi korundu, hesap bazlı giriş kilidi eklendi; credentials `/app/memory/test_credentials.md`.
- Ortam URL ve DB bağlantıları .env üzerinden; API `/api` öneki kullanır.

## Muhasebe kuralları
- Order payments gelir; Refunds ve Service Fees gider (pozitif CSV ters kayıtları gideri azaltır).
- Gelir kaydına bağlı üç ek maliyet yalnızca bir kez giderlere eklenir.
- Refunds kaydındaki product_cost_recovery/shipping_cost_recovery gideri azaltır, yeni satış geliri değildir.
- Aynı siparişin eski maliyetleri tekrar yazılmaz; geri kazanımlar bunları azaltır.
- Sipariş marjı = net / Order payments tutarı × 100. Satış yoksa yüzde tanımsız (—).
- Net kâr = gelir − iadeler/hizmet ücretleri/diğer geçmiş giderler − üç ek maliyet + ürün/kargo geri kazanımları.
- CSV `total` satırdaki Amazon ücretlerinden sonraki tutardır; bileşen ücretleri yeniden düşülmez.
- Kişisel ürün/kargo/ekstra maliyet Amazon bakiyesinden düşmez. Bankada statülü payout gelir değildir.
- Dövizler kur olmadan toplanmaz; özetler seçili para birimine göre ayrılır.
- Geçmiş kategoriler/kayıtlar silinmez, eksik maliyet alanları sıfırdır.

## Durum ve öncelikler
### P0 — Tamamlandı ve doğrulandı (2026-10-05)
- Üç kategori, SKU kaldırma, maliyet giriş/düzenleme ve birleşik gelir/gider/net kâr özeti.
- Refunds ürün maliyeti geri kazanımı ve kargo claim geri ödemesi; sonradan düzenleme.
- Sipariş bazında tek satır, net tutar ve % marj, yeşil/kırmızı görünüm, detay açma ve alt kayıt silme.
- CSV önizleme, bilinmeyen/hatalı satır bildirimi ve tekrar yükleme koruması (5 MB / 10.000 satır sınırı).
- Mağaza/pazar seçim tutarlılığı, dropdown görünürlüğü ve açık validasyon.
- USD/CAD/EUR vb. ayrı özetler; Dashboard/Report/Payouts aynı muhasebe hesabını kullanır.
- 5 hatalı girişte hesap bazlı 15dk kilit, açık CORS origin ve ingress alias normalizasyonu.
- Backend 20/20 test, normal çerezli frontend akışları ve 320/768/1024/1440 görünüm doğrulaması.
### P1 — Sonraki
- ChatGPT entegrasyonu için kullanım/model/anahtar seçimi bekleniyor.
- Kullanıcının gerçek Amazon CSV örneğiyle bölgesel rapor uyumluluğunu doğrulama.
- Güncel döviz kurlarıyla isteğe bağlı konsolide rapor (bu kapsamda entegrasyon yok).
### P2 — Gelecek
- Özel kategori yönetimi (yeniden istenirse), bütçe/maliyet trend analizi.
- Amazon rezerv ve ödeme mutabakatı.
- Claim takibi: beklemede / onaylandı / ödendi; geri ödeme tarihine göre raporlama.
- Büyük veri hacmi için sunucu tarafında sipariş sayfalaması (mevcut işlem görünümü en fazla 10.000 kayıt çeker).

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