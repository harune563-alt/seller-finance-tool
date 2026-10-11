import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { MP_BY_CODE } from "@/constants/marketplaces";
import { CostStatusBadge, TableCard, THead, Td, EmptyRow, usd, pct, tone, unitUsd } from "@/components/fba/common";

const COLS = [["", false], ["Tarih"], ["Amazon Order ID"], ["Pazar"], ["ASIN"], ["SKU"], ["Ürün"], ["Adet", true], ["Amazon Net", true], ["FIFO Ürün", true],
  ["FIFO Inbound", true], ["Toplam FBA", true], ["Ekstra", true], ["Net Kâr/Zarar", true], ["Marj %", true], ["Maliyet Durumu"]];

const AllocationDetail = ({ order }) => (
  <tr data-testid={`fba-order-detail-${order.order_id}`}>
    <td colSpan={COLS.length} className="bg-slate-50 px-6 py-3">
      {order.allocations.length === 0 ? <p className="text-xs text-rose-700">Bu sipariş için henüz lot tahsisi yok. Eşleşen SKU için lot ekleyin.</p> : (
        <table className="text-xs min-w-[640px]">
          <thead className="text-slate-500"><tr>{["Lot", "SKU", "Order Item ID", "Adet", "Ürün / Birim", "Inbound / Birim", "Landed / Birim", "Tahsis Toplamı"].map(h => <th key={h} className="text-left font-semibold px-2 py-1">{h}</th>)}</tr></thead>
          <tbody>
            {order.allocations.map((a, i) => (
              <tr key={`${a.lot_id}-${i}`} data-testid={`fba-alloc-${order.order_id}-${i}`}>
                <td className="px-2 py-1 font-mono">{a.lot_code}</td>
                <td className="px-2 py-1 font-mono">{a.sku}</td>
                <td className="px-2 py-1 font-mono">{a.order_item_id || "—"}</td>
                <td className="px-2 py-1 font-mono-num" data-testid={`fba-alloc-qty-${order.order_id}-${i}`}>{a.quantity}</td>
                <td className="px-2 py-1 font-mono-num">{unitUsd(a.product_unit_cost_usd)}</td>
                <td className="px-2 py-1 font-mono-num">{unitUsd(a.inbound_unit_cost_usd)}</td>
                <td className="px-2 py-1 font-mono-num">{unitUsd(a.landed_unit_cost_usd)}</td>
                <td className="px-2 py-1 font-mono-num font-semibold">{usd(a.total_allocated_cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </td>
  </tr>
);

export const FbaOrdersTable = ({ orders }) => {
  const [open, setOpen] = useState({});
  return (
    <TableCard testId="fba-orders-table">
      <THead cols={COLS} />
      <tbody>
        {orders.length === 0 && <EmptyRow cols={COLS.length} text="Bu filtrede FBA siparişi yok. FBA siparişleri Amazon Orders / Fulfillment Import ile otomatik gelir." testId="fba-orders-empty" />}
        {orders.map(o => (
          <Fragment key={`${o.marketplace}-${o.order_id}`}>
            <tr className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => setOpen(s => ({ ...s, [o.order_id]: !s[o.order_id] }))} data-testid={`fba-order-row-${o.order_id}`}>
              <Td>{open[o.order_id] ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</Td>
              <Td>{o.date}</Td>
              <Td className="font-mono text-xs">{o.order_id}</Td>
              <Td>{MP_BY_CODE[o.marketplace]?.flag} {o.marketplace}</Td>
              <Td className="font-mono text-xs">{o.asin || "—"}</Td>
              <Td className="font-mono text-xs">{o.sku || "—"}</Td>
              <Td className="max-w-56 truncate" title={o.product_name}>{o.product_name || "—"}</Td>
              <Td right>{o.quantity}</Td>
              <Td right data-testid={`fba-order-net-rev-${o.order_id}`}>{usd(o.amazon_net_usd)}</Td>
              <Td right>{usd(o.product_cost_usd)}</Td>
              <Td right>{usd(o.inbound_cost_usd)}</Td>
              <Td right data-testid={`fba-order-total-cost-${o.order_id}`}>{usd(o.total_cost_usd)}</Td>
              <Td right>{usd(o.extra_cost_usd)}</Td>
              <Td right className={tone(o.net_profit_usd)} data-testid={`fba-order-profit-${o.order_id}`}>{o.net_profit_usd == null ? "Bekliyor" : usd(o.net_profit_usd)}</Td>
              <Td right className={tone(o.margin_percent)}>{pct(o.margin_percent)}</Td>
              <Td><CostStatusBadge status={o.cost_status} testId={`fba-order-status-${o.order_id}`} /></Td>
            </tr>
            {open[o.order_id] && <AllocationDetail order={o} />}
          </Fragment>
        ))}
      </tbody>
    </TableCard>
  );
};
