"""
Biblioteca Escolar — API + frontend estático (MVP).

Segurança aplicada:
- Bearer token opaco, TTL 24h, revogável no logout (tabela sessoes, hash SHA-256)
- Rate limit + lockout no login (5 falhas / 15 min por RA+IP)
- Todas as rotas /api exigem autenticação; rotas de admin exigem papel admin
- Headers de segurança: CSP, X-Frame-Options, nosniff, no-referrer, no-store em /api
- Validação de entrada (Pydantic), tamanho máximo de corpo, SQL parametrizado
- Transação atômica no empréstimo (evita dois alunos pegarem o último exemplar)
- Hook anti-bot Cloudflare Turnstile no login (ativa com TURNSTILE_SECRET_KEY)
"""
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import db
import sed_client

ZOICE_API_DIR = os.environ.get("ZOICE_API_DIR", "/home/vh450/zoice_api")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 10 * 1024 * 1024  # 10MB (uploads de capa por IA)
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY", "")

app = FastAPI(title="Biblioteca Escolar API", docs_url=None, redoc_url=None, openapi_url=None)


# =====================================================================
# Middlewares de segurança
# =====================================================================
@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.url.path.startswith("/api"):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data: https://books.google.com https://upload.wikimedia.org; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
    if os.environ.get("FORCE_HTTPS") == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        length = request.headers.get("content-length")
        if length and int(length) > MAX_BODY:
            return JSONResponse({"detail": "Corpo da requisição muito grande."}, status_code=413)
    return await call_next(request)


# =====================================================================
# Schemas
# =====================================================================
class LoginBody(BaseModel):
    ra: str = Field(min_length=1, max_length=20)
    senha: str = Field(min_length=1, max_length=128)
    cf_turnstile_token: str = ""  # preenchido quando o anti-bot estiver ativo


class LivroBody(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    autor: str = Field(default="", max_length=200)
    genero: str = Field(default="", max_length=50)
    ano: int | None = Field(default=None, ge=1000, le=2100)
    isbn: str = Field(default="", max_length=30)
    capa_url: str = Field(default="", max_length=500)
    sinopse: str = Field(default="", max_length=4000)
    total_exemplares: int = Field(default=1, ge=1, le=1000)


class EmprestimoBody(BaseModel):
    livro_id: int = Field(ge=1)


class DevolucaoBody(BaseModel):
    emprestimo_id: int = Field(ge=1)


class AdminBody(BaseModel):
    ra: str = Field(min_length=1, max_length=20)


class ConfigBody(BaseModel):
    prazo_emprestimo_dias: int | None = Field(default=None, ge=1, le=90)
    limite_livros_por_aluno: int | None = Field(default=None, ge=1, le=50)
    prazo_preparacao_dias: int | None = Field(default=None, ge=1, le=30)
    limite_solicitacoes_pendentes: int | None = Field(default=None, ge=1, le=20)


# =====================================================================
# Helpers
# =====================================================================
def _status_emprestimo(row) -> str:
    if row["data_devolucao"]:
        return "devolvido"
    st = row["status"]
    if st == "ativo" and row["data_prevista"] and row["data_prevista"] < time.strftime("%Y-%m-%d"):
        return "atrasado"
    return st


def _emprestimo_dict(row, prazo_preparacao_dias: int | None = None) -> dict:
    status = _status_emprestimo(row)
    dias = 0
    if status == "atrasado" and row["data_prevista"]:
        dias = (date.today() - date.fromisoformat(row["data_prevista"])).days
    d = {
        "id": row["id"],
        "livro_id": row["livro_id"],
        "titulo": row["titulo"],
        "autor": row["autor"],
        "cor": row["cor"],
        "aluno_ra": row["aluno_ra"],
        "aluno_nome": row["aluno_nome"],
        "status": status,
        "data_solicitacao": row["data_solicitacao"],
        "data_preparado": row["data_preparado"],
        "data_emprestimo": row["data_emprestimo"],
        "data_prevista": row["data_prevista"],
        "data_devolucao": row["data_devolucao"],
        "dias_atraso": dias,
    }
    if status == "solicitado" and prazo_preparacao_dias:
        exp = date.fromisoformat(row["data_solicitacao"]) + timedelta(days=prazo_preparacao_dias)
        d["expira_em"] = exp.isoformat()
        d["dias_restantes"] = max(0, (exp - date.today()).days)
    return d


def _validar_turnstile(request: Request, token: str) -> None:
    """Hook anti-bot Cloudflare. Só exige validação se a secret estiver configurada."""
    if not TURNSTILE_SECRET:
        return
    import requests

    if not token:
        raise HTTPException(status_code=400, detail="Falha na verificação anti-bot. Recarregue a página.")
    try:
        r = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": TURNSTILE_SECRET, "response": token,
                  "remoteip": request.client.host if request.client else ""},
            timeout=5,
        )
        ok = r.json().get("success") is True
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=403, detail="Falha na verificação anti-bot.")


