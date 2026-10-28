#!/usr/bin/env python3
"""Capas reais e acervo de apresentação.

Baixa as capas do Open Library para os livros do acervo, salva em `web/capas/` e
grava o caminho local em `livros.capa_url` (servido por `img-src 'self'`, sem
depender de internet na hora da apresentação).

Uso (por padrão só simula):
    ./venv/bin/python tools/capas_acervo.py                 # relatório, sem gravar
    ./venv/bin/python tools/capas_acervo.py --aplicar       # baixa e grava
    ./venv/bin/python tools/capas_acervo.py --semear --aplicar   # + títulos do ACERVO_EXTRA
    BIBLIO_DB=/tmp/x.db ./venv/bin/python tools/capas_acervo.py --aplicar
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
CAPAS = WEB / "capas"
DB = Path(os.environ.get("BIBLIO_DB", RAIZ / "biblioteca.db"))
UA = "BibliotecaEscolar/1.0 (https://library.autoava.us)"
FIELDS = "key,title,author_name,cover_i,first_publish_year,edition_key,isbn"

# Títulos para deixar o acervo com cara de biblioteca escolar de verdade.
# Sinopses escritas à mão em PT-BR (a API costuma devolver texto em inglês).
ACERVO_EXTRA = [
    ("Vidas Secas", "Graciliano Ramos", "Romance", 1938,
     "A família de retirantes de Fabiano atravessa o sertão em busca de água e de um lugar para viver."),
    ("Capitães da Areia", "Jorge Amado", "Romance", 1937,
     "Meninos abandonados vivem em um trapiche de Salvador e sobrevivem de pequenos furtos."),
    ("A Hora da Estrela", "Clarice Lispector", "Romance", 1977,
     "Macabéa, nordestina pobre no Rio de Janeiro, tem a vida narrada por um escritor atormentado."),
    ("Iracema", "José de Alencar", "Clássico", 1865,
     "A virgem dos lábios de mel e o guerreiro branco Martim vivem o mito de origem do Ceará."),
    ("Macunaíma", "Mário de Andrade", "Clássico", 1928,
     "O herói sem nenhum caráter nasce na Amazônia e atravessa o país em busca de um amuleto."),
    ("Torto Arado", "Itamar Vieira Junior", "Romance", 2019,
     "Duas irmãs no sertão baiano enfrentam a herança da escravidão e a luta pela terra."),
    ("Quarto de Despejo", "Carolina Maria de Jesus", "Drama", 1960,
     "Diário de uma catadora de papel na favela do Canindé, em São Paulo."),
    ("O Quinze", "Rachel de Queiroz", "Romance", 1930,
     "A seca de 1915 no Ceará separa a professora Conceição e o vaqueiro Vicente."),
    ("A Revolução dos Bichos", "George Orwell", "Clássico", 1945,
     "Os animais da granja expulsam o fazendeiro e criam um governo próprio que se corrompe."),
    ("Fahrenheit 451", "Ray Bradbury", "Ficção", 1953,
     "Em um futuro em que livros são proibidos, um bombeiro começa a questionar o que queima."),
    ("Admirável Mundo Novo", "Aldous Huxley", "Ficção", 1932,
     "Uma sociedade controlada por engenharia genética e prazer programado dispensa a liberdade."),
    ("O Hobbit", "J.R.R. Tolkien", "Fantasia", 1937,
     "Bilbo Bolseiro deixa o conforto do Condado para acompanhar anões em busca de um tesouro."),
    ("As Crônicas de Nárnia", "C.S. Lewis", "Fantasia", 1950,
     "Crianças atravessam um guarda-roupa e encontram um reino congelado sob uma feiticeira."),
    ("Alice no País das Maravilhas", "Lewis Carroll", "Fantasia", 1865,
     "Alice cai na toca do coelho e encontra personagens absurdos e um país de regras invertidas."),
    ("Viagem ao Centro da Terra", "Júlio Verne", "Aventura", 1864,
     "Um professor e seu sobrinho descem por uma cratera na Islândia rumo a um mundo subterrâneo."),
    ("A Ilha do Tesouro", "Robert Louis Stevenson", "Aventura", 1883,
     "Jim Hawkins encontra um mapa do tesouro e embarca com piratas disfarçados de marinheiros."),
    ("O Diário de Anne Frank", "Anne Frank", "Drama", 1947,
     "Uma adolescente judia registra dois anos escondida de nazistas em Amsterdã."),
    ("Extraordinário", "R.J. Palacio", "Juvenil", 2012,
     "August, com uma síndrome facial rara, encara o primeiro ano em uma escola comum."),
    ("A Culpa É das Estrelas", "John Green", "Juvenil", 2012,
     "Hazel e Augustus se conhecem em um grupo de apoio e vivem um amor com prazo curto."),
    ("Orgulho e Preconceito", "Jane Austen", "Romance", 1813,
     "Elizabeth Bennet e o sr. Darcy precisam vencer o orgulho e o preconceito que os separam."),
    ("Frankenstein", "Mary Shelley", "Clássico", 1818,
     "Victor Frankenstein dá vida a uma criatura e abandona o ser que criou."),
    ("Drácula", "Bram Stoker", "Mistério", 1897,
     "Cartas e diários revelam a chegada do conde Drácula à Inglaterra e a caçada para detê-lo."),
    ("O Cão dos Baskervilles", "Arthur Conan Doyle", "Mistério", 1902,
     "Sherlock Holmes investiga a lenda de um cão monstruoso que ronda a família Baskerville."),
    ("Duna", "Frank Herbert", "Ficção", 1965,
     "Paul Atreides chega a um planeta de deserto e especiaria, onde sua família cai em uma armadilha."),
]


# O Open Library raramente tem edição brasileira destes títulos: a busca de capa
# cai para a edição em inglês (a arte costuma ser a mesma da edição nacional).
ALIASES = {
    "grande sertao veredas": ("The Devil to Pay in the Backlands", "João Guimarães Rosa"),
    "harry potter e a pedra filosofal": ("Harry Potter and the Philosopher's Stone", "J. K. Rowling"),
    "percy jackson e o ladrao de raios": ("The Lightning Thief", "Rick Riordan"),
    "a menina que roubava livros": ("The Book Thief", "Markus Zusak"),
    "e assim que acaba": ("It Ends With Us", "Colleen Hoover"),
    "as cronicas de narnia": ("The Chronicles of Narnia", "C. S. Lewis"),
    "o diario de anne frank": ("The Diary of a Young Girl", "Anne Frank"),
    "extraordinario": ("Wonder", "R. J. Palacio"),
    "a culpa e das estrelas": ("The Fault in Our Stars", "John Green"),
    "orgulho e preconceito": ("Pride and Prejudice", "Jane Austen"),
    "o cao dos baskervilles": ("The Hound of the Baskervilles", "Arthur Conan Doyle"),
    "duna": ("Dune", "Frank Herbert"),
    "a ilha do tesouro": ("Treasure Island", "Robert Louis Stevenson"),
}


def slug(texto: str, limite: int = 48) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto[:limite] or "livro"


def norm(texto: object) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto.lower())
    return " ".join(texto.split())


def parecido(a: object, b: object) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _http(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def buscar_candidatos(titulo: str, autor: str, idioma: str | None) -> list[dict]:
    """Candidatos do Open Library ordenados por semelhança de título/autor.

    Busca por `q=` (texto livre) em vez de `title=`: assim a edição brasileira,
    quando existe, aparece na frente — e `idioma="por"` filtra por português.
    """
    params = {"q": f"{titulo} {autor}".strip(), "fields": FIELDS, "limit": "10"}
    if idioma:
        params["language"] = idioma
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    try:
        dados = json.loads(_http(url))
    except Exception as exc:  # rede instável não deve derrubar o lote
        print(f"    ! Open Library falhou: {exc}")
        return []
    ranked = []
    for doc in dados.get("docs") or []:
        if not isinstance(doc, dict) or not doc.get("cover_i"):
            continue
        autor_doc = ", ".join(doc.get("author_name") or [])
        nota_titulo = parecido(titulo, doc.get("title"))
        nota_autor = parecido(autor, autor_doc) if autor else 1.0
        if autor and norm(autor).split()[-1] not in norm(autor_doc):
            nota_autor = 0.0
        nota = 0.7 * nota_titulo + 0.3 * nota_autor
        if nota_titulo < 0.62 or (autor and nota_autor < 0.3):
            continue
        ranked.append((nota, doc))
    ranked.sort(key=lambda par: par[0], reverse=True)
    return [doc for _, doc in ranked]


def dimensoes_jpeg(dados: bytes) -> tuple[int, int]:
    """Lê largura/altura de um JPEG sem depender de Pillow (SOF0..SOF3/5..7/9..11)."""
    i = 2
    while i < len(dados) - 9:
        if dados[i] != 0xFF:
            i += 1
            continue
        marcador = dados[i + 1]
        if marcador in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            altura = int.from_bytes(dados[i + 5:i + 7], "big")
            largura = int.from_bytes(dados[i + 7:i + 9], "big")
            return largura, altura
        tamanho = int.from_bytes(dados[i + 2:i + 4], "big")
        i += 2 + tamanho
    return 0, 0


def baixar_melhor_capa(cover_ids: list[int], minimo_largura: int = 280) -> tuple[bytes, tuple[int, int], int]:
    """Baixa até achar uma capa com resolução decente; devolve a maior encontrada."""
    melhor: tuple[bytes, tuple[int, int], int] | None = None
    for cover_id in cover_ids:
        try:
            dados = _http(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false")
        except Exception:
            continue
        if len(dados) < 3000 or dados[:2] != b"\xff\xd8":
            continue
        largura, altura = dimensoes_jpeg(dados)
        if melhor is None or largura * altura > melhor[1][0] * melhor[1][1]:
            melhor = (dados, (largura, altura), cover_id)
        if largura >= minimo_largura:
            break
    if melhor is None:
        raise ValueError("nenhuma capa baixou")
    return melhor


def semear(conn: sqlite3.Connection, aplicar: bool) -> list[str]:
    sys.path.insert(0, str(RAIZ / "server"))
    import db as dbmod  # noqa: E402  (cor_para vem do próprio projeto)

    existentes = {norm(r["titulo"]) for r in conn.execute("SELECT titulo FROM livros")}
    criados = []
    for titulo, autor, genero, ano, sinopse in ACERVO_EXTRA:
        if norm(titulo) in existentes:
            continue
        criados.append(titulo)
        if aplicar:
            total = 3
            conn.execute(
                "INSERT INTO livros (titulo, autor, genero, ano, isbn, cor, capa_url, sinopse,"
                " total_exemplares, disponiveis) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (titulo, autor, genero, ano, "", dbmod.cor_para(titulo), "", sinopse, total, total),
            )
    if aplicar and criados:
        conn.commit()
    return criados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="grava no banco e baixa as imagens")
    ap.add_argument("--semear", action="store_true", help="adiciona os títulos do ACERVO_EXTRA")
    ap.add_argument("--refazer", action="store_true", help="refaz capas que já existem")
    args = ap.parse_args()

    if not DB.exists():
        print(f"banco não encontrado: {DB}")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    if args.semear:
        novos = semear(conn, args.aplicar)
        rotulo = "adicionados" if args.aplicar else "seriam adicionados"
        print(f"{len(novos)} títulos {rotulo}: {', '.join(novos) if novos else '—'}\n")

    livros = conn.execute("SELECT id, titulo, autor, capa_url FROM livros ORDER BY id").fetchall()
    ok = falhou = pulou = 0
    for livro in livros:
        capa = (livro["capa_url"] or "").strip()
        if capa.startswith("capas/") and (WEB / capa).exists() and not args.refazer:
            pulou += 1
            continue
        docs = buscar_candidatos(livro["titulo"], livro["autor"] or "", "por")
        if not docs:
            docs = buscar_candidatos(livro["titulo"], livro["autor"] or "", None)
        if not docs:
            alias = ALIASES.get(norm(livro["titulo"]))
            if alias:
                docs = buscar_candidatos(alias[0], alias[1], None)
        if not docs:
            print(f"  [{livro['id']:>3}] SEM CAPA  {livro['titulo']}")
            falhou += 1
            continue
        arquivo = CAPAS / f"{livro['id']:03d}-{slug(livro['titulo'])}.jpg"
        relativo = f"capas/{arquivo.name}"
        try:
            ids = [int(doc["cover_i"]) for doc in docs[:4]]
            dados, (largura, altura), cover_id = baixar_melhor_capa(ids)
            if args.aplicar:
                arquivo.parent.mkdir(parents=True, exist_ok=True)
                tmp = arquivo.with_suffix(".tmp")
                tmp.write_bytes(dados)
                tmp.replace(arquivo)
                conn.execute("UPDATE livros SET capa_url = ? WHERE id = ?", (relativo, livro["id"]))
            print(f"  [{livro['id']:>3}] OK  {livro['titulo'][:38]:<38} {largura}x{altura} {len(dados)//1024:>3} KB"
                  f"  [{docs[0].get('title')}]")
            ok += 1
        except Exception as exc:
            print(f"  [{livro['id']:>3}] FALHOU  {livro['titulo']}: {exc}")
            falhou += 1
        time.sleep(0.2)

    if args.aplicar:
        conn.commit()
    conn.close()
    print(f"\nresumo: {ok} com capa, {falhou} sem, {pulou} já tinham"
          f"{'' if args.aplicar else ' (SIMULAÇÃO — use --aplicar)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
