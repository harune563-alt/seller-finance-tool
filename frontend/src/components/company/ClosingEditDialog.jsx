import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { TextField, FormError, apiError } from "@/components/company/Fields";

export const ClosingEditDialog = ({ row, onClose, onSaved }) => {
  const [form, setForm] = useState({ revenue: row.revenue ?? "", expenses: row.expenses ?? "", net_profit: row.net_profit ?? "" });
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const change = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const save = async event => { event.preventDefault(); setBusy(true); setError(""); try { await api.put(`/company/closings/${row.id}`, Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value === "" ? null : Number(value)]))); toast.success("Kapanış kaydı güncellendi"); onSaved(); onClose(); } catch (err) { setError(apiError(err)); } finally { setBusy(false); } };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent className="bg-white" data-testid="closing-edit-dialog"><DialogHeader><DialogTitle>Kapanış Kaydını Düzenle</DialogTitle><DialogDescription>{row.store_name} · {row.period}</DialogDescription></DialogHeader><form onSubmit={save} className="space-y-4"><TextField label="Gelir (USD)" id="edit-closing-revenue" value={form.revenue} onChange={v => change("revenue", v)} type="number" step="0.01" /><TextField label="Gider (USD)" id="edit-closing-expenses" value={form.expenses} onChange={v => change("expenses", v)} type="number" step="0.01" /><TextField label="Net Kâr / Zarar (USD)" id="edit-closing-net" value={form.net_profit} onChange={v => change("net_profit", v)} type="number" step="0.01" /><FormError error={error} id="edit-closing-error" /><DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={onClose}>Vazgeç</Button><Button type="submit" disabled={busy}>{busy ? "Kaydediliyor…" : "Güncelle"}</Button></DialogFooter></form></DialogContent></Dialog>;
};
