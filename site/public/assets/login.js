/*
 * Login da área do cliente.
 *
 * Com SUPABASE_URL e SUPABASE_ANON_KEY no /config.js, entra pelo Supabase Auth (e-mail e senha) e entrega a
 * sessão ao painel pelo fragmento da URL: APP_URL/login#access_token=…&refresh_token=…. O fragmento não vai
 * para o servidor, e o painel apaga o fragmento assim que lê.
 * Sem Supabase (ambiente local), usa o POST /auth/dev-login da API com e-mail e apelido da empresa, como o
 * login do painel faz no Minikube.
 */
(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches, root = document.documentElement;
  var CFG = window.SETTLR_CONFIG || {};
  var APP_URL = String(CFG.appUrl || "").replace(/\/$/, "");
  var WA_NUMBER = String(CFG.whatsappNumber || "").replace(/\D/g, "");
  var MODE = CFG.supabaseUrl && CFG.supabaseAnonKey ? "supabase" : "dev";
  /* Versão fixa: a CSP só libera este endereço do jsDelivr. */
  var SUPABASE_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js";
  function $(id) { return document.getElementById(id); }

  var I18N = {
    "en-US": {
      "l.eyebrow": "CLIENT AREA", "l.h1": "Sign in to the dashboard", "l.sub": "Your company's exceptions, payments and conversations.",
      "l.email": "Email", "l.emailPh": "you@company.com", "l.emailErr": "Enter a valid email.", "l.pass": "Password", "l.forgot": "Forgot password", "l.show": "Show password", "l.hide": "Hide password", "l.passErr": "Enter your password.",
      "l.tenant": "Company", "l.tenantErr": "Enter your company's handle.", "l.dev": "local environment · sign-in without password",
      "l.submit": "Sign in", "l.busy": "Signing in…",
      "l.invite": "Got an invitation from your company? Open the link in the email to create your password.",
      "l.or": "NOT A CLIENT YET", "l.newP": "<b>Want Settlr at your company?</b> Accounts are opened with our team, in a WhatsApp conversation.", "l.wa": "Chat on WhatsApp",
      "l.help": "Trouble signing in? Contact your company's account owner.",
      "e.creds": "Email or password doesn't match. Check them and try again.", "e.tenant": "We couldn't find this company, or this email has no access to it.", "e.net": "We couldn't reach the server. Check your connection and try again.", "e.cfg": "Sign-in isn't configured on this server. Tell the Settlr team.", "e.generic": "Sign-in failed. Try again in a few minutes.",
      "r.eyebrow": "RECOVER ACCESS", "r.h1": "Forgot your password?", "r.sub": "We'll email you a link. It's valid for one hour.", "r.sent": "If this email has an account, the link arrives in a few minutes. Check your spam folder too.", "r.submit": "Send the link", "r.back": "Back to sign in",
      "a.h2": "Billed, paid, reconciled.", "a.lead": "When you sign in, you only see what needs a decision. The system already settled the rest with the bank.",
      "a.c1s": "E2E matches the invoice", "a.c1t": "reconciled", "a.c2s": "2 possible invoices", "a.c2t": "to confirm", "a.c3b": "Request for 8 installments", "a.c3s": "above the cap of 6", "a.c3t": "approval", "a.f1": "Sample data",
      "wa.msg": "Hi! I'd like to bring Settlr to my company."
    },
    "es": {
      "l.eyebrow": "ÁREA DEL CLIENTE", "l.h1": "Entrar al panel", "l.sub": "Excepciones, pagos y conversaciones de tu empresa.",
      "l.email": "Correo", "l.emailPh": "tu@empresa.com", "l.emailErr": "Ingresa un correo válido.", "l.pass": "Contraseña", "l.forgot": "Olvidé la contraseña", "l.show": "Mostrar contraseña", "l.hide": "Ocultar contraseña", "l.passErr": "Ingresa la contraseña.",
      "l.tenant": "Empresa", "l.tenantErr": "Ingresa el identificador de la empresa.", "l.dev": "entorno local · entrada sin contraseña",
      "l.submit": "Entrar", "l.busy": "Entrando…",
      "l.invite": "¿Recibiste una invitación de tu empresa? Abre el enlace del correo para crear tu contraseña.",
      "l.or": "TODAVÍA NO ES CLIENTE", "l.newP": "<b>¿Quieres Settlr en tu empresa?</b> La cuenta se abre con nuestro equipo, en una conversación por WhatsApp.", "l.wa": "Hablar por WhatsApp",
      "l.help": "¿Problemas para entrar? Habla con el dueño de la cuenta de tu empresa.",
      "e.creds": "El correo o la contraseña no coinciden. Revísalos e intenta de nuevo.", "e.tenant": "No encontramos esta empresa, o este correo no tiene acceso a ella.", "e.net": "No pudimos conectar con el servidor. Revisa tu conexión e intenta de nuevo.", "e.cfg": "El acceso no está configurado en este servidor. Avisa al equipo de Settlr.", "e.generic": "No se pudo entrar. Intenta de nuevo en unos minutos.",
      "r.eyebrow": "RECUPERAR ACCESO", "r.h1": "¿Olvidaste la contraseña?", "r.sub": "Te enviamos un enlace por correo. Es válido por una hora.", "r.sent": "Si ese correo tiene una cuenta, el enlace llega en unos minutos. Revisa también la carpeta de spam.", "r.submit": "Enviar el enlace", "r.back": "Volver a entrar",
      "a.h2": "Cobrado, pagado, conciliado.", "a.lead": "Al entrar, ves solo lo que necesita una decisión. El resto el sistema ya lo concilió con el banco.",
      "a.c1s": "E2E igual al de la factura", "a.c1t": "conciliado", "a.c2s": "2 facturas posibles", "a.c2t": "por confirmar", "a.c3b": "Pedido de 8 cuotas", "a.c3s": "sobre el máximo de 6", "a.c3t": "aprobación", "a.f1": "Datos de ejemplo",
      "wa.msg": "¡Hola! Quiero llevar Settlr a mi empresa."
    }
  };
  var PT = {
    "l.busy": "Entrando…", "l.hide": "Ocultar senha", "l.show": "Mostrar senha",
    "e.creds": "E-mail ou senha não conferem. Confira e tente de novo.", "e.tenant": "Não achamos essa empresa, ou esse e-mail não tem acesso a ela.", "e.net": "Não conseguimos falar com o servidor. Confira a conexão e tente de novo.", "e.cfg": "O login não está configurado neste servidor. Avise a equipe do Settlr.", "e.generic": "Não foi possível entrar. Tente de novo em alguns minutos.",
    "wa.msg": "Olá! Quero levar o Settlr para a minha empresa."
  };
  var LANG_LABEL = { "pt-BR": ["PT-BR", "Idioma: Português (Brasil)"], "en-US": ["EN-US", "Language: English (US)"], "es": ["ES", "Idioma: Español"] };

  var nodes = document.querySelectorAll("[data-i18n]"), ph = document.querySelectorAll("[data-i18n-ph]"), ar = document.querySelectorAll("[data-i18n-aria]");
  nodes.forEach(function (n) { n._pt = n.innerHTML; });
  ph.forEach(function (n) { n._pt = n.getAttribute("placeholder"); });
  ar.forEach(function (n) { n._pt = n.getAttribute("aria-label"); });
  var lang = "pt-BR", lastError = null;
  function t(k) { var d = I18N[lang]; return d && d[k] != null ? d[k] : PT[k]; }
  function money(v) { return new Intl.NumberFormat(lang, { style: "currency", currency: "BRL" }).format(v); }

  function apply(next, animate) {
    lang = next; var d = I18N[lang];
    function run() {
      root.lang = lang;
      nodes.forEach(function (n) { var k = n.getAttribute("data-i18n"); n.innerHTML = d && d[k] != null ? d[k] : n._pt; });
      ph.forEach(function (n) { var k = n.getAttribute("data-i18n-ph"); n.setAttribute("placeholder", d && d[k] != null ? d[k] : n._pt); });
      ar.forEach(function (n) { var k = n.getAttribute("data-i18n-aria"); n.setAttribute("aria-label", d && d[k] != null ? d[k] : n._pt); });
      document.querySelectorAll("[data-brl]").forEach(function (n) { n.textContent = money(+n.getAttribute("data-brl")); });
      if (WA_NUMBER) $("wa-new").href = "https://wa.me/" + WA_NUMBER + "?text=" + encodeURIComponent(t("wa.msg"));
      $("lang-code").textContent = LANG_LABEL[lang][0]; $("lang-btn").setAttribute("aria-label", LANG_LABEL[lang][1]);
      document.querySelectorAll("#lang-menu [data-lang]").forEach(function (b) { b.setAttribute("aria-checked", String(b.dataset.lang === lang)); });
      if (lastError) $("login-msg-t").textContent = t(lastError);
      root.classList.remove("swapping");
    }
    if (animate && !reduce) { root.classList.add("swapping"); setTimeout(run, 160); } else run();
    try { localStorage.setItem("settlr-lang", lang); } catch (e) {}
  }

  /* Menu do idioma */
  var btn = $("lang-btn"), menu = $("lang-menu");
  function openMenu(v) { menu.hidden = !v; btn.setAttribute("aria-expanded", String(v)); if (v) (menu.querySelector('[aria-checked="true"]') || menu.querySelector("button")).focus(); }
  btn.addEventListener("click", function () { openMenu(menu.hidden); });
  menu.querySelectorAll("[data-lang]").forEach(function (b) { b.addEventListener("click", function () { openMenu(false); btn.focus(); if (b.dataset.lang !== lang) apply(b.dataset.lang, true); }); });
  document.addEventListener("click", function (e) { if (!menu.hidden && !$("lang").contains(e.target)) openMenu(false); });
  menu.addEventListener("keydown", function (e) {
    var it = Array.prototype.slice.call(menu.querySelectorAll("button")), i = it.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); it[(i + 1) % it.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); it[(i - 1 + it.length) % it.length].focus(); }
    if (e.key === "Escape") { openMenu(false); btn.focus(); }
  });

  /* Modo de login: local entra com e-mail e empresa, produção com e-mail e senha */
  if (MODE === "dev") { $("fl-tenant").hidden = false; $("fl-pass").hidden = true; $("dev-note").hidden = false; }
  if (!WA_NUMBER) $("wa-new").removeAttribute("href");

  /* Mostrar senha */
  var shown = false;
  $("eye").addEventListener("click", function () {
    shown = !shown; $("pass").type = shown ? "text" : "password";
    $("eye").innerHTML = '<svg><use href="#i-' + (shown ? "eye-off" : "eye") + '"/></svg>';
    $("eye").setAttribute("aria-label", t(shown ? "l.hide" : "l.show"));
  });

  function view(id) { ["v-login", "v-reset"].forEach(function (v) { $(v).classList.toggle("on", v === id); }); var f = $(id).querySelector("input"); if (f) f.focus(); }
  $("to-reset").addEventListener("click", function () { $("remail").value = $("email").value; $("reset-msg").hidden = true; view("v-reset"); });
  $("to-login").addEventListener("click", function () { view("v-login"); });

  var okEmail = function (v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()); };
  document.querySelectorAll("input").forEach(function (i) { i.addEventListener("input", function () { var f = i.closest(".field"); if (f) f.classList.remove("bad"); }); });

  function busy(b, on, label) { if (on) b._html = b.innerHTML; b.disabled = on; b.innerHTML = on ? '<span class="spin" aria-hidden="true"></span><span>' + label + "</span>" : b._html; }
  function fail(key) { lastError = key; var m = $("login-msg"); m.className = "note bad"; m.hidden = false; $("login-msg-t").textContent = t(key); }

  /* Supabase carregado sob demanda, só no modo de produção */
  var sbClient = null;
  function supabaseClient() {
    if (sbClient) return Promise.resolve(sbClient);
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script"); s.src = SUPABASE_JS; s.async = true;
      s.onload = function () {
        if (!window.supabase || !window.supabase.createClient) return reject(new Error("cfg"));
        sbClient = window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseAnonKey, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } });
        resolve(sbClient);
      };
      s.onerror = function () { reject(new Error("net")); };
      document.head.appendChild(s);
    });
  }

  /* Entrega a sessão ao painel. O fragmento não chega ao servidor de destino. */
  function handoff(access, refresh) {
    if (!APP_URL) { fail("e.cfg"); return; }
    var frag = "access_token=" + encodeURIComponent(access) + (refresh ? "&refresh_token=" + encodeURIComponent(refresh) : "");
    window.location.assign(APP_URL + "/login#" + frag);
  }

  $("f-login").addEventListener("submit", function (e) {
    e.preventDefault();
    $("login-msg").hidden = true; lastError = null;
    var email = $("email").value.trim(), bad = false;
    if (!okEmail(email)) { $("fl-email").classList.add("bad"); bad = true; }
    if (MODE === "supabase" && !$("pass").value) { $("fl-pass").classList.add("bad"); bad = true; }
    if (MODE === "dev" && !$("tenant").value.trim()) { $("fl-tenant").classList.add("bad"); bad = true; }
    if (bad) { document.querySelector("#f-login .bad input").focus(); return; }
    var go = $("go"); busy(go, true, t("l.busy"));
    var done = function () { busy(go, false); };

    if (MODE === "supabase") {
      supabaseClient().then(function (sb) {
        return sb.auth.signInWithPassword({ email: email, password: $("pass").value });
      }).then(function (res) {
        if (res.error || !res.data || !res.data.session) { done(); fail(res.error && res.error.status === 400 ? "e.creds" : "e.generic"); return; }
        handoff(res.data.session.access_token, res.data.session.refresh_token);
      }).catch(function (err) { done(); fail(err && err.message === "cfg" ? "e.cfg" : "e.net"); });
      return;
    }

    fetch("/auth/dev-login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: email, tenant_slug: $("tenant").value.trim() }) })
      .then(function (r) {
        if (r.ok) return r.json().then(function (body) { handoff(body.access_token, null); });
        done(); fail(r.status === 404 || r.status === 401 || r.status === 403 ? "e.tenant" : "e.generic");
      })
      .catch(function () { done(); fail("e.net"); });
  });

  $("f-reset").addEventListener("submit", function (e) {
    e.preventDefault();
    var email = $("remail").value.trim();
    if (!okEmail(email)) { $("fr-email").classList.add("bad"); $("remail").focus(); return; }
    var rgo = $("rgo"); busy(rgo, true, "…");
    /* A resposta é a mesma exista ou não a conta: a tela não revela quem é cliente. */
    var show = function () { busy(rgo, false); $("reset-msg").hidden = false; };
    if (MODE !== "supabase") { show(); return; }
    supabaseClient().then(function (sb) { return sb.auth.resetPasswordForEmail(email, { redirectTo: APP_URL + "/login" }); }).then(show, show);
  });
  if (MODE === "dev") $("to-reset").hidden = true;

  /* Luz da marca */
  var cv = $("aurora"), ctx = cv.getContext("2d");
  var blobs = [
    { c: "rgba(91,61,245,.9)", r: .5, x: .35, y: .3, sx: .00019, sy: .00015 },
    { c: "rgba(143,120,255,.55)", r: .35, x: .75, y: .2, sx: .00015, sy: .00021 },
    { c: "rgba(198,244,50,.18)", r: .25, x: .6, y: .7, sx: .00023, sy: .00012 }
  ];
  function size() { var r = cv.getBoundingClientRect(); cv.width = Math.max(1, r.width / 3); cv.height = Math.max(1, r.height / 3); }
  function draw(tm) {
    var w = cv.width, h = cv.height; ctx.clearRect(0, 0, w, h);
    blobs.forEach(function (b, i) {
      var x = (b.x + Math.sin(tm * b.sx + i) * .08) * w, y = (b.y + Math.cos(tm * b.sy + i * 2) * .07) * h, r = b.r * Math.max(w, h);
      var g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, b.c); g.addColorStop(1, "rgba(0,0,0,0)"); ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    });
    if (!reduce) requestAnimationFrame(draw);
  }
  size(); window.addEventListener("resize", size); requestAnimationFrame(draw);

  var saved = null; try { saved = localStorage.getItem("settlr-lang"); } catch (e) {}
  apply(I18N[saved] || saved === "pt-BR" ? saved : "pt-BR", false);
})();
