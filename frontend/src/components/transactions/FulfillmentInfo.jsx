const TYPE_CLS = {
  FBA: "bg-blue-100 text-blue-800",
  FBM: "bg-violet-100 text-violet-800",
  MIXED: "bg-amber-100 text-amber-800",
  UNKNOWN: "bg-slate-100 text-slate-600",
};

export const FulfillmentBadge = ({ type, testId }) => {
  if (!type) return null;
  const cls = TYPE_CLS[type] || TYPE_CLS.UNKNOWN;
  return <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold whitespace-nowrap ${cls}`}
    data-testid={testId}>{type}</span>;
};

/** Sipariş satırında kompakt özet: fulfillment rozeti + SKU / adet / ürün adı (salt görüntü). */
export const FulfillmentSummary = ({ fulfillmentType, items, testIdPrefix }) => {
  if (!fulfillmentType) return null;
  const list = items || [];
  return <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1" data-testid={`${testIdPrefix}-summary`}>
    <FulfillmentBadge type={fulfillmentType} testId={`${testIdPrefix}-badge`} />
    {list.slice(0, 2).map((it, i) => <span key={it.order_item_id || i}
      className="text-[11px] text-slate-600 truncate max-w-64" title={it.product_name || ""}
      data-testid={`${testIdPrefix}-item-${i}`}>
      <span className="font-mono">{it.sku || "—"}</span> × {it.quantity ?? "—"}
      {it.product_name ? ` · ${it.product_name}` : ""}
    </span>)}
    {list.length > 2 && <span className="text-[11px] text-slate-400" data-testid={`${testIdPrefix}-more`}>+{list.length - 2} kalem</span>}
  </div>;
};

/** Detay görünümü: saklanan kalem meta verisi (ASIN, Order Item ID, durumlar). Salt görüntüdür. */
export const FulfillmentItemsDetail = ({ fulfillmentType, items, testIdPrefix }) => {
  const list = items || [];
  if (!fulfillmentType && !list.length) return null;
  return <div className="px-4 py-3 border-t border-slate-200 bg-blue-50/40" data-testid={`${testIdPrefix}-detail`}>
    <div className="flex flex-wrap items-center gap-2 mb-2">
      <span className="text-xs font-semibold text-slate-700">Fulfillment (All Orders)</span>
      <FulfillmentBadge type={fulfillmentType || "UNKNOWN"} testId={`${testIdPrefix}-detail-badge`} />
      <span className="text-[11px] text-slate-400">Yalnızca meta veri — tutarları etkilemez</span>
    </div>
    {list.length > 0 && <div className="overflow-x-auto">
      <table className="w-full text-xs min-w-[720px]">
        <thead className="text-slate-500">
          <tr>{["SKU", "ASIN", "Order Item ID", "Quantity", "Product Name", "Order Status", "Item Status"].map(h =>
            <th key={h} className="text-left font-semibold px-2 py-1 whitespace-nowrap">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {list.map((it, i) => <tr key={it.order_item_id || i} data-testid={`${testIdPrefix}-detail-item-${i}`}>
            <td className="px-2 py-1.5 font-mono break-all" data-testid={`${testIdPrefix}-sku-${i}`}>{it.sku || "—"}</td>
            <td className="px-2 py-1.5 font-mono break-all" data-testid={`${testIdPrefix}-asin-${i}`}>{it.asin || "—"}</td>
            <td className="px-2 py-1.5 font-mono break-all" data-testid={`${testIdPrefix}-order-item-${i}`}>{it.order_item_id || "—"}</td>
            <td className="px-2 py-1.5 font-mono-num" data-testid={`${testIdPrefix}-qty-${i}`}>{it.quantity ?? "—"}</td>
            <td className="px-2 py-1.5 max-w-56 truncate" title={it.product_name || ""} data-testid={`${testIdPrefix}-name-${i}`}>{it.product_name || "—"}</td>
            <td className="px-2 py-1.5 whitespace-nowrap" data-testid={`${testIdPrefix}-order-status-${i}`}>{it.order_status || "—"}</td>
            <td className="px-2 py-1.5 whitespace-nowrap" data-testid={`${testIdPrefix}-item-status-${i}`}>{it.item_status || "—"}</td>
          </tr>)}
        </tbody>
      </table>
    </div>}
  </div>;
};
