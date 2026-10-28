# Copyright (c) 2026 noPlanBonlyA. All rights reserved.
# Предоставлено только для оценки тестового задания, см. LICENSE.
"""Расчёт рекомендуемого заказа по одному товару.

Формула из задания:
    период покрытия = lead_days + 7
    целевой запас   = ceil(daily_sales * период покрытия + safety_stock)
    доступно        = stock + incoming
    заказ           = max(0, целевой запас - доступно)

Продажи хранятся в Decimal, а не во float: иначе, например,
0.1 * 30 = 3.0000000000000004 и округление вверх дало бы 4 вместо 3.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

# Сколько дней сверх срока поставки должен покрывать запас.
EXTRA_DAYS = 7


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    stock: int
    daily_sales: Decimal
    incoming: int
    lead_days: int
    safety_stock: int


@dataclass(frozen=True)
class Recommendation:
    product: Product
    coverage_days: int
    demand: Decimal  # daily_sales * coverage_days + safety_stock, до округления
    target_stock: int
    available: int
    order_qty: int

    @property
    def needs_order(self) -> bool:
        return self.order_qty > 0


def calculate(product: Product, extra_days: int = EXTRA_DAYS) -> Recommendation:
    coverage_days = product.lead_days + extra_days
    demand = product.daily_sales * coverage_days + product.safety_stock
    target_stock = int(demand.to_integral_value(rounding=ROUND_CEILING))
    available = product.stock + product.incoming
    order_qty = max(0, target_stock - available)
    return Recommendation(product, coverage_days, demand, target_stock, available, order_qty)


def calculate_all(products: list[Product], extra_days: int = EXTRA_DAYS) -> list[Recommendation]:
    return [calculate(p, extra_days) for p in products]
