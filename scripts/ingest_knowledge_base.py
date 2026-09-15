"""
Rebuild the knowledge base into PgVector.

    python -m scripts.ingest_knowledge_base

With the additional documents (opt-in):

    INCLUDE_ADDITIONAL_DOCUMENTS=true python -m scripts.ingest_knowledge_base

The logic lives in `src/ingestion.py`, not here. This file is only the
command line interface: the upload button in Streamlit calls the same
service, so there are never two pipelines that can quietly drift apart.
"""

from src import config
from src.ingestion import bangun_ulang


def main():
    print("Memuat, membersihkan, dan melakukan chunking PDF...")

    laporan = bangun_ulang()

    print()
    print("=== LAPORAN INGESTION ===")
    print(
        f"  Dokumen tambahan aktif    : "
        f"{config.INCLUDE_ADDITIONAL_DOCUMENTS}"
    )
    print(f"  PDF                       : {laporan['pdf_files']}")
    print(f"  Halaman total             : {laporan['pages_total']}")
    print(f"  Halaman dipakai           : {laporan['pages_kept']}")
    print(f"  Halaman dibuang (pendek)  : {laporan['pages_dropped_short']}")
    print(
        f"  Halaman dibuang (pustaka) : "
        f"{laporan['pages_dropped_reference']}"
    )
    print(f"  Halaman dipotong          : {laporan['pages_truncated']}")
    print(
        f"  Marker sitasi dibuang     : "
        f"{laporan['citation_markers_removed']}"
    )
    print(
        f"  Kata patah diperbaiki     : "
        f"{len(laporan['broken_words_repaired'])}"
    )
    print(f"  Jumlah chunk              : {laporan['chunks']}")

    if laporan["broken_words_repaired"]:
        print("\n  Kata patah yang diperbaiki:")
        for entry in laporan["broken_words_repaired"]:
            print(f"    {entry}")

    print()
    print("Ingestion berhasil.")
    print()
    print(
        "Langkah berikutnya: `python -m scripts.build_gold_chunks` — "
        "chunk_id bersifat content-addressed, jadi ikut berubah setiap "
        "kali teks atau konfigurasi chunking berubah."
    )


if __name__ == "__main__":
    main()
