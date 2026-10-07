// 盤中強勢族群（網站端）：讀自己的 Cloudflare Worker，每分鐘更新
//
// 設定頁填「盤中服務網址」與「存取碼」（只存在這台裝置的 localStorage）後才會出現：
//   今日頁最上面的「盤中強勢族群」卡（09:00～14:30）、市場底下的「盤中」子分頁。
// 計算在 intraday_core.js（和 Worker 共用，原始檔 intraday/core.js）。
// 依賴 intel.js 放在 window.DashUI 的小工具（el、fmt、signed、dir、md、openStock、goSub）。
import * as core from './intraday_core.js';

const KEY = 'dash-intraday';
const POLL_MS = 60000;
const TOP = 20;              // 排行列幾個族群
const MEMBERS = 10;          // 展開時先列幾檔
const LAST_MINUTE = 273;     // Worker 收到 13:33
const UI = window.DashUI || {};

const st = {U: null, ref: null, date: null, series: [], error: null, busy: false, open: null, memAll: null,
            empty: false, shownAll: false, closeSync: null};
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
  if (!r.ok) {
    let why = '';
    try { why = (await r.json()).error || ''; } catch (e) { /* 不是 JSON */ }
    throw new Error(why || '盤中服務回應 ' + r.status);
  }
  return r.json();
}

// ── 資料 ──
// 整份載入（每 3 分鐘一份快照＋今日名單）；沒有資料就保留畫面上原本那天的
async function load(path) {
  const d = await api(path);
  st.empty = !d.universe || !d.snaps || !d.snaps.length;
  if (!st.empty) {
    st.U = d.universe; st.ref = d.ref; st.date = d.date;
    st.series = core.fillForward(d.snaps);
  }
}

