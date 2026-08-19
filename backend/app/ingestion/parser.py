"""Document Loader / Parser — Markdown(YAML front matter) 및 HTML → 정규화된 Markdown 텍스트 + 메타데이터.

PRD §9~§12: Tier 1 포맷(Markdown, HTML)을 지원하고 문서 메타데이터를 필수로 추출한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from bs4 import BeautifulSoup, NavigableString, Tag

FRONT_MATTER_RE = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

# PRD §12 필수 메타데이터 키
REQUIRED_META = ("document_id", "title", "category", "source", "version", "effective_date", "updated_at", "status", "language")


@dataclass
class ParsedDocument:
    text: str                      # 정규화된 Markdown 본문
    metadata: dict[str, Any] = field(default_factory=dict)
    content_type: str = "markdown"


def detect_content_type(filename: str | None, content: str) -> str:
    name = (filename or "").lower()
    if name.endswith((".html", ".htm")):
        return "html"
    if name.endswith((".md", ".markdown", ".txt")):
        return "markdown"
    head = content.lstrip()[:200].lower()
    if head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head:
        return "html"
    return "markdown"


def parse_markdown(content: str) -> ParsedDocument:
    meta: dict[str, Any] = {}
    body = content
    m = FRONT_MATTER_RE.match(content)
    if m:
        try:
            loaded = yaml.safe_load(m.group(1)) or {}
            if isinstance(loaded, dict):
                meta = {str(k): _norm(v) for k, v in loaded.items()}
        except yaml.YAMLError:
            meta = {}
        body = content[m.end():]
    body = _normalize_newlines(body).strip() + "\n"
    if "title" not in meta:
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if h1:
            meta["title"] = h1.group(1).strip()
    return ParsedDocument(text=body, metadata=meta, content_type="markdown")


def parse_html(content: str) -> ParsedDocument:
    """HTML → Markdown 유사 텍스트. 제목(h1~h6)/문단/목록/표 구조를 보존한다."""
    soup = BeautifulSoup(content, "html.parser")
    meta: dict[str, Any] = {}
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").lower()
        if name and tag.get("content") is not None:
            meta[name.replace(":", "_")] = tag["content"]
    if soup.title and soup.title.string:
        meta.setdefault("title", soup.title.string.strip())
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        t.decompose()
    root = soup.body or soup
    lines: list[str] = []
    _walk(root, lines)
    text = _normalize_newlines("\n".join(lines))
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    if "title" not in meta:
        h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1:
            meta["title"] = h1.group(1).strip()
    return ParsedDocument(text=text, metadata=meta, content_type="html")


def parse(content: str, filename: str | None = None) -> ParsedDocument:
    ctype = detect_content_type(filename, content)
    return parse_html(content) if ctype == "html" else parse_markdown(content)


def build_metadata(parsed_meta: dict[str, Any], overrides: dict[str, Any] | None, *, fallback_title: str) -> dict[str, Any]:
    """front matter 메타 + 업로드 폼 값(overrides, 우선) → 저장용 메타데이터."""
    meta = {**parsed_meta, **{k: v for k, v in (overrides or {}).items() if v not in (None, "")}}
    title = str(meta.get("title") or fallback_title).strip()
    return {
        "document_id": str(meta.get("document_id") or _slug(title)),
        "title": title,
        "category": _opt(meta.get("category")),
        "source": _opt(meta.get("source")) or "upload",
        "version": _opt(meta.get("version")) or "1.0",
        "effective_date": _opt(meta.get("effective_date")),
        "updated_at": _opt(meta.get("updated_at")),
        "status": (str(meta.get("status") or "active")).lower(),
        "language": _opt(meta.get("language")) or "ko",
    }


# ── helpers ──────────────────────────────────────────────────────
def _walk(node: Tag, lines: list[str]) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            s = str(child).strip()
            if s and (not lines or lines[-1] != s):
                lines.append(s)
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            lines.append("")
            lines.append("#" * level + " " + child.get_text(" ", strip=True))
            lines.append("")
        elif name in ("p", "div", "section", "article", "main", "blockquote"):
            if name == "p":
                lines.append(child.get_text(" ", strip=True))
                lines.append("")
            else:
                _walk(child, lines)
        elif name in ("ul", "ol"):
            for i, li in enumerate(child.find_all("li", recursive=False), 1):
                bullet = f"{i}." if name == "ol" else "-"
                lines.append(f"{bullet} {li.get_text(' ', strip=True)}")
            lines.append("")
        elif name == "table":
            rows = child.find_all("tr")
            for ri, tr in enumerate(rows):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                lines.append("| " + " | ".join(cells) + " |")
                if ri == 0:
                    lines.append("|" + "---|" * len(cells))
            lines.append("")
        elif name in ("br",):
            lines.append("")
        else:
            _walk(child, lines)


def _normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _norm(v: Any) -> Any:
    # YAML이 날짜를 date 객체로 파싱하므로 문자열로 통일
    return v.isoformat() if hasattr(v, "isoformat") else v


def _opt(v: Any) -> str | None:
    return None if v in (None, "") else str(v)


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title).strip("-")
    return (s or "DOC").upper()[:40]
