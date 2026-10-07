/* Cliente da API — bearer token no header, tratamento de erros uniforme. */
const API = (() => {
  const SESSION_TOKEN = "biblio_token";
  const SESSION_USER = "biblio_usuario";

  function token() { return sessionStorage.getItem(SESSION_TOKEN); }
  function usuario() {
    try { return JSON.parse(sessionStorage.getItem(SESSION_USER) || "null"); }
    catch (e) { return null; }
  }
  function salvarSessao(token, usuario) {
    sessionStorage.setItem(SESSION_TOKEN, token);
    sessionStorage.setItem(SESSION_USER, JSON.stringify(usuario));
  }
  function limparSessao() {
    sessionStorage.removeItem(SESSION_TOKEN);
    sessionStorage.removeItem(SESSION_USER);
  }

  async function request(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    const t = token();
    if (t) headers["Authorization"] = "Bearer " + t;
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const resp = await fetch(path, Object.assign({}, opts, { headers }));
    if (resp.status === 401 && path !== "/api/auth/login") {
      limparSessao();
      if (!location.hash.startsWith("#/login")) {
        location.hash = "#/login";
        App.toast("Sessão expirada. Faça login novamente.", "err");
      }
      throw new Error("Não autenticado");
    }
    let data = null;
    try { data = await resp.json(); } catch (e) { /* sem corpo */ }
    if (!resp.ok) {
      const msg = (data && data.detail) ? data.detail : ("Erro " + resp.status);
      throw new Error(msg);
    }
    return data;
  }

  return {
    token, usuario, salvarSessao, limparSessao,
    get: (p) => request(p),
    post: (p, body) => request(p, { method: "POST", body }),
    postForm: (p, formData) => request(p, { method: "POST", body: formData }),
    put: (p, body) => request(p, { method: "PUT", body }),
    del: (p) => request(p, { method: "DELETE" }),
  };
})();
