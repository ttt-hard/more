"""检索服务多路实现。

`LexicalRetrievalService` 直接复用 SearchService 的词法检索；
`EmbeddingRetrievalService` 用 `HashEmbeddingBackend`（确定性哈希降维）
或可选的 `FastEmbedProvider` 做余弦相似；`HybridRetrievalService` 把
多路 backend 结果用 `ReciprocalRankFusionRanker`（RRF）融合。
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import replace
from typing import Protocol

from ..domain import SearchHit
from ..workspace_fs import WorkspaceFS
from ..notes import NoteService
from ..search import SearchService

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}")


class RetrievalService(Protocol):
    def retrieve(self, query: str, limit: int = 10) -> list[SearchHit]: ...


class RetrievalRanker(Protocol):
    def rerank(self, query: str, result_sets: list[list[SearchHit]], limit: int) -> list[SearchHit]: ...


class EmbeddingProvider(Protocol):
    def encode(self, text: str) -> list[float]: ...


class HashEmbeddingBackend:
    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 else -1.0
            weight = 1.0 + min(len(token) / 8.0, 1.0)
            vector[bucket] += sign * weight
            if len(token) >= 4:
                feature = f"{token[:2]}::{token[-2:]}"
                feature_digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                feature_bucket = int.from_bytes(feature_digest[:4], "big") % self.dimensions
                feature_sign = 1.0 if feature_digest[4] % 2 else -1.0
                vector[feature_bucket] += feature_sign * 0.5

        magnitude = math.sqrt(sum(component * component for component in vector))
        if magnitude <= 0:
            return vector
        return [component / magnitude for component in vector]

    def _tokenize(self, text: str) -> list[str]:
        return [match.group(0).casefold() for match in TOKEN_PATTERN.finditer(text)]


class FastEmbedProvider:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        try:
            from fastembed import TextEmbedding  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("fastembed is not installed") from exc
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def encode(self, text: str) -> list[float]:
        iterator = self._model.embed([text])
        vector = next(iter(iterator), None)
        if vector is None:
            return []
        return list(vector.tolist() if hasattr(vector, "tolist") else vector)


def build_embedding_provider(
    backend: str = "hash",
    *,
    fastembed_model: str = "BAAI/bge-small-en-v1.5",
) -> EmbeddingProvider:
    normalized = backend.strip().casefold()
    if normalized == "fastembed":
        return FastEmbedProvider(model_name=fastembed_model)
    if normalized != "hash":
        raise ValueError(f"Unsupported embedding backend: {backend}")
    return HashEmbeddingBackend()


class EmbeddingRetrievalService:
    def __init__(self, search_service: SearchService, encoder: EmbeddingProvider | None = None) -> None:
        self.search_service = search_service
        self.encoder = encoder or HashEmbeddingBackend()
        self._vector_cache: dict[str, tuple[float, ...]] = {}

    def retrieve(self, query: str, limit: int = 10) -> list[SearchHit]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return []

        query_vector = self._encode_text(normalized_query)
        scored_hits: list[SearchHit] = []
        for chunk in self.search_service.load_indexed_chunks():
            searchable_text = "\n".join(
                [
                    str(chunk["title"]),
                    " ".join(str(tag) for tag in chunk["tags"]),
                    str(chunk["summary"]),
                    str(chunk["text"]),
                ]
            ).strip()
            if not searchable_text:
                continue
            score = self._cosine_similarity(query_vector, self._encode_text(searchable_text))
            if score <= 0:
                continue
            scored_hits.append(
                SearchHit(
                    path=str(chunk["path"]),
                    kind=str(chunk["kind"]),
                    title=str(chunk["title"]),
                    score=score * 10.0,
                    snippet=self._make_snippet(str(chunk["text"]), normalized_query),
                    chunk_id="" if chunk.get("chunk_id") is None else str(chunk.get("chunk_id")),
                    section=str(chunk.get("section") or ""),
                    token_count=int(chunk.get("token_count") or 0),
                    start_offset=int(chunk.get("start_offset") or 0),
                )
            )

        return sorted(scored_hits, key=lambda hit: (-hit.score, hit.path))[:limit]

    def _encode_text(self, text: str) -> tuple[float, ...]:
        cached = self._vector_cache.get(text)
        if cached is not None:
            return cached
        vector = tuple(self.encoder.encode(text))
        self._vector_cache[text] = vector
        return vector

    def _cosine_similarity(self, left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            return 0.0
        return sum(l * r for l, r in zip(left, right, strict=False))

    def _make_snippet(self, text: str, query: str) -> str:
        lowered = text.casefold()
        query_tokens = [match.group(0).casefold() for match in TOKEN_PATTERN.finditer(query)] or [query.casefold()]
        first_index = min((lowered.find(token) for token in query_tokens if lowered.find(token) != -1), default=0)
        start = max(first_index - 80, 0)
        end = min(first_index + 200, len(text))
        snippet = text[start:end].strip().replace("\n", " ")
        return snippet[:240]


class LexicalRetrievalService:
    def __init__(self, service: SearchService) -> None:
        self.service = service

    def retrieve(self, query: str, limit: int = 10) -> list[SearchHit]:
        return self.service.search(query, limit=limit)


class HybridRetrievalService:
    def __init__(
        self,
        backends: list[RetrievalService],
        *,
        ranker: RetrievalRanker | None = None,
    ) -> None:
        self.backends = backends
        self.ranker = ranker

    def retrieve(self, query: str, limit: int = 10) -> list[SearchHit]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return []

        candidate_limit = max(limit, min(50, limit * 2))
        result_sets: list[list[SearchHit]] = []
        for backend in self.backends:
            result_sets.append(backend.retrieve(normalized_query, limit=candidate_limit))

        if self.ranker is not None:
            return self.ranker.rerank(normalized_query, result_sets, limit)[:limit]
        return self._merge_hits([hit for result_set in result_sets for hit in result_set])[:limit]

    def _merge_hits(self, hits: list[SearchHit]) -> list[SearchHit]:
        merged_by_path: dict[str, SearchHit] = {}
        for hit in hits:
            existing = merged_by_path.get(hit.path)
            if existing is None or hit.score > existing.score:
                merged_by_path[hit.path] = hit
        return sorted(merged_by_path.values(), key=lambda hit: (-hit.score, hit.path))


def build_default_retrieval_service(
    fs: WorkspaceFS,
    *,
    note_service: NoteService | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> RetrievalService:
    note_service = note_service or NoteService(fs)
    search_service = SearchService(fs, note_service=note_service)
    lexical_service = LexicalRetrievalService(search_service)
    embedding_service = EmbeddingRetrievalService(
        search_service,
        encoder=embedding_provider or build_embedding_provider("hash"),
    )
    return HybridRetrievalService([lexical_service, embedding_service], ranker=ReciprocalRankFusionRanker())


class ReciprocalRankFusionRanker:
    def __init__(self, constant: float = 60.0, backend_weights: list[float] | None = None) -> None:
        self.constant = constant
        self.backend_weights = backend_weights or []

    def rerank(self, query: str, result_sets: list[list[SearchHit]], limit: int) -> list[SearchHit]:
        del query
        fused: dict[str, dict[str, object]] = {}
        for backend_index, hits in enumerate(result_sets):
            backend_weight = self.backend_weights[backend_index] if backend_index < len(self.backend_weights) else 1.0
            for rank, hit in enumerate(hits, start=1):
                fused_entry = fused.setdefault(hit.path, {"hit": hit, "score": 0.0})
                fused_entry["score"] = float(fused_entry["score"]) + backend_weight / (self.constant + rank)
                if hit.score > fused_entry["hit"].score:
                    fused_entry["hit"] = hit

        reranked = [replace(entry["hit"], score=float(entry["score"])) for entry in fused.values()]
        return sorted(reranked, key=lambda hit: (-hit.score, hit.path))[:limit]


__all__ = [
    "HybridRetrievalService",
    "EmbeddingRetrievalService",
    "EmbeddingProvider",
    "FastEmbedProvider",
    "LexicalRetrievalService",
    "HashEmbeddingBackend",
    "ReciprocalRankFusionRanker",
    "RetrievalRanker",
    "RetrievalService",
    "build_embedding_provider",
    "build_default_retrieval_service",
]
