// 盤中強勢族群（網站端）：讀自己的 Cloudflare Worker，每分鐘更新
//
// 設定頁填「盤中服務網址」與「存取碼」（只存在這台裝置的 localStorage）後才會出現：
//   今日頁最上面的「盤中強勢族群」卡（09:00～14:30）、市場底下的「盤中」子分頁。
// 計算在 intraday_core.js（和 Worker 共用，原始檔 intraday/core.js）。
// 依賴 intel.js 放在 window.DashUI 的小工具（el、fmt、signed、dir、md、sparkSvg、openStock、goSub）。
import * as core from './intraday_core.js';

const KEY = 'dash-intraday';
const POLL_MS = 60000;
const TOP = 20;              // 排行列幾個族群
const MEMBERS = 10;          // 展開時先列幾檔
const UI = window.DashUI || {};

const st = {U: null, ref: null, date: null, series: [], error: null, busy: false, open: null, empty: false,
            shownAll: false};
let cfg = loadCfg();

function loadCfg() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
}
function saveCfg(c) {
  try { localStorage.setItem(KEY, JSON.stringify(c)); } catch (e) { /* 隱私模式：這次有效 */ }
}
function configured() { return !!(cfg.url && cfg.code); }

function taipei() {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  return {date: d.toISOString().slice(0, 10).replace(/-/g, ''), minute: (d.getUTCHours() - 9) * 60 + d.getUTCMinutes(),
          dow: d.getUTCDay()};
}
function marketOpen() {
  const n = taipei();
  return n.dow >= 1 && n.dow <= 5 && n.minute >= -5 && n.minute <= 275;
}
function showCard() {
  const n = taipei();
  return n.dow >= 1 && n.dow <= 5 && n.minute >= -5 && n.minute <= 330;     // 09:00～14:30
}

async function api(path) {
  const r = await fetch(cfg.url.replace(/\/+$/, '') + path,
                        {headers: {Authorization: 'Bearer ' + cfg.code}, cache: 'no-store'});
  if (r.status === 401) throw new Error('存取碼不對，請到設定頁重新輸入');
  if (!r.ok) throw new Error('盤中服務回應 ' + r.status);
  return r.json();
}

// ── 資料 ──
async function refresh(full) {
  if (!configured() || st.busy) return;
  st.busy = true;
  try {
    const now = taipei();
    if (full || !st.U || (marketOpen() && st.date !== now.date)) {
      const d = await api('/day?step=3&u=1');
      st.empty = !d.universe || !d.snaps || !d.snaps.length;
      if (!st.empty) {
        st.U = d.universe; st.ref = d.ref; st.date = d.date;
        st.series = core.fillForward(d.snaps);
      }
    } else {
      const last = st.series[st.series.length - 1];
      const d = await api('/day?date=' + st.date + '&step=1&from=' + core.hhmm(last.m + 1));
      const fresh = (d.snaps || []).filter(s => s.m > last.m);
      if (fresh.length) st.series = core.fillForward(st.series.concat(fresh));
    }
    st.error = null;
  } catch (e) {
    st.error = e.message || '讀取失敗';
  } finally {
    st.busy = false;
    render();
  }
}

function latest() { return st.series[st.series.length - 1]; }

// 連動用的序列：每 3 分鐘一個點（開盤後補的資料就是 3 分鐘一個），加上最新一份
function corrSeries() {
  const s = st.series.filter(x => x.m % 3 === 0);
  const last = latest();
  if (last && s[s.length - 1] !== last) s.push(last);
  return s;
}

// 30 分鐘前的排名，用來標「轉強」
function oldRanks() {
  const last = latest();
  const old = st.series.filter(x => x.m <= last.m - 30).pop();
  if (!old) return null;
  const rows = core.groupStats(st.U, st.ref, old);
  const out = {};
  rows.forEach((r, k) => { out[r.name] = k; });
  return out;
}

function ranking() {
  const snap = latest();
  const rows = core.groupStats(st.U, st.ref, snap);
  const old = oldRanks();
  rows.forEach((r, k) => { r.rank = k; r.rise = old && old[r.name] != null ? old[r.name] - k : null; });
  return core.dedupe(st.U, rows, TOP);
}

// ── 畫面 ──
const el = (tag, cls, text) => UI.el ? UI.el(tag, cls, text) : Object.assign(document.createElement(tag), {className: cls || '', textContent: text ?? ''});
const signed = (v, d, s) => (UI.signed ? UI.signed(v, d, s) : (v > 0 ? '+' : '') + Number(v).toFixed(d) + (s || ''));
const dir = v => (v > 0 ? 'up' : v < 0 ? 'down' : '');

