import { Search, X, ChevronLeft, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

export const RecordFilters = ({ history, prefix, searchLabel, categoryLabel, options, unit }) => {
  const { filters, change, clear, loading, total, error } = history;
  const active = Object.values(filters).some(Boolean);
  return <section className="border-y border-slate-200 py-5 space-y-4" data-testid={`${prefix}-filters`} aria-label="İşlem listesi filtreleri">
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(210px,2fr)_1fr_1fr_1.25fr_auto] items-end gap-3">
      <div className="min-w-0"><Label htmlFor={`${prefix}-search`}>{searchLabel}</Label><div className="relative mt-2"><Search aria-hidden="true" className="absolute left-3 top-3 w-4 h-4 text-slate-400" /><Input id={`${prefix}-search`} type="search" autoComplete="off" maxLength={200} value={filters.search} onChange={e => change("search", e.target.value)} placeholder={searchLabel} data-testid={`${prefix}-search-input`} className="pl-9 bg-white" /></div></div>
      <div className="min-w-0"><Label htmlFor={`${prefix}-filter-start`}>Başlangıç</Label><Input id={`${prefix}-filter-start`} type="date" value={filters.start_date} onChange={e => change("start_date", e.target.value)} data-testid={`${prefix}-filter-start-date`} className="mt-2 bg-white min-w-0 w-full" /></div>
      <div className="min-w-0"><Label htmlFor={`${prefix}-filter-end`}>Bitiş</Label><Input id={`${prefix}-filter-end`} type="date" value={filters.end_date} onChange={e => change("end_date", e.target.value)} data-testid={`${prefix}-filter-end-date`} className="mt-2 bg-white min-w-0 w-full" /></div>
      <div className="min-w-0"><Label htmlFor={`${prefix}-filter-category`}>{categoryLabel}</Label><Select value={filters.category || "ALL"} onValueChange={v => { if (v) change("category", v === "ALL" ? "" : v); }}>
        <SelectTrigger id={`${prefix}-filter-category`} data-testid={`${prefix}-filter-category`} className="mt-2 bg-white"><SelectValue /></SelectTrigger><SelectContent data-testid={`${prefix}-filter-category-options`}><SelectItem value="ALL" data-testid={`${prefix}-filter-category-all`}>Tümü</SelectItem>{options.map((c, i) => <SelectItem value={c} key={c} data-testid={`${prefix}-filter-category-${i}`}>{c}</SelectItem>)}</SelectContent>
      </Select></div>
      <Button type="button" variant="outline" disabled={!active} onClick={clear} data-testid={`${prefix}-clear-filters`} className="bg-white"><X className="w-4 h-4 mr-1" />Temizle</Button>
    </div>
    <div className="flex flex-wrap gap-2 items-center justify-between text-xs text-slate-500"><span data-testid={`${prefix}-search-result-count`} role="status">{loading ? "Aranıyor…" : `${total} ${unit} bulundu`}</span><span data-testid={`${prefix}-filter-scope`}>Liste filtreleri · Genel toplamlar değişmez</span></div>
    {error && <div role="alert" data-testid={`${prefix}-filter-error`} className="text-sm text-rose-700">{error}{!history.invalidDate && <Button variant="ghost" size="sm" type="button" onClick={history.retry} data-testid={`${prefix}-filter-retry`}>Tekrar dene</Button>}</div>}
  </section>;
};

export const RecordPagination = ({ history, prefix }) => history.total_pages > 1 ? <nav aria-label="Kayıt sayfaları" className="flex flex-wrap items-center justify-between gap-3 py-3" data-testid={`${prefix}-pagination`}>
  <span className="text-xs text-slate-500" data-testid={`${prefix}-page-count`}>Sayfa {history.page} / {history.total_pages}</span>
  <div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={history.loading || history.page <= 1} onClick={() => history.setPage(history.page - 1)} data-testid={`${prefix}-previous-page`}><ChevronLeft className="w-4 h-4 mr-1" />Önceki</Button><Button type="button" variant="outline" size="sm" disabled={history.loading || history.page >= history.total_pages} onClick={() => history.setPage(history.page + 1)} data-testid={`${prefix}-next-page`}>Sonraki<ChevronRight className="w-4 h-4 ml-1" /></Button></div>
</nav> : null;