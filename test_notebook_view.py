"""Регрессия: весь отчёт должен открываться в выводе ноутбука без HTTP-сервера."""
from contextlib import redirect_stdout
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import unittest
from unittest.mock import patch
from IPython.display import IFrame

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mvd_notebook_test", ROOT / "telegram_analysis.py")
mvd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvd)


class ParsedDocument(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.keys, self.kpis = [], []
        self.in_kpi = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article" and "data-key" in attrs:
            self.keys.append(attrs["data-key"])
        if tag == "div" and "tg-value" in attrs.get("class", "").split():
            self.in_kpi = True

    def handle_endtag(self, tag):
        if tag == "div":
            self.in_kpi = False

    def handle_data(self, text):
        if self.in_kpi:
            self.kpis.append(text.strip())


class NotebookDisplay:
    """Граница Jupyter: сохраняем реальные объекты IFrame и обновления display_id."""
    def __init__(self):
        self.frame = None

    def display(self, obj, **kwargs):
        if isinstance(obj, IFrame):
            self.frame = obj
        return self

    def update(self, obj):
        if isinstance(obj, IFrame):
            self.frame = obj

    def document(self):
        if self.frame is None:
            return None
        class FrameParser(HTMLParser):
            srcdoc = None
            def handle_starttag(self, tag, attrs):
                if tag == "iframe":
                    self.srcdoc = dict(attrs).get("srcdoc")
        parsed = FrameParser()
        parsed.feed(self.frame._repr_html_())
        return parsed.srcdoc


class NotebookViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.quality, cls.meta = mvd.load_data(next(ROOT.glob("*.csv")))

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.display = NotebookDisplay()
        for mocked in [patch.object(mvd, "display", self.display.display),
                       patch.object(mvd.go.Figure, "show", return_value=None),
                       patch.object(mvd, "OUTPUT_DIR", Path(self.temp.name))]:
            mocked.start()
            self.addCleanup(mocked.stop)

    def start(self):
        with redirect_stdout(StringIO()):
            return mvd.launch(self.source, self.quality, self.meta)

    def assert_complete_native_report(self):
        document = self.display.document()
        self.assertIsNotNone(document, "После запуска нужен встроенный отчёт, а не только панель виджетов")
        parsed = ParsedDocument(document)
        self.assertEqual(len(set(parsed.keys)), 36)
        self.assertIn("calendar", parsed.keys)
        self.assertIn("availability_month", parsed.keys)
        return parsed

    def test_start_displays_all_36_charts_without_download(self):
        self.start()
        parsed = self.assert_complete_native_report()
        self.assertEqual(parsed.kpis[0], "2 324")

    def test_open_button_refreshes_current_dates_without_local_server(self):
        app = self.start()
        app["controls"]["start"].value = self.source.Date.max().date()
        app["controls"]["end"].value = self.source.Date.max().date()
        # Открытие отчёта не должно зависеть от порта виртуальной машины.
        with patch("socket.socket", side_effect=AssertionError("HTTP-сервер не нужен")):
            with redirect_stdout(StringIO()):
                app["controls"]["open_html"].click()
        parsed = self.assert_complete_native_report()
        self.assertEqual(parsed.kpis[0], "1")


if __name__ == "__main__":
    unittest.main()
