"""Knowledge 색인 파이프라인: Uploaded → Parsing → Chunking → Embedding → Indexed | Error (PRD §30)."""
from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

from app.core.db import Database, now_iso
from app.ingestion.chunker import chunk_document
from app.ingestion.parser import build_metadata, parse
from app.providers.embeddings import EmbeddingProvider
from app.rag.retriever import VectorStore

logger = logging.getLogger(__name__)


class Indexer:
    def __init__(self, db: Database, embedder: EmbeddingProvider, store: VectorStore, *,
                 chunk_max_chars: int = 1200, chunk_overlap_chars: int = 150):
        self.db = db
        self.embedder = embedder
        self.store = store
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap_chars = chunk_overlap_chars
        self._lock = threading.Lock()  # 임베딩 API 호출·DB 갱신 직렬화

    # ── 등록 ──────────────────────────────────────────────────────
    def register(self, content: str, *, filename: str | None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """원문을 저장하고 uploaded 상태의 문서 레코드를 만든다(색인은 별도 호출)."""
        parsed = parse(content, filename)
        fallback_title = (filename or "untitled").rsplit(".", 1)[0]
        meta = build_metadata(parsed.metadata, overrides, fallback_title=fallback_title)
        doc = self.db.insert_document({
            **meta,
            "filename": filename,
            "content_type": parsed.content_type,
            "raw_text": content,
            "processing_status": "uploaded",
        })
        return doc

    # ── 색인 ──────────────────────────────────────────────────────
    def index(self, doc_pk: str) -> dict[str, Any]:
        doc = self.db.get_document(doc_pk)
        if not doc:
            raise KeyError(doc_pk)
        with self._lock:
            try:
                self.db.update_document(doc_pk, processing_status="parsing", error_message=None)
                parsed = parse(doc["raw_text"], doc.get("filename"))

                self.db.update_document(doc_pk, processing_status="chunking")
                chunks = chunk_document(parsed.text, title=doc["title"],
                                        max_chars=self.chunk_max_chars, overlap_chars=self.chunk_overlap_chars)
                if not chunks:
                    raise ValueError("문서에서 색인할 본문을 찾지 못했습니다.")

                self.db.update_document(doc_pk, processing_status="embedding")
                vecs = self.embedder.embed_documents([c.content for c in chunks])
                rows = [
                    {
                        "id": f"{doc['document_id']}-{c.chunk_index:03d}-{doc_pk[:6]}",
                        "chunk_index": c.chunk_index,
                        "section": c.section,
                        "content": c.content,
                        "embedding": np.asarray(vecs[i], dtype=np.float32).tobytes(),
                        "embedding_model": self.embedder.name,
                    }
                    for i, c in enumerate(chunks)
                ]
                self.db.replace_chunks(doc_pk, rows)
                self.db.update_document(doc_pk, processing_status="indexed", indexed_at=now_iso())
            except Exception as e:
                logger.exception("색인 실패: %s", doc_pk)
                self.db.update_document(doc_pk, processing_status="error", error_message=str(e)[:500])
            finally:
                self.store.invalidate()
        return self.db.get_document(doc_pk)  # type: ignore[return-value]

    def index_async(self, doc_pk: str) -> None:
        threading.Thread(target=self.index, args=(doc_pk,), daemon=True).start()
