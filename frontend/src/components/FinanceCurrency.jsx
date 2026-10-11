import { Select, SelectTrigger, SelectContent, SelectValue, SelectItem } from "@/components/ui/select";

export const FinanceCurrency = ({ summary, value, onChange, prefix }) => (
  <div className="flex items-center flex-wrap gap-3" data-testid={`${prefix}-currency-controls`}>
    <Select value={summary?.source_currency || value || "ALL"} onValueChange={v => { if (v) onChange(v); }}>
      <SelectTrigger aria-label="İşlem para birimi filtresi" className="w-48 bg-white" data-testid={`${prefix}-currency-select`}><SelectValue placeholder="İşlem para birimi" /></SelectTrigger>
      <SelectContent data-testid={`${prefix}-currency-options`}>
        <SelectItem value="ALL" data-testid={`${prefix}-currency-all`}>Tüm Para Birimleri</SelectItem>
        {(summary?.available_currencies || []).map(c => <SelectItem value={c} key={c} data-testid={`${prefix}-currency-${c.toLowerCase()}`}>{c}</SelectItem>)}
      </SelectContent>
    </Select>
    <span className="text-xs text-slate-500" data-testid={`${prefix}-currency-note`}>Kâr/zarar: USD · Amazon bakiyesi: yerel para birimi</span>
  </div>
);