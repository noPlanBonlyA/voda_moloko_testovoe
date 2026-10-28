# Copyright (c) 2026 noPlanBonlyA. All rights reserved.
# Предоставлено только для оценки тестового задания, см. LICENSE.
"""Запуск: python -m reorder examples/products.csv [-o report.csv] [--extra-days 7]"""

import argparse
import sys

from .calc import EXTRA_DAYS, calculate_all
from .loader import InputError, load_products
from .report import render_text, save_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reorder",
        description="Рассчитывает, сколько единиц каждого товара заказать у поставщика.",
    )
    parser.add_argument("input", help="файл с товарами: .csv или .json")
    parser.add_argument("-o", "--output", help="сохранить отчёт в файл (.csv, .json или .txt)")
    parser.add_argument("--extra-days", type=int, default=EXTRA_DAYS,
                        help=f"дней запаса сверх срока поставки (по умолчанию {EXTRA_DAYS})")
    args = parser.parse_args(argv)
    if args.extra_days < 0:
        parser.error("--extra-days не может быть отрицательным")

    try:
        products = load_products(args.input)
    except InputError as e:
        print("Ошибка во входных данных:", file=sys.stderr)
        for msg in e.errors:
            print(f"  - {msg}", file=sys.stderr)
        return 2

    recs = calculate_all(products, args.extra_days)
    print(render_text(recs))
    if args.output:
        save_report(recs, args.output)
        print(f"\nОтчёт сохранён: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