# =====================================================================
# Auth
# =====================================================================
@app.post("/api/auth/login")
def login(body: LoginBody, request: Request):
    _validar_turnstile(request, body.cf_turnstile_token)
    auth.checar_rate_limit(body.ra, request)

    try:
        dados = sed_client.validar_credenciais(body.ra, body.senha)
    except ValueError as e:
        auth.registrar_falha(body.ra, request)
        raise HTTPException(status_code=401, detail=str(e))

    auth.limpar_falhas(body.ra, request)
    conn = db.conectar()
    try:
        sessao = auth.gerar_token(conn, dados["ra"])
        is_admin = conn.execute("SELECT 1 FROM admins WHERE ra = ?", (dados["ra"],)).fetchone() is not None
    finally:
        conn.close()
    return {
        "token": sessao["token"],
        "expira_em": sessao["expira_em"],
        "usuario": {"ra": dados["ra"], "nome": dados["nome"], "turma": dados["turma"], "is_admin": is_admin},
    }


@app.post("/api/auth/logout")
def logout(request: Request, user: dict = Depends(auth.get_usuario)):
    auth.revogar_token(db.conectar(), request.state.token)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.get_usuario)):
    return {"usuario": user}


# =====================================================================
# Livros (qualquer usuário autenticado lê; admin escreve)
# =====================================================================
@app.get("/api/livros")
def listar_livros(
    q: str = Query(default="", max_length=100),
    genero: str = Query(default="", max_length=50),
    user: dict = Depends(auth.get_usuario),
):
    sql = "SELECT id, titulo, autor, genero, ano, isbn, cor, capa_url, sinopse, total_exemplares, disponiveis FROM livros WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (titulo LIKE ? OR autor LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if genero:
        sql += " AND genero = ?"
        params.append(genero)
    sql += " ORDER BY titulo COLLATE NOCASE"
    conn = db.conectar()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/livros/{livro_id}")
