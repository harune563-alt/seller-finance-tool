import { Button } from "@/components/ui/button";
import { TextField, SelectField } from "@/components/company/Fields";
import { isoDate } from "@/components/reports/DateRange";
import { MP_BY_CODE } from "@/constants/marketplaces";

export const fbaRange = preset => {
  const now = new Date();
  if (preset === "today") return [isoDate(now), isoDate(now)];
  if (preset === "month") return [isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), isoDate(now)];
  if (preset === "last-month") return [isoDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)), isoDate(new Date(now.getFullYear(), now.getMonth(), 0))];
  if (preset === "30-days") { const s = new Date(); s.setDate(s.getDate() - 30); return [isoDate(s), isoDate(now)]; }
  return null;
};

const PRESETS = [["today", "Bugün"], ["month", "Bu Ay"], ["last-month", "Geçen Ay"], ["30-days", "Son 30 Gün"], ["custom", "Özel Aralık"]];

export const FbaFilters = ({ value, onChange, marketplaces }) => {
  const pick = preset => {
    const r = fbaRange(preset);
    onChange({ ...value, preset, ...(r ? { start: r[0], end: r[1] } : {}) });
  };
  return (
    <div className="flex flex-wrap items-end gap-3 border border-slate-200 bg-white rounded-xl p-4" data-testid="fba-filters">
      <div className="flex flex-wrap gap-2">
        {PRESETS.map(([id, label]) => (
          <Button key={id} size="sm" variant={value.preset === id ? "default" : "outline"} onClick={() => pick(id)} data-testid={`fba-preset-${id}`}>{label}</Button>
        ))}
      </div>
      {value.preset === "custom" && <>
        <TextField label="Başlangıç" id="fba-start-date" type="date" value={value.start} onChange={v => onChange({ ...value, start: v })} />
        <TextField label="Bitiş" id="fba-end-date" type="date" value={value.end} onChange={v => onChange({ ...value, end: v })} />
      </>}
      <div className="w-48">
        <SelectField label="Pazar Yeri" id="fba-marketplace-filter" value={value.marketplace} onChange={v => onChange({ ...value, marketplace: v })}
          options={[{ value: "ALL", label: "Tümü" }, ...marketplaces.map(c => ({ value: c, label: `${MP_BY_CODE[c]?.flag || ""} ${MP_BY_CODE[c]?.name || c}` }))]} />
      </div>
      <p className="text-xs text-slate-400 ml-auto" data-testid="fba-range-label">{value.start} → {value.end}</p>
    </div>
  );
};
