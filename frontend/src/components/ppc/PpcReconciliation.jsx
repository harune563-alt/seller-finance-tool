import { formatUsd } from "@/components/FxStatus";
import SectionLedger from "@/pages/SectionLedger";
import { StatusPill } from "./ppcFormat";

const MonthlyTable = ({ recon }) => (
  <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="ppc-recon-card">
    <div className="px-5 py-4 border-b border-slate-100">
      <h2 className="font-display text-lg font-bold text-slate-900">Amazon Payments Mutabakatı (Aylık)</h2>
      <p className="text-xs text-slate-500 mt-1">Finansal reklam gideri ile dağıtılan PPC harcamasının karşılaştırması. Fark, henüz dağıtılmamış harcamayı gösterir.</p>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[760px]">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
            <th className="px-5 py-3">Pazar</th><th className="px-3 py-3">Ay</th>
            <th className="px-3 py-3 text-right">Amazon Payments Reklam Gideri</th><th className="px-3 py-3 text-right">Dağıtılan PPC</th>
            <th className="px-3 py-3 text-right">Fark / Dağıtılmayan</th><th className="px-3 py-3">Durum</th>
          </tr>
        </thead>
        <tbody>
          {recon.length === 0 && <tr><td colSpan={6} className="px-5 py-8 text-center text-slate-400" data-testid="ppc-recon-empty">Mutabakat verisi yok</td></tr>}
          {recon.map((r, i) => (
            <tr key={`${r.marketplace}-${r.month}`} className="border-b border-slate-50" data-testid={`ppc-recon-${i}`}>
              <td className="px-5 py-2.5 text-slate-600">{r.marketplace || "—"}</td>
              <td className="px-3 py-2.5 font-semibold text-slate-800">{r.month}</td>
              <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(r.financial_ad_expense_usd)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num text-amber-700">{formatUsd(r.attributed_ad_spend_usd)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num text-slate-600" data-testid={`ppc-recon-diff-${i}`}>{formatUsd(r.unattributed_usd)}</td>
              <td className="px-3 py-2.5"><StatusPill status={r.status} label={r.status_label} testId={`ppc-recon-status-${i}`} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

const FinancialTable = ({ financial }) => (
  <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="ppc-financial-card">
    <div className="px-5 py-4 border-b border-slate-100 flex justify-between items-center">
      <h2 className="font-display text-lg font-bold text-slate-900">Finansal Reklam Giderleri</h2>
      <span className="text-sm font-mono-num text-rose-700" data-testid="ppc-financial-total">{formatUsd(financial.total_usd)}</span>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[760px]">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
            <th className="px-5 py-3">Tarih</th><th className="px-3 py-3">Pazar</th><th className="px-3 py-3">Amazon İşlem Türü</th>
            <th className="px-3 py-3">Kaynak</th><th className="px-3 py-3">Açıklama</th><th className="px-3 py-3 text-right">Tutar</th><th className="px-3 py-3 text-right">USD</th>
          </tr>
        </thead>
        <tbody>
          {(financial.rows || []).length === 0 && <tr><td colSpan={7} className="px-5 py-6 text-center text-slate-400" data-testid="ppc-financial-empty">Finansal reklam gideri yok</td></tr>}
          {(financial.rows || []).map(r => (
            <tr key={r.id} className="border-b border-slate-50" data-testid={`ppc-fin-row-${r.id}`}>
              <td className="px-5 py-2.5 font-mono-num">{r.date}</td>
              <td className="px-3 py-2.5">{r.marketplace}</td>
              <td className="px-3 py-2.5 text-xs">{r.raw_transaction_type || r.category}</td>
              <td className="px-3 py-2.5 text-xs text-slate-500">{r.source === "amazon_payments_csv" ? "Amazon Payments" : "Manuel"}</td>
              <td className="px-3 py-2.5 text-xs text-slate-500 max-w-[220px] truncate" title={r.description}>{r.description || "—"}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{Number(r.amount).toFixed(2)} {r.currency}</td>
              <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(r.amount_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

export const PpcReconciliation = ({ recon, financial }) => (
  <div className="space-y-6" data-testid="ppc-reconciliation">
    <MonthlyTable recon={recon} />
    <FinancialTable financial={financial} />
    <details className="rounded-2xl bg-white border border-slate-200 p-5" data-testid="ppc-manual-financial">
      <summary className="cursor-pointer font-display font-bold text-slate-900">Amazon Payments dışı manuel finansal reklam gideri</summary>
      <p className="text-xs text-amber-800 bg-amber-50 rounded-md p-3 my-4">Yalnızca Amazon Payments raporunda görünmeyen (ör. kartla ödenen) reklam giderleri için kullanın. Amazon Payments'ta zaten olan bir gideri burada tekrar girmeyin.</p>
      <SectionLedger section="ppc" title="PPC Reklam Takibi" subtitle="Finansal PPC kayıtları" embedded />
    </details>
  </div>
);
