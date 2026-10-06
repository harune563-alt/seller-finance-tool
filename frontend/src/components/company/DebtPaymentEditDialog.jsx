import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { TextField, FormError, apiError, companyMoney } from "@/components/company/Fields";

export const DebtPaymentEditDialog = ({ debt, payment, onClose, onSaved }) => {
  const [form, setForm] = useState({ amount: payment.amount, date: payment.date, note: payment.note || "" });
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const change = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const save = async event => { event.preventDefault(); setBusy(true); setError(""); try { await api.put(`/company/debts/${debt.id}/payments/${payment.id}`, { ...form, amount: Number(form.amount) }); toast.success("Ödeme/tahsilat güncellendi"); onSaved(); onClose(); } catch (err) { setError(apiError(err)); } finally { setBusy(false); } };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent className="bg-white" data-testid="debt-payment-edit-dialog"><DialogHeader><DialogTitle>Ödeme / Tahsilatı Düzenle</DialogTitle><DialogDescription>{debt.person_name} · Mevcut {companyMoney(payment.amount, debt.currency)}</DialogDescription></DialogHeader><form onSubmit={save} className="space-y-4"><TextField label="Tutar" id="edit-debt-payment-amount" value={form.amount} onChange={v => change("amount", v)} type="number" min="0.01" step="0.01" max={debt.remaining + payment.amount} required /><TextField label="Tarih" id="edit-debt-payment-date" value={form.date} onChange={v => change("date", v)} type="date" required /><TextField label="Not" id="edit-debt-payment-note" value={form.note} onChange={v => change("note", v)} maxLength={500} /><FormError error={error} id="edit-debt-payment-error" /><DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={onClose}>Vazgeç</Button><Button type="submit" disabled={busy}>{busy ? "Kaydediliyor…" : "Güncelle"}</Button></DialogFooter></form></DialogContent></Dialog>;
};
