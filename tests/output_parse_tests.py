#!/usr/bin/env python3
"""Parse synthetic CLI output: python3 tests/output_parse_tests.py /build/vnstat.

Run unchanged against v2.13 to reproduce the serializer failures. The corrected
XML tag is percentile_95; legacy 95th_percentile was never a valid XML name.
Pass --comma-locale de_DE.UTF-8 to require decimal-comma locale coverage.
No real interfaces, daemon, network, or existing databases are used.
String round trips retain the existing interface-selector restrictions (also
used by summary mode); quote/backslash/angle-bracket coverage uses aliases.
"""

import argparse
import json
import locale
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


class OutputParseTests(unittest.TestCase):
    binary = None
    comma_locale = None

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="vnstat-output-")
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.config = root / "vnstat.conf"
        self.config.write_text(
            f'DatabaseDir "{root}"\nLocale "C"\nUseUTC 1\n', encoding="utf-8"
        )
        self.database = root / "vnstat.db"
        self.create_fixture()

    def create_fixture(self, name="fixture0", alias="Office", samples=None):
        self.name = name
        if samples is None:
            samples = [("2020-01-01 00:00:00", 3000, 6000)]
        self.database.unlink(missing_ok=True)
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE info (id INTEGER PRIMARY KEY, name TEXT, value TEXT)")
            db.execute("INSERT INTO info (name, value) VALUES ('dbversion', '1')")
            db.execute(
                "CREATE TABLE interface (id INTEGER PRIMARY KEY, name TEXT, alias TEXT, "
                "active INTEGER, created TEXT, updated TEXT, rxcounter INTEGER, "
                "txcounter INTEGER, rxtotal INTEGER, txtotal INTEGER)"
            )
            rx = sum(sample[1] for sample in samples)
            tx = sum(sample[2] for sample in samples)
            db.execute(
                "INSERT INTO interface VALUES (1, ?, ?, 1, ?, ?, 0, 0, ?, ?)",
                (name, alias, samples[0][0], samples[-1][0], rx, tx),
            )
            for table in ("fiveminute", "hour", "day", "month", "year", "top"):
                db.execute(
                    f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, interface INTEGER, "
                    "date TEXT, rx INTEGER, tx INTEGER)"
                )
                rows = samples if table == "fiveminute" else [("2020-01-01 00:00:00", rx, tx)]
                db.executemany(
                    f"INSERT INTO {table} (interface, date, rx, tx) VALUES (1, ?, ?, ?)", rows
                )

    def output(self, kind, mode="a", extra=(), output_locale="C"):
        env = dict(os.environ, TZ="UTC", LC_ALL=output_locale)
        result = subprocess.run(
            [str(self.binary), "--config", str(self.config), "-i", self.name,
             f"--{kind}", mode, "--locale", output_locale, *extra],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def comma(self):
        if self.comma_locale:
            return self.comma_locale
        self.skipTest("No decimal-comma locale supplied; use --comma-locale")

    def test_billing_metadata_preserves_every_minute(self):
        for minute in range(60):
            self.config.write_text(
                f'DatabaseDir "{self.directory.name}"\nLocale "C"\nUseUTC 1\n'
                f'MonthRotate 7\nMonthRotateHour 18\nMonthRotateMinute {minute}\n',
                encoding="utf-8",
            )
            with self.subTest(minute=minute, kind="json"):
                data = json.loads(self.output("json", "s"))
                self.assertEqual(data["monthrotate"], 7)
                self.assertEqual(data["monthrotatehour"], 18)
                self.assertEqual(data["monthrotateminute"], minute)
            with self.subTest(minute=minute, kind="xml"):
                billing = ET.fromstring(self.output("xml", "s")).find("billing")
                self.assertIsNotNone(billing)
                self.assertEqual(billing.findtext("monthrotate"), "7")
                self.assertEqual(billing.findtext("monthrotatehour"), "18")
                self.assertEqual(billing.findtext("monthrotateminute"), str(minute))

    def test_json_modes_parse(self):
        for mode in "asfhdmytp":
            with self.subTest(mode=mode):
                data = json.loads(self.output("json", mode))
                self.assertEqual(data["interfaces"][0]["name"], self.name)

    def test_xml_modes_parse(self):
        for mode in "asfhdmytp":
            with self.subTest(mode=mode):
                data = ET.fromstring(self.output("xml", mode))
                self.assertEqual(data.find("interface").attrib["name"], self.name)
                if mode == "p":
                    self.assertIsNotNone(data.find("interface/bandwidth/percentile_95"))

    def test_average_rx_tx_and_total(self):
        for rx, tx in ((3000, 6000), (0, 3000), (3000, 0), (0, 0)):
            with self.subTest(rx=rx, tx=tx):
                self.create_fixture(samples=[("2020-01-01 00:00:00", rx, tx)])
                data = json.loads(self.output("json", "p"))["interfaces"][0]["bandwidth"]
                xml = self.output("xml", "p")
                # Isolate arithmetic from the separate invalid-tag regression on v2.13.
                xml = xml.replace("<95th_percentile>", "<percentile_95>")
                xml = xml.replace("</95th_percentile>", "</percentile_95>")
                average = ET.fromstring(xml).find("interface/bandwidth/average")
                for key, value in (("rx", rx // 300), ("tx", tx // 300),
                                   ("total", (rx + tx) // 300)):
                    field = key + "_bytes_per_second"
                    self.assertEqual(data["average"][field], value)
                    self.assertEqual(int(average.findtext(field)), value)

    def test_multiple_sample_averages(self):
        self.create_fixture(samples=[("2020-01-01 00:00:00", 3000, 6000),
                                     ("2020-01-01 00:10:00", 6000, 3000)])
        data = json.loads(self.output("json", "p"))["interfaces"][0]["bandwidth"]
        average = ET.fromstring(self.output("xml", "p")).find("interface/bandwidth/average")
        for key, value in (("rx", 15), ("tx", 15), ("total", 30)):
            field = key + "_bytes_per_second"
            self.assertEqual(data["average"][field], value)
            self.assertEqual(int(average.findtext(field)), value)

    def test_json_strings_round_trip(self):
        name = "net&\t"
        aliases = ('Office "A" & lab <2> \\', "line\nrow\rtab\t", "caf\u00e9",
                   "".join(chr(value) for value in range(1, 32)))
        for alias in aliases:
            with self.subTest(alias=repr(alias)):
                self.create_fixture(name=name, alias=alias)
                data = json.loads(self.output("json", "s"))["interfaces"][0]
                self.assertEqual(data["name"], name)
                self.assertEqual(data["alias"], alias)

    def test_xml_strings_round_trip(self):
        name = "net&\t"
        for alias in ('Office "A" & lab <2> \'', "line\nrow\rtab\t", "caf\u00e9"):
            with self.subTest(alias=repr(alias)):
                self.create_fixture(name=name, alias=alias)
                data = ET.fromstring(self.output("xml", "s")).find("interface")
                self.assertEqual(data.attrib["name"], name)
                self.assertEqual(data.findtext("name"), name)
                self.assertEqual(data.findtext("alias"), alias)

    def test_xml_forbidden_control_replacement(self):
        self.create_fixture(alias="Office\x01lab")
        data = ET.fromstring(self.output("xml", "s")).find("interface")
        self.assertEqual(data.findtext("alias"), "Office\ufffdlab")

    def test_percentile_json_uses_decimal_point(self):
        self.create_fixture(samples=[("2020-01-01 00:00:00", 3000, 6000),
                                     ("2020-01-01 00:10:00", 6000, 3000)])
        data = json.loads(self.output("json", "p", output_locale=self.comma()))
        entries = data["interfaces"][0]["bandwidth"]["entries"]
        self.assertEqual(entries["coverage_percentage"], 66.7)

    def test_alert_json_uses_decimal_point(self):
        extra = ("--alert", "1", "0", "d", "total", "12000", "B")
        data = json.loads(self.output("json", extra=extra, output_locale=self.comma()))
        limit = data["interfaces"][0]["alert"]["limit"]
        self.assertEqual(limit["used_percentage"], 75.0)
        self.assertEqual(limit["remaining_percentage"], 25.0)

    def test_percentile_alert_json_uses_decimal_point(self):
        extra = ("--alert", "1", "0", "p", "rx", "40", "B/s")
        data = json.loads(self.output("json", extra=extra, output_locale=self.comma()))
        alert = data["interfaces"][0]["alert"]
        self.assertEqual(alert["limit"]["used_percentage"], 25.0)
        self.assertEqual(alert["entries"]["over_limit_percentage"], 0.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--comma-locale")
    args = parser.parse_args()
    OutputParseTests.binary = args.binary.resolve()
    if args.comma_locale:
        previous = locale.setlocale(locale.LC_NUMERIC)
        locale.setlocale(locale.LC_NUMERIC, args.comma_locale)
        if locale.localeconv()["decimal_point"] == ".":
            parser.error("--comma-locale must use a non-dot decimal separator")
        locale.setlocale(locale.LC_NUMERIC, previous)
    OutputParseTests.comma_locale = args.comma_locale
    unittest.main(argv=[__file__], verbosity=2)
