from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_book.py"


class BookBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp_dir.name) / "dist"
        result = subprocess.run(
            [sys.executable, str(BUILD), "--variant", "all", "--output", str(cls.output)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise AssertionError(f"build failed:\n{result.stdout}\n{result.stderr}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_all_expected_formats_exist(self) -> None:
        for variant in ("zh", "en", "bilingual"):
            for suffix in ("html", "txt", "epub"):
                path = self.output / f"villain-book-{variant}.{suffix}"
                self.assertTrue(path.exists(), path)
                self.assertGreater(path.stat().st_size, 1000, path)
        self.assertTrue((self.output / "index.html").exists())

    def test_html_contains_bilingual_content(self) -> None:
        page = (self.output / "villain-book-bilingual.html").read_text(encoding="utf-8")
        self.assertIn("反派书", page)
        self.assertIn("The Villain Book", page)
        self.assertIn("data-set-mode=\"bilingual\"", page)
        self.assertIn("方源", page)
        self.assertIn("Fang Yuan", page)

    def test_html_ids_are_unique(self) -> None:
        page = (self.output / "villain-book-bilingual.html").read_text(encoding="utf-8")
        ids = re.findall(r'id="([^"]+)"', page)
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        self.assertEqual(duplicates, [])

    def test_text_is_utf8_bom_and_contains_both_languages(self) -> None:
        payload = (self.output / "villain-book-bilingual.txt").read_bytes()
        self.assertTrue(payload.startswith(b"\xef\xbb\xbf"))
        text = payload.decode("utf-8-sig")
        self.assertIn("序：为什么向反派学习", text)
        self.assertIn("Preface: Why Learn from Villains", text)

    def test_epub_structure_and_mimetype(self) -> None:
        path = self.output / "villain-book-bilingual.epub"
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist()[0], "mimetype")
            self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
            info = archive.getinfo("mimetype")
            self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
            self.assertIn("OEBPS/content.opf", archive.namelist())
            self.assertIn("OEBPS/nav.xhtml", archive.namelist())
            chapter_names = [
                name for name in archive.namelist() if name.startswith("OEBPS/chapter-")
            ]
            self.assertGreaterEqual(len(chapter_names), 5)

    def test_manifest_records_published_chapters(self) -> None:
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        ids = {chapter["id"] for chapter in manifest["published_chapters"]}
        self.assertIn("preface", ids)
        self.assertIn("fang-yuan", ids)
        self.assertNotIn("an-lan", ids)

    def test_planned_chapters_do_not_leak_into_book(self) -> None:
        page = (self.output / "villain-book-bilingual.html").read_text(encoding="utf-8")
        self.assertNotIn("韩立：把谨慎活成长期策略", page)
        self.assertNotIn("Han Li: Making Caution a Long-Term Strategy", page)


class ContentValidationTests(unittest.TestCase):
    def test_content_check(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BUILD), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("9 numbered chapters configured", result.stdout)


if __name__ == "__main__":
    unittest.main()