async function refresh(full) {
  if (!configured() || st.busy) return;
  st.busy = true;
  try {
    const now = taipei();
    if (full || !st.U) await load('/day?step=3&u=1');
    // 畫面上是前一個交易日：只問今天（今天還沒資料的話 Worker 只讀一次 KV）
    else if (st.date !== now.date) await load('/day?date=' + now.date + '&step=3&u=1');
    else {
      const last = latest();
      const d = await api('/day?date=' + st.date + '&step=1&from=' + core.hhmm(last.m + 1));
      if (d.ref) st.ref = d.ref;          // Worker 會補上開盤時沒查到的昨收
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

// 盤中走勢小圖：橫軸從 09:00 到最新一份資料（end，分鐘），虛線是基準（昨收、或族群的 0%）
function lineSvg(pts, base, w, h, cls, end) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');
  const last = pts.length ? pts[pts.length - 1][1] : null;
  svg.setAttribute('class', 'lv-line ' + (cls || '') + ' ' + (last != null && base != null ? dir(last - base) : ''));
  if (pts.length < 2 || base == null) return svg;
  const vals = pts.map(q => q[1]).concat([base]);
  const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), span = hi - lo || 1;
  const X = m => (Math.min(Math.max(m, 0), end) / end * (w - 2) + 1).toFixed(1);
  const Y = v => (h - 1 - (v - lo) / span * (h - 2)).toFixed(1);
  const mk = (tag, attrs) => {
    const n = document.createElementNS(ns, tag);
    Object.keys(attrs).forEach(k => n.setAttribute(k, attrs[k]));
    n.setAttribute('vector-effect', 'non-scaling-stroke');
    svg.appendChild(n);
  };
  mk('line', {x1: 0, x2: w, y1: Y(base), y2: Y(base), class: 'lv-base'});
  mk('path', {d: pts.map((q, k) => (k ? 'L' : 'M') + X(q[0]) + ' ' + Y(q[1])).join(' ')});
  return svg;
}

// 個股價格：千元以上不帶小數，其餘最多兩位（去掉多餘的 0）
function price(v) {
  return v == null ? '—' : Number(v).toLocaleString('zh-TW', {maximumFractionDigits: v >= 1000 ? 0 : 2});
}

function detail(r) {
  const box = el('div', 'lv-detail');
  // 同一個族群的線共用橫軸：09:00 到最新一份（開盤頭半小時至少留 30 分鐘寬，線才不會擠成一團）
  const end = Math.max(30, Math.min(270, latest().m));
  const line = core.groupLine(st.U, st.ref, st.series, r.gi);
  const gpts = st.series.map((s, k) => [s.m, line[k]]).filter(q => q[1] != null);
  if (gpts.length > 1) box.appendChild(lineSvg(gpts, 0, 300, 46, 'lv-gline', end));
  const mem = core.members(st.U, st.ref, latest(), r.gi, corrSeries());
  const t = el('div', 'lv-mem');
  const head = el('div', 'lv-m lv-m-h');
  ['股票', '今日走勢', '價格・漲幅'].forEach(x => head.appendChild(el('span', null, x)));
  t.appendChild(head);
  mem.forEach((m, k) => {
    const row = el('button', 'lv-m');
    row.type = 'button';
    row.hidden = st.memAll !== r.name && k >= MEMBERS;
    // 左：名稱、標記；下一行代號、量比、連動
    const info = el('span', 'lv-mi');
    const n = el('span', 'lv-mn');
    n.appendChild(el('b', null, m.name));
    if (m.limit) n.appendChild(el('span', 'lv-lim', '漲停'));
    if (m.first) n.appendChild(el('span', 'lv-lead', m.lead + ' 領漲'));
    info.appendChild(n);
    info.appendChild(el('small', 'lv-ms', m.code + '　量比 ' + (m.vr == null ? '—' : m.vr.toFixed(1)) +
                                          '　連動 ' + (m.corr == null ? '—' : m.corr.toFixed(2))));
    row.appendChild(info);
    // 中：今日走勢（虛線＝昨收）
    const pts = st.series.filter(s => s.p[m.i] != null).map(s => [s.m, s.p[m.i]]);
    row.appendChild(lineSvg(pts, st.ref.y[m.i], 64, 26, 'lv-mline', end));
    // 右：目前價格、漲幅
    const q = el('span', 'lv-mq ' + dir(m.chg));
    q.appendChild(el('b', 'num', price(m.price)));
    q.appendChild(el('span', 'num', signed(m.chg, 2, '%')));
    row.appendChild(q);
    row.addEventListener('click', () => UI.openStock && UI.openStock(m.code));
    t.appendChild(row);
  });
  box.appendChild(t);
  if (st.memAll !== r.name && mem.length > MEMBERS) {
    const more = el('button', 'scr-more', '再看 ' + (mem.length - MEMBERS) + ' 檔');
    more.type = 'button';
    more.addEventListener('click', () => {
      st.memAll = r.name;                 // 記住，每分鐘重畫時才不會又收起來
      Array.prototype.forEach.call(t.querySelectorAll('.lv-m[hidden]'), x => { x.hidden = false; });
      more.remove();
    });
    box.appendChild(more);
  }
  box.appendChild(el('p', 'sd-note', '今日走勢＝09:00 到現在的成交價（虛線是昨收）；量比＝目前累積成交值 ÷ 同一時間點的 20 日平均；' +
                                     '連動＝今天每 3 分鐘漲跌和族群其他成員的相關係數（開盤 30 分鐘後才有）；領漲＝最先漲到 +3%。'));
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
      st.memAll = null;
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
// 設定好了：「盤中」排到市場的第一個子分頁；清除設定：藏起來、放回最後，選取狀態交給第一個看得到的
function setupTab() {
  const btn = document.querySelector('.subtab[data-sub="live"]');
  if (!btn) return;
  const bar = btn.parentNode;
  btn.hidden = !configured();
  if (configured()) {
    if (bar.firstElementChild !== btn) bar.insertBefore(btn, bar.firstElementChild);
  } else {
    bar.appendChild(btn);
    const first = bar.querySelector('.subtab:not([hidden])');
    if (btn.getAttribute('aria-selected') === 'true' && first) first.click();
  }
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
    // 網址一定要 https://（沒寫的話會被當成本站的路徑，存取碼就送錯地方）
    const raw = url.value.trim();
    let u = null;
    try { u = raw ? new URL(raw) : null; } catch (e) { /* 下面處理 */ }
    if (raw && (!u || u.protocol !== 'https:')) {
      msg.textContent = '網址要以 https:// 開頭（例如 https://local-dash-intraday.xxx.workers.dev）';
      return;
    }
    cfg = {url: u ? u.origin : '', code: code.value.trim()};
    url.value = cfg.url;
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

// 每分鐘一次：盤中抓新快照；收盤後第一次回到頁面補到 13:33；其他時候只重畫（14:30 收起今日卡、更新時間標示）
function tick() {
  if (document.hidden || !configured()) return;
  const n = taipei();
  if (marketOpen()) { refresh(false); return; }
  const last = latest();
  if (st.date === n.date && last && last.m < LAST_MINUTE && n.minute > 275 && st.closeSync !== n.date) {
    st.closeSync = n.date;
    refresh(false);
    return;
  }
  render();
}

function start() {
  setupSettings();
  setupTab();
  if (configured()) refresh(true);
  // 對齊到每分鐘第 30 秒左右：Worker 的快照大約第 15 秒才寫好
  setTimeout(() => { tick(); setInterval(tick, POLL_MS); }, ((90 - new Date().getSeconds()) % 60) * 1000);
  document.addEventListener('visibilitychange', tick);
}

start();
