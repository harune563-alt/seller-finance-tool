import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { TextField, SelectField, FormError, apiError } from "./Fields";

export const PersonDialog = ({ person, onClose, onSaved }) => {
  const [form, setForm] = useState({ name: person?.name || "", role: person?.role || "partner", note: person?.note || "" });
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const change = (field, value) => setForm(f => ({ ...f, [field]: value }));
  const save = async e => { e.preventDefault(); if (!form.name.trim()) { setError("İsim girin."); return; } setBusy(true); setError(""); try { const { data } = person ? await api.patch(`/company/people/${person.id}`, form) : await api.post("/company/people", form); toast.success("Kişi kaydedildi"); onSaved(data); onClose(); } catch (e) { setError(apiError(e)); } finally { setBusy(false); } };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent data-testid="person-dialog" className="bg-white"><DialogHeader><DialogTitle>{person ? "Kişiyi Düzenle" : "Kişi Ekle"}</DialogTitle><DialogDescription>Ortak, yatırımcı veya şirketin çalıştığı kişi</DialogDescription></DialogHeader><form onSubmit={save} className="space-y-4">
    <TextField label="Ad / Ünvan" id="person-name" value={form.name} onChange={v => change("name", v)} maxLength={100} required />
    <SelectField label="Kişi Türü" id="person-role" value={form.role} onChange={v => change("role", v)} options={[{ value: "partner", label: "Şirket Ortağı" }, { value: "investor", label: "Dış Yatırımcı" }, { value: "contact", label: "Diğer Kişi" }]} />
    <TextField label="Not" id="person-note" value={form.note} onChange={v => change("note", v)} maxLength={500} />
    <FormError error={error} id="person-error" /><div className="flex justify-end"><Button disabled={busy} type="submit" data-testid="person-save">{busy ? "Kaydediliyor…" : "Kaydet"}</Button></div>
  </form></DialogContent></Dialog>;
};