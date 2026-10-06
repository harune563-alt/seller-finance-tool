import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

export const today = () => new Date().toISOString().slice(0, 10);
export const currencyName = c => c === "TRY" ? "TL" : c;
export const companyMoney = (amount, currency = "USD") => amount == null ? "—" : new Intl.NumberFormat("tr-TR", { style: "currency", currency, minimumFractionDigits: 2 }).format(amount);
export const apiError = err => typeof err.response?.data?.detail === "string" ? err.response.data.detail : "Alanları kontrol edin. Kayıt tamamlanamadı.";

export const SelectField = ({ label, value, onChange, options, id, placeholder = "Seçin", disabled }) => <div className="min-w-0"><Label htmlFor={id}>{label}</Label><Select value={value || ""} onValueChange={v => { if (v) onChange(v); }} disabled={disabled}><SelectTrigger id={id} data-testid={id} className="mt-2 bg-white"><SelectValue placeholder={placeholder} /></SelectTrigger><SelectContent data-testid={`${id}-options`}>{options.map(o => <SelectItem key={o.value} value={o.value} data-testid={`${id}-option-${o.value}`}>{o.label}</SelectItem>)}</SelectContent></Select></div>;

export const TextField = ({ label, id, value, onChange, type = "text", ...props }) => <div className="min-w-0"><Label htmlFor={id}>{label}</Label><Input id={id} data-testid={id} className="mt-2 bg-white min-w-0" value={value} onChange={e => onChange(e.target.value)} type={type} {...props} /></div>;

export const CurrencyField = props => <SelectField label="Para Birimi" options={[{ value: "USD", label: "USD · Dolar" }, { value: "TRY", label: "TL · Türk Lirası" }]} {...props} />;
export const FormError = ({ error, id }) => error ? <p role="alert" data-testid={id} className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md">{error}</p> : null;