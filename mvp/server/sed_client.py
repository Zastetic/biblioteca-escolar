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
import json
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
# Declaração de matrícula (dá escola, ensino, turma/série e turno). Exige a sessão `sf_sid`
# que o LoginCompletoToken devolve em Set-Cookie — por isso o login passou a usar requests.Session.
UA_SED = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")
MATRICULA_URL = ("https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/ncaapi"
                 "/api/DeclaracaoMatriculaSF/Matriculas")
SED_TIMEOUT = float(os.environ.get("SED_TIMEOUT", "8"))


def _json_bom(resp) -> dict:
    """JSON tolerante ao BOM: a resposta da NCAAPI vem com UTF-8 BOM e `resp.json()` estoura."""
    texto = resp.content.decode("utf-8-sig", errors="replace")
    try:
        dados = json.loads(texto)
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


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
    '555666777', '555666777sp', '555666777SP' e '000555666777sp' caem todos em '555666777sp'.
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

    sessao = requests.Session()
    sessao.headers.update({"User-Agent": UA_SED})
    try:
        resp = sessao.post(
            SED_URL,
            json={"user": normalize_ra(ra), "senha": senha},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Ocp-Apim-Subscription-Key": SED_SUBSCRIPTION_KEY,
                "User-Agent": UA_SED,
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
    turma = _turma_da_matricula(sessao, str(du.get("CD_USUARIO") or ""))
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
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(ra) DO UPDATE SET
                 nome = excluded.nome, cpf = excluded.cpf,
                 email = excluded.email, nascimento = excluded.nascimento,
                 turma = CASE WHEN excluded.turma <> '' THEN excluded.turma ELSE alunos.turma END""",
            (chave, nome, turma, cpf, email, nascimento),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ra": chave, "nome": nome, "turma": turma}

def _formatar_turma(bruta: str) -> str:
    """'6082 - DESENVOLVIMENTO DE SISTEMAS - 3ª SERIE B MANHA ANUAL' -> '3ª série B · Manhã'."""
    texto = " ".join(str(bruta or "").upper().split())
    if not texto:
        return ""
    import re as _re

    serie = ""
    m = _re.search(r"\b(\d+)\s*[ªA]?\s*S[EÉ]RIE\s*([A-Z])?", texto)
    if m:
        serie = f"{m.group(1)}ª série" + (f" {m.group(2)}" if m.group(2) else "")
    else:
        m = _re.search(r"\b(\d+)\s*[ºO]\s*ANO\s*([A-Z])?", texto)
        if m:
            serie = f"{m.group(1)}º ano" + (f" {m.group(2)}" if m.group(2) else "")
    turno = ""
    for chave, rotulo in (("MANHA", "Manhã"), ("TARDE", "Tarde"), ("NOITE", "Noite"),
                          ("INTEGRAL", "Integral")):
        if chave in texto:
            turno = rotulo
            break
    partes = [p for p in (serie, turno) if p]
    return " · ".join(partes) if partes else " ".join(str(bruta or "").split())[:40]


def _turma_da_matricula(sessao, cd_usuario: str) -> str:
    """Busca a turma/série na declaração de matrícula usando a sessão do login.

    Falha em silêncio (retorna "") — turma é enfeite, não pode derrubar o login.
    `codigoAluno` NÃO é o CD_USUARIO: medido em 3 contas, é o CD_USUARIO sem o último dígito.
    """
    if not cd_usuario or not SED_SUBSCRIPTION_KEY:
        return ""
    codigo = cd_usuario[:-1]
    cabecalhos = {
        "Accept": "application/json, text/plain, */*",
        "Ocp-Apim-Subscription-Key": SED_SUBSCRIPTION_KEY,
        "Origin": "https://saladofuturo.educacao.sp.gov.br",
        "Referer": "https://saladofuturo.educacao.sp.gov.br/",
        "X-Product-Name": "SalaDoFuturo",
        # sem UA de navegador o gateway da NCAAPI responde 403 com uma pagina HTML de erro
        "User-Agent": UA_SED,
    }
    ano = time.strftime("%Y")
    for ano_letivo in (ano, str(int(ano) - 1)):
        try:
            r = sessao.get(MATRICULA_URL, params={"anoLetivo": ano_letivo, "codigoAluno": codigo},
                           headers=cabecalhos, timeout=SED_TIMEOUT)
            if r.status_code != 200:
                continue
            matriculas = (_json_bom(r).get("Matriculas") or [])
            if not matriculas:
                continue
            ativa = next((m for m in matriculas if str(m.get("situacaoAluno", "")).lower() == "ativo"),
                         matriculas[0])
            return _formatar_turma(ativa.get("turma", ""))
        except Exception:
            continue
    return ""
