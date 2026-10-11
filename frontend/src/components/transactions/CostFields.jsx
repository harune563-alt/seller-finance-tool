import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { COST_FIELDS } from "@/constants/marketplaces";

export const CostFields = ({ value, onChange, currency, prefix = "tx", fields = COST_FIELDS }) => (
  <div className={`grid grid-cols-1 ${fields.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3"} gap-4`} data-testid={`${prefix}-cost-fields`}>
    {fields.map(({ key, label }) => <div className="min-w-0" key={key}>
      <Label htmlFor={`${prefix}-${key}`} className="text-xs font-semibold text-slate-600">{label} ({currency})</Label>
      <Input id={`${prefix}-${key}`} type="number" min="0" max="1000000000000" step="0.01" placeholder="0.00" value={value[key] ?? ""}
        onChange={e => onChange({ ...value, [key]: e.target.value })} data-testid={`${prefix}-${key.replaceAll("_", "-")}-input`} className="mt-2 font-mono-num bg-white" />
    </div>)}
  </div>
);