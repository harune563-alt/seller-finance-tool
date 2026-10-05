import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export const PaymentReferenceDialog = ({ row, onClose, onSaved }) => {
  const [reference, setReference] = useState(row.payment_reference || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const save = async e => {
    e.preventDefault(); setSaving(true); setError("");
    try { await api.patch(`/payouts/${row.id}/reference`, { payment_reference: reference.trim() }); toast.success("Ödeme referansı güncellendi"); onSaved(); onClose(); }
    catch { setError("Ödeme referansı kaydedilemedi. Lütfen tekrar deneyin."); }
    finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}><DialogContent className="bg-white" data-testid="payout-reference-dialog">
    <DialogHeader><DialogTitle>Ödeme Referansı</DialogTitle><DialogDescription>{row.date} · {row.marketplace} · {row.category}</DialogDescription></DialogHeader>
    <form onSubmit={save} className="space-y-5"><div><Label htmlFor="edit-payout-reference">Referans</Label><Input id="edit-payout-reference" value={reference} maxLength={200} onChange={e => setReference(e.target.value)} data-testid="edit-payout-reference-input" className="mt-2" placeholder="Örn. TRANSFER-2026-001" /></div>
      {error && <p role="alert" className="text-sm text-rose-700" data-testid="payout-reference-error">{error}</p>}
      <DialogFooter><Button type="button" variant="outline" disabled={saving} onClick={onClose} data-testid="cancel-payout-reference">Vazgeç</Button><Button type="submit" disabled={saving} data-testid="save-payout-reference">{saving ? "Kaydediliyor…" : "Kaydet"}</Button></DialogFooter>
    </form>
  </DialogContent></Dialog>;
};