// Parallax MVP: as tres telas do ciclo, sem framework. Todo dado do banco entra por textContent.
"use strict";

const PRAGAS = ["Ferrugem", "Mancha Parda", "Lagarta", "Oídio", "Não identificado"];
const TAMANHO_ROTA = 7;
const PAPEIS = { produtor: "Produtor", gestor: "Coordenação", tecnico: "Técnico" };
const tela = document.getElementById("tela");
let usuario = null;

// ---------- utilitarios ----------
function h(tag, attrs = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined) el.append(f instanceof Node ? f : String(f));
  return el;
}
const num = (v, casas = 1) => Number(v).toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: 0 });
const hora = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const selo = (classe, texto) => h("span", { class: `selo ${classe}` }, texto);
const FAIXA = { alta: "Prioridade alta", media: "Prioridade média", baixa: "Prioridade baixa" };

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, { credentials: "same-origin", ...opcoes });
  if (r.status === 401 && caminho !== "/api/login") { mostrarLogin(); throw new Error("sessão expirada"); }
  const corpo = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) {
    const msg = corpo?.oracle || corpo?.detail || corpo?.error || `erro ${r.status}`;
    const e = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    e.status = r.status;
    throw e;
  }
  return corpo;
}
const json = (corpo) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });

function montar(id) {
  tela.replaceChildren(document.getElementById(id).content.cloneNode(true));
}

// ---------- sessao ----------
async function iniciar() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  try {
    usuario = await api("/api/me");
    abrir();
  } catch {
    if (!usuario) mostrarLogin();
  }
}

function mostrarLogin() {
  usuario = null;
  document.getElementById("sessao").hidden = true;
  montar("t-login");
  document.getElementById("form-login").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const dados = Object.fromEntries(new FormData(ev.target));
    const erro = document.getElementById("erro-login");
    erro.textContent = "";
    try {
      usuario = await api("/api/login", json(dados));
      abrir();
    } catch (e) {
      erro.textContent = e.status === 401 ? "Usuário ou senha incorretos." : `Não foi possível entrar: ${e.message}`;
    }
  });
}

document.getElementById("sair").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  mostrarLogin();
});

async function abrir() {
  const sessao = document.getElementById("sessao");
  sessao.hidden = false;
  document.getElementById("quem").textContent = `${usuario.name} (${PAPEIS[usuario.role]})`;
  const banco = document.getElementById("banco");
  try {
    const s = await api("/api/health");
    banco.textContent = `Oracle ${s.container}`;
    banco.title = s.database;
    banco.classList.remove("fora");
  } catch {
    banco.textContent = "sem banco";
    banco.classList.add("fora");
  }
  ({ produtor: telaProdutor, gestor: telaGestor, tecnico: telaTecnico })[usuario.role]();
}

