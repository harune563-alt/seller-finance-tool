import { COST_FIELDS, RECOVERY_FIELDS } from "@/constants/marketplaces";

const cents = value => Math.round(Number(value || 0) * 100);
export const groupOrders = rows => {
  const groups = new Map();
  for (const row of rows) {
    const orderId = (row.order_id || "").trim();
    const key = JSON.stringify([row.store_id, row.marketplace, row.currency, orderId || row.id]);
    if (!groups.has(key)) groups.set(key, { id: row.id, orderId, marketplace: row.marketplace, currency: row.currency, date: row.date, records: [], revenueCents: 0, expenseCents: 0, recoveredCents: 0, costsCents: 0 });
    const group = groups.get(key);
    group.records.push(row);
    group.date = group.date > row.date ? group.date : row.date;
    if (row.type === "income") {
      group.revenueCents += cents(row.amount);
      const costs = COST_FIELDS.reduce((sum, { key }) => sum + cents(row[key]), 0);
      group.costsCents += costs;
      group.expenseCents += costs;
    } else if (row.type === "expense") {
      group.expenseCents += cents(row.amount);
    }
    if (row.category === "Refunds") {
      const recovered = RECOVERY_FIELDS.reduce((sum, { key }) => sum + cents(row[key]), 0);
      group.recoveredCents += recovered;
      group.expenseCents -= recovered;
    }
  }
  return [...groups.values()].map(g => ({ ...g, revenue: g.revenueCents / 100, expenses: g.expenseCents / 100,
    recovered: g.recoveredCents / 100, costs: g.costsCents / 100,
    net: (g.revenueCents - g.expenseCents) / 100,
    margin: g.revenueCents > 0 ? (g.revenueCents - g.expenseCents) / g.revenueCents * 100 : null,
  })).sort((a, b) => b.date.localeCompare(a.date));
};