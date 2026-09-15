"""
PostgreSQL + PgVector vector store.

The engine is built once at import time and the store is cached, because
creating a PGVectorStore also builds the embedding model. An uncached
call would pay for that every time.
"""

from functools import lru_cache

from langchain_postgres import PGEngine, PGVectorStore

from src import config
from src.embeddings import get_embeddings


DATABASE_URL = config.DATABASE_URL
TABLE_NAME = config.TABLE_NAME


if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL tidak ditemukan di file .env.\n"
        "Contoh:\n"
        "  DATABASE_URL=postgresql+psycopg://postgres:password"
        "@localhost:5433/rag_stock_assistant"
    )


engine = PGEngine.from_connection_string(url=DATABASE_URL)


def get_psycopg_connection_url():
    """
    Convert the SQLAlchemy URL used by LangChain into the plain URL that
    psycopg expects.
    """
    return DATABASE_URL.replace(
        "postgresql+psycopg://",
        "postgresql://",
        1,
    )


@lru_cache(maxsize=1)
def get_vector_store():
    """
    Create (once) and return the PgVector store used by the application.
    """
    embeddings = get_embeddings()

    vector_store = PGVectorStore.create_sync(
        engine=engine,
        table_name=config.TABLE_NAME,
        embedding_service=embeddings,
    )

    return vector_store
