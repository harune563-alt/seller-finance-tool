import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatMoney } from "@/constants/marketplaces";

export const formatUsd = amount => amount == null ? "—" : formatMoney(amount, "USD");

export const FxStatus = ({ quote, loading, error, retry, prefix = "tx" }) => (
  <div className="text-xs text-slate-500 flex flex-wrap gap-2 items-center" data-testid={`${prefix}-fx-status`} aria-live="polite">
    {loading ? "Kur alınıyor…" : error ? <><span role="alert" className="text-rose-700" data-testid={`${prefix}-fx-error`}>{error}</span>{retry && <Button type="button" variant="ghost" size="sm" onClick={retry} data-testid={`${prefix}-fx-retry`}><RefreshCw className="w-3 h-3 mr-1" />Tekrar dene</Button>}</> : quote && <span data-testid={`${prefix}-fx-rate`}>1 {quote.base} = {Number(quote.rate).toFixed(6)} USD · Kur tarihi: {quote.rate_date}{quote.source !== "identity" && " · Frankfurter"}</span>}
  </div>
);

export const NativeBalances = ({ summary, field = "amazon_balance", prefix }) => (
  <div className="space-y-2 text-lg" data-testid={`${prefix}-native-balances`}>
    {!summary ? "…" : !summary.native_balances?.length ? "—" : summary.native_balances.map(row => <div key={row.currency} data-testid={`${prefix}-native-${row.currency.toLowerCase()}`}><span className="text-xs text-slate-500 mr-2">{row.currency}</span>{formatMoney(row[field], row.currency)}</div>)}
  </div>
);

export const MissingFxAlert = ({ summary, prefix }) => summary?.incomplete_count > 0 ? (
  <p role="alert" className="text-sm text-amber-800 bg-amber-50 border border-amber-200 p-3 rounded-md" data-testid={`${prefix}-missing-fx`}>
    {summary.incomplete_count} kaydın kuru alınamadı; eksik hesap göstermemek için USD toplamları bekletiliyor. Amazon bakiyeleri yerel para biriminde korunuyor. {summary.fx_errors?.[0]}
  </p>
) : null;