// ---------- produtor: foto, fila offline, retorno ----------
const FILA_DB = "parallax-fila";
function abrirFila() {
  return new Promise((ok, falha) => {
    const req = indexedDB.open(FILA_DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore("fotos", { keyPath: "id" });
    req.onsuccess = () => ok(req.result);
    req.onerror = () => falha(req.error);
  });
}
async function fila(modo, acao) {
  const base = await abrirFila();
  return new Promise((ok, falha) => {
    const tx = base.transaction("fotos", modo);
    const res = acao(tx.objectStore("fotos"));
    tx.oncomplete = () => ok(res?.result);
    tx.onerror = () => falha(tx.error);
  });
}
const filaTodas = () => fila("readonly", (s) => s.getAll());
const filaPor = (item) => fila("readwrite", (s) => s.put(item));
const filaTira = (id) => fila("readwrite", (s) => s.delete(id));

let enviando = false;
async function esvaziarFila() {
  if (enviando) return;
  enviando = true;
  try {
    for (const item of await filaTodas()) {
      const form = new FormData();
      form.append("plot_id", item.plot_id);
      form.append("severity_pct", item.severity_pct);
      form.append("suspected_pest", item.suspected_pest);
      form.append("captured_at", item.captured_at);
      form.append("queued_offline", item.offline ? "true" : "false");
      form.append("photo", item.blob, item.nome || "folha.jpg");
      try {
        await api("/api/photos", { method: "POST", body: form });
        await filaTira(item.id);
      } catch (e) {
        if (!e.status) { item.offline = true; await filaPor(item); break; } // sem sinal: tenta depois
        if (e.status >= 400 && e.status < 500 && e.status !== 401) await filaTira(item.id);
        avisoProdutor(`A foto não entrou: ${e.message}`);
      }
    }
  } finally {
    enviando = false;
    await atualizarContador();
    if (usuario?.role === "produtor") carregarFotos();
  }
}

async function atualizarContador() {
  const caixa = document.getElementById("fila");
  if (!caixa) return;
  const n = (await filaTodas()).length;
  caixa.dataset.n = n;
  document.getElementById("contador").textContent = n;
  document.getElementById("fila-texto").textContent = n === 0
    ? "Nenhuma foto esperando sinal."
    : `${n === 1 ? "1 foto esperando" : `${n} fotos esperando`} sinal. Sai sozinha quando o celular conectar.`;
}
function avisoProdutor(texto) {
  const t = document.getElementById("fila-texto");
  if (t) t.textContent = texto;
}

// severidade estimada pela cor: verde = folha sadia, amarelo e marrom = lesao. E estimativa, nao modelo treinado.
function estimarSeveridade(img) {
  const lado = 160;
  const c = document.createElement("canvas");
  const esc = lado / Math.max(img.naturalWidth, img.naturalHeight);
  c.width = Math.max(1, Math.round(img.naturalWidth * esc));
  c.height = Math.max(1, Math.round(img.naturalHeight * esc));
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, c.width, c.height);
  const px = ctx.getImageData(0, 0, c.width, c.height).data;
  let sadio = 0, lesao = 0;
  for (let i = 0; i < px.length; i += 4) {
    const r = px[i] / 255, g = px[i + 1] / 255, b = px[i + 2] / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    if (max < 0.15 || d / (max || 1) < 0.2) continue; // escuro ou cinza: fundo
    let hue = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    hue = (hue * 60 + 360) % 360;
    if (hue >= 70 && hue <= 170) sadio++;
    else if (hue >= 10 && hue < 70) lesao++;
  }
  const folha = sadio + lesao;
  if (folha < (px.length / 4) * 0.05) return null;
  return Math.round((1000 * lesao) / folha) / 10;
}

async function telaProdutor() {
  montar("t-produtor");
  const selTalhao = document.getElementById("talhao");
  const talhoes = await api("/api/plots");
  const ultimo = localStorage.getItem("parallax-ultimo-talhao");
  for (const t of talhoes) selTalhao.append(h("option", { value: t.plot_id, selected: t.plot_id === ultimo }, `${t.plot_name}, ${t.crop} (${t.farm_name})`));
  const selPraga = document.getElementById("praga-suspeita");
  for (const p of PRAGAS) selPraga.append(h("option", { value: p, selected: p === "Não identificado" }, p === "Não identificado" ? "Não sei" : p));

  let severidade = null;
  const foto = document.getElementById("foto");
  foto.addEventListener("change", () => {
    const arquivo = foto.files[0];
    if (!arquivo) return;
    const img = document.getElementById("previa-img");
    img.onload = () => {
      severidade = estimarSeveridade(img);
      document.getElementById("estimativa").textContent = severidade === null
        ? "Não achei folha na foto. Tente de perto, com a folha ocupando a tela."
        : `Estimativa pela cor: ${num(severidade)}% da folha com sinal de lesão. A técnica confirma na visita.`;
    };
    img.src = URL.createObjectURL(arquivo);
    document.getElementById("previa").hidden = false;
  });

  document.getElementById("form-foto").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const arquivo = foto.files[0];
    if (!arquivo) return;
    localStorage.setItem("parallax-ultimo-talhao", selTalhao.value);
    await filaPor({
      id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
      plot_id: selTalhao.value,
      suspected_pest: selPraga.value,
      severity_pct: severidade ?? 0,
      captured_at: new Date().toISOString(),
      offline: !navigator.onLine,
      blob: arquivo,
      nome: arquivo.name,
    });
    ev.target.reset();
    selTalhao.value = localStorage.getItem("parallax-ultimo-talhao");
    selPraga.value = "Não identificado";
    document.getElementById("previa").hidden = true;
    severidade = null;
    await atualizarContador();
    esvaziarFila();
  });

  await atualizarContador();
  esvaziarFila();
  carregarRetorno();
}

