import { useEffect, useState } from "react";
import api from "@/lib/api";
import { formatMoney } from "@/constants/marketplaces";
import { formatUsd } from "@/components/FxStatus";

const Row = ({ label, value, testId }) => (
  <div>
    <dt className="text-[11px] text-slate-500">{label}</dt>
    <dd className="text-xs font-medium text-slate-800 mt-0.5 break-all" data-testid={testId}>{value ?? "—"}</dd>
  </div>
);

/**
 * SellerFlash Cost Data — sipariş detayında yalnızca SellerFlash kaydı varsa görünür.
 * Referans alanlar finansal hesaplamaya iki kez dahil edilmez.
 */
export const SellerFlashCostSection = ({ orderId, marketplace, storeId }) => {
  const [state, setState] = useState({ loading: true, record: null });

  useEffect(() => {
    let active = true;
    setState({ loading: true, record: null });
    if (!orderId || !storeId || !marketplace) { setState({ loading: false, record: null }); return undefined; }
    api.get("/sellerflash/costs", { params: { store_id: storeId, marketplace, order_id: orderId } })
      .then(({ data }) => { if (active) setState({ loading: false, record: data?.found ? data.record : null }); })
      .catch(() => { if (active) setState({ loading: false, record: null }); });
    return () => { active = false; };
  }, [orderId, marketplace, storeId]);

  if (state.loading || !state.record) return null;
  const r = state.record;
  const money0 = v => (v == null ? "—" : formatMoney(v, r.currency || "USD"));

  return <div className="px-4 py-3 border-t border-slate-200 bg-indigo-50/50" data-testid={`sellerflash-section-${orderId}`}>
    <p className="text-xs font-semibold text-indigo-900 mb-2">SellerFlash Maliyet Verisi</p>
    <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      <Row label="Ürün Maliyeti" value={money0(r.product_cost)} testId={`sf-product-cost-${orderId}`} />
      <Row label="İlk Kargo Maliyeti" value={money0(r.initial_shipment_cost)} testId={`sf-shipping-cost-${orderId}`} />
      <Row label="Maliyet Kaynağı" value="SellerFlash" testId={`sf-cost-source-${orderId}`} />
      <Row label="Buyer Order Id" value={r.buyer_order_id || "—"} testId={`sf-buyer-order-${orderId}`} />
      <Row label="Buyer Durumu" value={r.buyer_order_status || "—"} />
      <Row label="Seller Durumu" value={r.seller_order_status || "—"} />
      <Row label="Seller İade (referans)" value={money0(r.seller_refund)} testId={`sf-seller-refund-${orderId}`} />
      <Row label="Buyer İade (referans)" value={money0(r.buyer_refund)} testId={`sf-buyer-refund-${orderId}`} />
      <Row label="SellerFlash Kâr (referans)" value={money0(r.profit)} testId={`sf-profit-${orderId}`} />
      <Row label="SellerFlash Kâr % (referans)" value={r.profit_rate == null ? "—" : `${r.profit_rate}%`} testId={`sf-profit-rate-${orderId}`} />
      <Row label="SF Sipariş Tarihi" value={r.order_date || r.order_date_raw || "—"} />
      <Row label="Teslim Bitiş" value={r.delivery_end_date || r.delivery_end_date_raw || "—"} />
      <Row label="USD Ürün+Kargo" value={`${formatUsd((r.product_cost_usd || 0) + (r.shipping_cost_usd || 0))}${r.fx?.rate ? ` · kur ${r.fx.rate}` : ""}`} testId={`sf-usd-costs-${orderId}`} />
      <Row label="İlk İçe Aktarma" value={(r.first_imported_at || "").slice(0, 10)} />
      <Row label="Son Güncelleme" value={(r.last_updated_at || "").slice(0, 10)} />
    </dl>
    {r.notes && <p className="text-[11px] text-slate-500 mt-2 break-words" data-testid={`sf-notes-${orderId}`}>Not: {r.notes}</p>}
  </div>;
};
