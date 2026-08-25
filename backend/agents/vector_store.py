"""Dual-embedding Pinecone vector store for the RAG knowledge base.

Strategy: one 768-dim serverless index (`reconloop-rag`). Primary embeddings
come from BAAI/bge-base-en-v1.5 (768-d) into the `bge-vectors` namespace; if
the HF Inference API call fails, all-MiniLM-L6-v2 (384-d) vectors are
zero-padded to 768-d and stored in the `minilm-vectors` namespace. Queries use
whichever backend served the embedding, so namespaces stay consistent.

(Nomic nomic-embed-text-v1.5 was the planned primary but is no longer served
by the HF Inference API - see changes.md 2026-08-25. bge-base-en-v1.5 is the
verified 768-dim replacement.)

Graceful offline mode: missing keys or API failures log warnings and return
empty results - never crash the pipeline.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone, ServerlessSpec

logger = logging.getLogger(__name__)

PRIMARY_EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
FALLBACK_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
PRIMARY_NAMESPACE = "bge-vectors"
FALLBACK_NAMESPACE = "minilm-vectors"
DEFAULT_INDEX_NAME = "reconloop-rag"
INDEX_DIMENSION = 768
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_CHUNK_SIZE_CHARS = 1000
_CHUNK_OVERLAP_CHARS = 100


class HuggingFaceDualEmbeddings(Embeddings):
    """LangChain Embeddings over the HF Inference API with model fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        primary_model: str = PRIMARY_EMBEDDING_MODEL,
        fallback_model: str = FALLBACK_EMBEDDING_MODEL,
    ):
        load_dotenv()
        key = (
            api_key or os.getenv("HUGGING_FACE_API_KEY") or os.getenv("HF_TOKEN") or ""
        ).strip()
        self.client = InferenceClient(api_key=key) if key else None
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.active_backend = "bge"

    @property
    def is_available(self) -> bool:
        return self.client is not None

    @staticmethod
    def _extract_vector(raw) -> list[float]:
        if isinstance(raw, list) and raw and isinstance(raw[0], (list, tuple)):
            raw = raw[0]
        return [float(x) for x in raw]

    def _embed_with_model(self, model: str, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            raw = self.client.feature_extraction(text=text, model=model)
            vectors.append(self._extract_vector(raw))
        return vectors

    def _embed(
        self, texts: list[str], query_prefix_for_primary: str
    ) -> list[list[float]]:
        if not self.client:
            raise RuntimeError("HUGGING_FACE_API_KEY not configured")
        last_error: Exception | None = None
        backends = (
            (self.primary_model, "bge", query_prefix_for_primary),
            (self.fallback_model, "minilm", ""),
        )
        for model, backend, prefix in backends:
            try:
                prepared = [f"{prefix}{text}" if prefix else text for text in texts]
                vectors = self._embed_with_model(model, prepared)
                self.active_backend = backend
                if backend == "minilm":
                    vectors = [v + [0.0] * (INDEX_DIMENSION - len(v)) for v in vectors]
                return vectors
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Embedding with %s failed (%s); trying fallback", model, exc
                )
        raise RuntimeError(f"All embedding models failed; last error: {last_error}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(list(texts), query_prefix_for_primary="")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], query_prefix_for_primary=BGE_QUERY_PREFIX)[0]


def _chunk_text(text: str, max_chars: int = _CHUNK_SIZE_CHARS) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=_CHUNK_OVERLAP_CHARS,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


class VectorStore:
    def __init__(
        self,
        api_key: str | None = None,
        hf_api_key: str | None = None,
        index_name: str = DEFAULT_INDEX_NAME,
        create_if_missing: bool = True,
    ):
        load_dotenv()
        self.index_name = index_name
        self.embeddings = HuggingFaceDualEmbeddings(api_key=hf_api_key)
        self.pc = None
        self.index = None
        key = (api_key or os.getenv("PINECONE_API_KEY") or "").strip()
        if not key:
            logger.warning("PINECONE_API_KEY not configured - vector store offline")
            return
        try:
            self.pc = Pinecone(api_key=key)
            self.index = self._connect_index(create_if_missing)
        except Exception as exc:
            logger.warning(
                "Pinecone initialization failed (%s) - vector store offline", exc
            )
            self.pc = None
            self.index = None

    def _connect_index(self, create_if_missing: bool):
        existing = self.pc.list_indexes().names()
        if self.index_name not in existing:
            if not create_if_missing:
                return None
            self.pc.create_index(
                name=self.index_name,
                dimension=INDEX_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        return self.pc.Index(self.index_name)

    @property
    def is_connected(self) -> bool:
        return self.index is not None

    def _namespace(self) -> str:
        return (
            PRIMARY_NAMESPACE
            if self.embeddings.active_backend == "bge"
            else FALLBACK_NAMESPACE
        )

    def upsert_texts(self, docs: list[dict]) -> int:
        """Upsert [{"id", "text", "metadata"}]; returns count written (0 on failure)."""
        if not self.is_connected or not self.embeddings.is_available or not docs:
            return 0
        try:
            vectors = self.embeddings.embed_documents([d["text"] for d in docs])
            namespace = self._namespace()
            items = [
                (doc["id"], vector, {**doc.get("metadata", {}), "text": doc["text"]})
                for doc, vector in zip(docs, vectors)
            ]
            self.index.upsert(vectors=items, namespace=namespace)
            return len(items)
        except Exception as exc:
            logger.warning("Pinecone upsert failed: %s", exc)
            return 0

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        """Semantic search over policy docs; returns [{"text", "source", "score"}]."""
        if (
            not self.is_connected
            or not self.embeddings.is_available
            or not query.strip()
        ):
            return []
        try:
            vector = self.embeddings.embed_query(query)
            response = self.index.query(
                vector=vector,
                top_k=top_k,
                include_metadata=True,
                namespace=self._namespace(),
            )
            return [
                {
                    "text": (match.metadata or {}).get("text", ""),
                    "source": (match.metadata or {}).get("source", "unknown"),
                    "score": float(match.score or 0.0),
                }
                for match in (response.matches or [])
            ]
        except Exception as exc:
            logger.warning("Pinecone search failed: %s", exc)
            return []

    def clear_namespaces(self) -> bool:
        """Delete every vector in both managed namespaces (for clean reseeds)."""
        if not self.is_connected:
            return False
        try:
            for namespace in (PRIMARY_NAMESPACE, FALLBACK_NAMESPACE):
                self.index.delete(delete_all=True, namespace=namespace)
            return True
        except Exception as exc:
            logger.warning("Pinecone namespace clear failed: %s", exc)
            return False

    def seed_from_directory(self, policies_dir: str) -> int:
        """Chunk and upsert every .md file in the directory; returns chunks written."""
        path = Path(policies_dir)
        if not path.exists():
            logger.warning("Policies directory not found: %s", policies_dir)
            return 0
        docs: list[dict] = []
        for md_file in sorted(path.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            for chunk_index, chunk in enumerate(_chunk_text(content)):
                docs.append(
                    {
                        "id": f"{md_file.name}::{chunk_index}",
                        "text": chunk,
                        "metadata": {"source": md_file.name, "chunk": chunk_index},
                    }
                )
        return self.upsert_texts(docs)


if __name__ == "__main__":
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    policies = (
        sys.argv[1] if len(sys.argv) > 1 else str(project_root / "data" / "policies")
    )
    store = VectorStore()
    if not store.is_connected:
        print("Pinecone not configured - cannot seed knowledge base")
        raise SystemExit(1)
    if not store.embeddings.is_available:
        print("HUGGING_FACE_API_KEY not configured - cannot embed documents")
        raise SystemExit(1)
    if store.clear_namespaces():
        print("Cleared existing namespaces for a clean reseed")
    written = store.seed_from_directory(policies)
    print(f"Seeded {written} chunks from {policies} (namespace={store._namespace()})")
