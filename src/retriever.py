"""
Retriever.

Configuration frozen in "Phase 1 - Retrieval Optimization" of the
notebook: plain similarity search with k=8 beat every MMR configuration
that was swept, so that is what the application uses.
"""

from functools import lru_cache

from src import config
from src.vector_store import get_vector_store


RETRIEVER_K = config.RETRIEVER_K


@lru_cache(maxsize=4)
def get_retriever(k=None):
    """
    Create (once per k) the retriever backed by PgVector similarity search.
    """
    vector_store = get_vector_store()

    retriever = vector_store.as_retriever(
        search_type=config.RETRIEVER_SEARCH_TYPE,
        search_kwargs={
            "k": k or config.RETRIEVER_K,
        },
    )

    return retriever


def retrieve_documents(query, k=None):
    """
    Retrieve the documents relevant to a user query.
    """
    retriever = get_retriever(k)

    documents = retriever.invoke(query)

    return documents