def detalhe_livro(livro_id: int, user: dict = Depends(auth.get_usuario)):
    conn = db.conectar()
    try:
        row = conn.execute(
            "SELECT id, titulo, autor, genero, ano, isbn, cor, capa_url, sinopse, total_exemplares, disponiveis"
            " FROM livros WHERE id = ?",
            (livro_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Livro não encontrado.")
    return dict(row)


@app.post("/api/livros", status_code=201)
def criar_livro(body: LivroBody, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        cur = conn.execute(
            "INSERT INTO livros (titulo, autor, genero, ano, isbn, cor, capa_url, sinopse, total_exemplares, disponiveis)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (body.titulo, body.autor, body.genero, body.ano, body.isbn,
             db.cor_para(body.titulo), body.capa_url, body.sinopse, body.total_exemplares, body.total_exemplares),
        )
        conn.commit()
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@app.put("/api/livros/{livro_id}")
def editar_livro(livro_id: int, body: LivroBody, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        row = conn.execute("SELECT * FROM livros WHERE id = ?", (livro_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Livro não encontrado.")
        # ajuste de exemplares: não pode ficar abaixo dos emprestados
        emprestados = row["total_exemplares"] - row["disponiveis"]
        if body.total_exemplares < emprestados:
            raise HTTPException(
                status_code=400,
                detail=f"Não é possível reduzir para {body.total_exemplares}: há {emprestados} exemplar(es) emprestado(s).",
            )
        novo_disp = row["disponiveis"] + (body.total_exemplares - row["total_exemplares"])
        conn.execute(
            "UPDATE livros SET titulo=?, autor=?, genero=?, ano=?, isbn=?, capa_url=?, sinopse=?,"
            " total_exemplares=?, disponiveis=? WHERE id=?",
            (body.titulo, body.autor, body.genero, body.ano, body.isbn, body.capa_url, body.sinopse,
             body.total_exemplares, novo_disp, livro_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/livros/{livro_id}")
def remover_livro(livro_id: int, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        row = conn.execute("SELECT * FROM livros WHERE id = ?", (livro_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Livro não encontrado.")
        if row["disponiveis"] != row["total_exemplares"]:
            raise HTTPException(status_code=400, detail="Não é possível remover: há exemplares emprestados.")
        conn.execute("DELETE FROM livros WHERE id = ?", (livro_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# =====================================================================
# Leitura de capa por IA (Zoice multimodal — 0 créditos)
# =====================================================================
PROMPT_CAPA = (
    "Esta é a foto da capa de um livro. Extraia as informações dela e responda APENAS um JSON válido, "
    "sem markdown e sem texto antes ou depois, com EXATAMENTE estas chaves: "
    "titulo (string), autor (string), genero (string — escolha a mais próxima entre: Romance, Mistério, "
    "Fantasia, Clássico, Aventura, Ficção, Drama, Juvenil), ano (número ou null), isbn (string ou null, "
    "somente dígitos e hífens), sinopse (string com 1 a 2 frases resumindo a obra, ou null se não souber)."
)


def _extrair_json_ia(texto: str) -> dict:
    """Tolera ```json fences e texto solto em volta do JSON."""
    t = texto.strip()
    if t.startswith("```"):
        partes = t.split("```")
        t = partes[1] if len(partes) >= 2 else t
        t = t.strip("`").strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise HTTPException(status_code=502, detail="Não consegui interpretar a resposta da IA. Tente outra foto.")


@app.post("/api/livros/ler-capa")
async def ler_capa(file: UploadFile = File(...), user: dict = Depends(auth.require_admin)):
    """IA lê a foto da capa e devolve os dados do livro para preencher o cadastro."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie uma imagem (JPG, PNG ou WebP).")
    dados = await file.read()
    if len(dados) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagem muito grande (máximo 8MB).")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(file.content_type, ".jpg")
    tmp = Path(tempfile.gettempdir()) / f"capa_{int(time.time() * 1000)}{ext}"
    tmp.write_bytes(dados)
    try:
        if ZOICE_API_DIR not in sys.path:
            sys.path.insert(0, ZOICE_API_DIR)
        from zoice_chat import ZoiceChat

        res = ZoiceChat().ask(PROMPT_CAPA, images=[str(tmp)], max_retries=4)
        info = _extrair_json_ia(res["text"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IA de leitura indisponível no momento: {e}")
    finally:
        tmp.unlink(missing_ok=True)

    if not isinstance(info, dict):
        raise HTTPException(status_code=502, detail="Resposta da IA em formato inesperado.")
    genero = str(info.get("genero") or "").strip()
    if genero not in db.GENEROS:
        genero = ""
    ano = info.get("ano")
    try:
        ano = int(ano) if ano not in (None, "") else None
        if ano is not None and not (1000 <= ano <= 2100):
            ano = None
    except (TypeError, ValueError):
        ano = None
    return {
        "titulo": str(info.get("titulo") or "").strip(),
        "autor": str(info.get("autor") or "").strip(),
        "genero": genero,
        "ano": ano,
        "isbn": str(info.get("isbn") or "").strip(),
        "sinopse": str(info.get("sinopse") or "").strip(),
    }


# =====================================================================
# Empréstimos — fluxo: solicitado → pronto → ativo → devolvido
# =====================================================================
@app.post("/api/emprestimos", status_code=201)
def solicitar_emprestimo(body: EmprestimoBody, user: dict = Depends(auth.get_usuario)):
    conn = db.conectar()
    try:
        cfg = db.get_config(conn)
        db.expirar_solicitacoes(conn, cfg["prazo_preparacao_dias"])
        # limite de solicitações aguardando retirada (solicitado + pronto)
        pendentes = conn.execute(
            "SELECT COUNT(*) AS n FROM emprestimos WHERE aluno_ra = ? AND status IN ('solicitado', 'pronto')",
            (user["ra"],),
        ).fetchone()["n"]
        if pendentes >= cfg["limite_solicitacoes_pendentes"]:
            raise HTTPException(
                status_code=400,
                detail=f"Você já tem {pendentes} solicitação(ões) aguardando retirada (limite de {cfg['limite_solicitacoes_pendentes']}).",
            )
        # limite de livros com o aluno
        ativos = conn.execute(
            "SELECT COUNT(*) AS n FROM emprestimos WHERE aluno_ra = ? AND status = 'ativo'",
            (user["ra"],),
        ).fetchone()["n"]
        if ativos >= cfg["limite_livros_por_aluno"]:
            raise HTTPException(
                status_code=400,
                detail=f"Limite de {cfg['limite_livros_por_aluno']} livros com você atingido. Devolva um antes de pegar outro.",
            )

        # transação atômica: reserva o exemplar
        conn.execute("BEGIN IMMEDIATE")
        try:
            livro = conn.execute(
                "SELECT id, titulo, disponiveis FROM livros WHERE id = ?", (body.livro_id,)
            ).fetchone()
            if not livro:
                raise HTTPException(status_code=404, detail="Livro não encontrado.")
            if livro["disponiveis"] <= 0:
                raise HTTPException(status_code=400, detail="Todos os exemplares estão emprestados.")
            ja_pedido = conn.execute(
                "SELECT 1 FROM emprestimos WHERE aluno_ra = ? AND livro_id = ?"
                " AND status IN ('solicitado', 'pronto', 'ativo')",
                (user["ra"], body.livro_id),
            ).fetchone()
            if ja_pedido:
                raise HTTPException(status_code=400, detail="Você já tem uma solicitação ou empréstimo deste livro.")
            cur = conn.execute(
                "INSERT INTO emprestimos (livro_id, aluno_ra, status, data_solicitacao)"
                " VALUES (?, ?, 'solicitado', date('now'))",
                (body.livro_id, user["ra"]),
            )
            conn.execute("UPDATE livros SET disponiveis = disponiveis - 1 WHERE id = ?", (body.livro_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return {
            "id": cur.lastrowid,
            "livro": livro["titulo"],
            "status": "solicitado",
            "prazo_preparacao_dias": cfg["prazo_preparacao_dias"],
        }
    finally:
        conn.close()


@app.post("/api/emprestimos/preparar")
def preparar_emprestimo(body: DevolucaoBody, user: dict = Depends(auth.require_admin)):
    """Bibliotecário separa o livro: solicitado → pronto."""
    conn = db.conectar()
    try:
        row = conn.execute(
            "SELECT e.*, l.titulo FROM emprestimos e JOIN livros l ON l.id = e.livro_id WHERE e.id = ?",
            (body.emprestimo_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
        if row["status"] != "solicitado":
            raise HTTPException(status_code=400, detail="Esta solicitação não está aguardando preparo.")
        conn.execute(
            "UPDATE emprestimos SET status = 'pronto', data_preparado = date('now') WHERE id = ?",
            (body.emprestimo_id,),
        )
        conn.commit()
        return {"ok": True, "livro": row["titulo"]}
    finally:
        conn.close()


@app.post("/api/emprestimos/retirar")
def retirar_emprestimo(body: DevolucaoBody, user: dict = Depends(auth.require_admin)):
    """Aluno pegou o livro no balcão: pronto → ativo (prazo de devolução começa aqui)."""
    conn = db.conectar()
    try:
        cfg = db.get_config(conn)
        row = conn.execute(
            "SELECT e.*, l.titulo FROM emprestimos e JOIN livros l ON l.id = e.livro_id WHERE e.id = ?",
            (body.emprestimo_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Empréstimo não encontrado.")
        if row["status"] != "pronto":
            raise HTTPException(status_code=400, detail="O livro ainda não foi separado pelo bibliotecário.")
        prevista = (date.today() + timedelta(days=cfg["prazo_emprestimo_dias"])).isoformat()
        conn.execute(
            "UPDATE emprestimos SET status = 'ativo', data_emprestimo = date('now'), data_prevista = ? WHERE id = ?",
            (prevista, body.emprestimo_id),
        )
        conn.commit()
        return {"ok": True, "livro": row["titulo"], "data_prevista": prevista}
    finally:
        conn.close()


@app.post("/api/emprestimos/cancelar")
def cancelar_emprestimo(body: DevolucaoBody, user: dict = Depends(auth.get_usuario)):
    """Aluno (dono) ou admin cancela uma solicitação ainda não retirada; exemplar volta ao acervo."""
    conn = db.conectar()
    try:
        row = conn.execute(
            "SELECT e.*, l.titulo FROM emprestimos e JOIN livros l ON l.id = e.livro_id WHERE e.id = ?",
            (body.emprestimo_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
        if not user["is_admin"] and row["aluno_ra"] != user["ra"]:
            raise HTTPException(status_code=403, detail="Você só pode cancelar as próprias solicitações.")
        if row["status"] not in ("solicitado", "pronto"):
            raise HTTPException(status_code=400, detail="Só solicitações ainda não retiradas podem ser canceladas.")
        conn.execute("UPDATE emprestimos SET status = 'cancelada' WHERE id = ?", (body.emprestimo_id,))
        conn.execute("UPDATE livros SET disponiveis = disponiveis + 1 WHERE id = ?", (row["livro_id"],))
        conn.commit()
        return {"ok": True, "livro": row["titulo"]}
    finally:
        conn.close()


@app.get("/api/emprestimos/meus")
def meus_emprestimos(user: dict = Depends(auth.get_usuario)):
    conn = db.conectar()
    try:
        cfg = db.get_config(conn)
        db.expirar_solicitacoes(conn, cfg["prazo_preparacao_dias"])
        rows = conn.execute(
            """SELECT e.*, l.titulo, l.autor, l.cor, a.nome AS aluno_nome
              FROM emprestimos e
              JOIN livros l ON l.id = e.livro_id
              JOIN alunos a ON a.ra = e.aluno_ra
              WHERE e.aluno_ra = ?
              ORDER BY e.data_solicitacao DESC, e.id DESC""",
            (user["ra"],),
        ).fetchall()
    finally:
        conn.close()
    return [_emprestimo_dict(r, cfg["prazo_preparacao_dias"]) for r in rows]


@app.get("/api/emprestimos")
def listar_emprestimos(
    busca: str = Query(default="", max_length=100),
    somente_ativos: bool = Query(default=False),
    status: str = Query(default="", max_length=20),
    user: dict = Depends(auth.require_admin),
):
    """Admin: todos os empréstimos, com busca livre por nome do aluno ou título do livro."""
    sql = """SELECT e.*, l.titulo, l.autor, l.cor, a.nome AS aluno_nome, a.turma AS aluno_turma
            FROM emprestimos e
            JOIN livros l ON l.id = e.livro_id
            JOIN alunos a ON a.ra = e.aluno_ra
            WHERE 1=1"""
    params: list = []
    if busca:
        termos = [t for t in busca.split() if t]
        for t in termos:
            sql += " AND (a.nome LIKE ? OR l.titulo LIKE ?)"
            params += [f"%{t}%", f"%{t}%"]
    if somente_ativos:
        sql += " AND e.status = 'ativo'"
    if status:
        sql += " AND e.status = ?"
        params.append(status)
    if status:
        sql += " ORDER BY e.data_solicitacao ASC, e.id ASC LIMIT 100"
    else:
        sql += " ORDER BY e.data_solicitacao DESC, e.id DESC LIMIT 200"
    conn = db.conectar()
    try:
        cfg = db.get_config(conn)
        db.expirar_solicitacoes(conn, cfg["prazo_preparacao_dias"])
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [_emprestimo_dict(r, cfg["prazo_preparacao_dias"]) for r in rows]


@app.post("/api/emprestimos/devolver")
def devolver(body: DevolucaoBody, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        row = conn.execute(
            "SELECT e.*, l.titulo FROM emprestimos e JOIN livros l ON l.id = e.livro_id WHERE e.id = ?",
            (body.emprestimo_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Empréstimo não encontrado.")
        if row["status"] == "devolvido" or row["data_devolucao"]:
            raise HTTPException(status_code=400, detail="Este empréstimo já foi devolvido.")
        if row["status"] != "ativo":
            raise HTTPException(status_code=400, detail="Só empréstimos retirados podem ser devolvidos.")
        conn.execute(
            "UPDATE emprestimos SET status = 'devolvido', data_devolucao = date('now') WHERE id = ?",
            (body.emprestimo_id,),
        )
        conn.execute("UPDATE livros SET disponiveis = disponiveis + 1 WHERE id = ?", (row["livro_id"],))
        conn.commit()
        return {"ok": True, "livro": row["titulo"]}
    finally:
        conn.close()


# =====================================================================
# Admin: dashboard, config, alunos, admins
# =====================================================================
@app.get("/api/admin/dashboard")
def dashboard(user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        cfg = db.get_config(conn)
        db.expirar_solicitacoes(conn, cfg["prazo_preparacao_dias"])
        hoje = time.strftime("%Y-%m-%d")
        emprestados = conn.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE status = 'ativo'"
        ).fetchone()[0]
        atrasados = conn.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE status = 'ativo' AND data_prevista < ?", (hoje,)
        ).fetchone()[0]
        solicitados = conn.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE status = 'solicitado'"
        ).fetchone()[0]
        prontos = conn.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE status = 'pronto'"
        ).fetchone()[0]
        disp = conn.execute("SELECT COALESCE(SUM(disponiveis),0) FROM livros").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM livros").fetchone()[0]

        recentes = conn.execute(
            """SELECT e.*, l.titulo, l.autor, l.cor, a.nome AS aluno_nome
              FROM emprestimos e JOIN livros l ON l.id = e.livro_id JOIN alunos a ON a.ra = e.aluno_ra
              ORDER BY e.id DESC LIMIT 6"""
        ).fetchall()

        ranking = conn.execute(
            """SELECT l.titulo, l.autor, l.cor, COUNT(e.id) AS n
              FROM emprestimos e JOIN livros l ON l.id = e.livro_id
              GROUP BY e.livro_id ORDER BY n DESC LIMIT 5"""
        ).fetchall()

        atrasados_lista = conn.execute(
            """SELECT e.*, l.titulo, l.autor, l.cor, a.nome AS aluno_nome
              FROM emprestimos e JOIN livros l ON l.id = e.livro_id JOIN alunos a ON a.ra = e.aluno_ra
              WHERE e.status = 'ativo' AND e.data_prevista < ?
              ORDER BY e.data_prevista LIMIT 10""",
            (hoje,),
        ).fetchall()

        solicitacoes = conn.execute(
            """SELECT e.*, l.titulo, l.autor, l.cor, a.nome AS aluno_nome
              FROM emprestimos e JOIN livros l ON l.id = e.livro_id JOIN alunos a ON a.ra = e.aluno_ra
              WHERE e.status = 'solicitado'
              ORDER BY e.data_solicitacao ASC, e.id ASC LIMIT 20"""
        ).fetchall()

        prontos_lista = conn.execute(
            """SELECT e.*, l.titulo, l.autor, l.cor, a.nome AS aluno_nome
              FROM emprestimos e JOIN livros l ON l.id = e.livro_id JOIN alunos a ON a.ra = e.aluno_ra
              WHERE e.status = 'pronto'
              ORDER BY e.data_preparado ASC, e.id ASC LIMIT 20"""
        ).fetchall()
    finally:
        conn.close()
    return {
        "stats": {
            "emprestados": emprestados,
            "atrasados": atrasados,
            "solicitados": solicitados,
            "prontos": prontos,
            "disponiveis": disp,
            "total_obras": total,
        },
        "recentes": [_emprestimo_dict(r, cfg["prazo_preparacao_dias"]) for r in recentes],
        "ranking": [dict(r) for r in ranking],
        "atrasados": [_emprestimo_dict(r, cfg["prazo_preparacao_dias"]) for r in atrasados_lista],
        "solicitacoes": [_emprestimo_dict(r, cfg["prazo_preparacao_dias"]) for r in solicitacoes],
        "prontos": [_emprestimo_dict(r, cfg["prazo_preparacao_dias"]) for r in prontos_lista],
    }


@app.get("/api/admin/relatorio")
def relatorio(
    tipo: str = Query(default="emprestimos", max_length=20),
    user: dict = Depends(auth.require_admin),
):
    """Exporta CSV para a secretaria: emprestimos (todos), ativos, atrasados ou devolvidos."""
    conn = db.conectar()
    try:
        cfg = db.get_config(conn)
        db.expirar_solicitacoes(conn, cfg["prazo_preparacao_dias"])
        where = ""
        if tipo == "ativos":
            where = "WHERE e.status = 'ativo'"
        elif tipo == "atrasados":
            where = "WHERE e.status = 'ativo' AND e.data_prevista < date('now')"
        elif tipo == "devolvidos":
            where = "WHERE e.status = 'devolvido'"
        rows = conn.execute(
            f"""SELECT e.id, e.status, a.nome AS aluno, a.ra AS ra, a.turma,
                       l.titulo AS livro,
                       e.data_solicitacao AS solicitado, e.data_preparado AS preparado,
                       e.data_emprestimo AS emprestimo, e.data_prevista AS prevista,
                       e.data_devolucao AS devolucao
                FROM emprestimos e
                JOIN alunos a ON a.ra = e.aluno_ra
                JOIN livros l ON l.id = e.livro_id
                {where}
                ORDER BY e.data_solicitacao DESC, e.id DESC LIMIT 5000"""
        ).fetchall()
    finally:
        conn.close()
    header = ["id", "status", "aluno", "ra", "turma", "livro",
              "solicitado", "preparado", "emprestimo", "prevista", "devolucao"]
    linhas = [header] + [[str(r[c]) if r[c] is not None else "" for c in header] for r in rows]
    csv_text = "\n".join(";".join(l) for l in linhas)
    fname = f"biblioteca_{tipo}_{time.strftime('%Y%m%d')}.csv"
    return Response(
        content="\ufeff" + csv_text,  # BOM para o Excel abrir os acentos corretamente
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/admin/config")
def get_config(user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        return db.get_config(conn)
    finally:
        conn.close()


@app.put("/api/admin/config")
def set_config(body: ConfigBody, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        if body.prazo_emprestimo_dias is not None:
            conn.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('prazo_emprestimo_dias', ?)",
                         (str(body.prazo_emprestimo_dias),))
        if body.limite_livros_por_aluno is not None:
            conn.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('limite_livros_por_aluno', ?)",
                         (str(body.limite_livros_por_aluno),))
        if body.prazo_preparacao_dias is not None:
            conn.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('prazo_preparacao_dias', ?)",
                         (str(body.prazo_preparacao_dias),))
        if body.limite_solicitacoes_pendentes is not None:
            conn.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('limite_solicitacoes_pendentes', ?)",
                         (str(body.limite_solicitacoes_pendentes),))
        conn.commit()
        return db.get_config(conn)
    finally:
        conn.close()


@app.get("/api/admin/alunos/{ra}")
def consultar_aluno(ra: str, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        aluno = conn.execute("SELECT ra, nome, turma FROM alunos WHERE ra = ?", (ra,)).fetchone()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado. Ele precisa ter feito login ao menos uma vez.")
        cfg = db.get_config(conn)
        db.expirar_solicitacoes(conn, cfg["prazo_preparacao_dias"])
        historico = conn.execute(
            """SELECT e.*, l.titulo, l.cor, a.nome AS aluno_nome
              FROM emprestimos e JOIN livros l ON l.id = e.livro_id JOIN alunos a ON a.ra = e.aluno_ra
              WHERE e.aluno_ra = ? ORDER BY e.data_solicitacao DESC, e.id DESC""",
            (ra,),
        ).fetchall()
        ativos = sum(1 for r in historico if r["status"] == "ativo")
        pendentes = sum(1 for r in historico if r["status"] in ("solicitado", "pronto"))
        atrasos = sum(1 for r in historico if _status_emprestimo(r) == "atrasado")
        is_admin = conn.execute("SELECT 1 FROM admins WHERE ra = ?", (ra,)).fetchone() is not None
    finally:
        conn.close()
    return {
        "ra": aluno["ra"], "nome": aluno["nome"], "turma": aluno["turma"], "is_admin": is_admin,
        "ativos": ativos, "pendentes": pendentes, "atrasos": atrasos,
        "historico": [_emprestimo_dict(r) for r in historico],
    }


@app.get("/api/admin/admins")
def listar_admins(user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        rows = conn.execute(
            "SELECT a.ra, a.nome FROM admins ad JOIN alunos a ON a.ra = ad.ra ORDER BY a.nome"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/admins", status_code=201)
def adicionar_admin(body: AdminBody, user: dict = Depends(auth.require_admin)):
    conn = db.conectar()
    try:
        aluno = conn.execute("SELECT 1 FROM alunos WHERE ra = ?", (body.ra,)).fetchone()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado. Ele precisa ter feito login ao menos uma vez.")
        conn.execute("INSERT OR IGNORE INTO admins (ra) VALUES (?)", (body.ra,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/admin/admins/{ra}")
def remover_admin(ra: str, user: dict = Depends(auth.require_admin)):
    if ra == user["ra"]:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo da lista de admins.")
    conn = db.conectar()
    try:
        cur = conn.execute("DELETE FROM admins WHERE ra = ?", (ra,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="RA não é admin.")
        return {"ok": True}
    finally:
        conn.close()


# =====================================================================
# Frontend estático
# =====================================================================
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


# =====================================================================
def main():
    db.init_db()
    import uvicorn

    porta = int(os.environ.get("PORTA", "8123"))
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="info")


if __name__ == "__main__":
    main()