async function carregarFotos() {
  const lista = document.getElementById("minhas-fotos");
  if (!lista) return;
  const fotos = await api("/api/photos/mine");
  lista.replaceChildren(...(fotos.length ? fotos.map((f) => h("li", {},
    h("b", {}, `${f.plot_name}: chegou à cooperativa`),
    h("span", { class: "meta" }, `Tirada ${hora(f.captured_at)}, recebida ${hora(f.received_at)}${f.connection === "offline_sync" ? " (saiu da fila sem sinal)" : ""}. ${f.suspected_pest === "Não identificado" ? "Praga a confirmar" : f.suspected_pest}, ${num(f.severity_pct)}% estimado.`)))
    : [h("li", { class: "vazio" }, "Nenhuma foto enviada por este aparelho ainda.")]));
}

async function carregarRetorno() {
  const lista = document.getElementById("retornos");
  const itens = await api("/api/feedback");
  lista.replaceChildren(...(itens.length ? itens.map((r) => h("li", {},
    h("b", {}, `${r.plot_name}: ${r.confirmed_pest}, ${num(r.severity_pct)}% de severidade`),
    h("span", { class: "meta" }, `${r.agronomist_name}, ${r.agronomist_registry}, olhou o talhão em ${hora(r.reported_at)}.`),
    r.note ? h("span", { class: "meta" }, `"${r.note}"`) : null))
    : [h("li", { class: "vazio" }, "Quando a técnica visitar, a resposta aparece aqui com o nome dela.")]));
}

window.addEventListener("online", () => { if (usuario?.role === "produtor") esvaziarFila(); });
setInterval(() => { if (usuario?.role === "produtor" && navigator.onLine) esvaziarFila(); }, 15000);

// ---------- gestor: rota, liberacao, concordancia ----------
let estadoRota = { itens: [], semana: "", previa: false };

async function telaGestor() {
  montar("t-gestor");
  const cultura = document.getElementById("cultura");
  const previa = document.getElementById("previa-semana");
  cultura.addEventListener("change", carregarRota);
  previa.addEventListener("change", carregarRota);
  document.getElementById("liberar").addEventListener("click", liberarRota);
  await carregarRota(true);
  carregarConcordancia();
}

async function carregarRota(primeira = false) {
  const cultura = document.getElementById("cultura");
  const previa = document.getElementById("previa-semana").checked;
  const escolhida = primeira === true ? "" : cultura.value;
  const q = new URLSearchParams({ preview: previa });
  if (escolhida) q.set("crop", escolhida);
  const r = await api(`/api/route?${q}`);
  if (cultura.options.length === 0) {
    cultura.append(h("option", { value: "" }, "Todas"));
    for (const c of r.crops) cultura.append(h("option", { value: c }, c));
  }
  cultura.value = escolhida;

  let itens = r.items.slice(0, TAMANHO_ROTA);
  const liberada = !previa && r.released.length > 0;
  if (liberada) {
    const porId = Object.fromEntries(r.items.map((i) => [i.plot_id, i]));
    const naRota = r.released.map((x) => porId[x.plot_id]).filter(Boolean);
    if (naRota.length) itens = naRota;
  }
  estadoRota = { itens, semana: r.week, previa };
  document.getElementById("titulo-rota").textContent = previa ? `Prévia da próxima rota (${r.week})` : `Rota da semana ${r.week}`;
  document.getElementById("apoio-rota").textContent = previa
    ? "Com as fotos que chegaram nesta semana. A rota de segunda sai daqui; não dá para liberar a prévia."
    : liberada
      ? `Liberada por ${r.released[0].released_by} em ${hora(r.released[0].released_at)}. Mudou a ordem? Libere de novo.`
      : "Feita com as fotos da semana passada. Confira a ordem e libere para o técnico.";
  document.getElementById("liberar").disabled = previa || itens.length === 0;
  document.getElementById("aviso-rota").textContent = "";
  desenharRota();

  const ind = document.getElementById("indicadores");
  const altas = r.items.filter((i) => i.band === "alta").length;
  ind.replaceChildren(
    indicador("Fotos nesta semana", r.photos_this_week, "entram na rota de segunda"),
    indicador("Talhões com foto", r.items.length, previa ? "na prévia" : `na semana ${r.week}`),
    indicador("Prioridade alta", altas, escolhida ? `em ${escolhida.toLowerCase()}` : "todas as culturas"),
  );
}

