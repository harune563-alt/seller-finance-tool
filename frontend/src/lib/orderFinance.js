import { COST_FIELDS, RECOVERY_FIELDS } from "@/constants/marketplaces";

const cents = value => Math.round(Number(value || 0) * 100);
export const groupOrders = rows => {
  const groups = new Map();
  for (const row of rows) {
    const orderId = (row.order_id || "").trim();
    const key = JSON.stringify([row.store_id, row.marketplace, row.currency, orderId ? "order" : "single", orderId || row.id]);
    if (!groups.has(key)) groups.set(key, { id: row.id, orderId, marketplace: row.marketplace, currency: row.currency, date: row.date, records: [], revenueCents: 0, expenseCents: 0, recoveredCents: 0, costsCents: 0, incomplete: false });
    const group = groups.get(key);
    group.records.push(row);
    if (row.fx_status !== "ready") group.incomplete = true;
    group.date = group.date > row.date ? group.date : row.date;
    if (row.type === "income") {
      group.revenueCents += cents(row.amount_usd);
      const costs = COST_FIELDS.reduce((sum, { key }) => sum + cents(row.usd_costs?.[key]), 0);
      group.costsCents += costs;
      group.expenseCents += costs;
    } else if (row.type === "expense") {
      group.expenseCents += cents(row.amount_usd);
    }
    if (row.category === "Refunds") {
      const recovered = RECOVERY_FIELDS.reduce((sum, { key }) => sum + cents(row.usd_costs?.[key]), 0);
      group.recoveredCents += recovered;
      group.expenseCents -= recovered;
    }
  }
  return [...groups.values()].map(g => {
    const base = { ...g, revenue: g.incomplete ? null : g.revenueCents / 100, expenses: g.incomplete ? null : g.expenseCents / 100,
      recovered: g.incomplete ? null : g.recoveredCents / 100, costs: g.incomplete ? null : g.costsCents / 100,
      net: g.incomplete ? null : (g.revenueCents - g.expenseCents) / 100,
      margin: !g.incomplete && g.revenueCents > 0 ? (g.revenueCents - g.expenseCents) / g.revenueCents * 100 : null,
    };
    return g.records.some(r => r.fulfillment_type === "FBA") ? withFba(base) : base;
  }).sort((a, b) => b.date.localeCompare(a.date));
};

// FBA: Net = Amazon Net (Payments income − Payments expenses) − FIFO cost − Extra cost. SellerFlash/product costs ignored.
const withFba = g => {
  const fifo = g.records.find(r => r.fba_fifo)?.fba_fifo || null;
  const status = fifo?.cost_status || "missing";
  const income = g.records.filter(r => r.type === "income");
  const amazonNetCents = income.reduce((s, r) => s + cents(r.amount_usd), 0) - g.records.filter(r => r.type === "expense").reduce((s, r) => s + cents(r.amount_usd), 0);
  const extraCents = income.reduce((s, r) => s + cents(r.usd_costs?.extra_cost), 0);
  const productCents = cents(fifo?.product_cost_usd), inboundCents = cents(fifo?.inbound_cost_usd);
  const totalCents = productCents + inboundCents + extraCents;
  const netCents = g.incomplete || status !== "costed" ? null : amazonNetCents - totalCents;
  const fba = { status, amazonNet: g.incomplete ? null : amazonNetCents / 100, product: productCents / 100, inbound: inboundCents / 100,
    extra: extraCents / 100, total: totalCents / 100, net: netCents == null ? null : netCents / 100,
    margin: netCents == null || amazonNetCents === 0 ? null : netCents / amazonNetCents * 100 };
  return { ...g, fba, costs: g.incomplete ? null : totalCents / 100, expenses: g.incomplete ? null : (g.revenueCents - amazonNetCents + totalCents) / 100, net: fba.net, margin: fba.margin };
};