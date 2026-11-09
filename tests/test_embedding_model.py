import asyncio
import hashlib
import threading

import pytest
from musefy_core.embeddings import DIMENSIONS, Embedder, Encode, input_hash, retrieval_document
from musefy_core.schemas import Credit, Metadata

from tests.test_catalog import example


def vector() -> list[float]:
    return [1.0, *([0.0] * (DIMENSIONS - 1))]


async def test_lazy_single_load_prefixes_and_exact_input_hash() -> None:
    calls: list[list[str]] = []
    loads: list[int] = []

    def factory() -> Encode:
        assert threading.current_thread() is not threading.main_thread()
        loads.append(1)

        def encode(texts: list[str]) -> list[list[float]]:
            calls.append(texts)
            return [vector() for _ in texts]

        return encode

    embedder = Embedder(factory=factory)
    assert not loads
    assert await embedder.embed_passages([]) == []
    assert not loads
    assert await embedder.embed_query("indagine psicologica") == vector()
    assert await embedder.embed_passages(["Una sinossi", "Another synopsis"]) == [vector(), vector()]
    assert calls == [["query: indagine psicologica"], ["passage: Una sinossi", "passage: Another synopsis"]]
    assert len(loads) == 1
    assert input_hash(" sinossi ") == hashlib.sha256(b" sinossi ").hexdigest()
    assert input_hash(" sinossi ") != input_hash("sinossi")


async def test_cancelled_request_keeps_worker_exclusive_and_event_loop_free() -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[list[str]] = []

    def encode(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        if len(calls) == 1:
            started.set()
            assert release.wait(timeout=3)
        return [vector()]

    embedder = Embedder(factory=lambda: encode)
    first = asyncio.create_task(embedder.embed_query("first"))
    assert await asyncio.to_thread(started.wait, 2)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(embedder.embed_query("second"))
    try:
        await asyncio.sleep(0.02)
        assert calls == [["query: first"]]
    finally:
        release.set()
    assert await asyncio.wait_for(second, 2) == vector()
    assert calls == [["query: first"], ["query: second"]]


async def test_rejects_invalid_inputs_and_backend_vectors() -> None:
    embedder = Embedder(factory=lambda: lambda texts: [[0.0] * DIMENSIONS for _ in texts])
    with pytest.raises(ValueError, match="nonempty"):
        await embedder.embed_query(" \n ")
    with pytest.raises(ValueError, match="1–128"):
        await embedder.embed_passages(["a"] * 129)
    with pytest.raises(ValueError, match="L2 normalized"):
        await embedder.embed_query("valid text")
    with pytest.raises(ValueError, match="positive"):
        Embedder(threads=0)


def test_retrieval_document_selected_fields_and_canonical_terms() -> None:
    title = example()
    title.title = "  Una\tstoria\n "
    title.genres = [" Drama ", "Sci-Fi", "Drama", "", "\t", "Émotion", "東京"]
    title.metadata = Metadata(
        format=" Movie\r\n special ",
        themes=[" Time\v travel ", "Drama", "Time travel"],
        keywords=["Drama", "Memory", ""],
        synopsis=" A\f story\r\nwith\tmemories. ",
    )
    assert retrieval_document(title) == (
        "Title: Una storia\n"
        "Format: Movie special; movie\n"
        "Genres: Drama; Sci-Fi; Émotion; 東京\n"
        "Themes / keywords: Drama; Memory; Time travel\n"
        "Synopsis: A story with memories."
    )
    before = retrieval_document(title)
    title.genres.reverse()
    title.metadata.themes = ["Memory", "Time travel"]
    title.metadata.keywords = ["Drama", "Drama"]
    title.metadata.staff = [Credit(name="Someone")]
    title.metadata.original_title = "Ignored"
    title.year = 1990
    assert retrieval_document(title) == before


def test_retrieval_document_omits_absent_optional_fields() -> None:
    title = example()
    title.genres = []
    title.metadata = Metadata()
    assert retrieval_document(title) == "Title: Una storia\nFormat: movie"
