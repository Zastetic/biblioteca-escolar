#!/usr/bin/env python3
"""Migração única: unifica o RA dos alunos na chave canônica (sed_client.chave_aluno).

Por que existe: até 08/10/2026 o espelho do aluno era gravado com o RA CRU digitado no login,
então a MESMA pessoa podia virar duas linhas ('123456789sp' e '000123456789sp', por exemplo).
Como `admins`, `sessoes` e `emprestimos` referenciam `alunos(ra)`, isso quebrava a busca do painel
adicionar admin / consultar aluno (match exato de string).

O que faz, para cada grupo de RAs que colapsam na mesma chave:
  1. garante a linha canônica (cria ou completa campos vazios com os dados das duplicatas);
  2. MOVE `emprestimos.aluno_ra`, `sessoes.ra` e `admins.ra` para a chave canônica;
  3. só então apaga as linhas antigas (sem isso o RESTRICT/CASCADE leva empréstimos e sessões junto).

Uso:
    ./venv/bin/python tools/migrar_ra_canonico.py                 # simulação (faz tudo e desfaz)
    ./venv/bin/python tools/migrar_ra_canonico.py --aplicar       # grava de verdade (com backup antes)
    ./venv/bin/python tools/migrar_ra_canonico.py --db /tmp/x.db --aplicar
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from sed_client import chave_aluno  # noqa: E402

CAMPOS = ("nome", "turma", "cpf", "email", "nascimento", "senha_hash")


def dados_da_linha(row) -> dict:
    return {c: (row[c] or "") for c in CAMPOS}


def melhor(membros):
    """Prefere a linha cujo ra JÁ é a chave; senão a que tem mais campos preenchidos."""
    return max(membros, key=lambda r: sum(1 for c in CAMPOS if (r[c] or "").strip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("BIBLIO_DB") or
                    str(Path(__file__).resolve().parent.parent / "biblioteca.db"))
    ap.add_argument("--aplicar", action="store_true", help="grava (padrão: simula e desfaz)")
    ap.add_argument("--backup-dir", default=str(Path(__file__).resolve().parent.parent / "backups"))
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print("Banco não encontrado:", args.db)
        return 2

    # Backup PRIMEIRO e com conexão limpa: `conn.backup()` trava para sempre se a conexão de
    # origem já tem transação de escrita aberta (o backup fica esperando um lock que ela mesma tem).
    if args.aplicar:
        Path(args.backup_dir).mkdir(parents=True, exist_ok=True)
        destino = Path(args.backup_dir) / f"biblioteca_pre_migracao_ra_{time.strftime('%Y%m%d_%H%M%S')}.db"
        orig = sqlite3.connect(args.db)
        copia = sqlite3.connect(destino)
        with copia:
            orig.backup(copia)
        copia.close()
        orig.close()
        print("backup do estado atual em:", destino, f"({destino.stat().st_size} bytes)")

    conn = sqlite3.connect(args.db, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    def contagem():
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("alunos", "admins", "sessoes", "emprestimos")}

    antes = contagem()
    rows = conn.execute("SELECT * FROM alunos").fetchall()
    grupos = defaultdict(list)
    for r in rows:
        grupos[chave_aluno(r["ra"])].append(r)

    print(f"{'RA antigo':22} -> {'chave canônica':22} empréstimos sessões admin")
    mudancas = 0
    for chave, membros in sorted(grupos.items()):
        if len(membros) == 1 and membros[0]["ra"] == chave:
            continue
        mudancas += 1
        ref = melhor(membros)
        for m in sorted(membros, key=lambda x: x["ra"]):
            emp = conn.execute("SELECT COUNT(*) FROM emprestimos WHERE aluno_ra = ?", (m["ra"],)).fetchone()[0]
            ses = conn.execute("SELECT COUNT(*) FROM sessoes WHERE ra = ?", (m["ra"],)).fetchone()[0]
            adm = conn.execute("SELECT COUNT(*) FROM admins WHERE ra = ?", (m["ra"],)).fetchone()[0]
            print(f"{m['ra']:22} -> {chave:22} {emp:11} {ses:7} {adm:5}")

        existente = conn.execute("SELECT * FROM alunos WHERE ra = ?", (chave,)).fetchone()
        base = existente or ref
        valores = {c: (base[c] or "") for c in CAMPOS}
        for m in membros:  # completa o que estiver vazio com qualquer duplicata
            for c in CAMPOS:
                if not valores[c].strip() and (m[c] or "").strip():
                    valores[c] = m[c]
        if existente:
            conn.execute(
                "UPDATE alunos SET nome=?, turma=?, cpf=?, email=?, nascimento=?, senha_hash=? WHERE ra=?",
                (*[valores[c] for c in CAMPOS], chave))
        else:
            conn.execute(
                "INSERT INTO alunos (ra, nome, turma, cpf, email, nascimento, senha_hash) VALUES (?,?,?,?,?,?,?)",
                (chave, *[valores[c] for c in CAMPOS]))

        for m in membros:
            if m["ra"] == chave:
                continue
            conn.execute("UPDATE emprestimos SET aluno_ra = ? WHERE aluno_ra = ?", (chave, m["ra"]))
            conn.execute("UPDATE sessoes SET ra = ? WHERE ra = ?", (chave, m["ra"]))
            conn.execute("INSERT OR IGNORE INTO admins (ra) SELECT ? WHERE EXISTS (SELECT 1 FROM admins WHERE ra = ?)",
                         (chave, m["ra"]))
            conn.execute("DELETE FROM admins WHERE ra = ?", (m["ra"],))
            conn.execute("DELETE FROM alunos WHERE ra = ?", (m["ra"],))

    depois = contagem()
    print(f"\nlinhas que mudaram de chave: {mudancas}")
    print("antes :", antes)
    print("depois:", depois)

    if args.aplicar and mudancas:
        conn.commit()
        print("MIGRAÇÃO APLICADA (rollback impossível a partir daqui; use o backup acima se precisar).")
    else:
        conn.rollback()
        print("\nSIMULAÇÃO — nada foi gravado (use --aplicar para valer).")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
