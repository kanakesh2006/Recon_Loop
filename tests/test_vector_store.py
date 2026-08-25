from types import SimpleNamespace

from backend.agents.vector_store import (
    FALLBACK_NAMESPACE,
    INDEX_DIMENSION,
    PRIMARY_NAMESPACE,
    HuggingFaceDualEmbeddings,
    VectorStore,
)


class FakeHFPrimary:
    def feature_extraction(self, text, model):
        if "MiniLM" not in model:
            return [0.25] * INDEX_DIMENSION
        return [0.5] * 384


class FakeHFPrimaryDown:
    def feature_extraction(self, text, model):
        if "MiniLM" not in model:
            raise RuntimeError("rate limited")
        return [0.5] * 384


def test_embeddings_primary_no_padding():
    embeddings = HuggingFaceDualEmbeddings(api_key="k")
    embeddings.client = FakeHFPrimary()

    vector = embeddings.embed_query("why is this order short")

    assert len(vector) == INDEX_DIMENSION
    assert embeddings.active_backend == "bge"


def test_embeddings_query_prefix_for_primary_and_plain_documents():
    embeddings = HuggingFaceDualEmbeddings(api_key="k")

    class Recording(FakeHFPrimary):
        calls = []

        def feature_extraction(self, text, model):
            Recording.calls.append(text)
            return super().feature_extraction(text, model)

    embeddings.client = Recording()
    embeddings.embed_query("fee rounding")

    assert Recording.calls[0] == (
        "Represent this sentence for searching relevant passages: fee rounding"
    )

    embeddings.embed_documents(["policy text"])

    assert Recording.calls[-1] == "policy text"


def test_embeddings_fallback_minilm_zero_padded():
    embeddings = HuggingFaceDualEmbeddings(api_key="k")
    embeddings.client = FakeHFPrimaryDown()

    vectors = embeddings.embed_documents(["hello world"])

    assert len(vectors) == 1
    assert len(vectors[0]) == INDEX_DIMENSION
    assert all(v == 0.0 for v in vectors[0][384:])
    assert vectors[0][:384] == [0.5] * 384
    assert embeddings.active_backend == "minilm"


def test_embeddings_unavailable_raises(monkeypatch):
    import pytest

    monkeypatch.setattr("backend.agents.vector_store.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("HUGGING_FACE_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    embeddings = HuggingFaceDualEmbeddings(api_key="")
    assert embeddings.is_available is False
    with pytest.raises(RuntimeError):
        embeddings.embed_query("anything")


def test_vector_store_offline_mode(monkeypatch):
    monkeypatch.setattr("backend.agents.vector_store.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.delenv("HUGGING_FACE_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    store = VectorStore()

    assert store.is_connected is False
    assert store.embeddings.is_available is False
    assert store.search("anything") == []
    assert store.upsert_texts([{"id": "a", "text": "t"}]) == 0
    assert store.seed_from_directory("no/such/dir") == 0


class FakeIndex:
    def __init__(self):
        self.upserts = []
        self.queries = []

    def upsert(self, vectors, namespace):
        self.upserts.append((vectors, namespace))
        return SimpleNamespace(upserted_count=len(vectors))

    def query(self, vector, top_k, include_metadata, namespace):
        self.queries.append({"namespace": namespace, "top_k": top_k})
        return SimpleNamespace(
            matches=[
                SimpleNamespace(
                    metadata={"text": "fee text", "source": "fee_schedule.md"},
                    score=0.93,
                ),
                SimpleNamespace(
                    metadata={
                        "text": "chargeback text",
                        "source": "chargeback_policy.md",
                    },
                    score=0.81,
                ),
            ]
        )


class FakeIndexList:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)


class FakePinecone:
    last_instance = None
    initial_names: list[str] = []

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.index_list = FakeIndexList(self.initial_names)
        self.created_kwargs = None
        self.fake_index = FakeIndex()
        FakePinecone.last_instance = self

    def list_indexes(self):
        return self.index_list

    def create_index(self, **kwargs):
        self.created_kwargs = kwargs
        self.index_list._names.append(kwargs["name"])

    def Index(self, name):
        return self.fake_index


def _stub_embeddings(backend="bge"):
    return SimpleNamespace(
        is_available=True,
        active_backend=backend,
        embed_query=lambda q: [0.1] * INDEX_DIMENSION,
        embed_documents=lambda texts: [[0.1] * INDEX_DIMENSION for _ in texts],
    )


def test_vector_store_search_and_upsert_primary_namespace(monkeypatch):
    monkeypatch.setattr("backend.agents.vector_store.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr("backend.agents.vector_store.Pinecone", FakePinecone)

    store = VectorStore(api_key="test-key")
    store.embeddings = _stub_embeddings("bge")

    assert store.is_connected is True
    assert FakePinecone.last_instance.created_kwargs["dimension"] == INDEX_DIMENSION

    written = store.upsert_texts(
        [
            {
                "id": "fee_schedule.md::0",
                "text": "fee text",
                "metadata": {"source": "fee_schedule.md"},
            }
        ]
    )
    assert written == 1
    vectors, namespace = FakePinecone.last_instance.fake_index.upserts[0]
    assert namespace == PRIMARY_NAMESPACE
    assert vectors[0][0] == "fee_schedule.md::0"
    assert vectors[0][2]["text"] == "fee text"

    results = store.search("why is the settlement short", top_k=2)
    assert len(results) == 2
    assert results[0]["source"] == "fee_schedule.md"
    assert results[0]["score"] == 0.93
    assert (
        FakePinecone.last_instance.fake_index.queries[0]["namespace"]
        == PRIMARY_NAMESPACE
    )


def test_vector_store_fallback_namespace(monkeypatch):
    monkeypatch.setattr("backend.agents.vector_store.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr("backend.agents.vector_store.Pinecone", FakePinecone)

    store = VectorStore(api_key="test-key")
    store.embeddings = _stub_embeddings("minilm")

    store.search("chargeback policy")

    assert (
        FakePinecone.last_instance.fake_index.queries[0]["namespace"]
        == FALLBACK_NAMESPACE
    )


def test_vector_store_existing_index_not_recreated(monkeypatch):
    monkeypatch.setattr("backend.agents.vector_store.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr("backend.agents.vector_store.Pinecone", FakePinecone)

    FakePinecone.last_instance = None
    FakePinecone.initial_names = ["already-exists"]
    store = VectorStore(api_key="test-key", index_name="already-exists")

    assert FakePinecone.last_instance.created_kwargs is None
    assert store.is_connected is True
