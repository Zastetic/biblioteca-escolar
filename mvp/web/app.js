/* Biblioteca Escolar — SPA (hash router) */
const App = (() => {
  const GENEROS = ["Romance", "Mistério", "Fantasia", "Clássico", "Aventura", "Ficção", "Drama", "Juvenil"];
  let loginMatrixObserver = null;
  let loginMatrixResizeHandler = null;

  function releaseLoginMatrixObserver() {
    if (loginMatrixObserver) {
      loginMatrixObserver.disconnect();
      loginMatrixObserver = null;
    }
    if (loginMatrixResizeHandler) {
      window.removeEventListener("resize", loginMatrixResizeHandler);
      loginMatrixResizeHandler = null;
    }
  }

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
    return `<div class="cover ${extra}${capa ? " tem-capa" : ""}" style="--c:${esc(livro.cor || "#7a4a2b")}" title="${esc(t)}">
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
      sub.textContent = "Biblioteca escolar · 2026";
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

  // rotas curtas/antigas que ainda podem estar salvas em links e favoritos
  const atalhosRota = {
    "#/admin": "#/admin/dashboard",
    "#/livros": "#/catalogo",
    "#/emprestimos": "#/meus-emprestimos",
    "#/alunos": "#/admin/alunos",
  };

  async function router() {
    const raw = location.hash || "#/login";
    if (raw !== "#/login") releaseLoginMatrixObserver();
    // rotas com parâmetro: #/livro/7
    let view = rotas[raw];
    let param = null;
    if (!view && raw.startsWith("#/livro/")) {
      view = livroView;
      param = raw.split("/")[2];
    }
    const out = document.getElementById("view");
    if (!view) {
      // hash desconhecido (ou "#/admin" sem aba): manda para a tela inicial do perfil
      const u = usuario();
      location.hash = atalhosRota[raw]
        || (!logado() ? "#/login" : (u && u.is_admin ? "#/admin/dashboard" : "#/catalogo"));
      return;
    }

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
    releaseLoginMatrixObserver();
    out.innerHTML = `
      <div class="login-wrap">
        <div class="login-matrix-band" aria-hidden="true">
          <div class="kana-matrix"></div>
        </div>
        <section class="login-showcase" aria-label="Acesse o acervo da escola">
          <p class="showcase-kicker"><span aria-hidden="true"></span> Leitura em movimento</p>
          <h2>Entre no acervo.<br><span>Encontre sua próxima leitura.</span></h2>
          <p class="showcase-copy">Use seu RA para consultar, solicitar e acompanhar livros da biblioteca.</p>
        </section>
        <div class="login-card-scene">
          <div class="login-card">
            <div class="login-card-top"><span>Entrar com RA e senha</span><span class="login-accent" aria-hidden="true"></span></div>
            <h2>Entrar</h2>
            <p class="intro">Entre com seu RA e senha da Secretaria Digital. Alunos e funcionários não precisam de cadastro.</p>
            <div class="error-box" id="loginErr"><span id="loginErrMsg"></span><button type="button" class="x" id="loginErrX">✕</button></div>
            <form id="loginForm">
              <div class="field">
                <label for="loginRa">RA do aluno</label>
                <input id="loginRa" name="ra" type="text" placeholder="Ex.: 123456789" autocomplete="username" maxlength="20">
                <div class="hint">O sufixo “sp” é adicionado automaticamente.</div>
              </div>
              <div class="field">
                <label for="loginSenha">Senha</label>
                <input id="loginSenha" name="senha" type="password" placeholder="Digite sua senha" autocomplete="current-password" maxlength="128">
              </div>
              <div class="turnstile-slot" id="cfTurnstile" hidden></div>
              <button type="submit" class="btn primary" style="width:100%;padding:12px 0" id="loginBtn">Entrar na biblioteca</button>
              <div class="anti-bot-hint" id="cfHint" hidden>Verificação anti-robô da Cloudflare · evita bloqueio por tentativas.</div>
            </form>
            <div class="login-foot">
              <span>Autenticação via</span>
              <span class="sedsig">Secretaria Digital</span>
            </div>
          </div>
        </div>
      </div>`;

    const matrix = $(".kana-matrix", out);
    const band = $(".login-matrix-band", out);
    const loginWrap = $(".login-wrap", out);
    const scene = $(".login-card-scene", out);
    if (matrix && band && loginWrap && scene) {
      const glyphs = Array.from("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ");
      const preencherMatriz = () => {
        if (!matrix.isConnected || !band.isConnected || !loginWrap.isConnected || !scene.isConnected) {
          releaseLoginMatrixObserver();
          return;
        }
        const sceneRect = scene.getBoundingClientRect();
        const wrapRect = loginWrap.getBoundingClientRect();
        band.style.left = `${sceneRect.left + sceneRect.width / 2 - wrapRect.left + 15}px`;
        const bandRect = band.getBoundingClientRect();
        const columns = Math.max(1, Math.ceil(bandRect.width / 40) + 1);
        const rows = Math.max(1, Math.ceil(bandRect.height / 40) + 1);
        const targetCount = columns * rows;
        while (matrix.children.length > targetCount) matrix.lastElementChild.remove();
        const fragment = document.createDocumentFragment();
        for (let i = matrix.children.length; i < targetCount; i++) {
          const cell = document.createElement("span");
          cell.textContent = glyphs[i % glyphs.length];
          fragment.appendChild(cell);
        }
        matrix.appendChild(fragment);
      };
      preencherMatriz();
      if ("ResizeObserver" in window) {
        loginMatrixObserver = new ResizeObserver(preencherMatriz);
        loginMatrixObserver.observe(loginWrap);
        loginMatrixObserver.observe(scene);
      } else {
        loginMatrixResizeHandler = preencherMatriz;
        window.addEventListener("resize", loginMatrixResizeHandler, { passive: true });
      }
    }

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

    // ---- anti-bot Cloudflare Turnstile (só ativa quando o servidor informa a sitekey) ----
    let turnstileToken = "";
    let turnstileWidget = null;
    let captchaSitekey = "";
    let captchaAtivo = false;
    let captchaFalhou = false;

    function estadoBotao(travado, rotulo) {
      const b = $("#loginBtn");
      if (!b) return;
      b.disabled = !!travado;
      b.classList.toggle("loading", !!travado && !!rotulo);
      b.textContent = rotulo || "Entrar na biblioteca";
    }

    // O botão só fica clicável quando dá para entrar: RA + senha preenchidos e,
    // se o anti-bot estiver ativo, token do captcha já resolvido (o endpoint exige).
    function camposPreenchidos() {
      const ra = ($("#loginRa") || {}).value || "";
      const senha = ($("#loginSenha") || {}).value || "";
      return !!ra.trim() && !!senha;
    }

    function atualizarBotao() {
      if (captchaFalhou) return estadoBotao(true, "Verificação falhou");
      if (!camposPreenchidos()) return estadoBotao(true);
      if (captchaAtivo && !turnstileToken) return estadoBotao(true, "Aguardando verificação…");
      return estadoBotao(false);
    }
    const sincronizarBotao = atualizarBotao;

    async function prepararCaptcha() {
      let sitekey = "";
      try {
        const cfg = await API.get("/api/publico");
        sitekey = (cfg && cfg.turnstile_sitekey) || "";
      } catch (e) {
        sitekey = "";
      }
      if (!sitekey) return; // servidor sem anti-bot: login segue como antes
      captchaAtivo = true;
      atualizarBotao();
      captchaSitekey = sitekey;
      const alvo = $("#cfTurnstile");
      const dica = $("#cfHint");
      if (alvo) alvo.hidden = false;
      if (dica) dica.hidden = false;
      const carregar = () => new Promise((ok, falha) => {
        if (window.turnstile) return ok();
        const s = document.createElement("script");
        s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
        s.async = true;
        s.defer = true;
        s.onload = ok;
        s.onerror = falha;
        document.head.appendChild(s);
      });
      try {
        await carregar();
        turnstileWidget = window.turnstile.render("#cfTurnstile", {
          sitekey,
          language: "pt-BR",
          theme: document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light",
          callback: (t) => { turnstileToken = t; captchaFalhou = false; sincronizarBotao(); },
          "expired-callback": () => { turnstileToken = ""; sincronizarBotao(); },
          "error-callback": () => { turnstileToken = ""; sincronizarBotao(); },
        });
      } catch (e) {
        captchaFalhou = true;
        estadoBotao(true, "Verificação falhou");
        showErr("Não foi possível carregar a verificação anti-robô. Recarregue a página.");
      }
    }
    prepararCaptcha();

    ["#loginRa", "#loginSenha"].forEach((sel) => {
      const el = $(sel);
      if (el) el.addEventListener("input", atualizarBotao);
    });
    atualizarBotao();

    $(".theme-toggle", document)?.addEventListener("click", () => {
      // o widget do Turnstile não troca de tema sozinho: recria no tema atual
      if (!captchaAtivo || captchaFalhou || !window.turnstile || turnstileWidget === null) return;
      const t = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
      try { window.turnstile.remove(turnstileWidget); } catch (e) { /* widget já removido */ }
      turnstileToken = "";
      turnstileWidget = window.turnstile.render("#cfTurnstile", {
        sitekey: captchaSitekey,
        language: "pt-BR",
        theme: t,
        callback: (tok) => { turnstileToken = tok; captchaFalhou = false; sincronizarBotao(); },
        "expired-callback": () => { turnstileToken = ""; sincronizarBotao(); },
      });
    });

    $("#loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const ra = $("#loginRa").value.trim();
      const senha = $("#loginSenha").value;
      box.classList.remove("show");
      if (!ra || !senha) { showErr("Preencha o RA e a senha para continuar."); return; }
      if (captchaAtivo) {
        if (captchaFalhou) { showErr("A verificação anti-robô não carregou. Recarregue a página e tente de novo."); return; }
        if (!turnstileToken) { showErr("Aguarde a verificação anti-robô terminar."); sincronizarBotao(); return; }
      }
      const btn = $("#loginBtn");
      btn.disabled = true; btn.textContent = "Verificando…"; btn.classList.add("loading");
      try {
        const r = await API.post("/api/auth/login", { ra, senha, cf_turnstile_token: turnstileToken });
        API.salvarSessao(r.token, r.usuario);
        renderHeader();
        location.hash = r.usuario.is_admin ? "#/admin/dashboard" : "#/catalogo";
        toast(`Bem-vindo, ${r.usuario.nome.split(" ")[0]}!`, "ok");
      } catch (err) {
        showErr(err.message);
        btn.classList.remove("loading");
        if (captchaAtivo && window.turnstile && turnstileWidget !== null) {
          turnstileToken = "";
          try { window.turnstile.reset(turnstileWidget); } catch (e2) { /* nada */ }
        }
        atualizarBotao();
      }
    });
  }

  // ---------- view: catálogo ----------
  async function catalogoView(out) {
    const u = usuario();
    const POR_PAGINA = 24;
    let todos = [];
    let pagina = 1;

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
      <div id="prateleiras"></div>
      <div id="gridOut"></div>
      <div id="paginacao"></div>`;

    const prateleiras = $("#prateleiras");
    const gridOut = $("#gridOut");
    const paginacao = $("#paginacao");
    const countEl = $("#catCount");

    function estrelas(livro) {
      if (!livro.nota_media) return "";
      const nota = Number(livro.nota_media);
      const cheias = Math.round(nota);
      const estrelas = "★".repeat(cheias) + "☆".repeat(Math.max(0, 5 - cheias));
      const qtd = livro.nota_qtd || 0;
      return `<span class="nota" title="Nota ${nota.toFixed(1)} com ${qtd} avaliações (${esc(livro.nota_fonte || "catálogo externo")})">
        <span class="estrelas" aria-hidden="true">${estrelas}</span>
        <b>${nota.toFixed(1).replace(".", ",")}</b>
        <span class="nota-qtd">(${qtd})</span>
      </span>`;
    }

    function cardHtml(l, classe = "") {
      return `<div class="livro-card ${classe}" data-livro="${l.id}" role="link" tabindex="0" aria-label="Ver detalhes de ${esc(l.titulo)}">
          ${coverHtml(l)}
          <div class="meta">
            <div class="t">${esc(l.titulo)}</div>
            <div class="a">${esc(l.autor)}</div>
            <div class="row"><span class="tag">${esc(l.genero)}</span><span class="disp ${l.disponiveis <= 0 ? "esgotado" : ""}">${l.disponiveis > 0 ? l.disponiveis + " disp." : "Esgotado"}</span></div>
            ${estrelas(l)}
          </div>
        </div>`;
    }

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

    // prateleira horizontal: swipe no celular, setas no desktop
    function prateleira(titulo, sub, lista) {
      if (!lista || !lista.length) return "";
      return `<section class="prateleira" aria-label="${esc(titulo)}">
        <div class="prateleira-head">
          <div>
            <h3>${esc(titulo)}</h3>
            ${sub ? `<div class="prateleira-sub">${esc(sub)}</div>` : ""}
          </div>
          <div class="prateleira-setas">
            <button type="button" class="seta" data-dir="-1" aria-label="Ver anteriores">‹</button>
            <button type="button" class="seta" data-dir="1" aria-label="Ver próximos">›</button>
          </div>
        </div>
        <div class="trilho">${lista.map(l => cardHtml(l, "sm")).join("")}</div>
      </section>`;
    }

    function renderPagina() {
      const totalPaginas = Math.max(1, Math.ceil(todos.length / POR_PAGINA));
      if (pagina > totalPaginas) pagina = totalPaginas;
      const inicio = (pagina - 1) * POR_PAGINA;
      const fatia = todos.slice(inicio, inicio + POR_PAGINA);
      gridOut.innerHTML = fatia.length
        ? `<div class="grid-livros">${fatia.map(l => cardHtml(l)).join("")}</div>`
        : `<div class="empty">Nenhuma obra encontrada.</div>`;

      if (totalPaginas <= 1) {
        paginacao.innerHTML = "";
        return;
      }
      paginacao.innerHTML = `
        <div class="paginacao">
          <button type="button" class="btn sm" data-pagina="${pagina - 1}" ${pagina === 1 ? "disabled" : ""}>‹ Anterior</button>
          <span class="pagina-info">Página <b>${pagina}</b> de ${totalPaginas}
            <span class="pagina-faixa">· ${inicio + 1}–${inicio + fatia.length} de ${todos.length}</span></span>
          <button type="button" class="btn sm" data-pagina="${pagina + 1}" ${pagina === totalPaginas ? "disabled" : ""}>Próxima ›</button>
        </div>`;
    }

    async function carregarPrateleiras() {
      try {
        const d = await API.get("/api/catalogo");
        const blocos = [
          prateleira("Mais alugados", "O que os alunos estão levando para casa", d.mais_alugados),
          prateleira("Melhores avaliados", "Nota média do catálogo externo (Open Library / Google Livros)", d.melhores_avaliados),
          prateleira("Novidades no acervo", "Últimas obras catalogadas", d.novidades),
        ].filter(Boolean);
        prateleiras.innerHTML = blocos.length
          ? blocos.join("")
          : "";
        prateleiras.querySelectorAll(".prateleira").forEach((sec) => {
          const trilho = $(".trilho", sec);
          sec.querySelectorAll(".seta").forEach((b) => b.addEventListener("click", () => {
            const passo = Math.max(220, trilho.clientWidth * 0.8);
            trilho.scrollBy({ left: Number(b.dataset.dir) * passo, behavior: "smooth" });
          }));
        });
      } catch (e) {
        prateleiras.innerHTML = "";
      }
    }

    async function carregar() {
      const q = encodeURIComponent($("#busca").value.trim());
      const g = encodeURIComponent($("#fGenero").value);
      const filtrando = !!(q || g);
      countEl.textContent = "Buscando…";
      gridOut.innerHTML = skeletonGrid();
      paginacao.innerHTML = "";
      if (filtrando) prateleiras.innerHTML = ""; // busca/filtro: só resultado
      let dados;
      try { dados = await API.get(`/api/livros?q=${q}&genero=${g}`); }
      catch (e) { gridOut.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
      todos = dados;
      pagina = 1;
      countEl.textContent = `${dados.length} obra(s) · ${dados.filter(l => l.disponiveis > 0).length} disponíveis`
        + (filtrando ? "" : " · deslize as prateleiras ou use a grade abaixo");
      if (!dados.length) {
        gridOut.innerHTML = `<div class="empty">Nenhuma obra encontrada.</div>`;
        return;
      }
      renderPagina();
      if (!filtrando) carregarPrateleiras(); // não espera o carrossel para mostrar a grade
    }

    // navegação dos cards (CSP estrita bloqueia onclick inline)
    out.addEventListener("click", (e) => {
      const card = e.target.closest(".livro-card");
      if (card && card.dataset.livro) location.hash = `#/livro/${card.dataset.livro}`;
      const botao = e.target.closest("[data-pagina]");
      if (botao && !botao.disabled) {
        pagina = Number(botao.dataset.pagina);
        renderPagina();
        gridOut.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    out.addEventListener("keydown", (e) => {
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
      if (e.key === "Enter") { e.preventDefault(); carregar(); }
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
              <div class="ficha-linha"><span class="k">ISBN</span><b>${esc(livro.isbn || "—")}</b></div>
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
          <div style="pointer-events:none;cursor:default;flex-shrink:0">${coverHtml(d, "sm")}</div>
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
          <div style="pointer-events:none;cursor:default;flex-shrink:0">${coverHtml(x, "sm")}</div>
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
        <div class="stat warn"><div class="n">${s.atrasados}</div><div class="l">${s.atrasados === 1 ? "Atrasado" : "Atrasados"}</div></div>
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
              <div style="pointer-events:none;cursor:default;flex-shrink:0">${coverHtml(x, "sm")}</div>
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
              <label>Foto da capa (identificar e buscar nos catálogos)</label>
              <div class="capa-upload">
                <input type="file" id="fCapaFoto" accept="image/jpeg,image/png,image/webp" hidden>
                <div class="capa-actions">
                  <button type="button" class="btn" id="btnCapaFoto">📷 Anexar foto</button>
                  <button type="button" class="btn primary" id="btnCapaPreencher" disabled>Preencher automaticamente</button>
                </div>
                <figure id="fCapaPreviewFigure" class="capa-preview-card" hidden>
                  <img id="fCapaPrev" alt="Prévia da foto anexada">
                  <figcaption>Foto enviada · usada para identificar</figcaption>
                </figure>
                <figure id="fCapaCatalogPreviewFigure" class="capa-preview-card" hidden>
                  <img id="fCapaCatalogPrev" alt="Capa retornada pelo catálogo">
                  <figcaption>Capa encontrada no catálogo</figcaption>
                </figure>
                <span class="hint" id="fCapaStatus" aria-live="polite">Anexe a foto para ver a prévia. A consulta só começa quando você clicar em “Preencher automaticamente”; os dados vêm do Google Books ou Open Library.</span>
                <div class="capa-match-picker" id="fCapaMatches" hidden>
                  <div class="field">
                    <label for="fCapaMatchSelect">Correspondências encontradas</label>
                    <select id="fCapaMatchSelect" class="select-classico"></select>
                  </div>
                  <button type="button" class="btn sm" id="btnUsarCapaMatch">Usar registro</button>
                  <div class="capa-match-sources" id="fCapaSources"></div>
                </div>
              </div>
            </div>
            <div class="field"><label>Título *</label><input id="fTitulo" required maxlength="200" placeholder="Dom Casmurro"></div>
            <div class="field"><label>Autor</label><input id="fAutor" maxlength="200" placeholder="Machado de Assis"></div>
            <div class="field"><label>ISBN</label>
              <div class="isbn-row">
                <input id="fIsbn" maxlength="30" placeholder="978-85-01-00000-0">
                <button type="button" class="btn sm" id="btnIsbnBuscar">Buscar dados</button>
              </div>
              <input type="hidden" id="fCapaUrl">
              <div class="hint" id="isbnStatus">Busca metadados e capa reais pelo ISBN (Google Books/Open Library).</div>
            </div>
            <div class="field"><label>Gênero</label><select id="fGenero"><option value="">Não identificado</option>${GENEROS.map(g => `<option>${g}</option>`).join("")}</select></div>
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
        <td><div style="pointer-events:none;cursor:default;flex-shrink:0">${coverHtml(l, "sm")}</div></td>
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
      resetarBuscaCatalogo();
      editId = id;
      $("#formTitulo" ).textContent = "Editar registro";
      $("#fTitulo" ).value = l.titulo; $("#fAutor" ).value = l.autor; $("#fIsbn" ).value = l.isbn;
      $("#fGenero" ).value = l.genero; $("#fAno" ).value = l.ano || ""; $("#fTotal" ).value = l.total_exemplares;
      $("#fSinopse" ).value = l.sinopse || "";
      $("#fCapaUrl" ).value = l.capa_url || "";
      setCatalogCoverPreview(l.capa_url || "");
      $("#btnCancelarEdit" ).style.display = "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    $("#btnCancelarEdit").addEventListener("click", () => {
      editId = null;
      $("#formTitulo").textContent = "Novo registro";
      $("#livroForm").reset();
      $("#btnCancelarEdit").style.display = "none";
      resetarBuscaCatalogo();
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
        resetarBuscaCatalogo();
        livros = await API.get("/api/livros");
        renderTabela();
      } catch (err) { toast(err.message, "erro"); }
    });

    // Identificação por Mistral (somente OCR) e preenchimento com registros catalogados.
    const inputCapa = $("#fCapaFoto");
    const btnCapaFoto = $("#btnCapaFoto");
    const btnCapaPreencher = $("#btnCapaPreencher");
    const photoPreviewFigure = $("#fCapaPreviewFigure");
    const statusCapa = $("#fCapaStatus");
    const matchBox = $("#fCapaMatches");
    const matchSelect = $("#fCapaMatchSelect");
    const sourceBox = $("#fCapaSources");
    let currentMatches = [];
    let matchStatusTarget = statusCapa;
    let capaObjectUrl = null;
    let selectedCapaFile = null;
    let lastCatalogValues = {};

    function limparMatches() {
      currentMatches = [];
      matchBox.hidden = true;
      matchSelect.replaceChildren();
      sourceBox.replaceChildren();
    }
    function limparDadosCatalogo() {
      const capaAnterior = lastCatalogValues["#fCapaUrl"];
      Object.entries(lastCatalogValues).forEach(([selector, value]) => {
        const field = $(selector);
        if (field && field.value === value) field.value = "";
      });
      if (capaAnterior && !$("#fCapaUrl").value) setCatalogCoverPreview("");
      lastCatalogValues = {};
    }
    function setCatalogCoverPreview(url) {
      const figure = $("#fCapaCatalogPreviewFigure");
      const image = $("#fCapaCatalogPrev");
      const safeUrl = typeof url === "string" && /^https:\/\/(books\.google\.com|covers\.openlibrary\.org)\//.test(url) ? url : "";
      if (!safeUrl) {
        figure.hidden = true;
        image.removeAttribute("src");
        return;
      }
      image.onerror = () => { figure.hidden = true; };
      image.onload = () => { figure.hidden = false; };
      figure.hidden = false;
      image.src = safeUrl;
      if (image.complete) figure.hidden = image.naturalWidth === 0;
    }
    function resetarBuscaCatalogo() {
      limparMatches();
      limparDadosCatalogo();
      if (capaObjectUrl) { URL.revokeObjectURL(capaObjectUrl); capaObjectUrl = null; }
      selectedCapaFile = null;
      btnCapaPreencher.disabled = true;
      inputCapa.value = "";
      $("#fCapaPrev").removeAttribute("src");
      photoPreviewFigure.hidden = true;
      setCatalogCoverPreview("");
      statusCapa.textContent = "Anexe a foto para ver a prévia. A consulta só começa quando você clicar em “Preencher automaticamente”; os dados vêm do Google Books ou Open Library.";
      statusCapa.style.color = "";
      const statusIsbn = $("#isbnStatus");
      statusIsbn.textContent = "Busca metadados e capa reais pelo ISBN (Google Books/Open Library).";
      statusIsbn.style.color = "";
    }
    function nomesDasFontes(match) {
      return (match.fontes || []).map(source => source.nome).filter(Boolean).join(" + ") || "catálogo bibliográfico";
    }
    function mostrarFontes(match) {
      sourceBox.replaceChildren();
      (match.fontes || []).forEach(source => {
        if (!source || typeof source.url !== "string" || !/^https:\/\/(books\.google\.com|openlibrary\.org)\//.test(source.url)) return;
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `Ver registro: ${source.nome}`;
        sourceBox.append(link);
      });
    }
    function aplicarRegistro(match, statusTarget = matchStatusTarget) {
      if (!match) return;
      limparDadosCatalogo();
      const preenchidos = {};
      const camposCopiados = [];
      const copiar = (selector, value, label = "") => {
        if (value === null || value === undefined || value === "") return;
        const field = $(selector);
        if (!field) return;
        const text = String(value);
        field.value = text;
        if (field.value !== text) return;
        preenchidos[selector] = text;
        if (label) camposCopiados.push(label);
      };
      copiar("#fTitulo", match.titulo, "título");
      copiar("#fAutor", match.autor, "autor");
      copiar("#fIsbn", match.isbn, "ISBN");
      copiar("#fAno", match.ano, "ano");
      copiar("#fGenero", match.genero && GENEROS.includes(match.genero) ? match.genero : "", "gênero");
      copiar("#fSinopse", match.sinopse, "sinopse");
      copiar("#fCapaUrl", match.capa_url);
      setCatalogCoverPreview(match.capa_url || "");
      lastCatalogValues = preenchidos;
      mostrarFontes(match);
      if (!camposCopiados.length) {
        statusTarget.textContent = `O registro de ${nomesDasFontes(match)} não trouxe campos de cadastro utilizáveis; nada foi preenchido.`;
        statusTarget.style.color = "var(--stamp)";
        return;
      }
      const aviso = match.confirmado ? "Confira os dados e a edição antes de salvar." : "Correspondência não confirmada pela foto; revise título e edição.";
      const quantidade = camposCopiados.length;
      statusTarget.textContent = `Preenchi ${quantidade} campo${quantidade === 1 ? "" : "s"} (${camposCopiados.join(", ")}) usando ${nomesDasFontes(match)}. ${aviso}`;
      statusTarget.style.color = match.confirmado ? "var(--ok)" : "var(--ink-soft)";
    }
    function mensagemSemResultado(data) {
      const ident = data.identificacao || {};
      const trecho = [ident.titulo, ident.autor].filter(Boolean).join(" — ");
      const problemas = Object.entries(data.provedores || {}).filter(([, state]) => ["quota", "bloqueado", "indisponivel", "resposta_invalida"].includes(state));
      if (!ident.titulo && !ident.isbn) return "Não consegui ler título ou ISBN. Tente uma foto mais nítida da capa ou digite o ISBN.";
      if (data.status === "fontes_indisponiveis") return `Não consegui consultar os catálogos agora (${problemas.map(([name]) => name === "google_books" ? "Google Books" : "Open Library").join(", ")}). Nada foi preenchido; tente novamente.`;
      const origem = trecho ? `Texto lido para busca: ${trecho}. ` : "";
      const indisponiveis = problemas.length ? ` Uma fonte ficou indisponível: ${problemas.map(([name]) => name === "google_books" ? "Google Books" : "Open Library").join(" e ")}.` : "";
      return `${origem}Não encontrei uma correspondência nos catálogos.${indisponiveis} Nada foi preenchido.`;
    }
    function mostrarCorrespondencias(data, statusTarget = statusCapa) {
      limparMatches();
      matchStatusTarget = statusTarget;
      currentMatches = Array.isArray(data.matches) ? data.matches : [];
      if (!currentMatches.length) {
        statusTarget.textContent = mensagemSemResultado(data);
        statusTarget.style.color = "var(--stamp)";
        return;
      }
      currentMatches.forEach((match, index) => {
        const source = nomesDasFontes(match);
        const label = [match.titulo, match.autor, match.ano, source, `${match.score}%`].filter(Boolean).join(" — ");
        matchSelect.add(new Option(label, String(index)));
      });
      matchBox.hidden = false;
      matchSelect.value = "0";
      mostrarFontes(currentMatches[0]);
      if (currentMatches[0].confirmado) {
        aplicarRegistro(currentMatches[0], statusTarget);
      } else {
        const identificacao = data.identificacao || {};
        const lido = [identificacao.titulo, identificacao.autor].filter(Boolean).join(" — ");
        statusTarget.textContent = `${currentMatches.length} opção(ões) encontrada(s)${lido ? ` para “${lido}”` : ""}, mas nenhuma foi confirmada pela foto. Escolha um registro e clique em “Usar registro”; nada foi preenchido ainda.`;
        statusTarget.style.color = "var(--ink-soft)";
      }
    }
    btnCapaFoto.addEventListener("click", () => inputCapa.click());
    $("#btnUsarCapaMatch").addEventListener("click", () => {
      aplicarRegistro(currentMatches[Number(matchSelect.value)]);
    });
    matchSelect.addEventListener("change", () => {
      const match = currentMatches[Number(matchSelect.value)];
      if (!match) return;
      mostrarFontes(match);
      matchStatusTarget.textContent = `Selecionado: ${match.titulo}. Clique em “Usar registro” para copiar somente os dados da fonte.`;
      matchStatusTarget.style.color = "var(--ink-soft)";
    });
    inputCapa.addEventListener("change", () => {
      const file = inputCapa.files[0];
      if (!file) return;
      limparMatches();
      limparDadosCatalogo();
      if (capaObjectUrl) URL.revokeObjectURL(capaObjectUrl);
      capaObjectUrl = URL.createObjectURL(file);
      selectedCapaFile = file;
      const preview = $("#fCapaPrev");
      preview.src = capaObjectUrl;
      photoPreviewFigure.hidden = false;
      btnCapaPreencher.disabled = false;
      statusCapa.textContent = "Foto anexada e prévia exibida. Clique em “Preencher automaticamente” para ler a capa e consultar os catálogos.";
      statusCapa.style.color = "";
      inputCapa.value = "";
    });
    btnCapaPreencher.addEventListener("click", async () => {
      const file = selectedCapaFile;
      if (!file) return;
      limparMatches();
      matchStatusTarget = statusCapa;
      btnCapaFoto.disabled = true;
      btnCapaPreencher.disabled = true;
      btnCapaPreencher.textContent = "Consultando catálogos…";
      statusCapa.textContent = "Lendo texto visível com Mistral e consultando Google Books/Open Library…";
      statusCapa.style.color = "";
      const form = new FormData();
      form.append("file", file);
      try {
        const data = await API.postForm("/api/livros/ler-capa", form);
        mostrarCorrespondencias(data, statusCapa);
      } catch (error) {
        statusCapa.textContent = error.message;
        statusCapa.style.color = "var(--stamp)";
      } finally {
        btnCapaFoto.disabled = false;
        btnCapaPreencher.textContent = "Preencher automaticamente";
        btnCapaPreencher.disabled = !selectedCapaFile;
      }
    });

    // A busca manual por ISBN usa os mesmos catálogos e a mesma seleção de fonte.
    $("#btnIsbnBuscar").addEventListener("click", async () => {
      const isbn = $("#fIsbn").value.trim().replace(/[^0-9Xx]/g, "");
      const statusIsbn = $("#isbnStatus");
      if (isbn.length !== 10 && isbn.length !== 13) {
        statusIsbn.textContent = "Digite um ISBN válido (10 ou 13 caracteres).";
        statusIsbn.style.color = "var(--stamp)";
        return;
      }
      limparDadosCatalogo();
      limparMatches();
      statusIsbn.textContent = "Buscando nos catálogos bibliográficos…";
      statusIsbn.style.color = "";
      try {
        const data = await API.get(`/api/livros/buscar-isbn?isbn=${encodeURIComponent(isbn)}`);
        mostrarCorrespondencias(data, statusIsbn);
      } catch (error) {
        statusIsbn.textContent = error.message;
        statusIsbn.style.color = "var(--stamp)";
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
          <div style="pointer-events:none;cursor:default;flex-shrink:0">${coverHtml(x, "sm")}</div>
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
            <div style="pointer-events:none;cursor:default;flex-shrink:0">${coverHtml(x, "sm")}</div>
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