function stamp() {
  const last = latest();
  if (!last) return '';
  const n = taipei();
  const lag = st.date === n.date && marketOpen() ? n.minute - last.m : 0;
  const day = st.date && st.date !== n.date ? st.date.slice(4, 6) + '/' + st.date.slice(6) + ' ' : '';
  return day + (last.t || core.hhmm(last.m)) + (lag >= 3 ? ' · 資料延遲 ' + lag + ' 分鐘' : ' 更新');
}

function tags(r) {
  const out = [];
  if ((st.U.yday || []).indexOf(r.name) >= 0) out.push(['延續', 'cont']);
  else if (r.hot) out.push(['新進', 'new']);
  if (r.rise != null && r.rise >= 5) out.push(['轉強', 'rise']);
  return out;
}

function groupRow(r, clickable) {
  const row = el(clickable ? 'button' : 'div', 'lv-grp' + (r.hot ? '' : ' is-weak'));
  if (clickable) row.type = 'button';
  const name = el('span', 'lv-name');
  name.appendChild(el('b', null, r.name));
  tags(r).forEach(t => name.appendChild(el('span', 'lv-tag lv-' + t[1], t[0])));
  row.appendChild(name);
  row.appendChild(el('span', 'lv-chg num ' + dir(r.chg), signed(r.chg, 1, '%')));
  row.appendChild(el('span', 'lv-br num', r.up + '/' + r.n));
  const sub = el('span', 'lv-sub');
  const bar = el('span', 'lv-bar');
  const b1 = el('b'); b1.style.flex = String(r.up);
  const b2 = el('s'); b2.style.flex = String(r.n - r.up);
  bar.appendChild(b1); bar.appendChild(b2);
  sub.appendChild(bar);
  sub.appendChild(document.createTextNode(
    '強勢 ' + r.strong + (r.limit ? '・漲停 ' + r.limit : '') + (r.vr != null ? '・量比 ' + r.vr.toFixed(1) : '') +
    (r.alias && r.alias.length ? '・亦屬 ' + r.alias.slice(0, 2).join('、') : '')));
  row.appendChild(sub);
  return row;
}

function detail(r) {
  const box = el('div', 'lv-detail');
  const line = core.groupLine(st.U, st.ref, st.series, r.gi).filter(v => v != null);
  if (line.length > 1 && UI.sparkSvg) {
    const sp = UI.sparkSvg(line);
    sp.classList.add('lv-spark');
    box.appendChild(sp);
  }
  const mem = core.members(st.U, st.ref, latest(), r.gi, corrSeries());
  const t = el('div', 'lv-mem');
  const head = el('div', 'lv-m lv-m-h');
  ['股票', '漲幅', '量比', '連動'].forEach(x => head.appendChild(el('span', null, x)));
  t.appendChild(head);
  mem.forEach((m, k) => {
    const row = el('button', 'lv-m');
    row.type = 'button';
    row.hidden = k >= MEMBERS;
    const n = el('span', 'lv-mn');
    n.appendChild(document.createTextNode(m.name + ' '));
    n.appendChild(el('small', null, m.code));
    if (m.limit) n.appendChild(el('span', 'lv-lim', '漲停'));
    if (m.first) n.appendChild(el('span', 'lv-lead', m.lead + ' 領漲'));
    row.appendChild(n);
    row.appendChild(el('span', 'num ' + dir(m.chg), signed(m.chg, 2, '%')));
    row.appendChild(el('span', 'num', m.vr == null ? '—' : m.vr.toFixed(1)));
    row.appendChild(el('span', 'num', m.corr == null ? '—' : m.corr.toFixed(2)));
    row.addEventListener('click', () => UI.openStock && UI.openStock(m.code));
    t.appendChild(row);
  });
  box.appendChild(t);
  if (mem.length > MEMBERS) {
    const more = el('button', 'scr-more', '再看 ' + (mem.length - MEMBERS) + ' 檔');
    more.type = 'button';
    more.addEventListener('click', () => {
      Array.prototype.forEach.call(t.querySelectorAll('.lv-m[hidden]'), x => { x.hidden = false; });
      more.remove();
    });
    box.appendChild(more);
  }
  box.appendChild(el('p', 'sd-note', '量比＝目前累積成交值 ÷ 同一時間點的 20 日平均；連動＝今天每 3 分鐘漲跌和族群其他成員的相關係數（開盤 30 分鐘後才有）；領漲＝最先漲到 +3%。'));
  return box;
}

