import { Button } from "@/components/ui/button";
import { TextField } from "@/components/company/Fields";

export const isoDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const datePreset = type => {
  const end = new Date(), start = new Date();
  if (type === "month") start.setDate(1);
  if (type === "year") { start.setMonth(0); start.setDate(1); }
  if (type === "30-days") start.setDate(start.getDate() - 30);
  if (type === "90-days") start.setDate(start.getDate() - 90);
  return [isoDate(start), isoDate(end)];
};
export const DateRange = ({ start, end, onChange, prefix }) => <div className="flex flex-wrap gap-3 items-end" data-testid={`${prefix}-date-controls`}>
  <TextField label="Başlangıç" id={`${prefix}-start-date`} type="date" value={start} onChange={v => onChange(v, end)} />
  <TextField label="Bitiş" id={`${prefix}-end-date`} type="date" value={end} onChange={v => onChange(start, v)} />
  <div className="flex flex-wrap gap-2">{[["month", "Bu Ay"], ["30-days", "Son 30 Gün"], ["90-days", "Son 90 Gün"], ["year", "Bu Yıl"]].map(([id, label]) => <Button key={id} variant="outline" size="sm" onClick={() => onChange(...datePreset(id))} data-testid={`${prefix}-preset-${id}`}>{label}</Button>)}</div>
</div>;