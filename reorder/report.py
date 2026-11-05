# Copyright (c) 2026 noPlanBonlyA. All rights reserved.
# Предоставлено только для оценки тестового задания, см. LICENSE.
"""Вывод результата: текст для консоли и сохранение в CSV / JSON / TXT."""

import csv
import json
from decimal import Decimal
from pathlib import Path

from .calc import Recommendation


def fmt(value: Decimal) -> str:
    """1.50 -> '1.5', 56.0 -> '56' (без экспоненты и лишних нулей)."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def explain(r: Recommendation) -> list[str]:
    p = r.product
    return [
        f"  период покрытия: {p.lead_days} + {r.coverage_days - p.lead_days} = {r.coverage_days} дн.",
        f"  целевой запас:   ⌈{fmt(p.daily_sales)} × {r.coverage_days} + {p.safety_stock}⌉"
        f" = ⌈{fmt(r.demand)}⌉ = {r.target_stock} шт.",
        f"  доступно:        {p.stock} на складе + {p.incoming} в пути = {r.available} шт.",
        f"  заказ:           max(0, {r.target_stock} − {r.available}) = {r.order_qty} шт.",
    ]


def render_text(recs: list[Recommendation]) -> str:
    to_order = [r for r in recs if r.needs_order]
    enough = [r for r in recs if not r.needs_order]
    lines = [f"Обработано товаров: {len(recs)}. Нужно заказать: {len(to_order)}."]

    if to_order:
        total = sum(r.order_qty for r in to_order)
        sku_w = max(len("SKU"), *(len(r.product.sku) for r in to_order))
        name_w = max(len("Товар"), *(len(r.product.name) for r in to_order))
        lines += ["", "К ЗАКАЗУ", f"{'SKU':<{sku_w}}  {'Товар':<{name_w}}  {'Заказ, шт':>9}"]
        lines += [f"{r.product.sku:<{sku_w}}  {r.product.name:<{name_w}}  {r.order_qty:>9}"
                  for r in to_order]
        lines.append(f"{'Итого':<{sku_w + name_w + 2}}  {total:>9}")

        lines += ["", "ПОЯСНЕНИЕ РАСЧЁТА"]
        for r in to_order:
            lines += ["", f"{r.product.sku} {r.product.name} — заказать {r.order_qty} шт."]
            lines += explain(r)
    else:
        lines += ["", "Заказывать ничего не нужно: запаса хватает по всем позициям."]

    if enough:
        lines += ["", "ЗАКАЗ НЕ НУЖЕН"]
        for r in enough:
            p = r.product
            reason = "продаж нет, " if p.daily_sales == 0 else ""
            lines.append(f"{p.sku} {p.name} — {reason}целевой запас {r.target_stock} шт., "
                         f"доступно {r.available} шт. ({p.stock} + {p.incoming} в пути)")
    return "\n".join(lines)


def _as_dict(r: Recommendation) -> dict:
    p = r.product
    return {
        "sku": p.sku,
        "name": p.name,
        "stock": p.stock,
        "incoming": p.incoming,
        "daily_sales": fmt(p.daily_sales),
        "lead_days": p.lead_days,
        "safety_stock": p.safety_stock,
        "coverage_days": r.coverage_days,
        "target_stock": r.target_stock,
        "available": r.available,
        "order_qty": r.order_qty,
    }


REPORT_FORMATS = (".txt", ".csv", ".json")


def save_report(recs: list[Recommendation], path: str | Path) -> None:
    """Формат выбирается по расширению: .txt, .csv или .json. Другие расширения — ошибка,
    чтобы, например, report.xlsx не оказался текстовым файлом под видом таблицы."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in REPORT_FORMATS:
        raise ValueError(f"неподдерживаемый формат отчёта '{suffix or path.name}', "
                         f"допустимы: {', '.join(REPORT_FORMATS)}")
    if suffix == ".json":
        path.write_text(json.dumps([_as_dict(r) for r in recs], ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    elif suffix == ".csv":
        rows = [_as_dict(r) for r in recs]
        # utf-8-sig — чтобы Excel сразу открыл кириллицу без «кракозябр».
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:  # .txt
        path.write_text(render_text(recs) + "\n", encoding="utf-8")
