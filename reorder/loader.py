# Copyright (c) 2026 noPlanBonlyA. All rights reserved.
# Предоставлено только для оценки тестового задания, см. LICENSE.
"""Чтение товаров из CSV или JSON с проверкой корректности данных.

Ошибки не обрываются на первой найденной: собираем все и показываем
списком, чтобы файл можно было исправить за один раз.
"""

import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .calc import Product

FIELDS = ("sku", "name", "stock", "daily_sales", "incoming", "lead_days", "safety_stock")
INT_FIELDS = ("stock", "incoming", "lead_days", "safety_stock")


class InputError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def load_products(path: str | Path) -> list[Product]:
    path = Path(path)
    if not path.is_file():
        raise InputError([f"Файл не найден: {path}"])

    if path.suffix.lower() == ".json":
        rows = _read_json(path)
    else:
        rows = _read_csv(path)
    return parse_rows(rows)


def parse_rows(rows: list[tuple[str, dict]]) -> list[Product]:
    """rows — пары (где находится запись, словарь полей)."""
    errors: list[str] = []
    products: list[Product] = []
    seen_skus: dict[str, str] = {}

    for where, row in rows:
        row_errors: list[str] = []
        missing = [f for f in FIELDS if f not in row]
        if missing:
            errors.append(f"{where}: нет полей {', '.join(missing)}")
            continue

        values = {f: str(row[f]).strip() for f in FIELDS}
        sku, name = values["sku"], values["name"]
        if not sku:
            row_errors.append("sku: пустое значение")
        elif sku in seen_skus:
            row_errors.append(f"sku: '{sku}' повторяется (впервые: {seen_skus[sku]})")
        else:
            seen_skus[sku] = where
        if not name:
            row_errors.append("name: пустое значение")

        numbers = {}
        for field in FIELDS[2:]:
            parse = _parse_non_negative_int if field in INT_FIELDS else _parse_non_negative_decimal
            try:
                numbers[field] = parse(values[field])
            except ValueError as e:
                row_errors.append(f"{field}: {e}")

        if row_errors:
            errors.extend(f"{where}: {msg}" for msg in row_errors)
            continue

        products.append(Product(sku=sku, name=name, **numbers))

    if errors:
        raise InputError(errors)
    if not products:
        raise InputError(["В файле нет ни одного товара"])
    return products


def _read_csv(path: Path) -> list[tuple[str, dict]]:
    # utf-8-sig убирает BOM, который добавляет Excel при сохранении в CSV.
    with path.open(encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first_line = text.split("\n", 1)[0]
    # Русский Excel по умолчанию сохраняет CSV через точку с запятой.
    delimiter = ";" if ";" in first_line and "," not in first_line else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    # Строка 1 — заголовок, поэтому данные начинаются со строки 2.
    return [(f"строка {i}", row) for i, row in enumerate(reader, start=2)
            if any((v or "").strip() for v in row.values())]


def _read_json(path: Path) -> list[tuple[str, dict]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise InputError([f"Некорректный JSON: {e}"]) from e
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise InputError(["JSON должен быть списком объектов"])
    return [(f"запись {i}", row) for i, row in enumerate(data, start=1)]


def _parse_non_negative_int(raw: str) -> int:
    # isdigit() отсекает "-1", "1.5", "True", пустую строку и т. п.
    if not raw.isascii() or not raw.isdigit():
        raise ValueError(f"ожидается целое число >= 0, получено '{raw}'")
    return int(raw)


def _parse_non_negative_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"ожидается число >= 0, получено '{raw}'") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"ожидается число >= 0, получено '{raw}'")
    return value
