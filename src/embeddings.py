"""
Embedding model.

Wrapped in lru_cache because the model is expensive to build. Without
it, every ask_question() or retrieve_documents() call reloads the
sentence-transformers model from disk; a 25-question evaluation used to
load it 25 times.

`local_files_only` is tried first because
`SentenceTransformer("sentence-transformers/...")` treats that name as a
repo id, not a folder. Even when the model is already cached,
huggingface_hub still contacts huggingface.co to check whether the
revision changed. On a slow network that check hangs until ReadTimeout -
about 20 seconds lost on the first question of every process - and on a
machine with no internet it delays application start for no reason.

So the first attempt passes `local_files_only=True`: if the model is
cached, zero network requests. If it is not cached, that attempt fails
and the model is downloaded as usual - once, and then it is cached.

A failed first attempt is NOT swallowed. The reason is kept in
`_ALASAN_UNDUH`, which `alasan_unduh()` returns, and it is printed once
to stderr; `sumber_model()` reports only where the model came from. If
the second attempt fails too, its error propagates unchanged.
"""

import sys
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from src import config


MODEL_NAME = config.EMBEDDING_MODEL_NAME

SUMBER_CACHE_LOKAL = "cache_lokal"
SUMBER_UNDUH = "unduh"

_SUMBER = None
_ALASAN_UNDUH = None


def _bangun(local_files_only):
    return HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL_NAME,
        model_kwargs={
            "device": config.EMBEDDING_DEVICE,
            "local_files_only": local_files_only,
        },
        encode_kwargs={"normalize_embeddings": config.EMBEDDING_NORMALIZE},
    )


@lru_cache(maxsize=1)
def get_embeddings():
    """
    Create (once) and return the embedding model used by the application.
    """
    global _SUMBER, _ALASAN_UNDUH

    try:
        embeddings = _bangun(local_files_only=True)

    except Exception as kesalahan:
        # Cache is cold (or broken). Download once - and say why, so
        # "why is startup slow" does not have to be guessed.
        _ALASAN_UNDUH = f"{type(kesalahan).__name__}: {kesalahan}"

        print(
            f"[embeddings] model belum ada di cache lokal, mengunduh "
            f"{config.EMBEDDING_MODEL_NAME} ...\n"
            f"[embeddings] sebab: {_ALASAN_UNDUH}",
            file=sys.stderr,
        )

        embeddings = _bangun(local_files_only=False)
        _SUMBER = SUMBER_UNDUH

        return embeddings

    _SUMBER = SUMBER_CACHE_LOKAL
    _ALASAN_UNDUH = None

    return embeddings


def sumber_model():
    """
    Where the model was last loaded from: "cache_lokal", "unduh", or None
    if `get_embeddings()` has not been called yet in this process.

    Used by `scripts/diagnose_embeddings.py` and the tests. It exists so
    the claim "no request to Hugging Face" can be checked rather than
    taken on faith.
    """
    return _SUMBER


def alasan_unduh():
    """
    The failure message from the local-cache attempt, if there was one.
    """
    return _ALASAN_UNDUH


def reset_cache_embeddings():
    """
    Clear the cached model. For tests and diagnostics only.
    """
    global _SUMBER, _ALASAN_UNDUH

    get_embeddings.cache_clear()
    _SUMBER = None
    _ALASAN_UNDUH = None
