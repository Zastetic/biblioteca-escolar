"""
Cliente SED (Secretaria Digital SP) — validação de credenciais.

MVP: por padrão roda em modo MOCK (SED_ENABLED != "true"), validando contra
alunos seed no banco local — o sistema funciona de ponta a ponta sem rede.

Produção: SED_ENABLED=true → valida na API real da SED:
  POST https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken
  (mesmo fluxo do autoava — ver DOCUMENTACAO.md seção 2)

Quando o login vier do anti-bot Cloudflare (Turnstile), o token é validado
em main.py ANTES desta chamada.
"""
import os
import time

import db

SED_ENABLED = os.environ.get("SED_ENABLED", "false").lower() == "true"
# Chave de assinatura da SED — NUNCA versionada. Vem do ambiente (mvp/.env, ver .env.example).
SED_SUBSCRIPTION_KEY = os.environ.get("SED_SUBSCRIPTION_KEY", "")
SED_URL = "https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken"
SED_TIMEOUT = float(os.environ.get("SED_TIMEOUT", "8"))


def normalize_ra(ra: str) -> str:
    ra = ra.strip()
    return ra if ra.lower().endswith("sp") else f"{ra}sp"


def validar_credenciais(ra: str, senha: str) -> dict:
    """
    Retorna {"ra", "nome", "turma"} se válido. Lança ValueError com a mensagem do erro.
    """
    ra = ra.strip()
    if SED_ENABLED:
        return _validar_sed(ra, senha)
    return _validar_mock(ra, senha)


def normalizar_nome(nome: str) -> str:
    """'MARIA DA SILVA SOUZA' -> 'Maria da Silva Souza'"""
    partes = [p.lower().capitalize() for p in str(nome).strip().split()]
    prepos = {"Da", "De", "Do", "Das", "Dos", "E"}
    return " ".join(p if p not in prepos else p.lower() for p in partes)


def _validar_mock(ra: str, senha: str) -> dict:
    conn = db.conectar()
    try:
        row = conn.execute(
            "SELECT ra, nome, turma, senha_hash FROM alunos WHERE ra = ?", (ra,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("RA ou senha incorretos. Confira os dados e tente novamente.")
    if row["senha_hash"] != db.hash_senha(senha):
        raise ValueError("RA ou senha incorretos. Confira os dados e tente novamente.")
    return {"ra": row["ra"], "nome": row["nome"], "turma": row["turma"]}


def _validar_sed(ra: str, senha: str) -> dict:
    """
    Valida na SED real via LoginCompletoToken (sedintegracoes).
    Sucesso (200) -> token JWT (24h) + DadosUsuario (nome, CPF, email, nascimento).
    Credencial inválida -> HTTP 401. Em sucesso, cria/atualiza o espelho do aluno.
    """
    if not SED_SUBSCRIPTION_KEY:
        raise ValueError("SED_SUBSCRIPTION_KEY não configurada (defina em mvp/.env).")

    import requests  # import local: dependência opcional no modo mock

    try:
        resp = requests.post(
            SED_URL,
            json={"user": normalize_ra(ra), "senha": senha},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Ocp-Apim-Subscription-Key": SED_SUBSCRIPTION_KEY,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            },
            timeout=SED_TIMEOUT,
        )
    except requests.RequestException:
        raise ValueError("Serviço da Secretaria Digital indisponível. Tente novamente em instantes.")

    if resp.status_code != 200:
        # 401 -> "Usuário ou senha incorretos!" (não revela qual dos dois)
        raise ValueError("RA ou senha incorretos. Confira os dados e tente novamente.")

    dados = resp.json()
    if not dados.get("token"):
        raise ValueError("Resposta inesperada da Secretaria Digital. Tente novamente.")

    du = dados.get("DadosUsuario") or {}
    nome = normalizar_nome(du.get("NAME") or f"Aluno {ra}")
    cpf = str(du.get("NR_CPF") or "")
    email = du.get("EMAIL") or ""
    nascimento = ""
    a = du.get("A") or []
    if a and a[0].get("DT_NASC"):
        nascimento = a[0]["DT_NASC"][:10]

    conn = db.conectar()
    try:
        conn.execute(
            """INSERT INTO alunos (ra, nome, turma, cpf, email, nascimento)
               VALUES (?, ?, '', ?, ?, ?)
               ON CONFLICT(ra) DO UPDATE SET
                 nome = excluded.nome, cpf = excluded.cpf,
                 email = excluded.email, nascimento = excluded.nascimento""",
            (ra, nome, cpf, email, nascimento),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ra": ra, "nome": nome, "turma": ""}