function indicador(rotulo, valor, apoio) {
  return h("div", { class: "indicador" }, h("span", {}, rotulo), h("b", {}, valor), h("small", {}, apoio));
}

function desenharRota() {
  const lista = document.getElementById("rota");
  const { itens, previa } = estadoRota;
  if (!itens.length) {
    lista.replaceChildren(h("li", { class: "vazio" }, "Nenhum talhão com foto nesta semana para esta cultura."));
    return;
  }
  lista.replaceChildren(...itens.map((i, pos) => {
    const li = h("li", { draggable: previa ? null : "true", "data-id": i.plot_id },
      h("div", { class: "local" },
        h("b", {}, `${i.farm_name}, ${i.plot_name}`), " ", selo(i.band, FAIXA[i.band]),
        h("details", { class: "porque" },
          h("summary", {}, `${i.crop}, ${i.municipality}. Por que está aqui?`),
          `Severidade média de ${num(i.avg_severity_pct)}% em ${i.samples} ${i.samples === 1 ? "foto" : "fotos"}` +
          `${i.enough_samples ? "" : " (amostra pequena, pesa menos)"}, ` +
          `${i.delta_pp >= 0 ? "subiu" : "caiu"} ${num(Math.abs(i.delta_pp))} pontos contra a semana anterior. ` +
          `Praga mais vista: ${i.main_pest || "nenhuma identificada"}. Pontuação ${num(i.priority_score, 2)}.`)),
      previa ? h("span") : h("div", { class: "setas" },
        h("button", { "aria-label": "Subir", disabled: pos === 0, onclick: () => mover(pos, -1) }, "↑"),
        h("button", { "aria-label": "Descer", disabled: pos === itens.length - 1, onclick: () => mover(pos, 1) }, "↓")));
    if (!previa) {
      li.addEventListener("dragstart", (e) => { li.classList.add("arrastando"); e.dataTransfer.setData("text/plain", String(pos)); });
      li.addEventListener("dragend", () => li.classList.remove("arrastando"));
      li.addEventListener("dragover", (e) => { e.preventDefault(); li.classList.add("sobre"); });
      li.addEventListener("dragleave", () => li.classList.remove("sobre"));
      li.addEventListener("drop", (e) => {
        e.preventDefault();
        li.classList.remove("sobre");
        const de = Number(e.dataTransfer.getData("text/plain"));
        const [item] = estadoRota.itens.splice(de, 1);
        estadoRota.itens.splice(pos, 0, item);
        desenharRota();
      });
    }
    return li;
  }));
}

function mover(pos, passo) {
  const itens = estadoRota.itens;
  [itens[pos], itens[pos + passo]] = [itens[pos + passo], itens[pos]];
  desenharRota();
}

async function liberarRota() {
  const aviso = document.getElementById("aviso-rota");
  try {
    const r = await api("/api/route/release", json({ plot_ids: estadoRota.itens.map((i) => i.plot_id) }));
    await carregarRota();
    document.getElementById("aviso-rota").textContent = `Rota liberada para o técnico: ${r.released} visitas na semana ${r.week}.`;
  } catch (e) {
    aviso.textContent = `Não liberou: ${e.message}`;
  }
}

async function carregarConcordancia() {
  const c = await api("/api/agreement");
  document.getElementById("concordancia").replaceChildren(
    h("div", { class: "taxa" }, h("b", {}, c.agreement_pct === null ? "sem laudo" : `${num(c.agreement_pct)}%`)),
    h("p", { class: "apoio" }, `${c.agreeing} de ${c.reports} laudos confirmaram a praga que a tela mostrou para o talhão na semana. ` +
      `Erro médio de severidade: ${c.avg_severity_error_pp === null ? "sem dado" : `${num(c.avg_severity_error_pp)} pontos`}.`));
  document.getElementById("laudos-recentes").replaceChildren(...c.recent.map((l) => h("li", {},
    h("b", {}, `${l.farm_name}, ${l.plot_name} `), selo(l.agrees ? "sim" : "nao", l.agrees ? "concordou" : "não concordou"),
    h("span", { class: "meta" }, `${l.week}: a tela mostrou ${l.screen_pest || "nada identificado"}, ${l.agronomist} confirmou ${l.confirmed_pest}.`))));
}

