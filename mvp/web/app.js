/* Biblioteca Escolar — SPA (hash router) */
const App = (() => {
  const GENEROS = ["Romance", "Mistério", "Fantasia", "Clássico", "Aventura", "Ficção", "Drama", "Juvenil"];

  // ---------- helpers ----------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function toast(msg, tipo = "") {
    const zone = document.getElementById("toastZone");
    const el = document.createElement("div");
    el.className = "toast " + (tipo === "erro" ? "err" : tipo === "ok" ? "ok" : "");
    el.textContent = msg;
    zone.appendChild(el);
    setTimeout(() => {
      el.classList.add("out");
      setTimeout(() => el.remove(), 280);
    }, 3400);
  }
  function animarNumero(el, alvo, dur = 750) {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = alvo;
      return;
    }
    const t0 = performance.now();
    (function tick(t) {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(alvo * eased);
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  }
  function confirmar(msg, titulo = "Confirmar") {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "modal-overlay";
      overlay.innerHTML = `
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="${esc(titulo)}">
          <div class="orn">❦</div>
          <h3>${esc(titulo)}</h3>
          <p>${esc(msg)}</p>
          <div class="modal-actions">
            <button class="btn" data-modal="cancelar" type="button">Cancelar</button>
            <button class="btn primary" data-modal="ok" type="button">Confirmar</button>
          </div>
        </div>`;
      function fechar(valor) {
        overlay.classList.add("out");
        document.removeEventListener("keydown", escKey);
        setTimeout(() => overlay.remove(), 190);
        resolve(valor);
      }
      function escKey(e) { if (e.key === "Escape") fechar(false); }
      overlay.querySelector('[data-modal="ok"]').addEventListener("click", () => fechar(true));
      overlay.querySelector('[data-modal="cancelar"]').addEventListener("click", () => fechar(false));
      overlay.addEventListener("click", (e) => { if (e.target === overlay) fechar(false); });
      document.addEventListener("keydown", escKey);
      document.body.appendChild(overlay);
    });
  }
  function coverHtml(livro, extra = "") {
    const t = String(livro.titulo || "");
    const tituloCurto = t.length > 42 ? t.slice(0, 42) + "…" : t;
    const capa = livro.capa_url
      ? `<img class="capa-img" src="${esc(livro.capa_url)}" alt="${esc(t)}" loading="lazy" referrerpolicy="no-referrer">`
      : "";
    return `<div class="cover ${extra}" style="--c:${esc(livro.cor || "#7a4a2b")}" title="${esc(t)}">
      ${capa}
      <div class="t">${esc(tituloCurto)}</div>
      <div class="a">${esc(livro.autor || "")}</div>
    </div>`;
  }
  function badge(status) {
    const map = {
      ativo: ["Ativo", "ativo"],
      atrasado: ["Atrasado", "atrasado"],
      devolvido: ["Devolvido", "devolvido"],
      solicitado: ["Solicitado", "solicitado"],
      pronto: ["Pronto p/ retirada", "pronto"],
      expirada: ["Expirada", "expirada"],
      cancelada: ["Cancelada", "cancelada"],
    };
    const [label, cls] = map[status] || [status, ""];
    return `<span class="badge ${cls}">${label}</span>`;
  }
  function fmtData(s) {
    if (!s) return "—";
    const d = new Date(s + (s.length === 10 ? "T12:00:00" : ""));
    if (isNaN(d)) return s;
    return d.toLocaleDateString("pt-BR");
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  // ---------- sessão / header ----------
  function usuario() { return API.usuario(); }
  function logado() { return !!API.token(); }

  function renderHeader() {
    const u = usuario();
    const right = document.getElementById("headerRight");
    const sub = document.getElementById("headerSub");
    const ribbon = document.getElementById("ribbonTop");
    if (u) {
      const papel = u.is_admin ? "Bibliotecário" : "Leitor";
      sub.textContent = u.is_admin ? "Administração · 2026" : "Área do leitor · 2026";
      ribbon.textContent = u.is_admin
        ? "Área administrativa · Acesso restrito a bibliotecários"
        : "Secretaria de Educação · Acervo aberto · Devolução em até 14 dias";
      right.innerHTML = `
        <div class="header-user">
          <span class="pill">RA <b>${esc(u.ra)}</b> · ${papel}</span>
          ${u.is_admin ? `<span class="pill solic" id="pillSolic" hidden title="Ver solicitações" style="cursor:pointer"></span>` : ""}
          <button class="sair" id="btnSair">Sair</button>
        </div>
        <br>
        <button class="theme-toggle" id="themeToggle"><span id="themeIcon">☾</span> <span id="themeLabel">Escuro</span></button>`;
      const sair = document.getElementById("btnSair");
      if (sair) sair.addEventListener("click", logout);
      // contador de solicitações pendentes (notificação visual para o bibliotecário)
      if (u.is_admin) {
        API.get("/api/emprestimos?status=solicitado")
          .then((lista) => {
            const p = document.getElementById("pillSolic");
            if (!p) return;
            const n = lista.length;
            if (n > 0) {
              p.textContent = `${n} solicitação${n > 1 ? "ões" : ""} p/ preparar`;
              p.classList.add("urgente");
              p.hidden = false;
              p.addEventListener("click", () => { location.hash = "#/admin/emprestimos"; });
            }
          })
          .catch(() => {});
      }
    } else {
      sub.textContent = "Sistema de empréstimos · 2026";
      ribbon.textContent = "Secretaria de Educação · Acervo aberto · Devolução em até 14 dias";
      right.innerHTML = `
        <button class="theme-toggle" id="themeToggle"><span id="themeIcon">☾</span> <span id="themeLabel">Escuro</span></button>`;
    }
    // CSP estrita bloqueia onclick inline — liga o toggle por listener
    const tb = document.getElementById("themeToggle");
    if (tb) tb.addEventListener("click", window.biblioToggleTema);
    if (window.biblioTema) window.biblioTema();
  }

  async function logout() {
    try { await API.post("/api/auth/logout"); } catch (e) { /* token pode já estar inválido */ }
    API.limparSessao();
    renderHeader();
    location.hash = "#/login";
    toast("Sessão encerrada.", "ok");
  }

  // ---------- router ----------
  const rotas = {
    "#/login": loginView,
    "#/catalogo": catalogoView,
    "#/meus-emprestimos": meusEmprestimosView,
    "#/admin/dashboard": adminDashboardView,
    "#/admin/livros": adminLivrosView,
    "#/admin/emprestimos": adminEmprestimosView,
    "#/admin/alunos": adminAlunosView,
  };

  async function router() {
    const raw = location.hash || "#/login";
    // rotas com parâmetro: #/livro/7
    let view = rotas[raw];
    let param = null;
    if (!view && raw.startsWith("#/livro/")) {
      view = livroView;
      param = raw.split("/")[2];
    }
    const out = document.getElementById("view");
    if (!view) { out.innerHTML = `<div class="empty">Página não encontrada.</div>`; return; }

    if (!logado() && raw !== "#/login") {
      location.hash = "#/login";
      return;
    }
    const u = usuario();
    if (u && !u.is_admin && raw.startsWith("#/admin")) {
      location.hash = "#/catalogo";
      return;
    }
    if (u && u.is_admin && raw === "#/login") {
      location.hash = "#/admin/dashboard";
      return;
    }

    renderHeader();
    out.classList.remove("active");
    out.classList.add("leave");
    await new Promise(r => setTimeout(r, 130));
    out.classList.remove("leave");
    try {
      await view(out, param);
    } catch (e) {
      out.innerHTML = `<div class="empty">${esc(e.message || "Erro inesperado.")}</div>`;
    }
    out.classList.add("active");
  }

  // ---------- view: login ----------
  async function loginView(out) {
    out.innerHTML = `
      <div class="login-wrap">
        <div class="login-card">
          <div class="orn">❦ ❦ ❦</div>
          <h2>Entrar</h2>
          <p class="intro">Entre com seu RA e senha da Secretaria Digital.<br>Alunos e funcionários não precisam de cadastro.</p>
          <div class="error-box" id="loginErr"><span id="loginErrMsg"></span><button type="button" class="x" id="loginErrX">✕</button></div>
          <form id="loginForm">
            <div class="field">
              <label for="loginRa">RA do aluno</label>
              <input id="loginRa" name="ra" type="text" placeholder="Ex.: 123456789" autocomplete="username" maxlength="20">
              <div class="hint">O sufixo “sp” é adicionado automaticamente.</div>
            </div>
            <div class="field">
              <label for="loginSenha">Senha</label>
              <input id="loginSenha" name="senha" type="password" placeholder="••••••••" autocomplete="current-password" maxlength="128">
            </div>
            <button type="submit" class="btn primary" style="width:100%;padding:12px 0" id="loginBtn">Entrar na biblioteca</button>
          </form>
          <div class="login-foot">
            <span>Verificação via SED</span>
            <span class="sedsig">Secretaria Digital</span>
          </div>
        </div>
      </div>`;

    const box = $("#loginErr");
    const msg = $("#loginErrMsg");
    function showErr(t) {
      msg.textContent = t;
      box.classList.add("show");
      const card = $(".login-card");
      if (card) {
        card.classList.remove("shake");
        void card.offsetWidth; /* reinicia a animação */
        card.classList.add("shake");
      }
    }
    $("#loginErrX").addEventListener("click", () => box.classList.remove("show"));

    $("#loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const ra = $("#loginRa").value.trim();
      const senha = $("#loginSenha").value;
      box.classList.remove("show");
      if (!ra || !senha) { showErr("Preencha o RA e a senha para continuar."); return; }
      const btn = $("#loginBtn");
      btn.disabled = true; btn.textContent = "Verificando…"; btn.classList.add("loading");
      try {
        const r = await API.post("/api/auth/login", { ra, senha });
        API.salvarSessao(r.token, r.usuario);
        renderHeader();
        location.hash = r.usuario.is_admin ? "#/admin/dashboard" : "#/catalogo";
        toast(`Bem-vindo, ${r.usuario.nome.split(" ")[0]}!`, "ok");
      } catch (err) {
        showErr(err.message);
        btn.disabled = false; btn.textContent = "Entrar na biblioteca"; btn.classList.remove("loading");
      }
    });
  }

  // ---------- view: catálogo ----------
  async function catalogoView(out) {
    const u = usuario();
    out.innerHTML = `
      <div class="page-head">
        <div>
          <h2>Catálogo</h2>
          <div class="sub" id="catCount">Carregando…</div>
        </div>
        <div class="right">
          ${u && u.is_admin ? `<a href="#/admin/dashboard" class="span-link">Ir para a administração →</a>` : ""}
        </div>
      </div>
      <div class="toolbar-cat">
        <div class="busca-bar">
          <label for="busca">Buscar</label>
          <input id="busca" type="text" placeholder="por título, autor ou palavra…">
        </div>
        <select id="fGenero" class="select-classico">
          <option value="">Todos os gêneros</option>
          ${GENEROS.map(g => `<option>${g}</option>`).join("")}
        </select>
        <button class="btn" id="btnBuscar">Buscar</button>
      </div>
      <div id="gridOut"></div>`;

    const gridOut = $("#gridOut" );
    const countEl = $("#catCount" );

    function skeletonGrid(n = 8) {
      return `<div class="grid-livros">${Array.from({ length: n }, () => `
        <div class="livro-card">
          <div class="skel skel-cover"></div>
          <div class="meta">
            <div class="skel skel-t"></div>
            <div class="skel skel-a"></div>
            <div class="row"><span class="skel skel-tag"></span><span class="skel skel-tag"></span></div>
          </div>
        </div>`).join("")}</div>`;
    }

    async function carregar() {
      const q = encodeURIComponent($("#busca").value.trim());
      const g = encodeURIComponent($("#fGenero").value);
      countEl.textContent = "Buscando…";
      gridOut.innerHTML = skeletonGrid();
      let dados;
      try { dados = await API.get(`/api/livros?q=${q}&genero=${g}`); }
      catch (e) { gridOut.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
      countEl.textContent = `${dados.length} obra(s) · ${dados.filter(l => l.disponiveis > 0).length} disponíveis`;
      if (!dados.length) { gridOut.innerHTML = `<div class="empty">Nenhuma obra encontrada.</div>`; return; }
      gridOut.innerHTML = `<div class="grid-livros">${dados.map(l => `
        <div class="livro-card" data-livro="${l.id}" role="link" tabindex="0" aria-label="Ver detalhes de ${esc(l.titulo)}">
          ${coverHtml(l)}
          <div class="meta">
            <div class="t">${esc(l.titulo)}</div>
            <div class="a">${esc(l.autor)}</div>
            <div class="row"><span class="tag">${esc(l.genero)}</span><span class="disp ${l.disponiveis <= 0 ? "esgotado" : ""}">${l.disponiveis > 0 ? l.disponiveis + " disp." : "Esgotado"}</span></div>
          </div>
        </div>`).join("")}</div>`;
    }

    // CSP estrita bloqueia onclick inline — navegação por delegação de evento
    gridOut.addEventListener("click", (e) => {
      const card = e.target.closest(".livro-card");
      if (card && card.dataset.livro) location.hash = `#/livro/${card.dataset.livro}`;
    });
    gridOut.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const card = e.target.closest(".livro-card");
      if (card && card.dataset.livro) { e.preventDefault(); location.hash = `#/livro/${card.dataset.livro}`; }
    });

    // busca ao digitar (debounce) — sem precisar do botão
    let buscaTimer = null;
    $("#busca").addEventListener("input", () => {
      clearTimeout(buscaTimer);
      buscaTimer = setTimeout(carregar, 260);
    });
    $("#btnBuscar").addEventListener("click", carregar);
    $("#busca").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { clearTimeout(buscaTimer); carregar(); }
    });
    $("#fGenero").addEventListener("change", carregar);
    await carregar();
  }

  // ---------- view: detalhe do livro ----------
  async function livroView(out, id) {
    let livro;
    try { livro = await API.get(`/api/livros/${id}`); }
    catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

    out.innerHTML = `
      <div class="breadcrumb"><a href="#/catalogo" style="color:var(--ink-soft)">← Catálogo</a> / ${esc(livro.titulo)}</div>
      <div class="detalhe">
        <div class="capa-wrap">
          ${coverHtml(livro, "lg")}
          <div class="selo ${livro.disponiveis <= 0 ? "no" : ""}" id="seloDisp">${livro.disponiveis > 0 ? "Disponível" : "Esgotado"}</div>
        </div>
        <div class="info">
          <h2>${esc(livro.titulo)}</h2>
          <div class="autor">${esc(livro.autor)}</div>
          <div class="tags"><span class="tag">${esc(livro.genero)}</span>${livro.ano ? `<span class="tag">${esc(livro.ano)}</span>` : ""}</div>
          <div class="card" style="margin-top:24px">
            <h3>Sinopse</h3>
            <p style="font-size:14.5px;line-height:1.75">${esc(livro.sinopse || "Sinopse não cadastrada.")}</p>
            <div style="margin-top:18px">
              <div class="ficha-linha"><span class="k">Classificação</span><b>${esc(livro.isbn || "—")}</b></div>
              <div class="ficha-linha"><span class="k">Exemplares</span><b id="dispLine">${livro.disponiveis} de ${livro.total_exemplares} disponíveis</b></div>
            </div>
          </div>
          <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:6px">
            <button class="btn primary" id="btnAlugar" style="min-width:240px;padding:12px 0"
              ${livro.disponiveis <= 0 ? "disabled" : ""}>Solicitar empréstimo</button>
            <span class="hint" style="font-size:12.5px" id="prazoHint">Carregando prazo…</span>
          </div>
          <p class="hint" style="margin-top:14px;font-size:12px">A devolução é registrada pelo bibliotecário.</p>
        </div>
      </div>`;

    const btn = $("#btnAlugar" );
    btn.addEventListener("click", async () => {
      btn.disabled = true; btn.textContent = "Solicitando…"; btn.classList.add("loading");
      try {
        const r = await API.post("/api/emprestimos", { livro_id: Number(id) });
        toast(`Solicitação enviada! O bibliotecário vai separar "${r.livro}" — prazo de ${r.prazo_preparacao_dias} dias.`, "ok");
        location.hash = "#/meus-emprestimos";
      } catch (e) {
        toast(e.message, "erro");
        btn.disabled = false; btn.textContent = "Solicitar empréstimo"; btn.classList.remove("loading");
      }
    });
    try {
      const cfg = await API.get("/api/admin/config");
      $("#prazoHint" ).textContent = `Prazo de ${cfg.prazo_emprestimo_dias} dias p/ devolução · limite de ${cfg.limite_livros_por_aluno} com você · até ${cfg.limite_solicitacoes_pendentes} aguardando retirada`;
    } catch (e) {
      $("#prazoHint" ).textContent = "Prazo configurado pela biblioteca";
    }
  }

  // ---------- view: meus empréstimos ----------
  async function meusEmprestimosView(out) {
    let dados, cfg;
    try {
      [dados, cfg] = await Promise.all([
        API.get("/api/emprestimos/meus"),
        API.get("/api/admin/config").catch(() => null),
      ]);
    } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

    const pendentes = dados.filter(d => d.status === "solicitado" || d.status === "pronto");
    const ativos = dados.filter(d => d.status === "ativo" || d.status === "atrasado");
    const devolvidos = dados.filter(d => d.status === "devolvido");
    const outros = dados.filter(d => d.status === "expirada" || d.status === "cancelada");
    const limitePend = cfg ? cfg.limite_solicitacoes_pendentes : 2;
    const limiteAtivos = cfg ? cfg.limite_livros_por_aluno : 3;

    function linha(d) {
      let desc = "";
      if (d.status === "solicitado") {
        desc = `Solicitado em <b>${fmtData(d.data_solicitacao)}</b> · aguardando o bibliotecário separar`
          + (d.expira_em ? ` (prazo até <b>${fmtData(d.expira_em)}</b>)` : "");
      } else if (d.status === "pronto") {
        desc = `<b style="color:var(--ok)">Pronto para retirada!</b> Passe no balcão da biblioteca no recreio.`;
      } else if (d.status === "ativo") {
        desc = `Emprestado em <b>${fmtData(d.data_emprestimo)}</b> · devolução até <b>${fmtData(d.data_prevista)}</b>`;
      } else if (d.status === "atrasado") {
        desc = `Emprestado em <b>${fmtData(d.data_emprestimo)}</b> · devolução era <b>${fmtData(d.data_prevista)}</b>`
          + ` — <b style="color:var(--stamp)">${d.dias_atraso} dia(s) de atraso</b>`;
      } else if (d.status === "devolvido") {
        desc = `Devolvido em <b>${fmtData(d.data_devolucao)}</b>`;
      } else if (d.status === "expirada") {
        desc = `Solicitação expirou — o bibliotecário não separou a tempo. Faça um novo pedido no catálogo.`;
      } else {
        desc = `Solicitação cancelada.`;
      }
      const podeCancelar = d.status === "solicitado" || d.status === "pronto";
      return `
        <div class="list-item">
          <div class="cover sm" style="--c:${esc(d.cor)};pointer-events:none;cursor:default"><div class="t">${esc(d.titulo)}</div></div>
          <div class="info">
            <div class="t">${esc(d.titulo)}</div>
            <div class="a">${esc(d.autor)}</div>
            <div class="d">${desc}</div>
          </div>
          ${badge(d.status)}
          ${podeCancelar ? `<button class="btn sm" data-cancela="${d.id}" style="flex-shrink:0">Cancelar</button>` : ""}
        </div>`;
    }

    out.innerHTML = `
      <div class="page-head">
        <div>
          <h2>Meus empréstimos</h2>
          <div class="sub">${pendentes.length} aguardando retirada · ${ativos.length} com você · ${devolvidos.length} devolvido(s)</div>
        </div>
        <div class="right">Aguardando retirada: <b>${pendentes.length}/${limitePend}</b><br>Livros com você: <b>${ativos.length}/${limiteAtivos}</b></div>
      </div>
      <div class="user-actions">
        <a href="#/catalogo">← Catálogo</a>
      </div>
      <div class="card" style="padding:8px 30px">
        ${dados.length ? dados.map(linha).join("")
          : `<div class="empty">Você ainda não solicitou nenhum livro.</div>`}
      </div>
      ${pendentes.length ? `<p class="hint" style="font-size:12.5px;margin-top:14px">Quando o status mudar para <b>Pronto p/ retirada</b>, é só passar no balcão no recreio para buscar.</p>` : ""}
      <p class="hint" style="font-size:12.5px;margin-top:18px">A devolução não é feita pelo site: procure o bibliotecário para registrar a entrega.</p>`;

    $all("[data-cancela]").forEach((b) => b.addEventListener("click", async () => {
      const d = dados.find(x => x.id === Number(b.dataset.cancela));
      if (!d) return;
      if (!await confirmar(`A solicitação de "${d.titulo}" será cancelada e o exemplar volta ao acervo.`, "Cancelar solicitação")) return;
      try {
        await API.post("/api/emprestimos/cancelar", { emprestimo_id: d.id });
        toast("Solicitação cancelada.", "ok");
        await App.router();
      } catch (e) { toast(e.message, "erro"); }
    }));
  }

  // ---------- view: admin dashboard ----------
  async function adminDashboardView(out) {
    let d, cfg;
    try {
      [d, cfg] = await Promise.all([API.get("/api/admin/dashboard"), API.get("/api/admin/config")]);
    } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const s = d.stats;

    function linhaSol(x, acoes) {
      return `
        <div class="list-item" style="padding:12px 0">
          <div class="cover sm" style="--c:${esc(x.cor)};pointer-events:none;cursor:default"><div class="t">${esc(x.titulo)}</div></div>
          <div class="info">
            <div class="t">${esc(x.titulo)}</div>
            <div class="a">${esc(x.aluno_nome)}</div>
            <div class="d">${acoes.desc}</div>
          </div>
          ${badge(x.status)}
          <div style="display:flex;gap:8px;flex-shrink:0">${acoes.botoes}</div>
        </div>`;
    }

    const botaoPreparar = (x) => `<button class="btn sm primary" data-preparar="${x.id}">Separar livro</button>`;
    const botaoRetirar = (x) => `<button class="btn sm primary" data-retirar="${x.id}">Registrar retirada</button>`;
    const botaoCancelar = (x) => `<button class="btn sm danger" data-cancela="${x.id}">Cancelar</button>`;

    out.innerHTML = `
      ${adminTabs("dashboard")}
      <div class="page-head">
        <div><h2>Bom dia, bibliotecário</h2><div class="sub">Situação do acervo em ${new Date().toLocaleDateString("pt-BR")}</div></div>
        <div class="right">
          <a href="#/catalogo" class="span-link">Ver como aluno →</a><br>
          <button class="btn sm" id="btnCsv" style="margin-top:8px">Exportar CSV</button>
        </div>
      </div>
      <div class="stat-grid">
        <div class="stat warn" title="Solicitações aguardando você separar o livro"><div class="n">${s.solicitados}</div><div class="l">A preparar</div></div>
        <div class="stat ok" title="Livros separados esperando o aluno buscar no recreio"><div class="n">${s.prontos}</div><div class="l">Pronto p/ retirada</div></div>
        <div class="stat"><div class="n">${s.emprestados}</div><div class="l">Emprestados agora</div></div>
        <div class="stat warn"><div class="n">${s.atrasados}</div><div class="l">Atrasados</div></div>
        <div class="stat ok"><div class="n">${s.disponiveis}</div><div class="l">Exemplares disponíveis</div></div>
        <div class="stat"><div class="n">${s.total_obras}</div><div class="l">Obras no acervo</div></div>
      </div>
      <div class="card" style="border-color:var(--warn)">
        <h3>⚠ Solicitações para preparar (${d.solicitacoes.length})</h3>
        <p class="hint" style="margin-bottom:10px">Separe o livro e marque como pronto — o aluno vem buscar no recreio. Solicitações não preparadas em <b>${cfg.prazo_preparacao_dias} dias</b> expiram sozinhas.</p>
        ${d.solicitacoes.length ? d.solicitacoes.map(x => linhaSol(x, {
          desc: `Pedido em <b>${fmtData(x.data_solicitacao)}</b> · expira em <b>${fmtData(x.expira_em)}</b> (${x.dias_restantes} dia(s))`,
          botoes: botaoPreparar(x) + botaoCancelar(x),
        })).join("")
        : `<div class="empty" style="padding:18px">Nenhuma solicitação pendente. Tudo em dia!</div>`}
      </div>
      <div class="card" style="border-color:var(--ok)">
        <h3>Prontos aguardando retirada (${d.prontos.length})</h3>
        <p class="hint" style="margin-bottom:10px">Aluno pega no balcão durante o recreio. Registre a retirada ao entregar — o prazo de devolução começa a contar.</p>
        ${d.prontos.length ? d.prontos.map(x => linhaSol(x, {
          desc: `Separado em <b>${fmtData(x.data_preparado)}</b> para <b>${esc(x.aluno_nome)}</b>`,
          botoes: botaoRetirar(x) + botaoCancelar(x),
        })).join("")
        : `<div class="empty" style="padding:18px">Nenhum livro separado aguardando retirada.</div>`}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:24px;align-items:start;margin-bottom:24px" class="dash-cols">
        <div class="card">
          <h3>⚠ Em atraso (${d.atrasados.length})</h3>
          ${d.atrasados.length ? d.atrasados.map(x => `
            <div class="list-item" style="padding:12px 0">
              <div class="cover sm" style="--c:${esc(x.cor)};pointer-events:none;cursor:default"><div class="t">${esc(x.titulo)}</div></div>
              <div class="info">
                <div class="t">${esc(x.titulo)}</div>
                <div class="a">${esc(x.aluno_nome)}</div>
                <div class="d"><b>${x.dias_atraso} dia(s)</b> de atraso</div>
              </div>
              ${badge("atrasado")}
            </div>`).join("")
          : `<div class="empty" style="padding:20px">Nenhum atraso. Tudo em dia!</div>`}
          <a href="#/admin/emprestimos" class="btn sm" style="margin-top:8px">Ver todos</a>
        </div>
        <div class="card">
          <h3>Mais alugados do mês</h3>
          ${d.ranking.length ? d.ranking.map((r, i) => `
            <div class="rank-item"><span><b class="n">${i + 1}.</b> ${esc(r.titulo)} — ${esc(r.autor)}</span><b>${r.n}</b></div>`).join("")
          : `<div class="empty" style="padding:20px">Sem empréstimos ainda.</div>`}
        </div>
      </div>
      <div class="card">
        <h3>Empréstimos recentes</h3>
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>Aluno</th><th>Livro</th><th>Pedido</th><th>Saída</th><th>Prevista</th><th>Status</th></tr></thead>
            <tbody>
              ${d.recentes.map(x => `
                <tr><td>${esc(x.aluno_nome)}</td><td class="t-title">${esc(x.titulo)}</td>
                <td>${fmtData(x.data_solicitacao)}</td><td>${fmtData(x.data_emprestimo)}</td><td>${fmtData(x.data_prevista)}</td><td>${badge(x.status)}</td></tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <h3>Configurações da biblioteca</h3>
        <div class="config-grid">
          <div class="field">
            <label for="cfgPrazo">Prazo de empréstimo (dias)</label>
            <input id="cfgPrazo" type="number" min="1" max="90" value="${cfg.prazo_emprestimo_dias}">
          </div>
          <div class="field">
            <label for="cfgLimite">Limite de livros por aluno</label>
            <input id="cfgLimite" type="number" min="1" max="50" value="${cfg.limite_livros_por_aluno}">
          </div>
          <div class="field">
            <label for="cfgPrep">Prazo p/ preparar solicitação (dias)</label>
            <input id="cfgPrep" type="number" min="1" max="30" value="${cfg.prazo_preparacao_dias}">
            <div class="hint">Solicitações não preparadas neste prazo expiram.</div>
          </div>
          <div class="field">
            <label for="cfgPend">Limite de solicitações por aluno</label>
            <input id="cfgPend" type="number" min="1" max="20" value="${cfg.limite_solicitacoes_pendentes}">
            <div class="hint">Quantas aguardando retirada cada aluno pode ter.</div>
          </div>
        </div>
        <button class="btn primary" id="btnCfg">Salvar configurações</button>
      </div>`;

    // contadores animados ao entrar no dashboard
    $all(".stat .n").forEach((el) => {
      const alvo = parseInt(el.textContent, 10) || 0;
      el.textContent = "0";
      animarNumero(el, alvo);
    });

    async function recarregar() { await App.router(); }

    $all("[data-preparar]").forEach((b) => b.addEventListener("click", async () => {
      try {
        const r = await API.post("/api/emprestimos/preparar", { emprestimo_id: Number(b.dataset.preparar) });
        toast(`"${r.livro}" separado! Aguardando o aluno buscar.`, "ok");
        await recarregar();
      } catch (e) { toast(e.message, "erro"); }
    }));
    $all("[data-retirar]").forEach((b) => b.addEventListener("click", async () => {
      try {
        const r = await API.post("/api/emprestimos/retirar", { emprestimo_id: Number(b.dataset.retirar) });
        toast(`"${r.livro}" entregue! Devolução até ${fmtData(r.data_prevista)}.`, "ok");
        await recarregar();
      } catch (e) { toast(e.message, "erro"); }
    }));
    $all("[data-cancela]").forEach((b) => b.addEventListener("click", async () => {
      const x = d.solicitacoes.concat(d.prontos).find(y => y.id === Number(b.dataset.cancela));
      if (!x) return;
      if (!await confirmar(`A solicitação de "${x.titulo}" (${x.aluno_nome}) será cancelada e o exemplar volta ao acervo.`, "Cancelar solicitação")) return;
      try {
        await API.post("/api/emprestimos/cancelar", { emprestimo_id: x.id });
        toast("Solicitação cancelada.", "ok");
        await recarregar();
      } catch (e) { toast(e.message, "erro"); }
    }));

    $("#btnCfg").addEventListener("click", async () => {
      const body = {
        prazo_emprestimo_dias: Number($("#cfgPrazo").value),
        limite_livros_por_aluno: Number($("#cfgLimite").value),
        prazo_preparacao_dias: Number($("#cfgPrep").value),
        limite_solicitacoes_pendentes: Number($("#cfgPend").value),
      };
      try {
        await API.put("/api/admin/config", body);
        toast("Configurações salvas.", "ok");
      } catch (e) { toast(e.message, "erro"); }
    });

    $("#btnCsv").addEventListener("click", async () => {
      try {
        const resp = await fetch("/api/admin/relatorio?tipo=emprestimos", {
          headers: { Authorization: "Bearer " + API.token() },
        });
        if (!resp.ok) throw new Error("Falha ao gerar o relatório.");
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "biblioteca_emprestimos.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        toast("Relatório exportado (CSV).", "ok");
      } catch (e) { toast(e.message, "erro"); }
    });
  }

  function adminTabs(atual) {
    const tabs = [
      ["dashboard", "Dashboard"], ["livros", "Livros"], ["emprestimos", "Empréstimos"], ["alunos", "Alunos & Admins"],
    ];
    return `<nav class="tabs">${tabs.map(([k, l]) =>
      `<a class="${k === atual ? "on" : ""}" href="#/admin/${k}">${l}</a>`).join("")}</nav>`;
  }

  // ---------- view: admin livros ----------
  async function adminLivrosView(out) {
    let livros;
    try { livros = await API.get("/api/livros"); }
    catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

    out.innerHTML = `
      ${adminTabs("livros")}
      <div class="page-head">
        <div><h2>Acervo</h2><div class="sub">${livros.length} obras cadastradas</div></div>
      </div>
      <div class="card">
        <h3 id="formTitulo">Novo registro</h3>
        <form id="livroForm">
          <div class="form-grid">
            <div class="field full">
              <label>Foto da capa (preenchimento automático por IA)</label>
              <div class="capa-upload">
                <input type="file" id="fCapaFoto" accept="image/*" hidden>
                <button type="button" class="btn" id="btnCapaFoto">📷 Foto da capa</button>
                <img id="fCapaPrev" alt="Prévia da capa" hidden>
                <span class="hint" id="fCapaStatus">A IA lê a capa e preenche título, autor, gênero, ano, ISBN e sinopse.</span>
              </div>
            </div>
            <div class="field"><label>Título *</label><input id="fTitulo" required maxlength="200" placeholder="Dom Casmurro"></div>
            <div class="field"><label>Autor</label><input id="fAutor" maxlength="200" placeholder="Machado de Assis"></div>
            <div class="field"><label>ISBN</label>
              <div class="isbn-row">
                <input id="fIsbn" maxlength="30" placeholder="978-85-01-00000-0">
                <button type="button" class="btn sm" id="btnIsbnBuscar">Buscar capa</button>
              </div>
              <input type="hidden" id="fCapaUrl">
              <div class="hint" id="isbnStatus">Busca dados e capa reais pelo ISBN (Google Books).</div>
            </div>
            <div class="field"><label>Gênero</label><select id="fGenero">${GENEROS.map(g => `<option>${g}</option>`).join("")}</select></div>
            <div class="field"><label>Ano de publicação</label><input id="fAno" type="number" min="1000" max="2100" placeholder="1899"></div>
            <div class="field"><label>Exemplares *</label><input id="fTotal" type="number" min="1" max="1000" value="1"></div>
            <div class="field full"><label>Sinopse</label><textarea id="fSinopse" rows="3" maxlength="4000" placeholder="Breve descrição da obra…"></textarea></div>
          </div>
          <div style="display:flex;gap:12px;margin-top:6px">
            <button type="submit" class="btn primary" id="btnSalvarLivro">Salvar</button>
            <button type="button" class="btn" id="btnCancelarEdit" style="display:none">Cancelar edição</button>
          </div>
        </form>
      </div>
      <div class="card">
        <h3>Obras cadastradas</h3>
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th></th><th>Título</th><th>Autor</th><th>Gênero</th><th>Exemplares</th><th style="text-align:right">Ações</th></tr></thead>
            <tbody id="livrosTbody"></tbody>
          </table>
        </div>
      </div>`;

    const tbody = $("#livrosTbody");
    let editId = null;

    function linha(l) {
      return `<tr>
        <td><div class="cover sm" style="--c:${esc(l.cor)};pointer-events:none;cursor:default"><div class="t">${esc(l.titulo)}</div></div></td>
        <td class="t-title">${esc(l.titulo)}</td><td>${esc(l.autor)}</td><td><span class="tag">${esc(l.genero)}</span></td>
        <td>${l.disponiveis} / ${l.total_exemplares}</td>
        <td><div class="actions">
          <button class="btn sm" data-edit="${l.id}">Editar</button>
          <button class="btn sm danger" data-del="${l.id}">Remover</button>
        </div></td></tr>`;
    }
    function renderTabela() {
      tbody.innerHTML = livros.map(linha).join("");
      $all("[data-edit]", tbody).forEach(b => b.addEventListener("click", () => preencher(Number(b.dataset.edit))));
      $all("[data-del]", tbody).forEach(b => b.addEventListener("click", async () => {
        const l = livros.find(x => x.id === Number(b.dataset.del));
        if (!await confirmar(`“${l.titulo}” será removido do acervo. Essa ação não pode ser desfeita.`, "Remover livro")) return;
        try {
          await API.del(`/api/livros/${l.id}`);
          toast("Livro removido.", "ok");
          livros = livros.filter(x => x.id !== l.id);
          renderTabela();
        } catch (e) { toast(e.message, "erro"); }
      }));
    }

    function preencher(id) {
      const l = livros.find(x => x.id === id);
      if (!l) return;
      editId = id;
      $("#formTitulo" ).textContent = "Editar registro";
      $("#fTitulo" ).value = l.titulo; $("#fAutor" ).value = l.autor; $("#fIsbn" ).value = l.isbn;
      $("#fGenero" ).value = l.genero; $("#fAno" ).value = l.ano || ""; $("#fTotal" ).value = l.total_exemplares;
      $("#fSinopse" ).value = l.sinopse || "";
      $("#fCapaUrl" ).value = l.capa_url || "";
      const prevCapa = $("#fCapaPrev" );
      if (l.capa_url) { prevCapa.src = l.capa_url; prevCapa.hidden = false; }
      else { prevCapa.hidden = true; }
      $("#btnCancelarEdit" ).style.display = "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    $("#btnCancelarEdit").addEventListener("click", () => {
      editId = null;
      $("#formTitulo").textContent = "Novo registro";
      $("#livroForm").reset();
      $("#btnCancelarEdit").style.display = "none";
    });
    $("#livroForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = {
        titulo: $("#fTitulo" ).value.trim(),
        autor: $("#fAutor" ).value.trim(),
        genero: $("#fGenero" ).value,
        ano: $("#fAno" ).value ? Number($("#fAno" ).value) : null,
        isbn: $("#fIsbn" ).value.trim(),
        capa_url: $("#fCapaUrl" ).value.trim(),
        sinopse: $("#fSinopse" ).value.trim(),
        total_exemplares: Number($("#fTotal" ).value),
      };
      if (!body.titulo) { toast("Informe o título.", "erro"); return; }
      try {
        if (editId) {
          await API.put(`/api/livros/${editId}`, body);
          toast("Livro atualizado.", "ok");
        } else {
          await API.post("/api/livros", body);
          toast("Livro cadastrado.", "ok");
        }
        editId = null;
        $("#formTitulo").textContent = "Novo registro";
        $("#livroForm").reset();
        $("#btnCancelarEdit").style.display = "none";
        livros = await API.get("/api/livros");
        renderTabela();
      } catch (err) { toast(err.message, "erro"); }
    });

    // preenchimento automático por foto da capa (IA — Zoice multimodal)
    const inputCapa = $("#fCapaFoto" );
    $("#btnCapaFoto" ).addEventListener("click", () => inputCapa.click());
    inputCapa.addEventListener("change", async () => {
      const f = inputCapa.files[0];
      if (!f) return;
      const prevCapa = $("#fCapaPrev" );
      const statusCapa = $("#fCapaStatus" );
      prevCapa.src = URL.createObjectURL(f);
      prevCapa.hidden = false;
      statusCapa.textContent = "Analisando capa… (leva alguns segundos)";
      statusCapa.style.color = "";
      const fd = new FormData();
      fd.append("file", f);
      try {
        const d = await API.postForm("/api/livros/ler-capa", fd);
        $("#fTitulo" ).value = d.titulo || "";
        $("#fAutor" ).value = d.autor || "";
        $("#fIsbn" ).value = d.isbn || "";
        $("#fAno" ).value = d.ano || "";
        if (d.genero) $("#fGenero" ).value = d.genero;
        $("#fSinopse" ).value = d.sinopse || "";
        statusCapa.textContent = "Preenchido! Confira os dados e salve.";
        statusCapa.style.color = "var(--ok)";
      } catch (e) {
        statusCapa.textContent = e.message;
        statusCapa.style.color = "var(--stamp)";
      }
    });

    // busca de dados + capa real pelo ISBN (Google Books, sem chave)
    $("#btnIsbnBuscar" ).addEventListener("click", async () => {
      const isbn = $("#fIsbn" ).value.trim().replace(/[^0-9Xx]/g, "");
      const st = $("#isbnStatus" );
      if (isbn.length < 10) { st.textContent = "Digite um ISBN válido (10 ou 13 dígitos)."; st.style.color = "var(--stamp)"; return; }
      st.textContent = "Buscando no Google Books…";
      st.style.color = "";
      try {
        const resp = await fetch(`https://www.googleapis.com/books/v1/volumes?q=isbn:${isbn}&maxResults=1`);
        if (!resp.ok) throw new Error("Google Books indisponível no momento.");
        const data = await resp.json();
        const vol = data.items && data.items[0] && data.items[0].volumeInfo;
        if (!vol) { st.textContent = "Nenhum livro encontrado com esse ISBN."; st.style.color = "var(--stamp)"; return; }
        $("#fTitulo" ).value = vol.title || $("#fTitulo" ).value;
        $("#fAutor" ).value = (vol.authors || []).join(", ");
        const ano = vol.publishedDate ? parseInt(vol.publishedDate.slice(0, 4), 10) : null;
        if (ano && ano >= 1000 && ano <= 2100) $("#fAno" ).value = ano;
        if (vol.description) {
          $("#fSinopse" ).value = vol.description.replace(/<[^>]*>/g, "").slice(0, 4000);
        }
        const capa = vol.imageLinks && (vol.imageLinks.thumbnail || vol.imageLinks.smallThumbnail);
        if (capa) {
          const capaUrl = capa.replace(/^http:/, "https:").replace(/&edge=curl/, "");
          $("#fCapaUrl" ).value = capaUrl;
          const prevCapa = $("#fCapaPrev" );
          prevCapa.src = capaUrl;
          prevCapa.hidden = false;
        }
        st.textContent = "Preenchido pelo Google Books! Confira e salve.";
        st.style.color = "var(--ok)";
      } catch (e) {
        st.textContent = e.message;
        st.style.color = "var(--stamp)";
      }
    });

    renderTabela();
  }

  // ---------- view: admin empréstimos ----------
  async function adminEmprestimosView(out) {
    out.innerHTML = `
      ${adminTabs("emprestimos")}
      <div class="page-head"><div><h2>Empréstimos</h2><div class="sub" id="empSub">Carregando…</div></div></div>
      <div class="card" style="border-color:var(--warn)">
        <h3>📥 Solicitações para preparar</h3>
        <div id="solList"></div>
      </div>
      <div class="card" style="border-color:var(--ok)">
        <h3>📗 Prontos aguardando retirada</h3>
        <div id="prontoList"></div>
      </div>
      <div class="card">
        <h3>Registrar devolução</h3>
        <p class="hint" style="margin-bottom:16px">Identifique o empréstimo pelo <b>nome do aluno</b> e o <b>título do livro</b> — não precisa do RA.</p>
        <div class="form-row">
          <div class="field"><label for="bNome">Nome do aluno</label><input id="bNome" placeholder="Ana Souza" maxlength="100"></div>
          <div class="field"><label for="bLivro">Livro</label><input id="bLivro" placeholder="O Cortiço" maxlength="200"></div>
          <button class="btn" id="bLocalizar">Localizar</button>
        </div>
        <div id="bResultado"></div>
      </div>
      <div class="card">
        <h3>Empréstimos ativos</h3>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>Aluno</th><th>Livro</th><th>Saída</th><th>Prevista</th><th>Status</th><th style="text-align:right">Ação</th></tr></thead>
          <tbody id="ativosTbody"></tbody>
        </table></div>
      </div>
      <div class="card">
        <h3>Histórico (últimas devoluções)</h3>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>Aluno</th><th>Livro</th><th>Saída</th><th>Devolvido</th><th>Status</th></tr></thead>
          <tbody id="histTbody"></tbody>
        </table></div>
      </div>`;

    function itemLista(x, acoes) {
      return `
        <div class="list-item" style="padding:12px 0">
          <div class="cover sm" style="--c:${esc(x.cor)};pointer-events:none;cursor:default"><div class="t">${esc(x.titulo)}</div></div>
          <div class="info">
            <div class="t">${esc(x.titulo)}</div>
            <div class="a">${esc(x.aluno_nome)}</div>
            <div class="d">${acoes.desc}</div>
          </div>
          ${badge(x.status)}
          <div style="display:flex;gap:8px;flex-shrink:0">${acoes.botoes}</div>
        </div>`;
    }

    async function carregar() {
      const [sols, prontos, ativos, todos] = await Promise.all([
        API.get("/api/emprestimos?status=solicitado"),
        API.get("/api/emprestimos?status=pronto"),
        API.get("/api/emprestimos?somente_ativos=true"),
        API.get("/api/emprestimos"),
      ]);
      const hist = todos.filter(x => x.status === "devolvido").slice(0, 10);
      $("#empSub" ).textContent = `${sols.length} p/ preparar · ${prontos.length} prontos · ${ativos.length} ativo(s) · histórico completo`;

      $("#solList" ).innerHTML = sols.length ? sols.map(x => itemLista(x, {
        desc: `Pedido em <b>${fmtData(x.data_solicitacao)}</b> · expira em <b>${fmtData(x.expira_em)}</b> (${x.dias_restantes} dia(s))`,
        botoes: `<button class="btn sm primary" data-preparar="${x.id}">Separar livro</button>
                 <button class="btn sm danger" data-cancela="${x.id}">Cancelar</button>`,
      })).join("") : `<div class="empty" style="padding:16px">Nenhuma solicitação pendente.</div>`;

      $("#prontoList" ).innerHTML = prontos.length ? prontos.map(x => itemLista(x, {
        desc: `Separado em <b>${fmtData(x.data_preparado)}</b> · aguardando ${esc(x.aluno_nome)} buscar`,
        botoes: `<button class="btn sm primary" data-retirar="${x.id}">Registrar retirada</button>
                 <button class="btn sm danger" data-cancela="${x.id}">Cancelar</button>`,
      })).join("") : `<div class="empty" style="padding:16px">Nenhum livro pronto aguardando retirada.</div>`;

      $("#ativosTbody" ).innerHTML = ativos.length ? ativos.map(x => `
        <tr><td>${esc(x.aluno_nome)}</td><td class="t-title">${esc(x.titulo)}</td>
        <td>${fmtData(x.data_emprestimo)}</td><td>${fmtData(x.data_prevista)}</td>
        <td>${badge(x.status)}</td>
        <td style="text-align:right"><button class="btn sm primary" data-dev="${x.id}">Devolver</button></td></tr>`).join("")
        : `<tr><td colspan="6" class="empty">Nenhum empréstimo ativo.</td></tr>`;
      $("#histTbody" ).innerHTML = hist.length ? hist.map(x => `
        <tr><td>${esc(x.aluno_nome)}</td><td class="t-title">${esc(x.titulo)}</td>
        <td>${fmtData(x.data_emprestimo)}</td><td>${fmtData(x.data_devolucao)}</td><td>${badge(x.status)}</td></tr>`).join("")
        : `<tr><td colspan="5" class="empty">Nenhuma devolução ainda.</td></tr>`;

      $all("[data-preparar]").forEach((b) => b.addEventListener("click", async () => {
        try {
          const r = await API.post("/api/emprestimos/preparar", { emprestimo_id: Number(b.dataset.preparar) });
          toast(`"${r.livro}" separado! Aguardando o aluno buscar.`, "ok");
          await carregar();
        } catch (e) { toast(e.message, "erro"); }
      }));
      $all("[data-retirar]").forEach((b) => b.addEventListener("click", async () => {
        try {
          const r = await API.post("/api/emprestimos/retirar", { emprestimo_id: Number(b.dataset.retirar) });
          toast(`"${r.livro}" entregue! Devolução até ${fmtData(r.data_prevista)}.`, "ok");
          await carregar();
        } catch (e) { toast(e.message, "erro"); }
      }));
      $all("[data-cancela]").forEach((b) => b.addEventListener("click", async () => {
        const x = sols.concat(prontos).find(y => y.id === Number(b.dataset.cancela));
        if (!x) return;
        if (!await confirmar(`A solicitação de "${x.titulo}" (${x.aluno_nome}) será cancelada.`, "Cancelar solicitação")) return;
        try {
          await API.post("/api/emprestimos/cancelar", { emprestimo_id: x.id });
          toast("Solicitação cancelada.", "ok");
          await carregar();
        } catch (e) { toast(e.message, "erro"); }
      }));
      $all("[data-dev]", $("#ativosTbody" )).forEach((b) => b.addEventListener("click", async () => {
        try {
          const r = await API.post("/api/emprestimos/devolver", { emprestimo_id: Number(b.dataset.dev) });
          toast(`Devolução de "${r.livro}" registrada.`, "ok");
          await carregar();
        } catch (e) { toast(e.message, "erro"); }
      }));
    }

    $("#bLocalizar" ).addEventListener("click", async () => {
      const busca = `${$("#bNome" ).value.trim()} ${$("#bLivro" ).value.trim()}`.trim();
      const outEl = $("#bResultado" );
      if (!busca) { outEl.innerHTML = `<div class="empty" style="padding:16px">Digite nome e/ou livro para localizar.</div>`; return; }
      try {
        const res = await API.get(`/api/emprestimos?busca=${encodeURIComponent(busca)}&somente_ativos=true`);
        outEl.innerHTML = res.length ? res.map(x => `
          <div class="result-box">
            <div class="cover sm" style="--c:${esc(x.cor)};pointer-events:none;cursor:default"><div class="t">${esc(x.titulo)}</div></div>
            <div class="info">
              <div class="t">${esc(x.titulo)}</div>
              <div class="d"><b>${esc(x.aluno_nome)}</b> · saída ${fmtData(x.data_emprestimo)} · prevista ${fmtData(x.data_prevista)}</div>
            </div>
            ${badge(x.status)}
            <button class="btn primary sm" data-dev2="${x.id}">Registrar devolução</button>
          </div>`).join("")
          : `<div class="empty" style="padding:16px">Nenhum empréstimo ativo encontrado com essa busca.</div>`;
        $all("[data-dev2]", outEl).forEach((b) => b.addEventListener("click", async () => {
          try {
            const r = await API.post("/api/emprestimos/devolver", { emprestimo_id: Number(b.dataset.dev2) });
            toast(`Devolução de "${r.livro}" registrada.`, "ok");
            $("#bNome" ).value = ""; $("#bLivro" ).value = "";
            outEl.innerHTML = "";
            await carregar();
          } catch (e) { toast(e.message, "erro"); }
        }));
      } catch (e) { outEl.innerHTML = `<div class="empty" style="padding:16px">${esc(e.message)}</div>`; }
    });

    try { await carregar(); } catch (e) { $("#empSub" ).textContent = e.message; }
  }

  // ---------- view: admin alunos ----------
  async function adminAlunosView(out) {
    out.innerHTML = `
      ${adminTabs("alunos")}
      <div class="page-head"><div><h2>Alunos</h2><div class="sub">Dados espelhados da SED no primeiro login</div></div></div>
      <div class="card">
        <h3>Consultar aluno</h3>
        <div class="form-row">
          <div class="field"><label for="aRa">RA</label><input id="aRa" placeholder="123456789" maxlength="20"><div class="hint">O sufixo “sp” é adicionado automaticamente.</div></div>
          <button class="btn" id="aLocalizar">Localizar</button>
        </div>
        <div id="aResultado"></div>
      </div>
      <div class="card">
        <h3>Admins</h3>
        <p class="hint" style="margin-bottom:16px">Quem tem RA nesta lista entra direto na área administrativa.</p>
        <div class="form-row">
          <div class="field"><label for="admRa">RA do novo admin</label><input id="admRa" placeholder="123456789" maxlength="20"></div>
          <button class="btn primary" id="admAdd">Adicionar admin</button>
        </div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>RA</th><th>Nome</th><th style="text-align:right">Ação</th></tr></thead>
          <tbody id="admTbody"></tbody>
        </table></div>
      </div>`;

    const eu = usuario();

    async function carregarAdmins() {
      const admins = await API.get("/api/admin/admins");
      $("#admTbody").innerHTML = admins.map(a => `
        <tr><td>${esc(a.ra)}</td><td>${esc(a.nome)}</td>
        <td style="text-align:right">${a.ra === eu.ra
          ? `<span class="hint">você</span>`
          : `<button class="btn sm danger" data-admdel="${esc(a.ra)}">Remover admin</button>`}</td></tr>`).join("");
      $all("[data-admdel]").forEach(b => b.addEventListener("click", async () => {
        if (!await confirmar("Este RA perderá o acesso à administração.", "Remover admin")) return;
        try {
          await API.del(`/api/admin/admins/${encodeURIComponent(b.dataset.admdel)}`);
          toast("Admin removido.", "ok");
          await carregarAdmins();
        } catch (e) { toast(e.message, "erro"); }
      }));
    }

    $("#aLocalizar").addEventListener("click", async () => {
      const ra = $("#aRa").value.trim();
      const outEl = $("#aResultado");
      if (!ra) return;
      try {
        const a = await API.get(`/api/admin/alunos/${encodeURIComponent(ra)}`);
        outEl.innerHTML = `
          <div style="margin-top:22px;border:1px solid var(--rule);padding:20px 24px">
            <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px">
              <div>
                <div style="font-family:var(--serif);font-style:italic;font-size:19px">${esc(a.nome)}</div>
                <div style="font-size:12.5px;color:var(--ink-soft);margin-top:3px">RA <b>${esc(a.ra)}</b> · ${esc(a.turma || "—")}</div>
              </div>
              <div style="text-align:right;font-size:12.5px;line-height:1.8">
                Empréstimos ativos: <b>${a.ativos}</b> · Atrasos: <b>${a.atrasos}</b>
              </div>
            </div>
            <div class="table-wrap" style="margin-top:16px">
              <table class="table">
                <thead><tr><th>Livro</th><th>Saída</th><th>Prevista</th><th>Status</th></tr></thead>
                <tbody>${a.historico.length ? a.historico.map(h => `
                  <tr><td class="t-title">${esc(h.titulo)}</td><td>${fmtData(h.data_emprestimo)}</td>
                  <td>${fmtData(h.data_prevista)}</td><td>${badge(h.status)}</td></tr>`).join("")
                  : `<tr><td colspan="4" class="empty">Sem histórico.</td></tr>`}</tbody>
              </table>
            </div>
          </div>`;
      } catch (e) {
        outEl.innerHTML = `<div class="empty" style="padding:16px">${esc(e.message)}</div>`;
      }
    });

    $("#admAdd").addEventListener("click", async () => {
      const ra = $("#admRa").value.trim();
      if (!ra) return;
      try {
        await API.post("/api/admin/admins", { ra });
        toast("Admin adicionado.", "ok");
        $("#admRa").value = "";
        await carregarAdmins();
      } catch (e) { toast(e.message, "erro"); }
    });

    try { await carregarAdmins(); } catch (e) { $("#admTbody").innerHTML = `<tr><td colspan="3" class="empty">${esc(e.message)}</td></tr>`; }
  }

  // ---------- boot ----------
  window.addEventListener("hashchange", router);
  window.addEventListener("DOMContentLoaded", () => {
    const bh = document.getElementById("brandHome");
    if (bh) bh.addEventListener("click", () => { location.hash = logado() ? "#/catalogo" : "#/login"; });
    if (!location.hash) location.hash = logado() ? (usuario().is_admin ? "#/admin/dashboard" : "#/catalogo") : "#/login";
    router();
  });

  return { toast, router };
})();
