"""
Banco de dados da Biblioteca Escolar (SQLite).
Schema + seed do MVP. Toda escrita é parametrizada (sem concatenação de SQL).
"""
import hashlib
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("BIBLIO_DB", str(Path(__file__).resolve().parent.parent / "biblioteca.db")))

PALETA = [
    "#7a4a2b", "#8c5a2b", "#4a3f35", "#3b2f63", "#2e6e8e", "#1d5c46",
    "#1e4d8c", "#262626", "#5a3d1a", "#6b4a2b", "#8a2b2b", "#b04a5a",
]

GENEROS = ["Romance", "Mistério", "Fantasia", "Clássico", "Aventura", "Ficção", "Drama", "Juvenil"]

LIVROS_SEED = [
    dict(titulo="Dom Casmurro", autor="Machado de Assis", genero="Romance", ano=1899,
         isbn="978-85-01-00001-7", total=5, cor="#7a4a2b",
         sinopse="Bento Santiago narra, já velho, a história de sua vida: o amor por Capitu, o ciúme que o consome e a dúvida que nunca se resolve."),
    dict(titulo="O Cortiço", autor="Aluísio Azevedo", genero="Romance", ano=1890,
         isbn="978-85-01-00002-4", total=2, cor="#8c5a2b",
         sinopse="A vida agitada e miserável dos moradores de um cortiço carioca, com a ambição de João Romão como pano de fundo."),
    dict(titulo="Grande Sertão: Veredas", autor="Guimarães Rosa", genero="Clássico", ano=1956,
         isbn="978-85-01-00003-1", total=1, cor="#4a3f35",
         sinopse="A saga de Riobaldo pelo sertão, entre jagunços, amores e a pergunta sobre o diabo existir."),
    dict(titulo="Harry Potter e a Pedra Filosofal", autor="J.K. Rowling", genero="Fantasia", ano=1997,
         isbn="978-85-01-00004-8", total=4, cor="#3b2f63",
         sinopse="Harry descobre que é um bruxo e entra para Hogwarts, onde enfrenta os primeiros mistérios da escola."),
    dict(titulo="O Pequeno Príncipe", autor="Antoine de Saint-Exupéry", genero="Juvenil", ano=1943,
         isbn="978-85-01-00005-5", total=5, cor="#2e6e8e",
         sinopse="Um piloto perdido no deserto encontra um pequeno príncipe que ensina o essencial: só se vê bem com o coração."),
    dict(titulo="Um Estudo em Vermelho", autor="Arthur Conan Doyle", genero="Mistério", ano=1887,
         isbn="978-85-01-00006-2", total=2, cor="#1d5c46",
         sinopse="O primeiro caso de Sherlock Holmes e dr. Watson, em Londres, com um assassinato enigmático."),
    dict(titulo="Percy Jackson e o Ladrão de Raios", autor="Rick Riordan", genero="Aventura", ano=2005,
         isbn="978-85-01-00007-9", total=3, cor="#1e4d8c",
         sinopse="Percy descobre ser filho de Poseidon e precisa recuperar o raio-mestre de Zeus antes que estoure uma guerra."),
    dict(titulo="1984", autor="George Orwell", genero="Ficção", ano=1949,
         isbn="978-85-01-00008-6", total=1, cor="#262626",
         sinopse="Winston Smith vive sob o Grande Irmão, num regime totalitário onde até os pensamentos são vigiados."),
    dict(titulo="O Senhor dos Anéis", autor="J.R.R. Tolkien", genero="Fantasia", ano=1954,
         isbn="978-85-01-00009-3", total=1, cor="#5a3d1a",
         sinopse="Frodo e a Sociedade do Anel partem para destruir o Um Anel na Montanha da Perdição."),
    dict(titulo="Memórias Póstumas de Brás Cubas", autor="Machado de Assis", genero="Clássico", ano=1881,
         isbn="978-85-01-00010-9", total=2, cor="#6b4a2b",
         sinopse="Um defunto autor conta suas memórias sem ordem, com ironia e pessimismo deliciosos."),
    dict(titulo="A Menina que Roubava Livros", autor="Markus Zusak", genero="Drama", ano=2005,
         isbn="978-85-01-00011-6", total=2, cor="#8a2b2b",
         sinopse="Na Alemanha nazista, Liesel rouba livros e encontra nas palavras uma forma de sobreviver."),
    dict(titulo="É Assim que Acaba", autor="Colleen Hoover", genero="Romance", ano=2016,
         isbn="978-85-01-00012-3", total=2, cor="#b04a5a",
         sinopse="Lily enfrenta decisões difíceis entre o amor que sonhou e a realidade que se impõe."),
]

