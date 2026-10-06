import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const BulkEditDialog = ({ title, description, endpoint, ids, fields, onClose, onSaved }) => {
  const [values, setValues] = useState({});
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const change = (key, value) => { setValues(current => ({ ...current, [key]: value })); setError(""); };
  const changes = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== "" && value != null));
  const submitPreview = event => { event.preventDefault(); if (!Object.keys(changes).length) { setError("En az bir alan doldurun."); return; } setPreview(true); };
  const save = async () => {
    setSaving(true); setError("");
    try { await api.post(endpoint, { ids, changes }); toast.success(`${ids.length} kayıt güncellendi`); onSaved(); onClose(); }
    catch (err) { setError(err.response?.data?.detail || "Toplu güncelleme yapılamadı."); setPreview(false); }
    finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}><DialogContent className="bg-white max-w-3xl" data-testid="bulk-edit-dialog"><DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{description} · {ids.length} kayıt seçildi</DialogDescription></DialogHeader>
    {!preview ? <form onSubmit={submitPreview} className="space-y-5 max-h-[65vh] overflow-y-auto pr-1"><div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{fields.map(field => <div key={field.key} className={field.type === "textarea" ? "sm:col-span-2" : ""}><Label htmlFor={`bulk-${field.key}`}>{field.label}</Label>{field.type === "select" ? <Select value={values[field.key] || ""} onValueChange={value => change(field.key, value)}><SelectTrigger id={`bulk-${field.key}`} className="mt-2" data-testid={`bulk-${field.key}`}><SelectValue placeholder="Değiştirme" /></SelectTrigger><SelectContent className="bg-white"><SelectItem value="__unchanged__" disabled>Değiştirme</SelectItem>{field.options.map(option => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent></Select> : field.type === "checkbox" ? <label className="flex items-center gap-2 mt-3"><Checkbox id={`bulk-${field.key}`} checked={values[field.key] === true} onCheckedChange={value => change(field.key, value === true)} /><span className="text-sm">{field.checkboxLabel}</span></label> : <Input id={`bulk-${field.key}`} type={field.type || "text"} value={values[field.key] ?? ""} onChange={event => change(field.key, event.target.value)} placeholder="Değiştirme" min={field.type === "number" ? "0" : undefined} step={field.type === "number" ? "0.01" : undefined} className="mt-2" data-testid={`bulk-${field.key}`} />}</div>)}</div>{error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md">{error}</p>}<p className="text-xs text-slate-500">Boş bırakılan alanlar korunur. Para birimi değişikliğinde ilgili finans kuralları yeniden doğrulanır.</p><DialogFooter><Button type="button" variant="outline" disabled={saving} onClick={onClose}>Vazgeç</Button><Button type="submit" disabled={saving}>Önizlemeyi Gör</Button></DialogFooter></form> : <div className="space-y-5"><div className="rounded-lg border border-amber-200 bg-amber-50 p-4"><p className="font-semibold text-amber-900">{ids.length} kayıt aşağıdaki alanlarla güncellenecek:</p><dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">{Object.entries(changes).map(([key, value]) => <div key={key} className="flex justify-between gap-3"><dt className="text-amber-800">{fields.find(field => field.key === key)?.label || key}</dt><dd className="font-semibold break-all">{String(value)}</dd></div>)}</dl></div>{error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md">{error}</p>}<DialogFooter><Button type="button" variant="outline" disabled={saving} onClick={() => setPreview(false)}>Geri Dön</Button><Button type="button" disabled={saving} onClick={save} data-testid="confirm-bulk-edit">{saving ? "Güncelleniyor…" : "Onayla ve Güncelle"}</Button></DialogFooter></div>}
  </DialogContent></Dialog>;
};
