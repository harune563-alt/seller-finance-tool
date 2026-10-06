import { useRef, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { TextField, FormError, today, companyMoney, currencyName, apiError } from "./Fields";

export const DebtPaymentDialog = ({ debt, onClose, onSaved }) => {
  const [form, setForm] = useState({ amount: "", date: today(), note: "" });
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const requestId = useRef(crypto.randomUUID());
  const change = (key, value) => { setForm(f => ({ ...f, [key]: value })); requestId.current = crypto.randomUUID(); };
  const submit = async e => { e.preventDefault(); setBusy(true); setError(""); try { await api.post(`/company/debts/${debt.id}/payments`, { ...form, amount: Number(form.amount), request_id: requestId.current }); toast.success("Hareket kaydedildi"); onSaved(); onClose(); } catch (e) { setError(apiError(e)); } finally { setBusy(false); } };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent className="bg-white" data-testid="debt-payment-dialog"><DialogHeader><DialogTitle>{debt.direction === "payable" ? "Borç Ödemesi" : "Alacak Tahsilatı"}</DialogTitle><DialogDescription>{debt.person_name} · Kalan {companyMoney(debt.remaining, debt.currency)}</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}>
    <TextField id="debt-payment-amount" label={`Tutar (${currencyName(debt.currency)})`} value={form.amount} onChange={v => change("amount", v)} type="number" min="0.01" step="0.01" max={debt.remaining} required />
    <TextField id="debt-payment-date" label="Tarih" value={form.date} onChange={v => change("date", v)} type="date" required />
    <TextField id="debt-payment-note" label="Not" value={form.note} onChange={v => change("note", v)} maxLength={500} />
    <FormError error={error} id="debt-payment-error" /><Button className="w-full" type="submit" disabled={busy} data-testid="debt-payment-submit">{busy ? "Kaydediliyor…" : "Kaydet"}</Button>
  </form></DialogContent></Dialog>;
};