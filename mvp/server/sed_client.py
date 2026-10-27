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
import logging
import os
import re
import time

import db

log = logging.getLogger("biblio.sed")

SED_ENABLED = os.environ.get("SED_ENABLED", "false").lower() == "true"
# Chave de assinatura da SED — NUNCA versionada. Vem do ambiente (mvp/.env, ver .env.example).
SED_SUBSCRIPTION_KEY = os.environ.get("SED_SUBSCRIPTION_KEY", "")
SED_URL = "https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken"
SED_TIMEOUT = float(os.environ.get("SED_TIMEOUT", "8"))


def corpo_json(resp) -> dict:
    """Corpo da resposta como dict (a SED às vezes responde sem JSON)."""
    try:
        dados = resp.json()
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


def mensagem_de_recusa(status_code: int, motivo: str) -> str:
    """Traduz a recusa da SED mostrando o motivo real em vez de culpar sempre o RA/senha.

    - 401 = credencial errada (mensagem genérica DE PROPÓSITO: não revela qual dos dois).
    - 403 = a SED ACEITOU a credencial e recusou a conta ("Usuário não pertence a rede
      estadual!"). Isso acontece em janelas na SED e para contas sem matrícula ativa — quem
      barrou foi a SED, não o RA/senha; esconder isso atrás de "RA ou senha incorretos" faz o
      aluno (e o dono) caçar erro na senha por horas.
    """
    if status_code == 401:
        return "RA ou senha incorretos. Confira os dados e tente novamente."
    if status_code == 403:
        return (f"A Secretaria Digital recusou esta conta ({motivo or 'acesso negado'}). "
                "A senha foi aceita — o bloqueio vem da SED. Tente de novo em alguns minutos; "
                "se persistir, procure a escola.")
    if status_code == 429:
        return "A Secretaria Digital está limitando os acessos. Tente novamente em alguns minutos."
    return ("A Secretaria Digital recusou o acesso no momento. "
            "Tente novamente em alguns minutos.")



def normalize_ra(ra: str) -> str:
    """RA como a SED espera no `user` do login (sufixo 'sp' garantido, resto como digitado)."""
    ra = ra.strip()
    return ra if ra.lower().endswith("sp") else f"{ra}sp"


def chave_aluno(ra: str) -> str:
    """Chave canônica do aluno no banco — UM RA por pessoa, não uma por jeito de digitar.

    Sem pontos/traços/espaços, minúscula, sem zeros à esquerda, com o sufixo 'sp':
    '1099851476', '1099851476sp', '1099851476SP' e '0001099851476sp' caem todos em '1099851476sp'.
    É essa chave que vai para `alunos.ra`, `sessoes.ra` e `admins.ra` (as três têm FK/cascade).
    """
    limpo = re.sub(r"[\s.\-/\\]", "", str(ra or "")).lower()
    if limpo.endswith("sp"):
        limpo = limpo[:-2]
    limpo = limpo.lstrip("0")
    return f"{limpo}sp" if limpo else ""


def validar_credenciais(ra: str, senha: str) -> dict:
    """
    Retorna {"ra", "nome", "turma"} se válido (ra = chave canônica). Lança ValueError.
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
    """Modo mock (dev offline). Procura pela chave canônica e, se não achar, pelo RA cru
    (os alunos seed do banco estão gravados sem o sufixo 'sp')."""
    conn = db.conectar()
    try:
        row = conn.execute(
            "SELECT ra, nome, turma, senha_hash FROM alunos WHERE ra IN (?, ?)",
            (chave_aluno(ra), ra),
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
    chave = chave_aluno(ra)
    if not chave:
        raise ValueError("Informe o RA do aluno.")

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
        corpo = corpo_json(resp)
        motivo = str(corpo.get("statusRetorno") or "").strip()
        # Nunca loga a senha; o RA + status já bastam para correlacionar com o relato do aluno.
        log.warning("SED recusou o login: HTTP %s statusRetorno=%r ra=%s", resp.status_code, motivo, chave)
        raise ValueError(mensagem_de_recusa(resp.status_code, motivo))

    dados = corpo_json(resp)
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
            (chave, nome, cpf, email, nascimento),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ra": chave, "nome": nome, "turma": ""}
