from app.ingestion.chunker import chunk_document
from app.ingestion.parser import build_metadata, parse

MD = """---
document_id: T-1
title: 테스트 정책
category: cs
version: "1.0"
effective_date: 2026-01-01
status: active
---

# 테스트 정책

## 첫 번째 섹션

문단 하나.

문단 둘.

## 두 번째 섹션

내용.
"""


def test_parse_markdown_front_matter():
    p = parse(MD, "t.md")
    assert p.content_type == "markdown"
    assert p.metadata["document_id"] == "T-1"
    assert p.metadata["effective_date"] == "2026-01-01"   # date → str
    assert p.text.startswith("# 테스트 정책")


def test_parse_html_to_markdown():
    html = "<html><head><title>가이드</title><meta name='document_id' content='H-1'></head><body><h1>가이드</h1><h2>절차</h2><p>첫 문단</p><ul><li>항목1</li><li>항목2</li></ul></body></html>"
    p = parse(html, "g.html")
    assert p.content_type == "html"
    assert p.metadata["document_id"] == "H-1"
    assert "# 가이드" in p.text and "## 절차" in p.text and "- 항목1" in p.text


def test_build_metadata_overrides_and_defaults():
    meta = build_metadata({"title": "A", "version": "1"}, {"title": "B", "category": ""}, fallback_title="x")
    assert meta["title"] == "B" and meta["version"] == "1" and meta["category"] is None
    assert meta["status"] == "active" and meta["language"] == "ko"
    assert build_metadata({}, None, fallback_title="환불 정책")["document_id"] == "환불-정책"


def test_chunk_by_sections():
    p = parse(MD, "t.md")
    chunks = chunk_document(p.text, title="테스트 정책", max_chars=1200)
    sections = [c.section for c in chunks]
    assert sections == ["테스트 정책 > 첫 번째 섹션", "테스트 정책 > 두 번째 섹션"]
    assert chunks[0].content.startswith("[테스트 정책 > 첫 번째 섹션]")
    assert "문단 하나." in chunks[0].content and "문단 둘." in chunks[0].content


def test_chunk_splits_long_section_with_overlap():
    body = "# 긴 문서\n\n## 섹션\n\n" + "\n\n".join(f"문장 {i}번입니다. " * 5 for i in range(40))
    chunks = chunk_document(body, title="긴 문서", max_chars=400, overlap_chars=60)
    assert len(chunks) > 3
    assert all(len(c.content) <= 480 for c in chunks)
    assert all(c.section == "긴 문서 > 섹션" for c in chunks)


def test_bm25_tokenizer_and_index():
    from app.rag.bm25 import BM25Index, rrf_fuse, tokenize

    toks = tokenize("배송비는 얼마인가요?")
    assert "배송비는" in toks and "배송" in toks and "송비" in toks  # 한글 bigram
    idx = BM25Index()
    idx.build(["배송비는 편도 3,000원입니다", "환불은 7일 이내 신청", "주문 취소는 결제 후 1시간"])
    assert idx.search("배송비 얼마")[0][0] == 0
    assert idx.search("환불 기간")[0][0] == 1
    assert idx.search("존재하지않는말")== []
    fused = rrf_fuse([[0, 1, 2], [2, 0, 1]], k=60, weights=[0.7, 0.3])
    assert fused[0][0] == 0  # dense 가중치 우세
