import { formatUsd } from "@/components/FxStatus";
import { CostStatusBadge } from "@/components/fba/common";

const Cell = ({ label, value, testId, cls = "text-slate-800" }) => (
  <div><div className="text-[11px] text-slate-500">{label}</div><strong className={`text-xs font-mono-num ${cls}`} data-testid={testId}>{value}</strong></div>
);

/** FBA siparişi: mevcut finansal satırın FBA FIFO maliyet/kâr görünümü (yeni işlem oluşturmaz). */
export const FbaProfitStrip = ({ fba, groupId }) => {
  const net = fba.net, cls = net == null ? "text-slate-500" : net < 0 ? "text-rose-700" : "text-emerald-700";
  return (
    <div className="px-4 sm:px-5 pb-4 -mt-1" data-testid={`order-fba-${groupId}`}>
      <div className="rounded-md border border-blue-200 bg-white/70 px-3 py-2 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-[auto_repeat(7,minmax(0,1fr))_auto] gap-3 items-center">
        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-800 justify-self-start" data-testid={`order-fba-badge-${groupId}`}>FBA</span>
        <Cell label="Amazon Net" value={formatUsd(fba.amazonNet)} testId={`order-fba-amazon-net-${groupId}`} />
        <Cell label="FBA Ürün Maliyeti" value={formatUsd(fba.product)} testId={`order-fba-product-${groupId}`} />
        <Cell label="FBA Inbound" value={formatUsd(fba.inbound)} testId={`order-fba-inbound-${groupId}`} />
        <Cell label="Ekstra Maliyet" value={formatUsd(fba.extra)} testId={`order-fba-extra-${groupId}`} />
        <Cell label="Toplam Maliyet" value={formatUsd(fba.total)} testId={`order-fba-total-${groupId}`} />
        <Cell label="Net Kâr / Zarar" value={net == null ? "Maliyet bekliyor" : formatUsd(net)} cls={cls} testId={`order-fba-net-${groupId}`} />
        <Cell label="Kâr Marjı" value={fba.margin == null ? "—" : `${fba.margin > 0 ? "+" : ""}${fba.margin.toFixed(2)}%`} cls={cls} testId={`order-fba-margin-${groupId}`} />
        <div><div className="text-[11px] text-slate-500">Maliyet Kaynağı</div><CostStatusBadge status={fba.status} testId={`order-fba-cost-source-${groupId}`} /></div>
      </div>
    </div>
  );
};