ALUNOS_SEED = [
    # ra, nome, turma, senha (plain para seed — hash na inserção)
    ("123456789", "Ana Souza", "3º ano A · EM", "admin123"),
    ("987654321", "Bruno Lima", "2º ano B · EM", "aluno123"),
    ("555666777", "Carla Mendes", "1º ano C · EM", "aluno123"),
]

# RA que são admin no seed
ADMINS_SEED = ["123456789"]

# Empréstimos de exemplo: (ra, livro_titulo, dias_saida, devolvido_em ou None)
# - 1984: saída há 21 dias (atrasado) · O Cortiço: saída há 7 dias (ativo)
# - Pequeno Príncipe: saída há 21 dias, devolvido 8 dias depois
EMPRESTIMOS_SEED = [
    ("987654321", "1984", 21, None),
    ("987654321", "O Cortiço", 7, None),
    ("555666777", "O Pequeno Príncipe", 21, 8),
]


def cor_para(titulo: str) -> str:
    return PALETA[int(hashlib.md5(titulo.encode("utf-8")).hexdigest(), 16) % len(PALETA)]


def hash_senha(senha: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), b"biblio-salt-mvp", 100_000).hex()


def conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS alunos (
    ra      TEXT PRIMARY KEY,
    nome    TEXT NOT NULL,
    turma   TEXT NOT NULL DEFAULT '',
    cpf     TEXT DEFAULT '',
    email   TEXT DEFAULT '',
    nascimento TEXT DEFAULT '',
    senha_hash TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS admins (
    ra TEXT PRIMARY KEY REFERENCES alunos(ra) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    autor TEXT NOT NULL DEFAULT '',
    genero TEXT NOT NULL DEFAULT '',
    ano INTEGER,
    isbn TEXT DEFAULT '',
    cor TEXT NOT NULL,
    capa_url TEXT DEFAULT '',
    sinopse TEXT DEFAULT '',
    nota_media REAL,
    nota_qtd INTEGER NOT NULL DEFAULT 0,
    nota_fonte TEXT NOT NULL DEFAULT '',
    total_exemplares INTEGER NOT NULL DEFAULT 1 CHECK (total_exemplares >= 0),
    disponiveis INTEGER NOT NULL DEFAULT 1 CHECK (disponiveis >= 0),
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS emprestimos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES livros(id) ON DELETE RESTRICT,
    aluno_ra TEXT NOT NULL REFERENCES alunos(ra) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'solicitado',
    data_solicitacao TEXT NOT NULL DEFAULT (date('now')),
    data_preparado TEXT,
    data_emprestimo TEXT,
    data_prevista TEXT,
    data_devolucao TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_emp_aluno ON emprestimos(aluno_ra);
CREATE INDEX IF NOT EXISTS idx_emp_livro ON emprestimos(livro_id);
CREATE TABLE IF NOT EXISTS sessoes (
    token_hash TEXT PRIMARY KEY,
    ra TEXT NOT NULL REFERENCES alunos(ra) ON DELETE CASCADE,
    criada_em TEXT NOT NULL DEFAULT (datetime('now')),
    expira_em TEXT NOT NULL,
    revogada_em TEXT
);
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""


def agora_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def migrar(conn: sqlite3.Connection) -> None:
    """Migra bancos antigos: fluxo solicitação→preparo→retirada + capa_url + notas."""
    # Notas externas (Open Library / Google Books) guardadas por livro
    cols_liv = {r["name"] for r in conn.execute("PRAGMA table_info(livros)").fetchall()}
    for coluna, ddl in (
        ("nota_media", "ALTER TABLE livros ADD COLUMN nota_media REAL"),
        ("nota_qtd", "ALTER TABLE livros ADD COLUMN nota_qtd INTEGER NOT NULL DEFAULT 0"),
        ("nota_fonte", "ALTER TABLE livros ADD COLUMN nota_fonte TEXT NOT NULL DEFAULT ''"),
    ):
        if coluna not in cols_liv:
            conn.execute(ddl)
    conn.commit()

    # Passo 1: emprestimos (status + datas novas)
    cols_emp = {r["name"] for r in conn.execute("PRAGMA table_info(emprestimos)").fetchall()}
    if "status" not in cols_emp:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.executescript(
                """
                CREATE TABLE emprestimos_novo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    livro_id INTEGER NOT NULL REFERENCES livros(id) ON DELETE RESTRICT,
                    aluno_ra TEXT NOT NULL REFERENCES alunos(ra) ON DELETE RESTRICT,
                    status TEXT NOT NULL DEFAULT 'solicitado',
                    data_solicitacao TEXT NOT NULL DEFAULT (date('now')),
                    data_preparado TEXT,
                    data_emprestimo TEXT,
                    data_prevista TEXT,
                    data_devolucao TEXT,
                    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
                );
                INSERT INTO emprestimos_novo (id, livro_id, aluno_ra, status, data_solicitacao, data_preparado,
                                              data_emprestimo, data_prevista, data_devolucao, criado_em)
                SELECT id, livro_id, aluno_ra,
                       CASE WHEN data_devolucao IS NOT NULL THEN 'devolvido' ELSE 'ativo' END,
                       data_emprestimo, data_emprestimo, data_emprestimo, data_prevista, data_devolucao, criado_em
                FROM emprestimos;
                DROP TABLE emprestimos;
                ALTER TABLE emprestimos_novo RENAME TO emprestimos;
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emp_aluno ON emprestimos(aluno_ra)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emp_livro ON emprestimos(livro_id)")
            conn.commit()
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    # Passo 2: livros.capa_url
    cols_liv = {r["name"] for r in conn.execute("PRAGMA table_info(livros)").fetchall()}
    if "capa_url" not in cols_liv:
        conn.execute("ALTER TABLE livros ADD COLUMN capa_url TEXT DEFAULT ''")
        conn.commit()


def expirar_solicitacoes(conn: sqlite3.Connection, prazo_preparacao_dias: int) -> None:
    """Solicitações não preparadas no prazo viram 'expirada' e liberam o exemplar."""
    rows = conn.execute(
        "SELECT id, livro_id FROM emprestimos WHERE status = 'solicitado'"
        " AND date(data_solicitacao) < date('now', ?)",
        (f"-{prazo_preparacao_dias} days",),
    ).fetchall()
    for r in rows:
        conn.execute("UPDATE emprestimos SET status = 'expirada' WHERE id = ?", (r["id"],))
        conn.execute("UPDATE livros SET disponiveis = disponiveis + 1 WHERE id = ?", (r["livro_id"],))
    if rows:
        conn.commit()


def seed(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrar(conn)

    if conn.execute("SELECT COUNT(*) FROM livros").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO livros (titulo, autor, genero, ano, isbn, cor, sinopse, total_exemplares, disponiveis)"
            " VALUES (:titulo, :autor, :genero, :ano, :isbn, :cor, :sinopse, :total, :total)",
            [dict(l, total=l["total"]) for l in LIVROS_SEED],
        )

    if conn.execute("SELECT COUNT(*) FROM alunos").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO alunos (ra, nome, turma, senha_hash) VALUES (?, ?, ?, ?)",
            [(ra, nome, turma, hash_senha(senha)) for ra, nome, turma, senha in ALUNOS_SEED],
        )

    if conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        conn.executemany("INSERT INTO admins (ra) VALUES (?)", [(ra,) for ra in ADMINS_SEED])

    if conn.execute("SELECT COUNT(*) FROM emprestimos").fetchone()[0] == 0:
        from datetime import date, timedelta
        for ra, titulo, dias_saida, dias_ate_devolver in EMPRESTIMOS_SEED:
            livro = conn.execute("SELECT id, total_exemplares FROM livros WHERE titulo = ?", (titulo,)).fetchone()
            if not livro:
                continue
            data_saida = (date.today() - timedelta(days=dias_saida)).isoformat()
            prevista = (date.fromisoformat(data_saida) + timedelta(days=14)).isoformat()
            if dias_ate_devolver:
                data_devolucao = (date.fromisoformat(data_saida) + timedelta(days=dias_ate_devolver)).isoformat()
                dec = 0  # devolvido: exemplar voltou, disponibilidade intacta
                status = "devolvido"
            else:
                data_devolucao = None
                dec = 1  # ativo/atrasado: exemplar está fora
                status = "ativo"
            conn.execute(
                "INSERT INTO emprestimos (livro_id, aluno_ra, status, data_solicitacao, data_preparado,"
                " data_emprestimo, data_prevista, data_devolucao)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (livro["id"], ra, status, data_saida, data_saida, data_saida, prevista, data_devolucao),
            )
            conn.execute("UPDATE livros SET disponiveis = disponiveis - ? WHERE id = ?", (dec, livro["id"]))

    CONFIG_DEFAULT = [
        ("prazo_emprestimo_dias", "14"),
        ("limite_livros_por_aluno", "3"),
        ("prazo_preparacao_dias", "2"),
        ("limite_solicitacoes_pendentes", "2"),
    ]
    for chave, valor in CONFIG_DEFAULT:
        conn.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))

    conn.commit()


def get_config(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
    cfg = {r["chave"]: r["valor"] for r in rows}
    return {
        "prazo_emprestimo_dias": int(cfg.get("prazo_emprestimo_dias", 14)),
        "limite_livros_por_aluno": int(cfg.get("limite_livros_por_aluno", 3)),
        "prazo_preparacao_dias": int(cfg.get("prazo_preparacao_dias", 2)),
        "limite_solicitacoes_pendentes": int(cfg.get("limite_solicitacoes_pendentes", 2)),
    }


def init_db() -> None:
    conn = conectar()
    try:
        seed(conn)
    finally:
        conn.close()
