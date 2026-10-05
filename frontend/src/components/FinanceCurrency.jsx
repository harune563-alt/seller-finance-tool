import { Select, SelectTrigger, SelectContent, SelectValue, SelectItem } from "@/components/ui/select";

export const FinanceCurrency = ({ summary, value, onChange, prefix }) => (
  <div className="flex items-center flex-wrap gap-3" data-testid={`${prefix}-currency-controls`}>
    <Select value={summary?.currency || value || ""} onValueChange={v => { if (v) onChange(v); }}>
      <SelectTrigger aria-label="Özet para birimi" className="w-28 bg-white" data-testid={`${prefix}-currency-select`}><SelectValue placeholder="Para birimi" /></SelectTrigger>
      <SelectContent data-testid={`${prefix}-currency-options`}>
        {(summary?.available_currencies || []).map(c => <SelectItem value={c} key={c} data-testid={`${prefix}-currency-${c.toLowerCase()}`}>{c}</SelectItem>)}
      </SelectContent>
    </Select>
    {(summary?.available_currencies?.length || 0) > 1 && <span className="text-xs text-slate-500" data-testid={`${prefix}-currency-note`}>Tutarlar para birimine göre ayrı; kur dönüşümü yok.</span>}
  </div>
);