#!/usr/bin/env python3
"""Deixa o banco com um estado de demonstração coerente com a data de hoje.

O seed original nasceu em agosto: todo empréstimo ativo virava "atrasado há 70
dias" no painel. Este script reescreve os empréstimos em datas relativas a hoje
(um atrasado curto, dois no prazo, um pronto p/ retirada, um solicitado e um
histórico de devoluções) e recalcula `livros.disponiveis`.

Uso (simula por padrão):
    ./venv/bin/python tools/demo_apresentacao.py
    ./venv/bin/python tools/demo_apresentacao.py --aplicar
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("BIBLIO_DB", RAIZ / "biblioteca.db"))

BRUNO = "987654321sp"
VICTOR = "1099851476sp"
JULIA = "1104299045sp"

# (livro, aluno, status, dias_solicitacao, dias_emprestimo, dias_prevista, dias_devolucao)
# dias negativos = passado.
ROTEIRO = [
    # ativo no prazo
    ("1984", BRUNO, "ativo", -3, -3, 11, None),
    ("Harry Potter e a Pedra Filosofal", JULIA, "ativo", -8, -8, 6, None),
    # ativo atrasado (6 dias) — o painel mostra atraso curto, não abandono
    ("O Cortiço", BRUNO, "ativo", -20, -20, -6, None),
    # pronto para retirada (solicitado ontem, separado hoje)
    ("A Menina que Roubava Livros", VICTOR, "pronto", -1, None, None, None),
    # solicitado hoje — aparece em "solicitações para preparar"
    ("Torto Arado", JULIA, "solicitado", 0, None, None, None),
    # histórico de devoluções
    ("O Pequeno Príncipe", VICTOR, "devolvido", -24, -24, -10, -11),
    ("Dom Casmurro", BRUNO, "devolvido", -30, -30, -16, -18),
    ("A Hora da Estrela", JULIA, "devolvido", -12, -12, 2, -4),
    ("Vidas Secas", VICTOR, "devolvido", -45, -45, -31, -33),
    # repetições no histórico: dá corpo ao ranking "mais alugados do mês"
    ("Dom Casmurro", JULIA, "devolvido", -18, -18, -4, -5),
    ("Harry Potter e a Pedra Filosofal", BRUNO, "devolvido", -22, -22, -8, -9),
    ("Torto Arado", VICTOR, "devolvido", -40, -40, -26, -27),
    ("1984", JULIA, "devolvido", -35, -35, -21, -22),
    ("O Pequeno Príncipe", BRUNO, "devolvido", -15, -15, -1, -2),
    ("Dom Casmurro", VICTOR, "devolvido", -55, -55, -41, -42),
]


def dia(offset: int | None) -> str | None:
    if offset is None:
        return None
    return (date.today() + timedelta(days=offset)).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="grava no banco")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    ids: dict[str, int] = {}
    for titulo, aluno, status, d_sol, d_emp, d_prev, d_dev in ROTEIRO:
        row = conn.execute("SELECT id FROM livros WHERE titulo = ?", (titulo,)).fetchone()
        if not row:
            print(f"  ! livro fora do acervo: {titulo}")
            continue
        ids[titulo] = row["id"]
        print(f"  {status:<10} {titulo[:34]:<34} {aluno} sol={dia(d_sol)} emp={dia(d_emp)}"
              f" prev={dia(d_prev)} dev={dia(d_dev)}")

    if not args.aplicar:
        print("\nSIMULAÇÃO — use --aplicar para gravar")
        return 0

    # O histórico de demonstração é o conjunto inteiro: apaga o antigo e grava o novo.
    conn.execute("DELETE FROM emprestimos")
    for titulo, aluno, status, d_sol, d_emp, d_prev, d_dev in ROTEIRO:
        if titulo not in ids:
            continue
        pronto_em = dia(d_sol + 1) if status in ("pronto", "devolvido", "ativo") else None
        conn.execute(
            "INSERT INTO emprestimos (livro_id, aluno_ra, status, data_solicitacao, data_preparado,"
            " data_emprestimo, data_prevista, data_devolucao) VALUES (?,?,?,?,?,?,?,?)",
            (ids[titulo], aluno, status, dia(d_sol), pronto_em, dia(d_emp), dia(d_prev), dia(d_dev)),
        )

    # disponiveis = total - (ativo + pronto + solicitado)
    conn.execute(
        """UPDATE livros SET disponiveis = MAX(0, total_exemplares - (
             SELECT COUNT(*) FROM emprestimos e
              WHERE e.livro_id = livros.id AND e.status IN ('ativo','pronto','solicitado')))"""
    )
    conn.commit()
    resumo = [dict(r) for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM emprestimos GROUP BY status ORDER BY status")]
    print("\ngravado. por status:", {r["status"]: r["n"] for r in resumo})
    print("exemplares disponíveis no acervo:",
          conn.execute("SELECT SUM(disponiveis) FROM livros").fetchone()[0])
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
