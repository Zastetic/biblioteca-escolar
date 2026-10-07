"""Testes de fumaça do MVP — roda contra o servidor (default http://127.0.0.1:8123).

Fluxo testado: solicitação → preparo → retirada → devolução (+ cancelamento e expiração).
Uso: TEST_BASE=http://127.0.0.1:PORT ./venv/bin/python tests/test_api.py
Atenção: a suíte mexe no banco — rode com banco descartável (BIBLIO_DB).
"""
import os
import sqlite3
import sys

import requests

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8123")
DB = os.environ.get("BIBLIO_DB", "")
ok = 0
falhas = []


def check(nome, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {nome}")
    else:
        falhas.append(nome)
        print(f"  FAIL  {nome} {extra}")


def login(ra, senha):
    r = requests.post(f"{BASE}/api/auth/login", json={"ra": ra, "senha": senha})
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def auth(token):
    return {"Authorization": f"Bearer {token}"}


print("== 1. Autenticação ==")
st, j = login("987654321", "aluno123")
check("login aluno ok (200)", st == 200 and j["token"] and not j["usuario"]["is_admin"])
aluno = j["token"]

st, j = login("123456789", "admin123")
check("login admin ok (200, is_admin)", st == 200 and j["usuario"]["is_admin"])
admin = j["token"]

st, j = login("987654321", "senha_errada")
check("login senha errada (401)", st == 401)

r = requests.get(f"{BASE}/api/livros")
check("livros sem token (401)", r.status_code == 401)

print("== 2. Perfis ==")
r = requests.post(f"{BASE}/api/livros", headers=auth(aluno), json={"titulo": "X", "total_exemplares": 1})
check("aluno cria livro (403)", r.status_code == 403)
r = requests.get(f"{BASE}/api/admin/dashboard", headers=auth(aluno))
check("aluno acessa dashboard admin (403)", r.status_code == 403)
r = requests.get(f"{BASE}/api/admin/dashboard", headers=auth(admin))
check("admin acessa dashboard (200)", r.status_code == 200)

print("== 3. Livros ==")
r = requests.get(f"{BASE}/api/livros", headers=auth(aluno))
check("lista livros (200, >=12)", r.status_code == 200 and len(r.json()) >= 12)
r = requests.post(f"{BASE}/api/livros", headers=auth(admin), json={
    "titulo": "Teste de Criação", "autor": "QA", "genero": "Ficção",
    "ano": 2026, "isbn": "000", "sinopse": "livro de teste", "total_exemplares": 2})
check("admin cria livro (201)", r.status_code == 201)
livro_id = r.json()["id"]
r = requests.put(f"{BASE}/api/livros/{livro_id}", headers=auth(admin), json={
    "titulo": "Teste de Criação (editado)", "autor": "QA", "genero": "Ficção",
    "ano": 2026, "isbn": "000", "sinopse": "editado", "total_exemplares": 2})
check("admin edita livro (200)", r.status_code == 200)

print("== 4. Solicitação (aluno) ==")
r = requests.get(f"{BASE}/api/livros?q=Dom Casmurro", headers=auth(aluno))
dom_id = r.json()[0]["id"]
dom_disp = r.json()[0]["disponiveis"]

# Bruno tem 2 ativos no seed (1984 atrasado + O Cortiço). Limites: 2 pendentes / 3 ativos.
r = requests.post(f"{BASE}/api/emprestimos", headers=auth(aluno), json={"livro_id": dom_id})
check("aluno solicita Dom Casmurro (201, solicitado)", r.status_code == 201 and r.json()["status"] == "solicitado")
dom_emp = r.json()["id"]

r = requests.post(f"{BASE}/api/emprestimos", headers=auth(aluno), json={"livro_id": dom_id})
check("mesmo livro de novo (400)", r.status_code == 400 and "já tem" in r.json()["detail"])

r = requests.get(f"{BASE}/api/livros/{dom_id}", headers=auth(aluno))
check("exemplar reservado (disp -1)", r.status_code == 200 and r.json()["disponiveis"] == dom_disp - 1)

r = requests.get(f"{BASE}/api/livros?q=1984", headers=auth(aluno))
q84 = r.json()[0]
check("1984 esgotado no seed", q84["disponiveis"] == 0)
r = requests.post(f"{BASE}/api/emprestimos", headers=auth(aluno), json={"livro_id": q84["id"]})
check("pegar livro esgotado (400)", r.status_code == 400)

r = requests.get(f"{BASE}/api/livros?q=O Pequeno Príncipe", headers=auth(aluno))
pp_id = r.json()[0]["id"]
r = requests.post(f"{BASE}/api/emprestimos", headers=auth(aluno), json={"livro_id": pp_id})
check("2ª solicitação ok (201)", r.status_code == 201)
pp_emp = r.json()["id"]

r = requests.get(f"{BASE}/api/livros?q=Grande Sertão", headers=auth(aluno))
gs_id = r.json()[0]["id"]
r = requests.post(f"{BASE}/api/emprestimos", headers=auth(aluno), json={"livro_id": gs_id})
check("3ª pendente bloqueada (400, limite 2)", r.status_code == 400 and "aguardando retirada" in r.json()["detail"])

print("== 5. Cancelamento ==")
r = requests.post(f"{BASE}/api/emprestimos/cancelar", headers=auth(aluno), json={"emprestimo_id": pp_emp})
check("aluno cancela a própria solicitação (200)", r.status_code == 200)
r = requests.get(f"{BASE}/api/livros/{pp_id}", headers=auth(aluno))
check("exemplar volta ao acervo (disp +1)", r.status_code == 200 and r.json()["disponiveis"] > 0)
# empréstimo já retirado (1984 do Bruno, ativo no seed) não pode ser cancelado
r = requests.get(f"{BASE}/api/emprestimos/meus", headers=auth(aluno))
ativo_seed = [e for e in r.json() if e["status"] == "ativo"][0]
r = requests.post(f"{BASE}/api/emprestimos/cancelar", headers=auth(aluno), json={"emprestimo_id": ativo_seed["id"]})
check("cancelar empréstimo já retirado (400)", r.status_code == 400)

# Carla (sem nada) solicita; Bruno tenta cancelar o dela
st_c, j_c = login("555666777", "aluno123")
carla = j_c["token"]
r = requests.post(f"{BASE}/api/emprestimos", headers=auth(carla), json={"livro_id": pp_id})
check("Carla solicita Pequeno Príncipe (201)", r.status_code == 201)
pp_carla = r.json()["id"]
r = requests.post(f"{BASE}/api/emprestimos/cancelar", headers=auth(aluno), json={"emprestimo_id": pp_carla})
check("aluno não cancela solicitação alheia (403)", r.status_code == 403)

print("== 6. Preparo e retirada (admin) ==")
r = requests.post(f"{BASE}/api/emprestimos/preparar", headers=auth(aluno), json={"emprestimo_id": dom_emp})
check("aluno tenta preparar (403)", r.status_code == 403)
r = requests.post(f"{BASE}/api/emprestimos/retirar", headers=auth(admin), json={"emprestimo_id": dom_emp})
check("retirar antes de preparar (400)", r.status_code == 400)
r = requests.post(f"{BASE}/api/emprestimos/preparar", headers=auth(admin), json={"emprestimo_id": dom_emp})
check("admin prepara (200, pronto)", r.status_code == 200)
r = requests.post(f"{BASE}/api/emprestimos/preparar", headers=auth(admin), json={"emprestimo_id": dom_emp})
check("preparar de novo (400)", r.status_code == 400)
r = requests.post(f"{BASE}/api/emprestimos/retirar", headers=auth(admin), json={"emprestimo_id": dom_emp})
check("admin registra retirada (200, ativo + prevista)", r.status_code == 200
      and r.json().get("data_prevista"))

print("== 7. Devolução ==")
r = requests.post(f"{BASE}/api/emprestimos/devolver", headers=auth(aluno), json={"emprestimo_id": dom_emp})
check("aluno tenta devolver (403)", r.status_code == 403)
r = requests.post(f"{BASE}/api/emprestimos/devolver", headers=auth(admin), json={"emprestimo_id": pp_carla})
check("devolver solicitação ainda não retirada (400)", r.status_code == 400)
r = requests.post(f"{BASE}/api/emprestimos/devolver", headers=auth(admin), json={"emprestimo_id": dom_emp})
check("admin devolve (200)", r.status_code == 200)
r = requests.post(f"{BASE}/api/emprestimos/devolver", headers=auth(admin), json={"emprestimo_id": dom_emp})
check("devolver duas vezes (400)", r.status_code == 400)

print("== 8. Expiração automática (prazo de preparação) ==")
if DB and os.path.exists(DB):
    conn = sqlite3.connect(DB)
    try:
        conn.execute("UPDATE emprestimos SET status='solicitado', data_solicitacao=date('now','-5 days'),"
                     " data_preparado=NULL, data_emprestimo=NULL, data_prevista=NULL"
                     " WHERE id=?", (pp_carla,))
        conn.execute("UPDATE livros SET disponiveis = disponiveis - 1 WHERE id=?", (pp_id,))
        conn.commit()
    finally:
        conn.close()
    r = requests.get(f"{BASE}/api/emprestimos/meus", headers=auth(carla))
    meus = r.json()
    expirado = [e for e in meus if e["id"] == pp_carla]
    check("solicitação vencida vira expirada", bool(expirado) and expirado[0]["status"] == "expirada")
    r = requests.get(f"{BASE}/api/livros/{pp_id}", headers=auth(aluno))
    check("exemplar liberado após expirar (disp +1)", r.status_code == 200 and r.json()["disponiveis"] > 0)
else:
    print("  SKIP  expiração (BIBLIO_DB não informado)")

print("== 9. Busca de devolução (nome + livro) ==")
r = requests.get(f"{BASE}/api/emprestimos?busca=bruno 1984&somente_ativos=true", headers=auth(admin))
check("busca nome+livro acha 1984 do Bruno", r.status_code == 200 and len(r.json()) >= 1
      and r.json()[0]["titulo"] == "1984")
r = requests.get(f"{BASE}/api/emprestimos?status=solicitado", headers=auth(admin))
check("filtro por status funcionando", r.status_code == 200)

print("== 10. Logout revoga token ==")
r = requests.post(f"{BASE}/api/auth/logout", headers=auth(aluno))
check("logout (200)", r.status_code == 200)
r = requests.get(f"{BASE}/api/livros", headers=auth(aluno))
check("token revogado falha (401)", r.status_code == 401)

print("== 11. Rate limit / lockout ==")
codigos = []
for i in range(6):
    r = requests.post(f"{BASE}/api/auth/login", json={"ra": "999999999", "senha": "errada"})
    codigos.append(r.status_code)
check("5 falhas -> 429 no sexto", codigos[-1] == 429, str(codigos))

print("== 12. Config e admins ==")
r = requests.put(f"{BASE}/api/admin/config", headers=auth(admin), json={
    "prazo_emprestimo_dias": 21, "limite_livros_por_aluno": 4,
    "prazo_preparacao_dias": 3, "limite_solicitacoes_pendentes": 1})
check("config atualizada (200)", r.status_code == 200
      and r.json()["prazo_emprestimo_dias"] == 21 and r.json()["prazo_preparacao_dias"] == 3)
r = requests.put(f"{BASE}/api/admin/config", headers=auth(admin), json={
    "prazo_emprestimo_dias": 14, "limite_livros_por_aluno": 3,
    "prazo_preparacao_dias": 2, "limite_solicitacoes_pendentes": 2})
check("config restaurada", r.status_code == 200)
r = requests.delete(f"{BASE}/api/admin/admins/123456789", headers=auth(admin))
check("admin nao remove a si mesmo (400)", r.status_code == 400)
r = requests.post(f"{BASE}/api/admin/admins", headers=auth(admin), json={"ra": "555666777"})
check("adiciona admin (201)", r.status_code == 201)
r = requests.delete(f"{BASE}/api/admin/admins/555666777", headers=auth(admin))
check("remove admin (200)", r.status_code == 200)

print("== 13. Limpeza ==")
r = requests.delete(f"{BASE}/api/livros/{livro_id}", headers=auth(admin))
check("remove livro de teste (200)", r.status_code == 200)

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    print("Falhas:", falhas)
    raise SystemExit(1)
