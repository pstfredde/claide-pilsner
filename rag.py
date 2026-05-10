"""
RAG-modul för pilsner-boten.
Laddar lexikonet för aktiv karaktär och bygger FAISS-index i minnet.
"""

import json
import os
import pathlib
import tomllib
import warnings
import logging
import numpy as np

# ── Tysta brus från externa bibliotek ────────────────────────────────────────

os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
warnings.filterwarnings("ignore")
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# ── Läs config ────────────────────────────────────────────────────────────────

_ROT      = pathlib.Path(__file__).parent
_cfg      = tomllib.loads((_ROT / "config.toml").read_text(encoding="utf-8"))
_KARAKTÄR = _cfg["bot"]["karakter"]
TOP_K     = _cfg["rag"]["antal_slangord"]
_EMB_MODELL = _cfg["rag"]["embedding_modell"]

LEX_PATH  = _ROT / "lexicon" / _KARAKTÄR / "lexikon.json"


# ── Hjälpfunktioner ───────────────────────────────────────────────────────────

def _ladda_lexikon() -> list[tuple[str, str]]:
    """Returnerar lista med (ord, definition) från alla kategorier."""
    lex = json.loads(LEX_PATH.read_text(encoding="utf-8"))
    poster = []
    for kategori in ("slangord", "fraser", "utrop"):
        for ord_, defn in lex.get(kategori, {}).items():
            poster.append((ord_, defn))
    return poster


def _bygg_index(poster: list[tuple[str, str]], modell):
    """Skapar FAISS-index av alla lexikonposter."""
    import faiss
    texter = [f"{o}: {d}" for o, d in poster]
    vektorer = modell.encode(texter, normalize_embeddings=True, show_progress_bar=False)
    dim = vektorer.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vektorer.astype("float32"))
    return index


# ── Ladda allt vid import ─────────────────────────────────────────────────────

from sentence_transformers import SentenceTransformer

import contextlib, io
with contextlib.redirect_stderr(io.StringIO()):
    _modell = SentenceTransformer(_EMB_MODELL, local_files_only=True)
_poster = _ladda_lexikon()
_index  = _bygg_index(_poster, _modell)


# ── Publik funktion ───────────────────────────────────────────────────────────

def hitta_relevant_slang(fråga: str, k: int = TOP_K) -> dict[str, str]:
    """
    Returnerar de k mest relevanta slangorden för en given fråga.
    Resultat: {ord: definition}
    """
    import faiss
    vec = _modell.encode([fråga], normalize_embeddings=True)
    _, idx = _index.search(vec.astype("float32"), k)
    return {
        _poster[i][0]: _poster[i][1]
        for i in idx[0]
        if i < len(_poster)
    }
