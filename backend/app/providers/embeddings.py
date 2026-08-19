"""Embedding 추상화 (PRD §15: 모델 교체 가능하도록 추상화).

- VoyageEmbedding : Voyage AI REST (voyage-3, 한국어/다국어 성능 우수) — VOYAGE_API_KEY 필요
- LocalEmbedding  : sentence-transformers (예: intfloat/multilingual-e5-small) — 선택 설치
- HashEmbedding   : 문자 n-gram 해싱 벡터. API 키 없이 동작하는 로컬 폴백(어휘 기반). 데모/테스트용.
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Sequence

import httpx
import numpy as np


class EmbeddingProvider(ABC):
    name: str = "base"
    dim: int = 0

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


# ── Voyage AI ────────────────────────────────────────────────────
class VoyageEmbedding(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "voyage-3", timeout: float = 60.0):
        self.name = f"voyage:{model}"
        self.model = model
        self._client = httpx.Client(
            base_url="https://api.voyageai.com/v1",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        self.dim = 1024

    def _embed(self, texts: Sequence[str], input_type: str) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = list(texts[i:i + 64])
            r = self._client.post("/embeddings", json={"input": batch, "model": self.model, "input_type": input_type})
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        arr = np.asarray(out, dtype=np.float32)
        self.dim = arr.shape[1]
        return _l2norm(arr)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "query")[0]


# ── OpenAI ───────────────────────────────────────────────────────
class OpenAIEmbedding(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.name = f"openai:{model}"
        self.dim = 1536 if "small" in model else 3072

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = [t.replace("\n", " ") for t in texts[i:i + 100]]
            resp = self._client.embeddings.create(input=batch, model=self.model)
            out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        arr = np.asarray(out, dtype=np.float32) if out else np.zeros((0, self.dim), dtype=np.float32)
        if arr.size:
            self.dim = arr.shape[1]
        return _l2norm(arr)


# ── sentence-transformers (선택) ────────────────────────────────
class LocalEmbedding(EmbeddingProvider):
    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("sentence-transformers 미설치: `uv pip install -e '.[local-embeddings]'`") from e
        self.name = f"local:{model_name}"
        self._model = SentenceTransformer(model_name)
        self._is_e5 = "e5" in model_name.lower()
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        prefix = "passage: " if self._is_e5 else ""
        arr = self._model.encode([prefix + t for t in texts], normalize_embeddings=True)
        return np.asarray(arr, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        prefix = "query: " if self._is_e5 else ""
        return np.asarray(self._model.encode([prefix + text], normalize_embeddings=True)[0], dtype=np.float32)


# ── Hash n-gram (오프라인 폴백) ─────────────────────────────────
_TOKEN_RE = re.compile(r"[0-9a-z]+|[가-힣]+")
# 한국어 조사/어미 간이 제거(긴 것부터)
_KO_SUFFIXES = sorted(
    ["인가요", "한가요", "되나요", "하나요", "습니까", "습니다", "입니다", "합니다", "됩니다", "에서는", "으로는", "까지는",
     "부터는", "이에요", "예요", "나요", "까요", "죠", "에서", "으로", "부터", "까지", "에게", "한테", "이나", "이든",
     "은", "는", "이", "가", "을", "를", "의", "에", "로", "과", "와", "도", "만", "요"],
    key=len, reverse=True,
)
_KO_STOP = {"경우", "있", "수", "것", "등", "및", "또는", "그리고", "해당", "관련", "대한", "위해", "때", "후", "전"}


def _stem_ko(tok: str) -> str:
    for suf in _KO_SUFFIXES:
        if len(tok) - len(suf) >= 2 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


class HashEmbedding(EmbeddingProvider):
    """문자 2-gram + 어간 토큰을 해싱한 비음수 희소 벡터(정규화). 의미 유사도는 약하지만 어휘 일치 검색에는 충분하다."""

    def __init__(self, dim: int = 4096):
        self.name = f"hash:ngram-{dim}"
        self.dim = dim

    @staticmethod
    def _features(text: str) -> dict[str, float]:
        feats: dict[str, float] = {}

        def add(k: str, w: float) -> None:
            feats[k] = feats.get(k, 0.0) + w

        for tok in _TOKEN_RE.findall(text.lower()):
            if re.fullmatch(r"[가-힣]+", tok):
                stem = _stem_ko(tok)
                if stem in _KO_STOP or len(stem) < 2:
                    continue
                add(f"w:{stem}", 2.0)
                for i in range(len(stem) - 1):
                    add(f"g2:{stem[i:i + 2]}", 1.0)
                if len(stem) >= 4:
                    for i in range(len(stem) - 2):
                        add(f"g3:{stem[i:i + 3]}", 0.5)
            else:
                add(f"w:{tok}", 2.0)
        return feats

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for k, cnt in self._features(text).items():
            h = int(hashlib.blake2b(k.encode(), digest_size=8).hexdigest(), 16)
            v[h % self.dim] += 1.0 + math.log(cnt)
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)


def _l2norm(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def build_embedding_provider(kind: str, *, voyage_api_key: str | None = None, voyage_model: str = "voyage-3",
                             openai_api_key: str | None = None, openai_model: str = "text-embedding-3-small",
                             local_model: str = "intfloat/multilingual-e5-small") -> EmbeddingProvider:
    if kind == "voyage":
        if not voyage_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=voyage 이지만 VOYAGE_API_KEY가 없습니다.")
        return VoyageEmbedding(voyage_api_key, voyage_model)
    if kind == "openai":
        if not openai_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=openai 이지만 OPENAI_API_KEY(또는 키 파일)가 없습니다.")
        return OpenAIEmbedding(openai_api_key, openai_model)
    if kind == "local":
        return LocalEmbedding(local_model)
    if kind == "hash":
        return HashEmbedding()
    raise ValueError(f"unknown embedding provider: {kind}")
