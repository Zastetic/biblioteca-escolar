/* Tema compartilhado: aplica a preferência salva (mesma chave em todas as páginas)
   e liga o toggle. Default: segue o sistema. */
(function(){
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem("biblio_tema"); } catch(e) {}
  var preferDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  var theme = saved || (preferDark ? "dark" : "light");
  root.setAttribute("data-theme", theme);

  window.biblioTema = function(){
    var icon = document.getElementById("themeIcon");
    var label = document.getElementById("themeLabel");
    var t = root.getAttribute("data-theme");
    if (t === "dark") { if(icon) icon.textContent = "☀"; if(label) label.textContent = "Claro"; }
    else { if(icon) icon.textContent = "☾"; if(label) label.textContent = "Escuro"; }
    return t;
  };
  window.biblioToggleTema = function(){
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    try { localStorage.setItem("biblio_tema", next); } catch(e) {}
    root.setAttribute("data-theme", next);
    window.biblioTema();
  };
  window.addEventListener("DOMContentLoaded", window.biblioTema);
})();
