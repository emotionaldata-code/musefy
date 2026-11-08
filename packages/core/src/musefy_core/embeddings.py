"""One fixed embedding space, shared by offline indexing and online queries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from torch import Tensor

MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
DIMENSIONS = 384
MAX_TOKENS = 512
PROFILE = hashlib.sha256(
    json.dumps(
        {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "dimensions": DIMENSIONS,
            "max_tokens": MAX_TOKENS,
            "truncation": True,
            "pooling": "attention_mask_mean",
            "normalization": "l2",
            "query_prefix": "query: ",
            "passage_prefix": "passage: ",
        },
        sort_keys=True,
    ).encode()
).hexdigest()

type Encode = Callable[[list[str]], list[list[float]]]


def input_hash(synopsis: str) -> str:
    return hashlib.sha256(synopsis.encode()).hexdigest()


def validate_vectors(vectors: list[list[float]], count: int) -> None:
    if len(vectors) != count:
        raise ValueError("Embedding count does not match input count")
    for vector in vectors:
        if len(vector) != DIMENSIONS or not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding must contain 384 finite values")
        if not math.isclose(sum(value * value for value in vector), 1.0, abs_tol=1e-4):
            raise ValueError("Embedding must be L2 normalized")


class _Tokenizer(Protocol):
    def __call__(
        self, texts: list[str], *, max_length: int, padding: bool, truncation: bool, return_tensors: str
    ) -> Mapping[str, Tensor]: ...


class _Output(Protocol):
    last_hidden_state: Tensor


class _Transformer(Protocol):
    def __call__(self, **inputs: Tensor) -> _Output: ...


def _load_encoder(device: str, threads: int, local_files_only: bool) -> Encode:
    # Heavy imports and model downloads happen only in the inference worker.
    import torch
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(threads)
    tokenizer = cast(
        _Tokenizer,
        AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION, local_files_only=local_files_only),
    )
    model = cast(
        _Transformer,
        AutoModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION, local_files_only=local_files_only)
        .to(device)
        .eval(),
    )

    def encode(texts: list[str]) -> list[list[float]]:
        tokens = tokenizer(texts, max_length=MAX_TOKENS, padding=True, truncation=True, return_tensors="pt")
        inputs = {name: tensor.to(device) for name, tensor in tokens.items()}
        with torch.inference_mode():
            mask = inputs["attention_mask"]
            hidden = model(**inputs).last_hidden_state.masked_fill(~mask[..., None].bool(), 0.0)
            pooled = hidden.sum(dim=1) / mask.sum(dim=1)[..., None]
            normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return cast(list[list[float]], normalized.cpu().tolist())

    return encode


class Embedder:
    def __init__(
        self,
        *,
        device: str = "cpu",
        threads: int = 2,
        local_files_only: bool = True,
        factory: Callable[[], Encode] | None = None,
    ) -> None:
        if threads < 1:
            raise ValueError("threads must be positive")
        self._factory = factory or partial(_load_encoder, device, threads, local_files_only)
        self._encoder: Encode | None = None
        self._lock = asyncio.Lock()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if self._encoder is None:
            self._encoder = self._factory()
        vectors = self._encoder(texts)
        validate_vectors(vectors, len(texts))
        return vectors

    def _finished(self, future: asyncio.Future[list[list[float]]]) -> None:
        # Keep ownership until the CPU worker finishes, even if its caller was cancelled.
        if not future.cancelled():
            future.exception()
        self._lock.release()

    async def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > 128 or any(not text.strip() for text in texts):
            raise ValueError("Provide 1–128 nonempty texts")
        await self._lock.acquire()
        future = asyncio.create_task(asyncio.to_thread(self._encode, [prefix + text for text in texts]))
        future.add_done_callback(self._finished)
        return await asyncio.shield(future)

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "passage: ")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query: "))[0]
