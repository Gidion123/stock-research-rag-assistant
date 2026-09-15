"""
Knowledge-base ingestion service. Shared by the CLI and the UI.

There are two ways a document gets in: `scripts/ingest_knowledge_base.py`
rebuilds the whole knowledge base, and the upload button in Streamlit
adds a single PDF. If each had its own implementation they would drift
apart sooner or later - different text cleaning, a different chunk size,
a different way of building `chunk_id` - and the gold chunks used in
evaluation would no longer match what is in the database.

So both call the functions in this file. Streamlit does not run a shell
command; it calls `tambah_pdf()`.
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

from src import config
from src.preprocessing import (
    load_and_split_documents,
    new_ingestion_report,
    split_documents,
)


UKURAN_MAKS_PDF_MB = 25

MINIMUM_CHUNK_BARU = 1


class IngestionError(Exception):
    """A failure that can be explained to the user without jargon."""


# ============================================================
# 1. VALIDATION
# ============================================================

def validasi_pdf(path):
    """
    Check the file before doing any work on it.

    Checking early is much cheaper than finding out the PDF is broken
    halfway through embedding.
    """
    path = Path(path)

    if not path.exists():
        raise IngestionError("Berkasnya tidak ditemukan.")

    if path.suffix.lower() != ".pdf":
        raise IngestionError("Hanya berkas PDF yang didukung.")

    ukuran_mb = path.stat().st_size / (1024 * 1024)

    if ukuran_mb == 0:
        raise IngestionError("Berkasnya kosong.")

    if ukuran_mb > UKURAN_MAKS_PDF_MB:
        raise IngestionError(
            f"Berkasnya terlalu besar ({ukuran_mb:.1f} MB). "
            f"Maksimal {UKURAN_MAKS_PDF_MB} MB."
        )

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        jumlah_halaman = len(reader.pages)

    except Exception as exception:
        raise IngestionError(
            "Berkas PDF-nya tidak bisa dibaca — mungkin rusak atau "
            "terkunci kata sandi."
        ) from exception

    if jumlah_halaman == 0:
        raise IngestionError("PDF-nya tidak punya halaman.")

    return {"pages": jumlah_halaman, "size_mb": round(ukuran_mb, 2)}


def sidik_jari_berkas(path):
    """
    SHA-1 of the file contents, to catch the same document uploaded twice
    under different names.
    """
    digest = hashlib.sha1()

    with open(path, "rb") as file:
        for blok in iter(lambda: file.read(65536), b""):
            digest.update(blok)

    return digest.hexdigest()[:16]


def daftar_dokumen(include_additional=None):
    """The PDFs that currently make up the knowledge base."""
    from src.preprocessing import get_pdf_files

    if include_additional is None:
        include_additional = config.INCLUDE_ADDITIONAL_DOCUMENTS

    return [
        {
            "name": p.name,
            "folder": p.parent.name,
            "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
        }
        for p in get_pdf_files(include_additional=include_additional)
    ]


def _sudah_ada(path, tujuan):
    """
    Duplicate by name OR by contents. Name alone is not enough: the same
    file often gets re-uploaded under a different name.
    """
    if (tujuan / Path(path).name).exists():
        return f"Dokumen dengan nama '{Path(path).name}' sudah ada."

    sidik_baru = sidik_jari_berkas(path)

    for lama in tujuan.glob("*.pdf"):
        if sidik_jari_berkas(lama) == sidik_baru:
            return f"Isi dokumen ini sama dengan '{lama.name}'."

    return None


# ============================================================
# 2. EMBEDDING INTO PGVECTOR
# ============================================================

def _simpan_ke_vector_store(chunks):
    from src.vector_store import get_vector_store

    if not chunks:
        raise IngestionError(
            "Tidak ada teks yang bisa diambil dari dokumen itu. "
            "Kemungkinan isinya berupa hasil pindaian tanpa teks."
        )

    vector_store = get_vector_store()
    vector_store.add_documents(chunks)

    return len(chunks)


# ============================================================
# 3. ADD ONE DOCUMENT (used by the UI)
# ============================================================

def tambah_pdf(
    sumber,
    nama_berkas=None,
    ke_folder_tambahan=False,
):
    """
    Add one PDF to the knowledge base.

    `sumber` may be a path, bytes, or a file object (a Streamlit upload).

    The flow is exactly the CLI's: clean -> chunk -> stable chunk_id ->
    embed -> PgVector. There is no second processing path.

    Returns a summary; raises `IngestionError` with a message that is
    safe to show to the user.
    """
    tujuan = (
        config.ADDITIONAL_DIR if ke_folder_tambahan else config.PRIMARY_DIR
    )
    tujuan.mkdir(parents=True, exist_ok=True)

    sementara = None

    try:
        # ---- write to a temporary file first ----
        if isinstance(sumber, (str, Path)):
            sementara = Path(sumber)
            hapus_sementara = False
            nama_berkas = nama_berkas or sementara.name
        else:
            isi = sumber.read() if hasattr(sumber, "read") else sumber
            nama_berkas = nama_berkas or getattr(sumber, "name", "dokumen.pdf")

            handle = tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False
            )
            handle.write(isi)
            handle.close()

            sementara = Path(handle.name)
            hapus_sementara = True

        info = validasi_pdf(sementara)

        nama_aman = Path(nama_berkas).name

        if not nama_aman.lower().endswith(".pdf"):
            nama_aman += ".pdf"

        duplikat = _sudah_ada(sementara, tujuan)

        if duplikat:
            raise IngestionError(duplikat)

        # ---- copy it under the final name, then process ----
        #
        # `load_pdf` takes `source` and `category` from the file path, and
        # that metadata is what shows up as the citation [name.pdf hal.N].
        # Processing straight from the temporary file would produce
        # citations reading "tmpXXXX.pdf". So the file is copied first,
        # and deleted again if processing fails - the knowledge base must
        # not keep a document whose chunks never made it in.
        from src.preprocessing import load_pdf

        final = tujuan / nama_aman
        shutil.copyfile(sementara, final)

        try:
            laporan = new_ingestion_report()
            halaman = load_pdf(final, collect_report=laporan)

            chunks = split_documents(halaman)

            if len(chunks) < MINIMUM_CHUNK_BARU:
                raise IngestionError(
                    "Tidak ada teks yang bisa diambil dari dokumen itu. "
                    "Kemungkinan isinya berupa hasil pindaian tanpa teks."
                )

            jumlah = _simpan_ke_vector_store(chunks)

        except Exception:
            final.unlink(missing_ok=True)
            raise

        return {
            "file_name": nama_aman,
            "pages": info["pages"],
            "size_mb": info["size_mb"],
            "chunks": jumlah,
            "folder": tujuan.name,
        }

    finally:
        if sementara is not None and hapus_sementara:
            try:
                sementara.unlink(missing_ok=True)
            except OSError:
                pass


# ============================================================
# 4. FULL REBUILD (used by the CLI)
# ============================================================

def bangun_ulang(include_additional=None, hapus_data_lama=True):
    """
    Rebuild the whole knowledge base from the PDF folders.

    This is what `scripts/ingest_knowledge_base.py` calls.
    """
    import psycopg

    from src.vector_store import (
        TABLE_NAME,
        get_psycopg_connection_url,
        get_vector_store,
    )

    if include_additional is None:
        include_additional = config.INCLUDE_ADDITIONAL_DOCUMENTS

    laporan = new_ingestion_report()
    chunks = load_and_split_documents(
        include_additional=include_additional,
        report=laporan,
    )

    if hapus_data_lama:
        with psycopg.connect(get_psycopg_connection_url()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE TABLE {TABLE_NAME};")

            connection.commit()

    vector_store = get_vector_store()
    vector_store.add_documents(chunks)

    laporan["chunks"] = len(chunks)

    return laporan


__all__ = [
    "IngestionError",
    "UKURAN_MAKS_PDF_MB",
    "validasi_pdf",
    "sidik_jari_berkas",
    "daftar_dokumen",
    "tambah_pdf",
    "bangun_ulang",
]
