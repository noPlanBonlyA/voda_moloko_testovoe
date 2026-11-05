# Copyright (c) 2026 noPlanBonlyA. All rights reserved.
# Предоставлено только для оценки тестового задания, см. LICENSE.
"""Чтение товаров из CSV или JSON с проверкой корректности данных.

Ошибки не обрываются на первой найденной: собираем все и показываем
списком, чтобы файл можно было исправить за один раз.
"""

import csv
import io
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
    if path.is_dir():
        raise InputError([f"{path}: это папка, а не файл"])
    if not path.exists():
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
        # DictReader складывает значения сверх числа колонок заголовка под ключ None.
        # Скорее всего, столбцы сдвинуты, поэтому строку не принимаем.
        extra = row.get(None)
        if extra:
            errors.append(f"{where}: лишние значения сверх колонок заголовка: "
                          f"{', '.join(map(repr, extra))}")
            continue
        # Нет поля в JSON, null в JSON или короткая строка CSV (DictReader подставит None).
        missing = [f for f in FIELDS if row.get(f) is None]
        if missing:
            errors.append(f"{where}: нет значений для полей {', '.join(missing)}")
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


def _read_text(path: Path) -> str:
    """Читает файл целиком; любые проблемы чтения превращает в InputError."""
    try:
        # utf-8-sig убирает BOM, который добавляет Excel при сохранении в CSV.
        # newline="" сохраняет переводы строк внутри кавычек для модуля csv.
        with path.open(encoding="utf-8-sig", newline="") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise InputError([
            f"{path}: файл не в кодировке UTF-8 (ошибка в байте {e.start}). "
            "Сохраните его в UTF-8: в Excel — «Сохранить как» → «CSV UTF-8»."
        ]) from e
    except PermissionError as e:
        raise InputError([f"{path}: нет прав на чтение файла"]) from e
    except OSError as e:
        raise InputError([f"{path}: не удалось прочитать файл ({e.strerror or e})"]) from e


def _read_csv(path: Path) -> list[tuple[str, dict]]:
    text = _read_text(path)
    first_line = text.split("\n", 1)[0]
    # Русский Excel по умолчанию сохраняет CSV через точку с запятой.
    delimiter = ";" if ";" in first_line and "," not in first_line else ","
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        header = [h.strip() for h in reader.fieldnames or []]
        missing = [f for f in FIELDS if f not in header]
        if missing:
            raise InputError([f"{path}: в заголовке нет колонок {', '.join(missing)}"])
        reader.fieldnames = header
        # Строка 1 — заголовок, поэтому данные начинаются со строки 2.
        return [(f"строка {i}", row) for i, row in enumerate(reader, start=2)
                if not _is_blank(row)]
    except csv.Error as e:
        raise InputError([f"{path}: некорректный CSV ({e})"]) from e


def _is_blank(row: dict) -> bool:
    """Пустая строка CSV (например, в конце файла). Лишние значения тоже проверяем."""
    values = [v for k, v in row.items() if k is not None] + row.get(None, [])
    return not any(v and v.strip() for v in values)


def _read_json(path: Path) -> list[tuple[str, dict]]:
    try:
        data = json.loads(_read_text(path))
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
