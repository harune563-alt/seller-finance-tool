import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CurrencyField, TextField, SelectField, FormError, apiError } from "@/components/company/Fields";

export const CashEditDialog = ({ row, onClose, onSaved }) => {
  const [form, setForm] = useState({ amount: Math.abs(row.amount), date: row.date, note: row.note || "", currency: row.currency, direction: row.amount < 0 ? "out" : "in" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const change = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const save = async event => { event.preventDefault(); setBusy(true); setError(""); try { await api.put(`/company/cash/${row.id}`, { ...form, amount: Number(form.amount) }); toast.success("Kasa hareketi güncellendi"); onSaved(); onClose(); } catch (err) { setError(apiError(err)); } finally { setBusy(false); } };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent className="bg-white" data-testid="cash-edit-dialog"><DialogHeader><DialogTitle>Kasa Hareketini Düzenle</DialogTitle><DialogDescription>{row.date} · {row.currency}</DialogDescription></DialogHeader><form onSubmit={save} className="space-y-4"><div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><CurrencyField id="edit-cash-currency" value={form.currency} onChange={v => change("currency", v)} /><SelectField label="Hareket" id="edit-cash-direction" value={form.direction} onChange={v => change("direction", v)} options={[{ value: "in", label: "Nakit Girişi" }, { value: "out", label: "Nakit Çıkışı" }]} /><TextField label="Tutar" id="edit-cash-amount" value={form.amount} onChange={v => change("amount", v)} type="number" min="0.01" step="0.01" required /><TextField label="Tarih" id="edit-cash-date" value={form.date} onChange={v => change("date", v)} type="date" required /><TextField label="Açıklama" id="edit-cash-note" value={form.note} onChange={v => change("note", v)} maxLength={500} /></div><FormError error={error} id="edit-cash-error" /><DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={onClose}>Vazgeç</Button><Button type="submit" disabled={busy}>{busy ? "Kaydediliyor…" : "Güncelle"}</Button></DialogFooter></form></DialogContent></Dialog>;
};
