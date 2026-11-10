#!/usr/bin/env python3
"""Build the bilingual book into HTML, plain text, and EPUB."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
import textwrap
import tomllib
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "book.toml"
PUBLISHED_STATUSES = {"draft", "review", "final"}
LANG_MARKERS = {
    "zh": re.compile(r"^<!--\s*lang:zh\s*-->\s*$", re.MULTILINE),
    "en": re.compile(r"^<!--\s*lang:en\s*-->\s*$", re.MULTILINE),
}


@dataclass
class Part:
    id: str
    title_zh: str
    title_en: str
    intro_zh: str = ""
    intro_en: str = ""


@dataclass
class Chapter:
    id: str
    part: str
    kind: str
    order: int
    status: str
    file: str
    title_zh: str
    title_en: str
    subtitle_zh: str = ""
    subtitle_en: str = ""
    number: int | None = None
    content_zh: str = ""
    content_en: str = ""


@dataclass
class Book:
    metadata: dict[str, str]
    parts: list[Part]
    chapters: list[Chapter] = field(default_factory=list)

    def published(self) -> list[Chapter]:
        return [
            chapter
            for chapter in sorted(self.chapters, key=lambda item: item.order)
            if chapter.status in PUBLISHED_STATUSES
        ]


def load_book(config_path: Path = DEFAULT_CONFIG) -> Book:
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    metadata = {key: str(value) for key, value in raw["book"].items()}
    parts = [Part(**part) for part in raw["parts"]]
    chapters = [Chapter(**chapter) for chapter in raw["chapters"]]
    return Book(metadata=metadata, parts=parts, chapters=chapters)


def split_languages(text: str, source: Path) -> tuple[str, str]:
    zh_match = LANG_MARKERS["zh"].search(text)
    en_match = LANG_MARKERS["en"].search(text)
    if not zh_match or not en_match:
        raise ValueError(f"{source}: expected both <!-- lang:zh --> and <!-- lang:en -->")
    if zh_match.start() >= en_match.start():
        raise ValueError(f"{source}: Chinese marker must appear before English marker")
    chinese = text[zh_match.end() : en_match.start()].strip()
    english = text[en_match.end() :].strip()
    return chinese, english


def validate_book(book: Book, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    part_ids = {part.id for part in book.parts}
    chapter_ids: set[str] = set()
    chapter_numbers: set[int] = set()

    for chapter in book.chapters:
        if chapter.id in chapter_ids:
            errors.append(f"duplicate chapter id: {chapter.id}")
        chapter_ids.add(chapter.id)
        if chapter.part not in part_ids:
            errors.append(f"{chapter.id}: unknown part '{chapter.part}'")
        if chapter.number is not None:
            if chapter.number in chapter_numbers:
                errors.append(f"duplicate chapter number: {chapter.number}")
            chapter_numbers.add(chapter.number)

        if chapter.status not in {"planned", *PUBLISHED_STATUSES}:
            errors.append(f"{chapter.id}: unknown status '{chapter.status}'")
        if chapter.status == "planned":
            continue

        path = root / chapter.file
        if not path.exists():
            errors.append(f"{chapter.id}: missing source file {chapter.file}")
            continue
        source = path.read_text(encoding="utf-8")
        try:
            chinese, english = split_languages(source, path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not chinese:
            errors.append(f"{chapter.id}: empty Chinese body")
        if not english:
            errors.append(f"{chapter.id}: empty English body")

    numbered = sorted(number for number in chapter_numbers if number is not None)
    if numbered and numbered != list(range(1, max(numbered) + 1)):
        errors.append("chapter numbers must be contiguous from 1")
    if len(numbered) != 30:
        errors.append(f"expected 30 numbered chapters, found {len(numbered)}")
    return errors


def hydrate_content(book: Book, root: Path = ROOT) -> None:
    for chapter in book.published():
        path = root / chapter.file
        chinese, english = split_languages(path.read_text(encoding="utf-8"), path)
        chapter.content_zh = chinese
        chapter.content_en = english


def title_for(book: Book, language: str) -> str:
    return book.metadata[f"title_{language}"]


def short_title_for(book: Book, language: str) -> str:
    return book.metadata[f"short_title_{language}"]


def subtitle_for(book: Book, language: str) -> str:
    return book.metadata[f"subtitle_{language}"]


def author_for(book: Book, language: str) -> str:
    return book.metadata[f"author_{language}"]


def chapter_title(chapter: Chapter, language: str) -> str:
    return getattr(chapter, f"title_{language}")


def chapter_subtitle(chapter: Chapter, language: str) -> str:
    return getattr(chapter, f"subtitle_{language}")


def part_title(part: Part, language: str) -> str:
    return getattr(part, f"title_{language}")


def part_intro(part: Part, language: str) -> str:
    return getattr(part, f"intro_{language}")


def variant_languages(variant: str) -> list[str]:
    if variant == "bilingual":
        return ["zh", "en"]
    return [variant]


def visible_chapters(book: Book) -> list[Chapter]:
    return book.published()


def chapter_anchor(chapter: Chapter) -> str:
    return f"chapter-{chapter.id}"


def escape_html(value: str) -> str:
    return html.escape(value, quote=False)


def inline_markdown(value: str) -> str:
    tokens: dict[str, str] = {}

    def stash(fragment: str) -> str:
        key = f"\x00TOKEN{len(tokens)}\x00"
        tokens[key] = fragment
        return key

    text = html.escape(value, quote=False)

    def code_replacement(match: re.Match[str]) -> str:
        return stash(f"<code>{match.group(1)}</code>")

    def link_replacement(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.escape(match.group(2), quote=True)
        return stash(f'<a href="{url}">{label}</a>')

    text = re.sub(r"`([^`]+)`", code_replacement, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replacement, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    for key, fragment in tokens.items():
        text = text.replace(key, fragment)
    return text


def plain_inline(value: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    return text.strip()


def slugify_heading(value: str, index: int) -> str:
    text = plain_inline(value).lower()
    ascii_words = re.findall(r"[a-z0-9]+", text)
    if ascii_words:
        return "-".join(ascii_words)[:50] + f"-{index}"
    return f"section-{index}"


def is_block_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        not stripped
        or re.match(r"^#{1,6}\s+", stripped)
        or re.match(r"^>\s?", stripped)
        or re.match(r"^[-*+]\s+", stripped)
        or re.match(r"^\d+\.\s+", stripped)
        or stripped == "---"
        or stripped.startswith("<!--")
    )


def render_blocks(markdown_text: str, id_prefix: str = "") -> str:
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    index = 0
    heading_index = 0

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("<!--"):
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            heading_index += 1
            anchor = slugify_heading(heading.group(2), heading_index)
            if id_prefix:
                anchor = f"{id_prefix}-{anchor}"
            output.append(
                f'<h{level} id="{anchor}">{inline_markdown(heading.group(2))}</h{level}>'
            )
            index += 1
            continue

        if stripped == "---":
            output.append("<hr />")
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            quote_text = " ".join(part.strip() for part in quote_lines if part.strip())
            output.append(f"<blockquote><p>{inline_markdown(quote_text)}</p></blockquote>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", raw_line)
        ordered = re.match(r"^\s*\d+\.\s+(.+)$", raw_line)
        if unordered or ordered:
            kind = "ul" if unordered else "ol"
            items: list[str] = []
            pattern = r"^\s*[-*+]\s+(.+)$" if unordered else r"^\s*\d+\.\s+(.+)$"
            while index < len(lines):
                match = re.match(pattern, lines[index])
                if not match:
                    break
                items.append(f"<li>{inline_markdown(match.group(1).strip())}</li>")
                index += 1
            output.append(f"<{kind}>{''.join(items)}</{kind}>")
            continue

        paragraph: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                break
            if paragraph and is_block_start(candidate):
                break
            paragraph.append(candidate.strip())
            index += 1
            if index < len(lines) and not lines[index].strip():
                break
        if paragraph:
            output.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
        else:
            index += 1

    return "\n".join(output)


def render_plain_blocks(markdown_text: str, wrap_width: int = 92) -> str:
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = plain_inline(" ".join(part.strip() for part in paragraph))
        if re.search(r"[\u3400-\u9fff]", text):
            output.append(text)
        else:
            output.append(
                textwrap.fill(
                    text,
                    width=wrap_width,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        paragraph.clear()

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("<!--"):
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush()
            output.append(plain_inline(heading.group(2)))
            continue
        if stripped == "---":
            flush()
            output.append("----------")
            continue
        if stripped.startswith(">"):
            flush()
            output.append("  " + plain_inline(re.sub(r"^\s*>\s?", "", stripped)))
            continue
        if re.match(r"^[-*+]\s+", stripped):
            flush()
            output.append("- " + plain_inline(re.sub(r"^[-*+]\s+", "", stripped)))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            flush()
            output.append(plain_inline(stripped))
            continue
        paragraph.append(stripped)
    flush()
    return "\n\n".join(output)


def html_lang_block(chapter: Chapter, language: str, variant: str) -> str:
    content = getattr(chapter, f"content_{language}")
    lang_attr = "zh-Hans" if language == "zh" else "en"
    block_class = f"lang-block lang-{language}"
    return (
        f'<div class="{block_class}" lang="{lang_attr}">\n'
        f"{render_blocks(content, id_prefix=f'{chapter.id}-{language}')}\n"
        f"</div>"
    )


def chapter_heading(chapter: Chapter, variant: str) -> str:
    languages = variant_languages(variant)
    title_parts = []
    subtitle_parts = []
    for language in languages:
        lang_class = f"lang-{language}"
        title_parts.append(
            f'<span class="{lang_class}" lang="{"zh-Hans" if language == "zh" else "en"}">'
            f"{escape_html(chapter_title(chapter, language))}</span>"
        )
        subtitle_parts.append(
            f'<span class="{lang_class}" lang="{"zh-Hans" if language == "zh" else "en"}">'
            f"{escape_html(chapter_subtitle(chapter, language))}</span>"
        )
    number = (
        f'<span class="chapter-number">{chapter.number:02d}</span>'
        if chapter.number is not None
        else '<span class="chapter-number">00</span>'
    )
    return (
        f'<header class="chapter-header">{number}'
        f'<h1>{"<span class=\"title-sep\"> / </span>".join(title_parts)}</h1>'
        f'<p class="chapter-subtitle">{"<span class=\"title-sep\"> / </span>".join(subtitle_parts)}</p>'
        f"</header>"
    )


def render_chapter(chapter: Chapter, variant: str) -> str:
    languages = variant_languages(variant)
    blocks = []
    for language in languages:
        blocks.append(html_lang_block(chapter, language, variant))
    divider = (
        '<div class="language-divider" aria-hidden="true"><span>EN</span></div>'
        if variant == "bilingual"
        else ""
    )
    body = divider.join(blocks)
    return (
        f'<section class="chapter" id="{chapter_anchor(chapter)}" data-chapter="{chapter.id}">\n'
        f"{chapter_heading(chapter, variant)}\n"
        f"{body}\n"
        f"</section>"
    )


def toc_html(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    chunks = ['<nav class="toc" aria-label="Table of contents">']
    for part in book.parts:
        chapters = [chapter for chapter in visible_chapters(book) if chapter.part == part.id]
        if not chapters:
            continue
        chunks.append('<section class="toc-part">')
        chunks.append(
            "<h2>"
            + "".join(
                f'<span class="lang-{language}" lang="{"zh-Hans" if language == "zh" else "en"}">'
                f"{escape_html(part_title(part, language))}</span>"
                for language in languages
            )
            + "</h2>"
        )
        chunks.append("<ol>")
        for chapter in chapters:
            number = f"{chapter.number:02d}" if chapter.number is not None else "00"
            title = "".join(
                f'<span class="lang-{language}" lang="{"zh-Hans" if language == "zh" else "en"}">'
                f"{escape_html(chapter_title(chapter, language))}</span>"
                for language in languages
            )
            chunks.append(
                f'<li><a href="#{chapter_anchor(chapter)}"><span class="toc-number">{number}</span>'
                f'<span class="toc-title">{title}</span></a></li>'
            )
        chunks.append("</ol>")
        chunks.append("</section>")
    chunks.append("</nav>")
    return "\n".join(chunks)


def edition_label(book: Book, variant: str) -> str:
    if variant == "zh":
        return f"第 {book.metadata['edition']} 版 · {book.metadata['updated']}"
    if variant == "en":
        return f"Edition {book.metadata['edition']} · {book.metadata['updated']}"
    return (
        f"第 {book.metadata['edition']} 版 / Edition {book.metadata['edition']} "
        f"· {book.metadata['updated']}"
    )


HTML_CSS = """
:root {
  color-scheme: light;
  --paper: #f8f6f0;
  --ink: #191b1d;
  --muted: #696761;
  --line: #d8d3c8;
  --red: #a53a2b;
  --teal: #275e58;
  --panel: rgba(248, 246, 240, 0.94);
  --serif: "Iowan Old Style", "Palatino Linotype", "Noto Serif CJK SC",
    "Source Han Serif SC", "Songti SC", Georgia, serif;
  --sans: "Avenir Next", "Segoe UI", "Noto Sans CJK SC",
    "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background:
    linear-gradient(90deg, transparent 0, transparent 49.8%, rgba(165, 58, 43, 0.035) 50%, transparent 50.2%),
    var(--paper);
  font-family: var(--serif);
  font-size: 18px;
  line-height: 1.9;
}
body[data-mode="zh"] .lang-en,
body[data-mode="en"] .lang-zh { display: none !important; }
body[data-mode="zh"] .title-sep,
body[data-mode="en"] .title-sep { display: none !important; }
.reading-progress {
  position: fixed;
  inset: 0 auto auto 0;
  z-index: 20;
  width: 0;
  height: 3px;
  background: var(--red);
}
.site-bar {
  position: sticky;
  top: 0;
  z-index: 15;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 62px;
  padding: 10px clamp(20px, 4vw, 64px);
  border-bottom: 1px solid var(--line);
  background: var(--panel);
  backdrop-filter: blur(12px);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
  color: var(--ink);
  text-decoration: none;
  white-space: nowrap;
}
.brand strong { font-size: 1rem; letter-spacing: 0.02em; }
.brand span {
  color: var(--muted);
  font-family: var(--sans);
  font-size: 0.66rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.mode-switch {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #fffdf8;
}
.mode-switch button {
  min-width: 62px;
  padding: 6px 12px;
  border: 0;
  border-right: 1px solid var(--line);
  color: var(--muted);
  background: transparent;
  font: 600 0.72rem/1.2 var(--sans);
  letter-spacing: 0.02em;
  cursor: pointer;
}
.mode-switch button:last-child { border-right: 0; }
.mode-switch button[aria-pressed="true"] {
  color: #fffdf8;
  background: var(--teal);
}
.mode-switch button:focus-visible,
.toc a:focus-visible { outline: 2px solid var(--red); outline-offset: 3px; }
.reader-shell {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 760px);
  justify-content: center;
  gap: clamp(32px, 6vw, 92px);
  padding: 0 clamp(20px, 5vw, 76px);
}
.toc-panel {
  position: sticky;
  top: 80px;
  max-height: calc(100vh - 110px);
  margin-top: 46px;
  overflow: auto;
  font-family: var(--sans);
}
.toc-panel summary {
  display: none;
  padding: 10px 0;
  cursor: pointer;
  color: var(--red);
  font-weight: 700;
}
.toc-part { margin-bottom: 28px; }
.toc-part h2 {
  margin: 0 0 10px;
  color: var(--muted);
  font: 700 0.68rem/1.45 var(--sans);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.toc-part h2 .lang-zh,
.toc-part h2 .lang-en { display: block; }
.toc-part h2 .lang-en { margin-top: 3px; font-weight: 500; letter-spacing: 0.06em; }
.toc ol { margin: 0; padding: 0; list-style: none; }
.toc li { margin: 0; }
.toc a {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 7px;
  padding: 7px 0;
  color: #383937;
  text-decoration: none;
  font-size: 0.78rem;
  line-height: 1.45;
}
.toc a:hover { color: var(--red); }
.toc-number { color: #9b968b; font-variant-numeric: tabular-nums; }
.toc-title .lang-zh,
.toc-title .lang-en { display: block; }
.toc-title .lang-en { margin-top: 2px; color: var(--muted); font-size: 0.9em; }
main.book {
  min-width: 0;
  width: 100%;
  max-width: 760px;
  padding: clamp(48px, 7vw, 96px) 0 120px;
}
.book-cover {
  min-height: min(760px, calc(100vh - 120px));
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-bottom: 1px solid var(--line);
}
.kicker {
  margin: 0 0 20px;
  color: var(--red);
  font: 700 0.72rem/1.4 var(--sans);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.book-cover h1 {
  max-width: 12em;
  margin: 0;
  font-size: clamp(2.5rem, 7vw, 5.8rem);
  line-height: 1.06;
  font-weight: 600;
  letter-spacing: 0;
}
.book-cover h1 .lang-zh,
.book-cover h1 .lang-en { display: block; }
.book-cover h1 .lang-en {
  margin-top: 22px;
  color: var(--teal);
  font-size: 0.42em;
  line-height: 1.2;
}
.book-subtitle {
  max-width: 34em;
  margin: 32px 0 0;
  padding-left: 20px;
  border-left: 3px solid var(--red);
  color: #3f403d;
  font-size: 1.05rem;
}
.book-subtitle .lang-zh,
.book-subtitle .lang-en { display: block; }
.book-subtitle .lang-en { margin-top: 12px; color: var(--muted); font-size: 0.92em; }
.cover-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 22px;
  margin-top: 42px;
  color: var(--muted);
  font: 600 0.72rem/1.4 var(--sans);
  letter-spacing: 0.07em;
  text-transform: uppercase;
}
.description {
  max-width: 36em;
  margin-top: 52px;
  color: #3f403d;
  font-size: 0.98rem;
}
.description .lang-en { margin-top: 16px; color: var(--muted); }
.chapter {
  padding: 96px 0 24px;
  border-top: 1px solid var(--line);
}
.chapter:first-of-type { margin-top: 96px; }
.chapter-header {
  position: relative;
  margin-bottom: 48px;
  padding-top: 26px;
}
.chapter-number {
  position: absolute;
  top: -14px;
  right: 0;
  color: rgba(39, 94, 88, 0.22);
  font: 700 clamp(3rem, 10vw, 6rem)/1 var(--sans);
  font-variant-numeric: tabular-nums;
}
.chapter h1 {
  max-width: 18em;
  margin: 0;
  padding-right: 1.5em;
  font-size: clamp(1.8rem, 4.2vw, 3rem);
  line-height: 1.22;
  font-weight: 600;
  letter-spacing: 0;
}
.chapter h1 .lang-en {
  margin-top: 10px;
  color: var(--teal);
  font-size: 0.56em;
  line-height: 1.24;
}
.chapter-subtitle {
  max-width: 36em;
  margin: 22px 0 0;
  color: var(--muted);
  font-size: 0.95rem;
}
.chapter-subtitle .lang-zh,
.chapter-subtitle .lang-en { display: block; }
.chapter-subtitle .lang-en { margin-top: 7px; font-size: 0.92em; }
.lang-block > h2 {
  margin: 2.4em 0 0.65em;
  color: var(--red);
  font-size: 1.18rem;
  line-height: 1.4;
  font-weight: 700;
  letter-spacing: 0.01em;
}
.lang-block > h3 { margin-top: 1.8em; font-size: 1.05rem; }
.lang-block p { margin: 0 0 1.25em; }
.lang-block ul,
.lang-block ol { margin: 0 0 1.4em; padding-left: 1.5em; }
.lang-block li { margin: 0.3em 0; }
.lang-block blockquote {
  margin: 1.8em 0;
  padding: 2px 0 2px 24px;
  border-left: 3px solid var(--teal);
  color: #434542;
  font-size: 1.03em;
}
.lang-block blockquote p { margin: 0; }
.lang-block a { color: var(--teal); text-underline-offset: 0.16em; }
.lang-block code {
  padding: 0.08em 0.28em;
  border-radius: 3px;
  background: #ece8df;
  font: 0.88em/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.language-divider {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 58px 0 42px;
  color: var(--muted);
  font: 700 0.66rem/1 var(--sans);
  letter-spacing: 0.15em;
}
.language-divider::before,
.language-divider::after {
  height: 1px;
  flex: 1;
  background: var(--line);
  content: "";
}
.colophon {
  margin-top: 96px;
  padding-top: 36px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font: 0.78rem/1.8 var(--sans);
}
.colophon .lang-zh,
.colophon .lang-en { display: block; }
.colophon .lang-en { margin-top: 14px; }
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --paper: #181a19;
    --ink: #ece9e1;
    --muted: #a8a69e;
    --line: #343734;
    --red: #dc7867;
    --teal: #71aaa2;
    --panel: rgba(24, 26, 25, 0.94);
  }
  body {
    background:
      linear-gradient(90deg, transparent 0, transparent 49.8%, rgba(220, 120, 103, 0.025) 50%, transparent 50.2%),
      var(--paper);
  }
  .mode-switch { background: #202321; }
  .toc a { color: #d4d0c7; }
  .book-subtitle,
  .description { color: #d4d0c7; }
  .lang-block blockquote { color: #d4d0c7; }
  .lang-block code { background: #292c29; }
}
@media (max-width: 900px) {
  body { font-size: 17px; }
  .site-bar { align-items: flex-start; flex-direction: column; gap: 8px; padding-block: 12px; }
  .mode-switch { position: absolute; top: 12px; right: 18px; }
  .reader-shell { display: block; padding-inline: 20px; }
  .toc-panel { position: static; max-height: none; margin-top: 22px; }
  .toc-panel summary { display: block; }
  .toc-panel:not([open]) .toc { display: none; }
  main.book { padding-top: 30px; }
  .book-cover { min-height: auto; padding: 64px 0 72px; }
  .book-cover h1 { font-size: clamp(2.4rem, 12vw, 4.5rem); }
  .chapter { padding-top: 72px; }
  .chapter:first-of-type { margin-top: 60px; }
  .chapter h1 { padding-right: 0; }
  .chapter-number { top: -24px; }
}
@media (max-width: 520px) {
  .brand span { display: none; }
  .mode-switch { top: 10px; }
  .mode-switch button { min-width: 48px; padding-inline: 8px; }
}
@media print {
  .site-bar,
  .toc-panel,
  .reading-progress,
  .language-divider { display: none !important; }
  body { background: #fff; color: #000; font-size: 11pt; }
  .reader-shell { display: block; padding: 0; }
  main.book { max-width: none; }
  .book-cover { min-height: 0; }
  .chapter { break-before: page; }
}
"""


HTML_JS = """
(() => {
  const body = document.body;
  const switchButtons = [...document.querySelectorAll("[data-set-mode]")];
  const storageKey = "villain-book-reading-mode";

  function applyMode(mode) {
    body.dataset.mode = mode;
    switchButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.setMode === mode));
    });
  }

  if (switchButtons.length) {
    const saved = localStorage.getItem(storageKey);
    applyMode(saved || "bilingual");
    switchButtons.forEach((button) => {
      button.addEventListener("click", () => {
        applyMode(button.dataset.setMode);
        localStorage.setItem(storageKey, button.dataset.setMode);
      });
    });
  }

  const progress = document.querySelector(".reading-progress");
  const updateProgress = () => {
    if (!progress) return;
    const height = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = height > 0 ? window.scrollY / height : 0;
    progress.style.width = `${Math.min(100, Math.max(0, ratio * 100))}%`;
  };
  document.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  updateProgress();

  const toc = document.querySelector(".toc-panel");
  if (toc && window.matchMedia("(max-width: 900px)").matches) toc.removeAttribute("open");
})();
"""


def render_cover(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    title = "".join(
        f'<span class="lang-{language}" lang="{"zh-Hans" if language == "zh" else "en"}">'
        f"{escape_html(title_for(book, language))}</span>"
        for language in languages
    )
    subtitle = "".join(
        f'<span class="lang-{language}" lang="{"zh-Hans" if language == "zh" else "en"}">'
        f"{escape_html(subtitle_for(book, language))}</span>"
        for language in languages
    )
    description = "".join(
        f'<span class="lang-{language}" lang="{"zh-Hans" if language == "zh" else "en"}">'
        f"{escape_html(book.metadata[f'description_{language}'])}</span>"
        for language in languages
    )
    authors = " · ".join(
        dict.fromkeys(author_for(book, language) for language in languages)
    )
    return (
        '<header class="book-cover" id="top">'
        '<p class="kicker">MONOBASE · OPEN BOOK PROJECT</p>'
        f"<h1>{title}</h1>"
        f'<p class="book-subtitle">{subtitle}</p>'
        f'<div class="cover-meta"><span>{escape_html(authors)}</span>'
        f"<span>{escape_html(edition_label(book, variant))}</span></div>"
        f'<div class="description">{description}</div>'
        "</header>"
    )


def render_colophon(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    rights = "".join(
        f'<span class="lang-{language}" lang="{"zh-Hans" if language == "zh" else "en"}">'
        f"{escape_html(book.metadata[f'rights_{language}'])}</span>"
        for language in languages
    )
    return (
        '<footer class="colophon">'
        f"<p>{rights}</p>"
        f'<p>Version {escape_html(book.metadata["edition"])} · '
        f'{escape_html(book.metadata["updated"])}</p>'
        "</footer>"
    )


def render_html_document(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    lang_attr = "zh-Hans" if variant == "zh" else ("en" if variant == "en" else "zh-Hans")
    switch = ""
    if variant == "bilingual":
        switch = (
            '<div class="mode-switch" role="group" aria-label="Language">'
            '<button type="button" data-set-mode="bilingual" aria-pressed="true">双语</button>'
            '<button type="button" data-set-mode="zh" aria-pressed="false">中文</button>'
            '<button type="button" data-set-mode="en" aria-pressed="false">EN</button>'
            "</div>"
        )
    chapters = "\n".join(render_chapter(chapter, variant) for chapter in visible_chapters(book))
    return f"""<!doctype html>
<html lang="{lang_attr}" data-variant="{variant}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="{html.escape(book.metadata['description_zh'], quote=True)}" />
  <title>{escape_html(title_for(book, languages[0]))}</title>
  <style>{HTML_CSS}</style>
</head>
<body data-mode="{'bilingual' if variant == 'bilingual' else variant}">
  <div class="reading-progress" aria-hidden="true"></div>
  <header class="site-bar">
    <a class="brand" href="#top"><strong>{escape_html(short_title_for(book, languages[0]))}</strong><span>The Villain Book</span></a>
    {switch}
  </header>
  <div class="reader-shell">
    <aside class="toc-wrap">
      <details class="toc-panel" open>
        <summary>目录 / Contents</summary>
        {toc_html(book, variant)}
      </details>
    </aside>
    <main class="book">
      {render_cover(book, variant)}
      {chapters}
      {render_colophon(book, variant)}
    </main>
  </div>
  <script>{HTML_JS}</script>
</body>
</html>
"""


def render_text_document(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    separator = "=" * 78
    output: list[str] = [separator]
    for language in languages:
        output.extend(
            [
                title_for(book, language),
                subtitle_for(book, language),
                f"{author_for(book, language)} · {edition_label(book, variant)}",
            ]
        )
        if language != languages[-1]:
            output.append("")
    output.extend([separator, "", "目录 / CONTENTS", ""])

    for part in book.parts:
        chapters = [chapter for chapter in visible_chapters(book) if chapter.part == part.id]
        if not chapters:
            continue
        output.append("")
        for language in languages:
            output.append(part_title(part, language))
        for chapter in chapters:
            number = f"{chapter.number:02d}" if chapter.number is not None else "00"
            for language in languages:
                output.append(f"{number}  {chapter_title(chapter, language)}")
        output.append("")

    for chapter in visible_chapters(book):
        output.extend(["", "", "=" * 78, ""])
        for language in languages:
            heading = chapter_title(chapter, language)
            if chapter.number is not None:
                heading = f"{chapter.number:02d}  {heading}"
            output.extend([heading, chapter_subtitle(chapter, language), ""])
            output.append(render_plain_blocks(getattr(chapter, f"content_{language}")))
            output.append("")

    output.extend(["", "=" * 78, ""])
    for language in languages:
        if language == "zh":
            output.extend(
                [
                    book.metadata["rights_zh"],
                    f"版本 {book.metadata['edition']} · {book.metadata['updated']}",
                    "",
                ]
            )
        else:
            output.extend(
                [
                    book.metadata["rights_en"],
                    f"Version {book.metadata['edition']} · {book.metadata['updated']}",
                    "",
                ]
            )
    return "\n".join(output).strip() + "\n"


def xml_escape(value: str) -> str:
    return html.escape(value, quote=True)


def epub_title_page(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    titles = "".join(
        f'<p class="cover-title lang-{language}">{xml_escape(title_for(book, language))}</p>'
        for language in languages
    )
    subtitles = "".join(
        f'<p class="cover-subtitle lang-{language}">{xml_escape(subtitle_for(book, language))}</p>'
        for language in languages
    )
    authors = " · ".join(dict.fromkeys(author_for(book, language) for language in languages))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-Hans">
<head><title>{xml_escape(short_title_for(book, languages[0]))}</title>
<link rel="stylesheet" type="text/css" href="styles.css" /></head>
<body class="cover-page">
  <div class="cover-frame">
    <p class="cover-kicker">MONOBASE · OPEN BOOK PROJECT</p>
    {titles}
    {subtitles}
    <p class="cover-author">{xml_escape(authors)}</p>
    <p class="cover-edition">{xml_escape(edition_label(book, variant))}</p>
  </div>
</body>
</html>
"""


def epub_nav(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    entries: list[str] = []
    for part in book.parts:
        chapters = [chapter for chapter in visible_chapters(book) if chapter.part == part.id]
        if not chapters:
            continue
        part_labels = " / ".join(part_title(part, language) for language in languages)
        entries.append(f"<li><span>{xml_escape(part_labels)}</span><ol>")
        for chapter in chapters:
            labels = " / ".join(chapter_title(chapter, language) for language in languages)
            entries.append(
                f'<li><a href="{chapter_anchor(chapter)}.xhtml">{xml_escape(labels)}</a></li>'
            )
        entries.append("</ol></li>")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-Hans">
<head><title>目录 / Contents</title><link rel="stylesheet" type="text/css" href="styles.css" /></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>目录 / Contents</h1>
    <ol>{''.join(entries)}</ol>
  </nav>
</body>
</html>
"""


def epub_chapter(book: Book, chapter: Chapter, variant: str) -> str:
    languages = variant_languages(variant)
    heading_parts = []
    subtitle_parts = []
    for language in languages:
        lang_attr = "zh-Hans" if language == "zh" else "en"
        heading_parts.append(
            f'<span class="lang-{language}" xml:lang="{lang_attr}">'
            f"{xml_escape(chapter_title(chapter, language))}</span>"
        )
        subtitle_parts.append(
            f'<span class="lang-{language}" xml:lang="{lang_attr}">'
            f"{xml_escape(chapter_subtitle(chapter, language))}</span>"
        )
    number = f"{chapter.number:02d}" if chapter.number is not None else "00"
    body_blocks = []
    for language in languages:
        lang_attr = "zh-Hans" if language == "zh" else "en"
        body_blocks.append(
            f'<section class="lang-block lang-{language}" xml:lang="{lang_attr}">'
            f"{render_blocks(getattr(chapter, f'content_{language}'), id_prefix=f'{chapter.id}-{language}')}</section>"
        )
    divider = (
        '<div class="language-divider">EN</div>' if variant == "bilingual" else ""
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-Hans">
<head><title>{xml_escape(chapter_title(chapter, languages[0]))}</title>
<link rel="stylesheet" type="text/css" href="styles.css" /></head>
<body>
  <section class="chapter">
    <p class="chapter-number">{number}</p>
    <h1>{'<span class="title-sep"> / </span>'.join(heading_parts)}</h1>
    <p class="chapter-subtitle">{'<span class="title-sep"> / </span>'.join(subtitle_parts)}</p>
    {divider.join(body_blocks)}
  </section>
</body>
</html>
"""


def epub_colophon(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    rights = "".join(
        f'<p class="lang-{language}">{xml_escape(book.metadata[f"rights_{language}"])}</p>'
        for language in languages
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-Hans">
<head><title>Colophon</title><link rel="stylesheet" type="text/css" href="styles.css" /></head>
<body>
  <section class="chapter colophon">
    <h1>版本 / Edition</h1>
    <p>{xml_escape(book.metadata['edition'])} · {xml_escape(book.metadata['updated'])}</p>
    {rights}
  </section>
</body>
</html>
"""


EPUB_CSS = """
@charset "utf-8";
html { font-size: 100%; }
body {
  margin: 5%;
  color: #1c1d1e;
  font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif CJK SC",
    "Source Han Serif SC", "Songti SC", Georgia, serif;
  line-height: 1.78;
}
h1, h2, h3 { line-height: 1.3; page-break-after: avoid; }
h1 { margin: 0 0 0.6em; font-size: 1.65em; }
h2 { margin: 2.2em 0 0.65em; color: #9b3529; font-size: 1.18em; }
h3 { margin-top: 1.7em; font-size: 1.05em; }
p { margin: 0 0 1.05em; text-align: justify; }
blockquote {
  margin: 1.6em 0;
  padding: 0.2em 0 0.2em 1.1em;
  border-left: 3px solid #285d57;
  color: #41423f;
}
ul, ol { margin: 0 0 1.3em; padding-left: 1.4em; }
li { margin: 0.25em 0; }
hr { margin: 2em 0; border: 0; border-top: 1px solid #ccc6bb; }
a { color: #285d57; text-decoration: underline; }
code { font-family: monospace; font-size: 0.9em; }
.chapter { page-break-before: always; }
.chapter-number {
  margin: 0;
  color: #a9a499;
  font-family: sans-serif;
  font-size: 1.6em;
  font-weight: bold;
  letter-spacing: 0.08em;
}
.chapter-subtitle { margin: -0.2em 0 2.4em; color: #66645f; font-size: 0.96em; }
.title-sep { color: #aaa49a; }
.lang-en { font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif; }
.language-divider {
  margin: 3.2em 0 2.5em;
  color: #8b877e;
  font-family: sans-serif;
  font-size: 0.68em;
  font-weight: bold;
  letter-spacing: 0.18em;
  text-align: center;
}
.cover-page {
  margin: 0;
  padding: 12% 8%;
  background: #f5f1e8;
  color: #1c1d1e;
  min-height: 80vh;
}
.cover-frame { max-width: 32em; margin: 16% auto 0; }
.cover-kicker {
  color: #9b3529;
  font-family: sans-serif;
  font-size: 0.68em;
  font-weight: bold;
  letter-spacing: 0.18em;
}
.cover-title {
  margin: 0.65em 0 0.12em;
  font-size: 2.8em;
  font-weight: 600;
  line-height: 1.08;
  text-align: left;
}
.cover-title.lang-en {
  margin-top: 0.8em;
  color: #285d57;
  font-size: 1.45em;
  line-height: 1.2;
}
.cover-subtitle {
  margin: 1.2em 0 0;
  padding-left: 0.8em;
  border-left: 3px solid #9b3529;
  color: #4a4b48;
  font-size: 0.9em;
  text-align: left;
}
.cover-author, .cover-edition {
  margin-top: 2.4em;
  color: #66645f;
  font-family: sans-serif;
  font-size: 0.68em;
  letter-spacing: 0.06em;
  text-align: left;
  text-transform: uppercase;
}
.cover-edition { margin-top: 0.6em; }
.colophon { color: #66645f; font-size: 0.9em; }
"""


def epub_toc_ncx(book: Book, variant: str) -> str:
    languages = variant_languages(variant)
    points: list[str] = []
    order = 1
    for chapter in visible_chapters(book):
        labels = " / ".join(chapter_title(chapter, language) for language in languages)
        points.append(
            f'<navPoint id="navPoint-{order}" playOrder="{order}">'
            f"<navLabel><text>{xml_escape(labels)}</text></navLabel>"
            f'<content src="{chapter_anchor(chapter)}.xhtml" />'
            "</navPoint>"
        )
        order += 1
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-Hans">
  <head>
    <meta name="dtb:uid" content="{book_identifier(book)}" />
    <meta name="dtb:depth" content="1" />
    <meta name="dtb:totalPageCount" content="0" />
    <meta name="dtb:maxPageNumber" content="0" />
  </head>
  <docTitle><text>{xml_escape(title_for(book, languages[0]))}</text></docTitle>
  <navMap>{''.join(points)}</navMap>
</ncx>
"""


def book_identifier(book: Book) -> str:
    seed = f"{book.metadata['title_zh']}|{book.metadata['title_en']}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/MonoBase/villain-book/' + seed)}"


def epub_package(book: Book, variant: str, chapter_files: Iterable[str]) -> str:
    languages = variant_languages(variant)
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />',
        '<item id="css" href="styles.css" media-type="text/css" />',
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml" />',
        '<item id="colophon" href="colophon.xhtml" media-type="application/xhtml+xml" />',
    ]
    spine = ['<itemref idref="cover" />', '<itemref idref="nav" />']
    for index, filename in enumerate(chapter_files, start=1):
        item_id = f"chapter-{index}"
        manifest.append(
            f'<item id="{item_id}" href="{filename}" media-type="application/xhtml+xml" />'
        )
        spine.append(f'<itemref idref="{item_id}" />')
    spine.append('<itemref idref="colophon" />')
    language_tags = "".join(
        f"<dc:language>{'zh-Hans' if language == 'zh' else 'en'}</dc:language>"
        for language in languages
    )
    titles = "".join(
        f'<dc:title id="title-{language}" xml:lang="{"zh-Hans" if language == "zh" else "en"}">'
        f"{xml_escape(title_for(book, language))}</dc:title>"
        for language in languages
    )
    creators = "".join(
        dict.fromkeys(
            f"<dc:creator>{xml_escape(author_for(book, language))}</dc:creator>"
            for language in languages
        )
    )
    descriptions = "".join(
        f'<dc:description xml:lang="{"zh-Hans" if language == "zh" else "en"}">'
        f"{xml_escape(book.metadata[f'description_{language}'])}</dc:description>"
        for language in languages
    )
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="zh-Hans">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_identifier(book)}</dc:identifier>
    {titles}
    {creators}
    {language_tags}
    {descriptions}
    <dc:publisher>MonoBase</dc:publisher>
    <dc:date>{book.metadata['updated']}</dc:date>
    <meta property="dcterms:modified">{modified}</meta>
    <meta name="cover" content="cover" />
  </metadata>
  <manifest>{''.join(manifest)}</manifest>
  <spine toc="ncx">{''.join(spine)}</spine>
</package>
"""


def write_epub(book: Book, variant: str, path: Path) -> None:
    chapters = visible_chapters(book)
    chapter_files = [f"{chapter_anchor(chapter)}.xhtml" for chapter in chapters]
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(
            "OEBPS/content.opf",
            epub_package(book, variant, chapter_files),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr(
            "OEBPS/nav.xhtml", epub_nav(book, variant), compress_type=zipfile.ZIP_DEFLATED
        )
        archive.writestr(
            "OEBPS/toc.ncx", epub_toc_ncx(book, variant), compress_type=zipfile.ZIP_DEFLATED
        )
        archive.writestr(
            "OEBPS/styles.css", EPUB_CSS, compress_type=zipfile.ZIP_DEFLATED
        )
        archive.writestr(
            "OEBPS/cover.xhtml",
            epub_title_page(book, variant),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr(
            "OEBPS/colophon.xhtml",
            epub_colophon(book, variant),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for chapter, filename in zip(chapters, chapter_files, strict=True):
            archive.writestr(
                f"OEBPS/{filename}",
                epub_chapter(book, chapter, variant),
                compress_type=zipfile.ZIP_DEFLATED,
            )


def write_variant(book: Book, variant: str, output_dir: Path) -> list[Path]:
    stem = f"villain-book-{variant}"
    html_path = output_dir / f"{stem}.html"
    txt_path = output_dir / f"{stem}.txt"
    epub_path = output_dir / f"{stem}.epub"

    html_path.write_text(render_html_document(book, variant), encoding="utf-8")
    txt_path.write_text(render_text_document(book, variant), encoding="utf-8-sig")
    write_epub(book, variant, epub_path)
    return [html_path, txt_path, epub_path]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(config_path: Path, output_dir: Path, variant: str) -> list[Path]:
    book = load_book(config_path)
    errors = validate_book(book, root=config_path.parent)
    if errors:
        raise ValueError("\n".join(errors))
    hydrate_content(book, root=config_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_file in output_dir.glob("villain-book-*"):
        if old_file.is_file():
            old_file.unlink()
    if (output_dir / "index.html").exists():
        (output_dir / "index.html").unlink()
    if (output_dir / "manifest.json").exists():
        (output_dir / "manifest.json").unlink()

    variants = ["zh", "en", "bilingual"] if variant == "all" else [variant]
    written: list[Path] = []
    for current in variants:
        written.extend(write_variant(book, current, output_dir))

    if "bilingual" in variants:
        shutil.copyfile(
            output_dir / "villain-book-bilingual.html", output_dir / "index.html"
        )
        written.append(output_dir / "index.html")

    manifest = {
        "book_zh": book.metadata["title_zh"],
        "book_en": book.metadata["title_en"],
        "edition": book.metadata["edition"],
        "updated": book.metadata["updated"],
        "published_chapters": [
            {
                "id": chapter.id,
                "number": chapter.number,
                "title_zh": chapter.title_zh,
                "title_en": chapter.title_en,
                "status": chapter.status,
            }
            for chapter in visible_chapters(book)
        ],
        "files": [
            {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in written
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    written.append(manifest_path)

    checksums = output_dir / "SHA256SUMS.txt"
    checksums.write_text(
        "\n".join(f"{sha256(path)}  {path.name}" for path in written) + "\n",
        encoding="utf-8",
    )
    written.append(checksums)
    return written


def print_check(config_path: Path) -> int:
    book = load_book(config_path)
    errors = validate_book(book, root=config_path.parent)
    published = visible_chapters(book)
    planned = len(book.chapters) - len(published)
    if errors:
        print("Content check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"Content check passed: {len(published)} published, "
        f"{planned} planned, 30 numbered chapters configured."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--variant",
        choices=["all", "zh", "en", "bilingual"],
        default="all",
        help="Edition to build. 'all' writes all three editions.",
    )
    parser.add_argument("--check", action="store_true", help="Validate content only.")
    args = parser.parse_args()

    config_path = args.config.resolve()
    if args.check:
        return print_check(config_path)
    try:
        files = build(config_path, args.output.resolve(), args.variant)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"Build failed:\n{exc}", file=sys.stderr)
        return 1
    for path in files:
        print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

