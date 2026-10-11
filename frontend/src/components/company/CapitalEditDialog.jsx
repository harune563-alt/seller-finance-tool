import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CurrencyField, TextField, SelectField, FormError, apiError } from "@/components/company/Fields";

export const CapitalEditDialog = ({ entry, people, storeId, onClose, onSaved }) => {
  const [form, setForm] = useState({ amount: entry.amount, date: entry.date, note: entry.note || "", person_id: entry.person_id, store_id: storeId, currency: entry.currency, direction: entry.direction });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const change = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const save = async event => {
    event.preventDefault(); setBusy(true); setError("");
    try { await api.put(`/company/capital/${entry.id}`, { ...form, amount: Number(form.amount) }); toast.success("Sermaye kaydı güncellendi"); onSaved(); onClose(); }
    catch (err) { setError(apiError(err)); } finally { setBusy(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent className="bg-white" data-testid="capital-edit-dialog"><DialogHeader><DialogTitle>Sermaye Kaydını Düzenle</DialogTitle><DialogDescription>{entry.person_name} · {entry.date}</DialogDescription></DialogHeader><form onSubmit={save} className="space-y-4"><div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><SelectField label="Kişi" id="edit-capital-person" value={form.person_id} onChange={v => change("person_id", v)} options={people.map(person => ({ value: person.id, label: person.name }))} /><SelectField label="Hareket" id="edit-capital-direction" value={form.direction} onChange={v => change("direction", v)} options={[{ value: "contribution", label: "Sermaye Girişi" }, { value: "withdrawal", label: "Sermaye İadesi" }]} /><CurrencyField id="edit-capital-currency" value={form.currency} onChange={v => change("currency", v)} /><TextField label="Tutar" id="edit-capital-amount" value={form.amount} onChange={v => change("amount", v)} type="number" min="0.01" step="0.01" required /><TextField label="Tarih" id="edit-capital-date" value={form.date} onChange={v => change("date", v)} type="date" required /><TextField label="Not" id="edit-capital-note" value={form.note} onChange={v => change("note", v)} maxLength={500} /></div><FormError error={error} id="edit-capital-error" /><DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={onClose}>Vazgeç</Button><Button type="submit" disabled={busy}>{busy ? "Kaydediliyor…" : "Güncelle"}</Button></DialogFooter></form></DialogContent></Dialog>;
};
