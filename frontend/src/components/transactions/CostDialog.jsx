import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { COST_FIELDS, RECOVERY_FIELDS, formatMoney } from "@/constants/marketplaces";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { CostFields } from "./CostFields";
import { FxStatus, formatUsd } from "@/components/FxStatus";

export const CostDialog = ({ row, onClose, onSaved }) => {
  const refund = row.category === "Refunds";
  const fields = refund ? RECOVERY_FIELDS : COST_FIELDS;
  const [costs, setCosts] = useState(Object.fromEntries(fields.map(({ key }) => [key, row.usd_costs?.[key] ?? 0])));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const total = fields.reduce((sum, { key }) => sum + (Number(costs[key]) || 0), 0);
  const impact = row.amount_usd == null ? null : refund ? total - row.amount_usd : row.amount_usd - total;
  const save = async e => {
    e.preventDefault(); setError("");
    if (fields.some(({ key }) => !Number.isFinite(Number(costs[key])) || Number(costs[key]) < 0)) { setError("Tutarlar sıfır veya pozitif olmalıdır."); return; }
    setSaving(true);
    try {
      await api.patch(`/transactions/${row.id}/costs`, Object.fromEntries(fields.map(({ key }) => [key, Number(costs[key])])));
      toast.success("Maliyetler güncellendi"); onSaved(); onClose();
    } catch { setError("Maliyetler kaydedilemedi."); } finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}><DialogContent className="bg-white max-w-2xl" data-testid="cost-edit-dialog">
    <DialogHeader><DialogTitle>{refund ? "İade Geri Kazanımlarını Düzenle" : "Maliyetleri Düzenle"}</DialogTitle><DialogDescription>{row.order_id || row.category} · {row.date} · {formatMoney(row.amount, row.currency)}</DialogDescription></DialogHeader>
    <form onSubmit={save} noValidate className="space-y-6">
      <FxStatus quote={row.fx} prefix="edit" />
      {row.cost_currency !== "USD" && <p className="text-xs text-slate-500" data-testid="edit-legacy-cost-note">Eski {row.cost_currency} maliyetlerin USD karşılıkları gösteriliyor; yeni tutarlar USD olarak kaydedilecek.</p>}
      <CostFields value={costs} onChange={setCosts} currency="USD" prefix="edit" fields={fields} />
      <div className="flex justify-between gap-3 flex-wrap text-sm"><span>{refund ? "İadenin Kâr/Zarar Etkisi (USD)" : "Net Kâr (USD)"}</span><strong data-testid="edit-net-profit" className={impact < 0 ? "text-rose-600" : "text-emerald-700"}>{formatUsd(impact)}</strong></div>
      {error && <p role="alert" data-testid="edit-costs-error" className="text-sm text-rose-600">{error}</p>}
      <DialogFooter><Button type="button" variant="outline" disabled={saving} onClick={onClose} data-testid="cancel-cost-edit">Vazgeç</Button><Button type="submit" disabled={saving} data-testid="save-cost-edit">{saving ? "Kaydediliyor…" : "Maliyetleri Kaydet"}</Button></DialogFooter>
    </form>
  </DialogContent></Dialog>;
};