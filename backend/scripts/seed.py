"""샘플 문서를 색인한다:  .venv/bin/python scripts/seed.py  (서버 실행 여부와 무관하게 DB에 직접 색인)"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.services import build_services  # noqa: E402

def main() -> None:
    svc = build_services(get_settings())
    existing = {d["document_id"] for d in svc.db.list_documents()}
    for path in sorted((Path(__file__).resolve().parent.parent / "sample_docs").iterdir()):
        if path.suffix.lower() not in (".md", ".html", ".htm", ".txt"):
            continue
        doc = svc.indexer.register(path.read_text(encoding="utf-8"), filename=path.name)
        if doc["document_id"] in existing:
            print(f"skip (이미 존재): {doc['document_id']} {doc['title']}")
            svc.db.delete_document(doc["id"])
            continue
        doc = svc.indexer.index(doc["id"])
        print(f"{doc['processing_status']:8s} {doc['document_id']:12s} {doc['title']} ({doc['chunk_count']} chunks)")
    print("health:", svc.health())

if __name__ == "__main__":
    main()