function renderCard() {
  const card = document.querySelector('.td-live');
  if (!card) return;
  card.hidden = !(configured() && showCard() && st.date === taipei().date && st.series.length);
  if (card.hidden) return;
  card.textContent = '';
  const h = el('h3', 'lv-h');
  h.appendChild(document.createTextNode('盤中強勢族群'));
  const live = el('span', 'lv-live');
  live.appendChild(el('i'));
  live.appendChild(document.createTextNode(stamp()));
  h.appendChild(live);
  card.appendChild(h);
  const rows = ranking();
  const hot = rows.filter(r => r.hot).slice(0, 3);
  if (!hot.length) card.appendChild(el('p', 'ov-empty', '目前沒有族群有 3 檔以上漲 3%；以下是相對強的族群。'));
  (hot.length ? hot : rows.slice(0, 3)).forEach(r => card.appendChild(groupRow(r, false)));
  const more = el('button', 'ck-more', '看全部族群與連動個股 ›');
  more.type = 'button';
  more.addEventListener('click', () => UI.goSub && UI.goSub('live'));
  card.appendChild(more);
}

function renderPane() {
  const pane = document.querySelector('.subpanel[data-sub="live"]');
  if (!pane || pane.hidden) return;
  const body = pane.querySelector('.lv-body');
  body.textContent = '';
  if (!configured()) {
    body.appendChild(el('p', 'ov-empty', '還沒設定盤中服務：到設定頁填「盤中服務網址」與「存取碼」。'));
    return;
  }
  if (st.error) body.appendChild(el('p', 'lv-err', st.error));
  if (!st.series.length) {
    body.appendChild(el('p', 'ov-empty', st.empty ? '盤中服務還沒有資料：開盤後每分鐘會收一次。' : '載入中…'));
    return;
  }
  const last = latest();
  const b = core.breadth(st.U, st.ref, last);
  const rows = ranking();
  const hotN = rows.filter(r => r.hot).length;
  body.appendChild(el('p', 'ov-asof', stamp() + '　·　名單內上漲 ' + b.up + '／下跌 ' + b.down +
                                      '　·　強勢族群 ' + hotN + ' 個'));
  const risers = rows.filter(r => r.rise != null && r.rise >= 5).sort((a, c) => c.rise - a.rise).slice(0, 3);
  if (risers.length) {
    const p = el('p', 'lv-risers');
    p.appendChild(el('b', null, '剛轉強　'));
    p.appendChild(document.createTextNode(risers.map(r => r.name + ' ↑' + r.rise).join('　')));
    body.appendChild(p);
  }
  const list = el('div', 'lv-list ov-card');
  rows.slice(0, st.shownAll ? TOP : 10).forEach(r => {
    const item = el('div', 'lv-item');
    const row = groupRow(r, true);
    row.setAttribute('aria-expanded', String(st.open === r.name));
    row.addEventListener('click', () => {
      st.open = st.open === r.name ? null : r.name;
      renderPane();
    });
    item.appendChild(row);
    if (st.open === r.name) item.appendChild(detail(r));
    list.appendChild(item);
  });
  body.appendChild(list);
  if (!st.shownAll && rows.length > 10) {
    const more = el('button', 'scr-more', '再看 ' + (rows.length - 10) + ' 個族群');
    more.type = 'button';
    more.addEventListener('click', () => { st.shownAll = true; renderPane(); });
    body.appendChild(more);
  }
}

function render() {
  renderCard();
  renderPane();
}

// ── 子分頁、設定頁 ──
function setupTab() {
  const btn = document.querySelector('.subtab[data-sub="live"]');
  if (!btn) return;
  btn.hidden = !configured();
  if (configured() && btn.parentNode.firstElementChild !== btn) btn.parentNode.insertBefore(btn, btn.parentNode.firstElementChild);
  if (btn.dataset.bound) return;
  btn.dataset.bound = '1';
  btn.addEventListener('click', () => setTimeout(() => { renderPane(); if (!st.U) refresh(true); }, 0));
}

function setupSettings() {
  const url = document.getElementById('live-url'), code = document.getElementById('live-code');
  const msg = document.getElementById('live-msg');
  if (!url || !code) return;
  url.value = cfg.url || '';
  code.value = cfg.code ? cfg.code : '';
  document.getElementById('live-save').addEventListener('click', async () => {
    cfg = {url: url.value.trim(), code: code.value.trim()};
    saveCfg(cfg);
    if (!configured()) { msg.textContent = '已清除：盤中功能關閉'; setupTab(); render(); return; }
    msg.textContent = '測試連線中…';
    try {
      const s = await api('/status');
      msg.textContent = '連線成功' + (s.latest ? '（最近資料 ' + s.latest.slice(4, 6) + '/' + s.latest.slice(6) + '）' : '（還沒有資料，開盤後會開始收）');
      setupTab();
      refresh(true);
    } catch (e) {
      msg.textContent = '連線失敗：' + e.message;
    }
  });
}

function start() {
  setupSettings();
  setupTab();
  if (!configured()) return;
  refresh(true);
  setInterval(() => { if (!document.hidden && marketOpen()) refresh(false); }, POLL_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && marketOpen()) refresh(false); });
}

start();
