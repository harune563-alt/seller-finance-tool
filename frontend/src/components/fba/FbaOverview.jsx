import { Metric, usd, pct, tone } from "@/components/fba/common";

export const FbaOverview = ({ summary }) => {
  if (!summary) return null;
  const s = summary;
  return (
    <div className="space-y-3" data-testid="fba-overview">
      {s.pending_cost_orders > 0 && (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3" data-testid="fba-pending-warning">
          {s.pending_cost_orders} siparişte FBA maliyeti eksik (Missing FBA Cost). Bu siparişler için kâr eksik/bekliyor; eşleşen lot eklendiğinde FIFO maliyeti otomatik atanır.
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <Metric label="FBA Siparişleri" value={s.orders} testId="fba-kpi-orders" />
        <Metric label="Satılan Adet" value={s.units_sold} testId="fba-kpi-units" />
        <Metric label="Amazon Net Gelir" value={usd(s.amazon_net_revenue_usd)} testId="fba-kpi-revenue" />
        <Metric label="Gerçekleşen Ürün Maliyeti" value={usd(s.product_cost_usd)} testId="fba-kpi-product-cost" />
        <Metric label="Gerçekleşen Inbound Maliyeti" value={usd(s.inbound_cost_usd)} testId="fba-kpi-inbound-cost" />
        <Metric label="Toplam Gerçekleşen FBA Maliyeti" value={usd(s.total_fba_cost_usd)} testId="fba-kpi-total-cost" hint={s.extra_cost_usd ? `+ Ekstra maliyet ${usd(s.extra_cost_usd)}` : null} />
        <Metric label="Net FBA Kâr" value={usd(s.net_profit_usd)} valueClass={tone(s.net_profit_usd)} testId="fba-kpi-net-profit" hint={s.pending_cost_orders ? "Eksik maliyet nedeniyle kesin değil" : null} />
        <Metric label="Kâr Marjı" value={pct(s.margin_percent)} valueClass={tone(s.margin_percent)} testId="fba-kpi-margin" />
        <Metric label="Mevcut Stok Adedi" value={s.inventory_units} testId="fba-kpi-inventory-units" />
        <Metric label="Mevcut Stok Değeri" value={usd(s.inventory_value_usd)} testId="fba-kpi-inventory-value" hint="Varlık — gider değildir" />
      </div>
    </div>
  );
};
