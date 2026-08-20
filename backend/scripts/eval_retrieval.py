"""Retrieval 평가 (PRD §52: 골든 데이터셋, Recall@5) —

  .venv/bin/python scripts/eval_retrieval.py [--golden eval/golden.jsonl] [--top-k 5] [--mode hybrid|dense]

문서 단위 Recall@1/3/5 + MRR@5 를 계산한다. DATABASE_URL/DATABASE_PATH·임베딩 키는 서버와 동일하게 env 로 준다.
색인된 문서가 골든셋의 expected_document_id 를 포함해야 의미가 있다(sample_docs 는 scripts/seed.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.services import build_services  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(Path(__file__).resolve().parent.parent / "eval" / "golden.jsonl"))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--mode", choices=["hybrid", "dense"], default=None, help="미지정 시 서버 설정(RETRIEVAL_MODE)")
    args = ap.parse_args()

    svc = build_services(get_settings())
    if args.mode:
        svc.retriever.mode = args.mode
    rows = [json.loads(l) for l in Path(args.golden).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        print("golden set is empty");  return 2

    indexed_ids = {d["document_id"] for d in svc.db.list_documents() if d["processing_status"] == "indexed" and d["status"] == "active"}
    missing = {r["expected_document_id"] for r in rows} - indexed_ids
    if missing:
        print(f"⚠️  색인에 없는 정답 문서: {sorted(missing)} — 해당 항목은 실패로 집계됩니다")

    hits = {1: 0, 3: 0, 5: 0}
    mrr = 0.0
    print(f"\n{'rank':>4}  {'top':>6}  query")
    for r in rows:
        res = svc.retriever.retrieve(r["query"], top_k=max(args.top_k, 5))
        docs: list[str] = []
        for c in res.chunks:
            if c.document_id not in docs:
                docs.append(c.document_id)
        rank = docs.index(r["expected_document_id"]) + 1 if r["expected_document_id"] in docs else None
        for k in hits:
            if rank is not None and rank <= k:
                hits[k] += 1
        if rank:
            mrr += 1.0 / rank
        top = res.chunks[0].score if res.chunks else 0.0
        print(f"{str(rank) if rank else '-':>4}  {top:>6.3f}  {r['query']}  ({r.get('note','')})")

    n = len(rows)
    print(f"\nmode={svc.retriever.mode} · embedding={svc.embedder.name} · threshold={svc.settings.score_threshold} · n={n}")
    for k in (1, 3, 5):
        print(f"  Recall@{k}: {hits[k]}/{n} = {hits[k]/n*100:.1f}%" + ("   ← KPI 목표 ≥ 90%" if k == 5 else ""))
    print(f"  MRR@5   : {mrr/n:.3f}")
    return 0 if hits[5] / n >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
