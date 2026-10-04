export const MARKETPLACES = [
  { code: "US", name: "Amerika (US)", currency: "USD", symbol: "$", flag: "🇺🇸" },
  { code: "CA", name: "Kanada (Canada)", currency: "CAD", symbol: "CA$", flag: "🇨🇦" },
  { code: "MX", name: "Meksika (Mexico)", currency: "MXN", symbol: "MX$", flag: "🇲🇽" },
  { code: "UK", name: "İngiltere (UK)", currency: "GBP", symbol: "£", flag: "🇬🇧" },
  { code: "DE", name: "Almanya (Germany)", currency: "EUR", symbol: "€", flag: "🇩🇪" },
  { code: "FR", name: "Fransa (France)", currency: "EUR", symbol: "€", flag: "🇫🇷" },
  { code: "IT", name: "İtalya (Italy)", currency: "EUR", symbol: "€", flag: "🇮🇹" },
  { code: "ES", name: "İspanya (Spain)", currency: "EUR", symbol: "€", flag: "🇪🇸" },
  { code: "NL", name: "Hollanda (NL)", currency: "EUR", symbol: "€", flag: "🇳🇱" },
  { code: "SE", name: "İsveç (Sweden)", currency: "SEK", symbol: "kr", flag: "🇸🇪" },
  { code: "PL", name: "Polonya (Poland)", currency: "PLN", symbol: "zł", flag: "🇵🇱" },
  { code: "AU", name: "Avustralya", currency: "AUD", symbol: "A$", flag: "🇦🇺" },
  { code: "JP", name: "Japonya", currency: "JPY", symbol: "¥", flag: "🇯🇵" },
  { code: "AE", name: "BAE (UAE)", currency: "AED", symbol: "د.إ", flag: "🇦🇪" },
  { code: "SA", name: "S. Arabistan", currency: "SAR", symbol: "﷼", flag: "🇸🇦" },
  { code: "TR", name: "Türkiye", currency: "TRY", symbol: "₺", flag: "🇹🇷" },
];

export const MP_BY_CODE = MARKETPLACES.reduce((acc, m) => ({ ...acc, [m.code]: m }), {});

export const INCOME_CATEGORIES = [
  "Ürün Satışı", "FBA Satış", "FBM Satış", "İade Düzeltme", "Promosyon", "Diğer Gelir",
];

export const EXPENSE_CATEGORIES = [
  "FBA Ücreti", "Reklam (PPC)", "Ürün Maliyeti (COGS)", "Kargo / Nakliye",
  "İade / Refund", "Depolama Ücreti", "Abonelik", "Vergi", "Diğer Gider",
];

export const formatMoney = (amount, currency = "USD") => {
  const num = Number(amount) || 0;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(num);
  } catch {
    return `${currency} ${num.toFixed(2)}`;
  }
};