// ---------- tecnico: rota liberada e laudo ----------
async function telaTecnico() {
  montar("t-tecnico");
  const r = await api("/api/visits");
  const apoio = document.getElementById("apoio-visitas");
  const feitas = r.items.filter((i) => i.report_id).length;
  apoio.textContent = r.items.length
    ? `Semana ${r.week}: ${r.items.length} visitas na ordem da coordenação, ${feitas} com laudo.`
    : "A coordenação ainda não liberou a rota desta semana.";
  document.getElementById("visitas").replaceChildren(...r.items.map((v) => cartaoVisita(v, r.pests)));
}

function cartaoVisita(v, pragas) {
  const feito = Boolean(v.report_id);
  const card = h("li", { class: `visita${feito ? " feito" : ""}`, "data-id": v.plot_id },
    h("header", {},
      h("div", {}, h("span", { class: "ordem" }, `${v.visit_order}ª visita`), h("h2", {}, `${v.farm_name}, ${v.plot_name}`),
        h("span", { class: "meta" }, `${v.crop}, ${v.municipality}`)),
      selo(v.band, FAIXA[v.band])),
    h("div", { class: "mostrou" },
      h("b", {}, "O que a tela mostrou: "), `${v.main_pest || "nenhuma praga identificada"}, severidade média de ${num(v.avg_severity_pct)}% em ${v.samples} fotos.`,
      v.last_photo_id ? h("img", { src: `/api/photos/${v.last_photo_id}/image`, alt: "Última foto do produtor", loading: "lazy" }) : null));
  if (feito) {
    card.append(h("p", {}, h("b", {}, `Laudo ${v.report_id}`), ` por ${v.reported_by}: ${v.confirmed_pest} `,
      selo(v.agrees ? "sim" : "nao", v.agrees ? "concordou com a tela" : "não concordou")));
    return card;
  }
  let severidade = Math.round(v.avg_severity_pct);
  const saida = h("output", {}, `${severidade}%`);
  const ajuste = h("input", { type: "range", min: 0, max: 100, step: 1, value: severidade, "aria-label": "Ajuste fino da severidade" });
  const faixas = [[0, 10], [10, 20], [20, 30], [30, 50], [50, 100]];
  const botoesFaixa = faixas.map(([a, b]) => h("button", { type: "button", "aria-pressed": String(severidade >= a && severidade < b) }, `${a}-${b}%`));
  const marcar = () => {
    saida.textContent = `${severidade}%`;
    ajuste.value = severidade;
    botoesFaixa.forEach((bt, i) => bt.setAttribute("aria-pressed", String(severidade >= faixas[i][0] && (severidade < faixas[i][1] || (i === 4 && severidade === 100)))));
  };
  botoesFaixa.forEach((bt, i) => bt.addEventListener("click", () => { severidade = Math.round((faixas[i][0] + faixas[i][1]) / 2); marcar(); }));
  ajuste.addEventListener("input", () => { severidade = Number(ajuste.value); marcar(); });
  const praga = h("select", { name: "confirmed_pest" }, ...pragas.map((p) => h("option", { value: p, selected: p === v.main_pest }, p)));
  const obs = h("input", { name: "note", maxlength: 400, placeholder: "Observação para o produtor (opcional)" });
  const msg = h("p", { class: "aviso", role: "status" });
  const form = h("form", {},
    h("label", {}, "Praga confirmada na visita", praga),
    h("label", {}, "Severidade no talhão", h("div", { class: "faixas" }, botoesFaixa), h("div", { class: "ajuste" }, ajuste, saida)),
    h("label", {}, "Observação", obs),
    h("button", { class: "botao", type: "submit" }, "Assinar laudo"), msg);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      const r = await api("/api/reports", json({ plot_id: v.plot_id, confirmed_pest: praga.value, severity_pct: severidade, note: obs.value || null }));
      msg.textContent = r.agrees
        ? `Laudo ${r.report_id} assinado. Concordou com a tela (${r.screen_pest}). Taxa da carteira: ${num(r.summary.agreement_pct)}%.`
        : `Laudo ${r.report_id} assinado. A tela mostrou ${r.screen_pest || "nada identificado"}; você confirmou ${praga.value}. Taxa da carteira: ${num(r.summary.agreement_pct)}%.`;
      form.querySelector("button[type=submit]").disabled = true;
      card.classList.add("feito");
    } catch (e) {
      msg.textContent = `Não gravou: ${e.message}`;
    }
  });
  card.append(form);
  return card;
}

iniciar();
