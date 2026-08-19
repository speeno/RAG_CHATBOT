"""Semantic + Structure Based Chunking (PRD §13~§14).

Document → Section(#/##/###) → Paragraph 구조를 따라 하나의 의미 단위로 청크를 만든다.
- 섹션 하나가 chunk_max_chars 이하이면 그대로 하나의 청크
- 크면 문단 단위로 누적하며 분할하고, 인접 청크 사이에 overlap을 둔다
- 모든 청크는 상위 제목 경로(section)를 유지하고, 본문 앞에 "제목 > 소제목" 헤더를 붙여 검색 문맥을 보강한다
한국어 기준 1 token ≈ 1.5~2 chars 이므로 기본값 1200 chars ≈ 400~800 tokens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass
class Chunk:
    chunk_index: int
    section: str          # "환불 정책 > 환불 가능 기간"
    content: str          # 검색/LLM 컨텍스트에 쓰이는 본문(헤더 포함)


@dataclass
class _Section:
    path: list[str]
    paragraphs: list[str]


def split_sections(text: str) -> list[_Section]:
    sections: list[_Section] = []
    path: list[str] = []
    buf: list[str] = []
    in_code = False

    def flush() -> None:
        paras = _paragraphs("\n".join(buf))
        if paras:
            sections.append(_Section(path=list(path), paragraphs=paras))
        buf.clear()

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            buf.append(line)
            continue
        m = None if in_code else HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            path = path[: level - 1] + [title]
            continue
        buf.append(line)
    flush()
    return sections


def _paragraphs(block: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", block)]
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        # 목록/표는 줄 단위로 붙어 있으므로 그대로 하나의 문단으로 취급
        out.append(p)
    return out


def chunk_document(text: str, *, title: str, max_chars: int = 1200, overlap_chars: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec in split_sections(text):
        section_label = " > ".join(sec.path) if sec.path else title
        header = _header(title, sec.path)
        budget = max(200, max_chars - len(header))
        pieces = _pack(sec.paragraphs, budget, overlap_chars)
        for piece in pieces:
            chunks.append(Chunk(chunk_index=len(chunks), section=section_label, content=f"{header}\n{piece}".strip()))
    if not chunks and text.strip():
        chunks.append(Chunk(0, title, f"{_header(title, [])}\n{text.strip()}"))
    return chunks


def _header(title: str, path: list[str]) -> str:
    parts = [title] + [p for p in path if p != title]
    return "[" + " > ".join(parts) + "]"


def _pack(paragraphs: list[str], budget: int, overlap: int) -> list[str]:
    """문단을 budget 이내로 누적. 단일 문단이 budget을 넘으면 문장 단위로 재분할."""
    units: list[str] = []
    for p in paragraphs:
        if len(p) <= budget:
            units.append(p)
        else:
            units.extend(_split_long(p, budget))
    pieces: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for u in units:
        add = len(u) + (2 if cur else 0)
        if cur and cur_len + add > budget:
            pieces.append("\n\n".join(cur))
            # overlap: 직전 조각의 끝부분을 다음 조각 앞에 이어 붙임
            tail = _tail("\n\n".join(cur), overlap)
            cur = [tail, u] if tail else [u]
            cur_len = sum(len(x) for x in cur) + 2 * (len(cur) - 1)
        else:
            cur.append(u)
            cur_len += add
    if cur:
        pieces.append("\n\n".join(cur))
    return pieces


def _split_long(p: str, budget: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?。？！])\s+|(?<=다\.)\s*", p)
    out: list[str] = []
    cur = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(s) > budget:  # 문장 자체가 너무 길면 강제 분할
            if cur:
                out.append(cur)
                cur = ""
            out.extend(s[i:i + budget] for i in range(0, len(s), budget))
            continue
        if cur and len(cur) + 1 + len(s) > budget:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _tail(text: str, n: int) -> str:
    if n <= 0 or len(text) <= n:
        return "" if n <= 0 else text
    tail = text[-n:]
    # 단어/문장 경계에서 시작하도록 다듬기
    cut = re.search(r"[\s.。!?]", tail)
    return tail[cut.end():].strip() if cut else tail.strip()
