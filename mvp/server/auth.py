"""
Autenticação: bearer tokens opacos (não-JWT), armazenados com hash SHA-256 no banco.
- TTL padrão: 24h (configurável via TOKEN_TTL_MIN, para testes)
- Logout: marca a sessão como revogada (expira na hora)
- Rate limit + lockout no login (anti brute-force)
"""
import hashlib
import os
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request, status

import db

TTL_MINUTOS = int(os.environ.get("TOKEN_TTL_MIN", "1440"))  # 24h
LOGIN_MAX_TENTATIVAS = int(os.environ.get("LOGIN_MAX_TENTATIVAS", "8"))
LOGIN_JANELA_SEG = int(os.environ.get("LOGIN_JANELA_SEG", "600"))  # 10 min de bloqueio

# Rate limiting em memória: chave -> {"tentativas": [...timestamps...], "bloqueado_ate": ts}
_tentativas: dict = {}


def _ip_cliente(request: Request) -> str:
    """IP real do visitante.

    Atrás do túnel da Cloudflare o socket é sempre 127.0.0.1: usar `request.client.host`
    fazia o bloqueio valer por RA no mundo inteiro (qualquer erro de outra pessoa travava
    o dono). `CF-Connecting-IP` é preenchido pela Cloudflare e é o IP do visitante.
    """
    encaminhado = (request.headers.get("cf-connecting-ip") or "").strip()
    if encaminhado:
        return encaminhado
    return request.client.host if request.client else "?"


def _chave_login(ra: str, request: Request) -> str:
    # Bloqueio por RA + IP: impede ataque distribuído na mesma conta e brute force geral
    return f"{ra}|{_ip_cliente(request)}"


def checar_rate_limit(ra: str, request: Request) -> None:
    chave = _chave_login(ra, request)
    agora = time.time()
    info = _tentativas.get(chave)

    if info and info.get("bloqueado_ate") and agora < info["bloqueado_ate"]:
        restante = int(info["bloqueado_ate"] - agora)
        raise HTTPException(status_code=429, detail=f"Muitas tentativas. Tente novamente em {restante // 60 + 1} min.")

    # limpeza periódica simples
    if len(_tentativas) > 5000:
        _tentativas.clear()

    if info:
        info["tentativas"] = [t for t in info["tentativas"] if agora - t < LOGIN_JANELA_SEG]


def registrar_falha(ra: str, request: Request) -> None:
    chave = _chave_login(ra, request)
    agora = time.time()
    info = _tentativas.setdefault(chave, {"tentativas": [], "bloqueado_ate": None})
    info["tentativas"].append(agora)
    if len(info["tentativas"]) >= LOGIN_MAX_TENTATIVAS:
        info["bloqueado_ate"] = agora + LOGIN_JANELA_SEG
        info["tentativas"] = []


def limpar_falhas(ra: str, request: Request) -> None:
    _tentativas.pop(_chave_login(ra, request), None)


def gerar_token(conn, ra: str) -> dict:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expira = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + TTL_MINUTOS * 60))
    # purge de sessões velhas (expiradas/revogadas) pra tabela não crescer
    conn.execute("DELETE FROM sessoes WHERE expira_em < datetime('now') OR revogada_em IS NOT NULL")
    conn.execute(
        "INSERT INTO sessoes (token_hash, ra, expira_em) VALUES (?, ?, ?)",
        (token_hash, ra, expira),
    )
    conn.commit()
    return {"token": token, "expira_em": expira}


def revogar_token(conn, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn.execute(
        "UPDATE sessoes SET revogada_em = datetime('now') WHERE token_hash = ? AND revogada_em IS NULL",
        (token_hash,),
    )
    conn.commit()


def usuario_por_token(conn, token: str):
    """Retorna dict do aluno + is_admin se o token for válido; senão None."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        """
        SELECT s.ra, s.expira_em,
               a.nome, a.turma,
               (SELECT COUNT(*) FROM admins ad WHERE ad.ra = a.ra) AS is_admin
        FROM sessoes s JOIN alunos a ON a.ra = s.ra
        WHERE s.token_hash = ? AND s.revogada_em IS NULL AND s.expira_em >= datetime('now')
        """,
        (token_hash,),
    ).fetchone()
    if not row:
        return None
    return {
        "ra": row["ra"],
        "nome": row["nome"],
        "turma": row["turma"],
        "is_admin": bool(row["is_admin"]),
    }


def extrair_bearer(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou formato inválido.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token ausente.")
    return token


def get_usuario(request: Request, authorization: str = Header(default="")) -> dict:
    """Dependency: exige token válido (não expirado, não revogado)."""
    token = extrair_bearer(authorization)
    conn = db.conectar()
    try:
        user = usuario_por_token(conn, token)
    finally:
        conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada. Faça login novamente.")
    # guarda o token cru no state da request (logout precisa dele)
    request.state.token = token
    return user


def require_admin(user: dict = Depends(get_usuario)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Acesso restrito a bibliotecários.")
    return user
