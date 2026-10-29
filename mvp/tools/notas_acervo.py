#!/usr/bin/env python3
"""Notas externas do acervo (Open Library; Google Books quando a quota deixa).

Grava `nota_media`, `nota_qtd` e `nota_fonte` em `livros`, para a prateleira
"Melhores avaliações" do catálogo. A nota é da fonte externa, não dos alunos.

Uso (simula por padrão):
    ./venv/bin/python tools/notas_acervo.py
    ./venv/bin/python tools/notas_acervo.py --aplicar
    BIBLIO_DB=/tmp/x.db ./venv/bin/python tools/notas_acervo.py --aplicar
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("BIBLIO_DB", RAIZ / "biblioteca.db"))
UA = "BibliotecaEscolar/1.0 (https://library.autoava.us)"
FIELDS = "key,title,author_name,ratings_average,ratings_count,edition_count"
ALIASES = {
    "harry potter e a pedra filosofal": ("Harry Potter and the Philosopher's Stone", "J. K. Rowling"),
    "o pequeno principe": ("The Little Prince", "Antoine de Saint-Exupéry"),
    "percy jackson e o ladrao de raios": ("The Lightning Thief", "Rick Riordan"),
    "1984": ("Nineteen Eighty-Four", "George Orwell"),
    "o senhor dos aneis": ("The Lord of the Rings", "J. R. R. Tolkien"),
    "a menina que roubava livros": ("The Book Thief", "Markus Zusak"),
    "e assim que acaba": ("It Ends with Us", "Colleen Hoover"),
    "a revolucao dos bichos": ("Animal Farm", "George Orwell"),
    "as cronicas de narnia": ("The Chronicles of Narnia", "C. S. Lewis"),
    "a ilha do tesouro": ("Treasure Island", "Robert Louis Stevenson"),
    "o diario de anne frank": ("The Diary of a Young Girl", "Anne Frank"),
    "extraordinario": ("Wonder", "R. J. Palacio"),
    "a culpa e das estrelas": ("The Fault in Our Stars", "John Green"),
    "admiravel mundo novo": ("Brave New World", "Aldous Huxley"),
    "alice no pais das maravilhas": ("Alice's Adventures in Wonderland", "Lewis Carroll"),
    "macunaima": ("Macunaíma", "Mário de Andrade"),
    "orgulho e preconceito": ("Pride and Prejudice", "Jane Austen"),
    "frankenstein": ("Frankenstein", "Mary Shelley"),
    "o cao dos baskervilles": ("The Hound of the Baskervilles", "Arthur Conan Doyle"),
    "um estudo em vermelho": ("A Study in Scarlet", "Arthur Conan Doyle"),
    "o cortico": ("The Slum", "Aluísio Azevedo"),
}


MIN_AVALIACOES = 3          # nota de 1 pessoa não vira "melhor avaliado"
GOOGLE_URL = "https://www.googleapis.com/books/v1/volumes"


def norm(texto: object) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = "".join(c if c.isalnum() or c == " " else " " for c in texto.lower())
    return " ".join(texto.split())


def parecido(a: object, b: object) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _http(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def openlibrary_nota(titulo: str, autor: str) -> tuple[float, int, str] | None:
    """Melhor nota entre as edições encontradas no Open Library."""
    params = {"q": f"{titulo} {autor}".strip(), "fields": FIELDS, "limit": "10"}
    try:
        dados = json.loads(_http("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)))
    except Exception as exc:
        print(f"    ! Open Library: {exc}")
        return None
    melhor = None
    for doc in dados.get("docs") or []:
        media = doc.get("ratings_average")
        qtd = doc.get("ratings_count") or 0
        if not media or qtd <= 0:
            continue
        autor_doc = ", ".join(doc.get("author_name") or [])
        if autor and norm(autor).split()[-1] not in norm(autor_doc):
            continue
        if parecido(titulo, doc.get("title")) < 0.7:
            continue
        # prefere quem tem mais avaliações (nota mais confiável)
        candidato = (float(media), int(qtd), f"Open Library · {doc.get('title', '')[:40]}")
        if melhor is None or candidato[1] > melhor[1]:
            melhor = candidato
    return melhor


def melhor_nota(titulo: str, autor: str) -> tuple[float, int, str] | None:
    """Busca no título em português e no alias em inglês; fica com o mais avaliado."""
    candidatos = []
    pt = openlibrary_nota(titulo, autor)
    if pt:
        candidatos.append(pt)
    alias = ALIASES.get(norm(titulo))
    if alias:
        en = openlibrary_nota(alias[0], alias[1])
        if en:
            candidatos.append(en)
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c[1])


def google_nota(isbn: str) -> tuple[float, int, str] | None:
    """Google Books expõe averageRating/ratingsCount — só usado se a quota permitir."""
    if not isbn:
        return None
    try:
        params = {"q": f"isbn:{isbn.replace('-', '')}", "maxResults": "3", "country": "BR"}
        dados = json.loads(_http(GOOGLE_URL + "?" + urllib.parse.urlencode(params)))
    except Exception:
        return None
    for item in dados.get("items") or []:
        info = item.get("volumeInfo") or {}
        media, qtd = info.get("averageRating"), info.get("ratingsCount") or 0
        if media and qtd:
            return (float(media), int(qtd), "Google Livros")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="grava no banco")
    ap.add_argument("--refazer", action="store_true", help="refaz livros que já têm nota")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    livros = conn.execute("SELECT id, titulo, autor, isbn, nota_media FROM livros ORDER BY id").fetchall()

    ok = falhou = pulou = 0
    for livro in livros:
        if livro["nota_media"] and not args.refazer:
            pulou += 1
            continue
        achado = google_nota(livro["isbn"] or "") or melhor_nota(livro["titulo"], livro["autor"] or "")
        if not achado:
            print(f"  [{livro['id']:>3}] SEM NOTA   {livro['titulo'][:44]}")
            falhou += 1
            continue
        media, qtd, fonte = achado
        confiavel = qtd >= MIN_AVALIACOES
        print(f"  [{livro['id']:>3}] {media:.1f} ({qtd:>3}) {livro['titulo'][:36]:<36} [{fonte[:26]}]"
              f"{'' if confiavel else '  <- poucas avaliações'}")
        if args.aplicar:
            conn.execute(
                "UPDATE livros SET nota_media = ?, nota_qtd = ?, nota_fonte = ? WHERE id = ?",
                (round(media, 2), qtd, fonte.split(" · ")[0], livro["id"]),
            )
        ok += 1
        time.sleep(0.15)

    if args.aplicar:
        conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM livros WHERE nota_media IS NOT NULL").fetchone()[0]
    print(f"\nresumo: {ok} com nota, {falhou} sem, {pulou} já tinham · no banco: {total}"
          f"{'' if args.aplicar else '  (SIMULAÇÃO — use --aplicar)'}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
