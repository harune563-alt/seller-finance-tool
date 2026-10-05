"""Shared P&L arithmetic; a transaction's attached costs are counted exactly once."""
from decimal import Decimal, ROUND_HALF_UP

COST_FIELDS = {"product_cost": "Ürün Maliyeti", "shipping_cost": "Kargo Maliyeti", "extra_cost": "Ekstra Maliyet"}
RECOVERY_FIELDS = {"product_cost_recovery": "Ürün Maliyeti İadesi", "shipping_cost_recovery": "Kargo Ücreti İadesi (Claim)"}
CATEGORIES = {"Order payments": "income", "Refunds": "expense", "Service Fees": "expense"}
EXTERNAL_CATEGORIES = {"Ürün Maliyeti (COGS)", "Kargo / Nakliye", *COST_FIELDS.values()}


def money(value=0):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def summarize(transactions):
    revenue = expenses = amazon_expenses = payouts = Decimal(0)
    costs = {key: Decimal(0) for key in COST_FIELDS}
    recoveries = {key: Decimal(0) for key in RECOVERY_FIELDS}
    categories, marketplaces, trend = {}, {}, {}
    for tx in transactions:
        amount = money(tx["amount"])
        income = amount if tx["type"] == "income" else Decimal(0)
        expense = amount if tx["type"] == "expense" else Decimal(0)
        if tx["type"] == "expense":
            categories[tx["category"]] = categories.get(tx["category"], Decimal(0)) + amount
            if tx["category"] not in EXTERNAL_CATEGORIES:
                amazon_expenses += amount
        if tx["type"] == "income":
            for key, label in COST_FIELDS.items():
                value = money(tx.get(key, 0))
                costs[key] += value
                expense += value
                if value:
                    categories[label] = categories.get(label, Decimal(0)) + value
        if tx["category"] == "Refunds":
            for key, label in RECOVERY_FIELDS.items():
                value = money(tx.get(key, 0))
                recoveries[key] += value
                expense -= value
                if value:
                    categories[label] = categories.get(label, Decimal(0)) - value
        if tx["type"] == "payout" and tx["category"] == "Bankada":
            payouts += amount
        revenue += income
        expenses += expense
        for mapping, key in ((marketplaces, tx["marketplace"]), (trend, tx["date"][:7])):
            bucket = mapping.setdefault(key, {"revenue": Decimal(0), "expenses": Decimal(0)})
            bucket["revenue"] += income
            bucket["expenses"] += expense
    def buckets(mapping, label):
        return [{label: key, "revenue": float(v["revenue"]), "expenses": float(v["expenses"]),
                 "net": float(v["revenue"] - v["expenses"])} for key, v in sorted(mapping.items())]
    net = revenue - expenses
    return {
        "revenue": float(revenue), "expenses": float(expenses), "net_profit": float(net),
        "margin": float(money(net / revenue * 100)) if revenue else 0,
        "amazon_balance": float(revenue - amazon_expenses - payouts),
        "payouts_received": float(payouts), "transaction_count": len(transactions),
        **{key: float(value) for key, value in costs.items()},
        **{key: float(value) for key, value in recoveries.items()},
        "by_marketplace": buckets(marketplaces, "marketplace"),
        "by_category": [{"category": k, "amount": float(v)} for k, v in categories.items()],
        "trend": buckets(trend, "month"),
    }