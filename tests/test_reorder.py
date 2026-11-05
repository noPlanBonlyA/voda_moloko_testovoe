# Copyright (c) 2026 noPlanBonlyA. All rights reserved.
# Предоставлено только для оценки тестового задания, см. LICENSE.
"""Запуск: python -m unittest -v"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path

from reorder.__main__ import main
from reorder.calc import Product, calculate
from reorder.loader import InputError, load_products, parse_rows
from reorder.report import save_report

ROOT = Path(__file__).resolve().parent.parent
HEADER = "sku,name,stock,daily_sales,incoming,lead_days,safety_stock"


def product(stock=0, daily_sales="0", incoming=0, lead_days=0, safety_stock=0):
    return Product("X1", "Test", stock, Decimal(daily_sales), incoming, lead_days, safety_stock)


class CalculateTest(unittest.TestCase):
    def test_basic_order(self):
        # A001 из примера: ⌈4 × 12 + 8⌉ = 56, доступно 12 → 44
        r = calculate(product(stock=12, daily_sales="4", lead_days=5, safety_stock=8))
        self.assertEqual((r.coverage_days, r.target_stock, r.available, r.order_qty), (12, 56, 12, 44))

    def test_fractional_sales_rounded_up(self):
        # 0.7 × 9 + 1 = 7.3 → 8
        r = calculate(product(daily_sales="0.7", lead_days=2, safety_stock=1))
        self.assertEqual(r.target_stock, 8)
        self.assertEqual(r.order_qty, 8)

    def test_no_float_error_on_exact_product(self):
        # Во float 0.1 * 30 = 3.0000000000000004, и ceil дал бы 4.
        r = calculate(product(daily_sales="0.1", lead_days=23))
        self.assertEqual(r.target_stock, 3)

    def test_incoming_reduces_order(self):
        # A003: ⌈2 × 14 + 6⌉ = 34, доступно 8 + 5 = 13 → 21
        r = calculate(product(stock=8, daily_sales="2", incoming=5, lead_days=7, safety_stock=6))
        self.assertEqual((r.available, r.order_qty), (13, 21))

    def test_enough_stock_gives_zero_not_negative(self):
        r = calculate(product(stock=100, daily_sales="5", lead_days=3, safety_stock=15))
        self.assertEqual(r.target_stock, 65)
        self.assertEqual(r.order_qty, 0)
        self.assertFalse(r.needs_order)

    def test_exactly_enough_gives_zero(self):
        r = calculate(product(stock=10, daily_sales="1", lead_days=3))
        self.assertEqual(r.order_qty, 0)

    def test_zero_sales_orders_only_safety_stock(self):
        r = calculate(product(stock=1, daily_sales="0", lead_days=10, safety_stock=4))
        self.assertEqual(r.target_stock, 4)
        self.assertEqual(r.order_qty, 3)

    def test_zero_sales_zero_safety_stock(self):
        r = calculate(product())
        self.assertEqual(r.order_qty, 0)

    def test_extra_days_is_configurable(self):
        r = calculate(product(daily_sales="2", lead_days=5), extra_days=10)
        self.assertEqual((r.coverage_days, r.order_qty), (15, 30))


class LoaderTest(unittest.TestCase):
    def row(self, **overrides):
        data = {"sku": "A1", "name": "Tea", "stock": "1", "daily_sales": "1.5",
                "incoming": "0", "lead_days": "2", "safety_stock": "0"}
        data.update(overrides)
        return data

    def assert_rejected(self, fragment, **overrides):
        with self.assertRaises(InputError) as ctx:
            parse_rows([("строка 2", self.row(**overrides))])
        self.assertIn(fragment, "\n".join(ctx.exception.errors))

    def test_valid_row(self):
        [p] = parse_rows([("строка 2", self.row())])
        self.assertEqual(p.daily_sales, Decimal("1.5"))
        self.assertEqual(p.lead_days, 2)

    def test_decimal_comma_accepted(self):
        [p] = parse_rows([("строка 2", self.row(daily_sales="1,5"))])
        self.assertEqual(p.daily_sales, Decimal("1.5"))

    def test_rejects_negative_int(self):
        self.assert_rejected("stock", stock="-1")

    def test_rejects_fractional_int_field(self):
        self.assert_rejected("lead_days", lead_days="2.5")

    def test_rejects_negative_sales(self):
        self.assert_rejected("daily_sales", daily_sales="-0.5")

    def test_rejects_non_numeric_and_nan(self):
        self.assert_rejected("daily_sales", daily_sales="abc")
        self.assert_rejected("daily_sales", daily_sales="NaN")

    def test_rejects_empty_values(self):
        self.assert_rejected("sku: пустое", sku=" ")
        self.assert_rejected("stock", stock="")

    def test_rejects_duplicate_sku(self):
        with self.assertRaises(InputError) as ctx:
            parse_rows([("строка 2", self.row()), ("строка 3", self.row())])
        self.assertIn("повторяется", ctx.exception.errors[0])

    def test_duplicate_detected_even_if_first_row_invalid(self):
        with self.assertRaises(InputError) as ctx:
            parse_rows([("строка 2", self.row(stock="-1")), ("строка 3", self.row())])
        self.assertIn("повторяется", ctx.exception.errors[-1])

    def test_rejects_missing_column(self):
        row = self.row()
        del row["incoming"]
        with self.assertRaises(InputError) as ctx:
            parse_rows([("строка 2", row)])
        self.assertIn("incoming", ctx.exception.errors[0])

    def test_collects_all_errors(self):
        with self.assertRaises(InputError) as ctx:
            parse_rows([("строка 2", self.row(stock="-1", lead_days="x"))])
        self.assertEqual(len(ctx.exception.errors), 2)

    def test_sample_csv(self):
        products = load_products(ROOT / "examples" / "products.csv")
        orders = {p.sku: calculate(p).order_qty for p in products}
        self.assertEqual(orders, {"A001": 44, "A002": 0, "A003": 21, "A004": 0, "A005": 0, "A006": 14})

    def test_csv_with_semicolon_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.csv"
            path.write_text("sku;name;stock;daily_sales;incoming;lead_days;safety_stock\n"
                            "B1;Хлеб;3;2,5;0;1;2\n", encoding="utf-8-sig")
            [p] = load_products(path)
        self.assertEqual((p.name, calculate(p).order_qty), ("Хлеб", 19))  # ⌈2.5×8+2⌉=22, −3

    def test_json_input(self):
        products = load_products(ROOT / "examples" / "products.json")
        self.assertGreaterEqual(len(products), 5)

    def test_missing_file(self):
        with self.assertRaises(InputError):
            load_products(ROOT / "nope.csv")

    def load_errors(self, content: bytes, name="p.csv") -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(content)
            with self.assertRaises(InputError) as ctx:
                load_products(path)
        return ctx.exception.errors

    def test_rejects_extra_csv_value(self):
        # Восьмое значение не относится ни к одной колонке — вероятен сдвиг столбцов.
        errors = self.load_errors(f"{HEADER}\nA,Test,2,1,0,2,0,EXTRA\n".encode())
        self.assertEqual(len(errors), 1)
        self.assertIn("строка 2", errors[0])
        self.assertIn("'EXTRA'", errors[0])

    def test_rejects_short_csv_row(self):
        errors = self.load_errors(f"{HEADER}\nA,Test,2,1\n".encode())
        self.assertIn("строка 2: нет значений для полей incoming, lead_days, safety_stock", errors[0])

    def test_rejects_missing_header_column(self):
        errors = self.load_errors(b"sku,name,stock\nA,Test,1\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("в заголовке нет колонок daily_sales", errors[0])

    def test_rejects_json_null(self):
        data = [{"sku": "A", "name": None, "stock": 1, "daily_sales": 1,
                 "incoming": 0, "lead_days": 1, "safety_stock": 0}]
        errors = self.load_errors(json.dumps(data).encode(), name="p.json")
        self.assertIn("нет значений для полей name", errors[0])

    def test_non_utf8_csv(self):
        errors = self.load_errors(f"{HEADER}\nA,Кофе,1,1,0,1,0\n".encode("cp1251"))
        self.assertIn("не в кодировке UTF-8", errors[0])

    def test_non_utf8_json(self):
        errors = self.load_errors('[{"name": "Кофе"}]'.encode("cp1251"), name="p.json")
        self.assertIn("не в кодировке UTF-8", errors[0])

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "права доступа POSIX, не под root")
    def test_unreadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.csv"
            path.write_text(f"{HEADER}\nA,T,1,1,0,1,0\n", encoding="utf-8")
            path.chmod(0)
            try:
                with self.assertRaises(InputError) as ctx:
                    load_products(path)
            finally:
                path.chmod(0o644)
        self.assertIn("нет прав на чтение", ctx.exception.errors[0])

    def test_directory_instead_of_file(self):
        with self.assertRaises(InputError) as ctx:
            load_products(ROOT / "examples")
        self.assertIn("это папка", ctx.exception.errors[0])


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_prints_report_and_saves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ext in ("csv", "json", "txt"):
                out_path = Path(tmp) / f"report.{ext}"
                code, out, _ = self.run_cli(str(ROOT / "examples" / "products.csv"), "-o", str(out_path))
                self.assertEqual(code, 0)
                self.assertTrue(out_path.stat().st_size > 0)
            saved = json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8"))
        self.assertIn("A001 Coffee — заказать 44 шт.", out)
        self.assertEqual(saved[0]["order_qty"], 44)

    def test_nothing_to_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.csv"
            path.write_text("sku,name,stock,daily_sales,incoming,lead_days,safety_stock\n"
                            "A,Tea,100,1,0,1,0\nB,Salt,0,0,0,5,0\n", encoding="utf-8")
            code, out, _ = self.run_cli(str(path))
        self.assertEqual(code, 0)
        self.assertIn("Заказывать ничего не нужно", out)

    def test_invalid_input_exit_code(self):
        code, _, err = self.run_cli(str(ROOT / "examples" / "invalid.csv"))
        self.assertEqual(code, 2)
        self.assertIn("Ошибка во входных данных", err)

    def test_unsupported_report_format_rejected_before_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "report.xlsx"
            with self.assertRaises(SystemExit) as ctx:
                self.run_cli(str(ROOT / "examples" / "products.csv"), "-o", str(out_path))
            self.assertFalse(out_path.exists())
        self.assertEqual(ctx.exception.code, 2)

    def test_save_report_rejects_unknown_suffix(self):
        recs = [calculate(product())]
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("report.xlsx", "report"):
                with self.assertRaises(ValueError):
                    save_report(recs, Path(tmp) / name)

    def test_report_write_error_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "no_such_dir" / "report.csv"
            code, _, err = self.run_cli(str(ROOT / "examples" / "products.csv"), "-o", str(out_path))
        self.assertEqual(code, 1)
        self.assertIn("Не удалось сохранить отчёт", err)


if __name__ == "__main__":
    unittest.main()
