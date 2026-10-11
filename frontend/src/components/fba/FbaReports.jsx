import { TableCard, THead, Td, EmptyRow, Metric, usd, pct, tone } from "@/components/fba/common";

const ASIN_COLS = [["ASIN"], ["Ürün"], ["SKU(lar)"], ["Sipariş", true], ["Adet", true], ["Amazon Net", true], ["Ürün Maliyeti", true],
  ["Inbound", true], ["Toplam FBA", true], ["Net Kâr/Zarar", true], ["Marj %", true],
  ["PPC Harcama", true], ["PPC Sonrası Net", true], ["PPC Sonrası Marj %", true], ["PPC Satış", true], ["ACoS %", true], ["ROAS", true]];

const roas = v => v == null ? "—" : `${Number(v).toFixed(2)}x`;

export const AsinReport = ({ rows, summary }) => (
  <div className="space-y-4" data-testid="fba-asin-report">
    {summary && <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="fba-general-report">
      <Metric label="Toplam FBA Siparişi" value={summary.orders} testId="fba-gen-orders" />
      <Metric label="Toplam Satılan Adet" value={summary.units_sold} testId="fba-gen-units" />
      <Metric label="Toplam Amazon Net" value={usd(summary.amazon_net_revenue_usd)} testId="fba-gen-revenue" />
      <Metric label="Toplam FIFO Ürün Maliyeti" value={usd(summary.product_cost_usd)} testId="fba-gen-product" />
      <Metric label="Toplam FIFO Inbound" value={usd(summary.inbound_cost_usd)} testId="fba-gen-inbound" />
      <Metric label="Toplam FBA Maliyeti" value={usd(summary.total_fba_cost_usd)} testId="fba-gen-total" />
      <Metric label="Toplam Net Kâr/Zarar" value={usd(summary.net_profit_usd)} valueClass={tone(summary.net_profit_usd)} testId="fba-gen-net" />
      <Metric label="Genel Kâr Marjı" value={pct(summary.margin_percent)} valueClass={tone(summary.margin_percent)} testId="fba-gen-margin" />
    </div>}
    <p className="text-xs text-slate-400" data-testid="fba-asin-ppc-note">
      PPC harcaması yalnızca ASIN analizinde kârı düşürür; finansal gider zaten Amazon Payments hesabında sayıldığı için genel giderlere ikinci kez eklenmez.
    </p>
    <TableCard testId="fba-asin-table">
      <THead cols={ASIN_COLS} />
      <tbody>
        {rows.length === 0 && <EmptyRow cols={ASIN_COLS.length} text="Bu filtrede FBA satışı yok" testId="fba-asin-empty" />}
        {rows.map(r => (
          <tr key={r.asin} className="border-b border-slate-100" data-testid={`fba-asin-row-${r.asin}`}>
            <Td className="font-mono text-xs">{r.asin}</Td>
            <Td className="max-w-56 truncate" title={r.product_name}>{r.product_name || "—"}</Td>
            <Td className="font-mono text-xs">{r.skus.join(", ") || "—"}</Td>
            <Td right>{r.orders}</Td>
            <Td right>{r.units_sold}</Td>
            <Td right>{usd(r.amazon_net_revenue_usd)}</Td>
            <Td right>{usd(r.product_cost_usd)}</Td>
            <Td right>{usd(r.inbound_cost_usd)}</Td>
            <Td right>{usd(r.total_fba_cost_usd)}</Td>
            <Td right className={tone(r.net_profit_usd)}>{usd(r.net_profit_usd)}</Td>
            <Td right className={tone(r.margin_percent)}>{pct(r.margin_percent)}</Td>
            <Td right className="text-rose-700" data-testid={`fba-asin-ppc-${r.asin}`}>{usd(r.ppc_spend_usd)}</Td>
            <Td right className={tone(r.net_profit_after_ppc_usd)} data-testid={`fba-asin-net-ppc-${r.asin}`}>{usd(r.net_profit_after_ppc_usd)}</Td>
            <Td right className={tone(r.margin_after_ppc_percent)}>{pct(r.margin_after_ppc_percent)}</Td>
            <Td right>{usd(r.ppc_sales_usd)}</Td>
            <Td right>{r.acos_percent == null ? "—" : pct(r.acos_percent)}</Td>
            <Td right>{roas(r.roas)}</Td>
          </tr>
        ))}
      </tbody>
    </TableCard>
  </div>
);

const INV_COLS = [["ASIN"], ["SKU"], ["Ürün"], ["Kalan Adet", true], ["Kalan Ürün Maliyeti", true], ["Kalan Inbound", true], ["Toplam Stok Değeri", true], ["Açık Lot", true]];

export const InventoryReport = ({ data }) => (
  <div className="space-y-4" data-testid="fba-inventory-report">
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      <Metric label="Toplam FBA Stok Değeri / Stoktaki Sermaye" value={usd(data?.totals?.inventory_value_usd)} testId="fba-inv-total-value" hint="Kalan adet × landed birim maliyet (açık lotlar). Gelir/Gider değildir." />
      <Metric label="Kalan Adet" value={data?.totals?.remaining_units ?? 0} testId="fba-inv-total-units" />
      <Metric label="Açık Lot" value={data?.totals?.open_lots ?? 0} testId="fba-inv-open-lots" />
    </div>
    <TableCard testId="fba-inventory-table">
      <THead cols={INV_COLS} />
      <tbody>
        {!data?.rows?.length && <EmptyRow cols={INV_COLS.length} text="Açık FBA stoğu yok" testId="fba-inventory-empty" />}
        {(data?.rows || []).map(r => (
          <tr key={`${r.asin}-${r.sku}`} className="border-b border-slate-100" data-testid={`fba-inv-row-${r.sku}`}>
            <Td className="font-mono text-xs">{r.asin || "—"}</Td>
            <Td className="font-mono text-xs">{r.sku}</Td>
            <Td className="max-w-56 truncate" title={r.product_name}>{r.product_name || "—"}</Td>
            <Td right>{r.remaining_units}</Td>
            <Td right>{usd(r.remaining_product_cost_usd)}</Td>
            <Td right>{usd(r.remaining_inbound_cost_usd)}</Td>
            <Td right className="font-semibold">{usd(r.remaining_value_usd)}</Td>
            <Td right>{r.open_lots}</Td>
          </tr>
        ))}
      </tbody>
    </TableCard>
  </div>
);
