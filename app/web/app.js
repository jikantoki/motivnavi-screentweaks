"use strict";

const TOKEN = new URLSearchParams(location.search).get("token") || "";

const ICONS = {
  pc: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
  navi: '<svg viewBox="0 0 24 24"><path d="M5 16.5 6.6 11a2 2 0 0 1 1.9-1.5h7a2 2 0 0 1 1.9 1.5l1.6 5.5"/><rect x="3.5" y="16" width="17" height="3.5" rx="1.2"/><path d="M7 19.5V21M17 19.5V21"/><path d="m12 2.5 2.2 4.5L12 6l-2.2 1Z"/></svg>',
};

const $ = (id) => document.getElementById(id);
let selected = null;
let busy = false;

async function api(path, body) {
  const opts = { headers: { "X-Token": TOKEN } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `エラー (${res.status})`);
  return data;
}

function showError(msg) {
  const el = $("error");
  el.textContent = msg;
  el.hidden = !msg;
}

function select(id) {
  selected = id;
  document.querySelectorAll(".mode").forEach((el) => {
    el.setAttribute("aria-checked", String(el.dataset.mode === id));
    el.tabIndex = el.dataset.mode === id ? 0 : -1;
  });
  $("ok").disabled = !selected;
}

function render(state) {
  const tpl = $("mode-template");
  const box = $("modes");
  box.innerHTML = "";

  for (const m of state.modes) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.mode = m.id;
    node.querySelector(".mode-icon").innerHTML = ICONS[m.id] || "";
    node.querySelector(".mode-name").textContent =
      m.name + (m.id === state.defaultMode ? "（デフォルト）" : "");
    node.querySelector(".mode-desc").textContent = m.description;
    node.querySelector(".dim").textContent = `${m.dim_sec}秒`;
    node.querySelector(".sleep").textContent = `${m.suspend_sec}秒`;
    node.querySelector(".badge").hidden = m.id !== state.currentMode;
    node.addEventListener("click", () => select(m.id));
    box.appendChild(node);
  }

  // 矢印キーでも選べるようにする
  box.addEventListener("keydown", (e) => {
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const ids = state.modes.map((m) => m.id);
    const step = e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 1;
    const next = ids[(ids.indexOf(selected) + step + ids.length) % ids.length];
    select(next);
    box.querySelector(`[data-mode="${next}"]`).focus();
  });

  const cur = state.modes.find((m) => m.id === state.currentMode);
  $("current").innerHTML = cur
    ? `現在: <b>${cur.name}</b>`
    : state.current.exists
      ? "現在: <b>カスタム設定</b>"
      : "現在: <b>未設定（システム既定）</b>";

  select(state.currentMode || state.defaultMode);
}

async function apply() {
  if (!selected || busy) return;
  busy = true;
  $("ok").disabled = true;
  $("ok").textContent = "適用中…";
  showError("");
  try {
    const r = await api("/api/apply", { mode: selected });
    $("done-title").textContent = `${r.name}に切り替えました`;
    $("current").innerHTML = "";
    $("current").append("現在: ", Object.assign(document.createElement("b"), { textContent: r.name }));
    $("done-text").textContent = `${r.configPath} を書き換えました。`;
    const note = $("done-note");
    note.hidden = r.reloaded;
    note.textContent = r.reloaded ? "" :
      "電源管理サービスへの反映を確認できませんでした。反映されない場合はログアウトして再ログインしてください。";
    $("select-view").hidden = true;
    $("done-view").hidden = false;
    $("close").focus();
  } catch (e) {
    showError(e.message);
    $("ok").disabled = false;
  } finally {
    $("ok").textContent = "OK";
    busy = false;
  }
}

async function closeApp() {
  try { await api("/api/close", {}); } catch (_) { /* すでに終了している */ }
  window.close();
}

$("ok").addEventListener("click", apply);
$("cancel").addEventListener("click", closeApp);
$("close").addEventListener("click", closeApp);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeApp(); });

// ブラウザ表示時に、ウィンドウが閉じられたことをサーバーが検知できるようにする
setInterval(() => { api("/api/ping").catch(() => {}); }, 5000);

api("/api/state")
  .then(render)
  .catch((e) => {
    $("current").textContent = "現在の設定を読み込めませんでした";
    showError(e.message);
  });
