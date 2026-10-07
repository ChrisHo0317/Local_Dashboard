// 盤中強勢族群（網站端）：讀自己的 Cloudflare Worker，每分鐘更新；有永豐金即時資料時每 5 秒更新
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
    live.frame = null;
    render();
  }
}

function latest() { return st.series[st.series.length - 1]; }

// ── 即時（永豐金行情程式 → Cloudflare 即時轉播站 intraday/livehub.js）──
// 盤中（平日 08:55～13:40）而且畫面在前景時，和轉播站保持 WebSocket 連線；收到的價量蓋在最新一分鐘的快照上，
// 變成「即時這一格」current()。LIVE_STALE_MS 沒收到就當作暫停，畫面自動退回每分鐘的資料。
const LIVE_STALE_MS = 30000;
const live = {ws: null, q: {}, date: null, t: null, recv: 0, seen: 0, state: 'off', why: '', retry: 0, timer: null,
              frame: null, idx: null, idxU: null};
const LIVE_DEAD_MS = 75000;            // 連 'pong' 都 75 秒沒收到：連線其實斷了（換網路、電腦睡醒），重連

function liveWanted() {
  const n = taipei();
  return configured() && !document.hidden && n.dow >= 1 && n.dow <= 5 && n.minute >= -5 && n.minute <= 280;
}

function liveSync() {
  if (liveWanted()) {
    if (!live.ws && live.state !== 'error') liveConnect();
  } else if (live.ws) {
    liveClose('off');
  }
}

function liveConnect() {
  clearTimeout(live.timer);
  let ws;
  try {
    ws = new WebSocket(cfg.url.replace(/\/+$/, '').replace(/^http/, 'ws') + '/stream');
  } catch (e) {
    live.state = 'error'; live.why = '網址不對，無法連線';
    return;
  }
  live.ws = ws;
  live.state = 'connecting';
  live.seen = Date.now();
  ws.onopen = () => {
    ws.send(JSON.stringify({auth: cfg.code}));
    live.retry = 0;
    ws._ping = setInterval(() => { try { ws.send('ping'); } catch (e) { /* 斷了就等 onclose */ } }, 30000);
  };
  ws.onmessage = e => {
    if (live.ws === ws) live.seen = Date.now();
    let m;
    try { m = JSON.parse(e.data); } catch (x) { return; }      // 'pong'
    if (live.ws === ws) liveMessage(m);
  };
  ws.onclose = e => {
    clearInterval(ws._ping);
    if (live.ws !== ws) return;                                 // 舊連線遲到的關閉，不影響新的
    live.ws = null;
    if (e.code === 4001) { live.state = 'error'; live.why = '存取碼不對'; scheduleRender(); return; }
    if (live.state !== 'off') live.state = 'idle';
    live.frame = null;
    scheduleRender();
    if (liveWanted()) live.timer = setTimeout(liveSync, Math.min(60000, 5000 * 2 ** live.retry++));
  };
}

function liveClose(state) {
  const ws = live.ws;
  live.ws = null;
  live.state = state;
  live.frame = null;
  clearTimeout(live.timer);
  if (ws) {
    clearInterval(ws._ping);
    try { ws.close(1000); } catch (e) { /* 已經關了 */ }
  }
}

function liveMessage(m) {
  if (m.type === 'full' || m.type === 'delta') {
    if (m.type === 'full' || live.date !== m.date) live.q = {};
    Object.assign(live.q, m.q || {});
    live.date = m.date; live.t = m.t; live.recv = Date.now(); live.state = 'live';
  } else if (m.type === 'hb') {
    if (live.date === m.date) { live.t = m.t; live.recv = Date.now(); }
  } else if (m.type === 'idle') {
    live.state = 'idle';
  }
  live.frame = null;
  scheduleRender();
}

// 即時這一格：最新一分鐘的快照，名單內有即時價量的股票換成即時的
function liveFrame() {
  const base = latest();
  if (!base || !st.U || live.state !== 'live' || live.date !== st.date || Date.now() - live.recv > LIVE_STALE_MS) return null;
  if (live.frame) return live.frame;
  if (live.idxU !== st.U) { live.idx = new Map(st.U.codes.map((c, i) => [c, i])); live.idxU = st.U; }
  const p = base.p.slice(), v = base.v.slice();
  for (const code in live.q) {
    const i = live.idx.get(code);
    if (i === undefined) continue;
    const a = live.q[code];
    if (a[0] > 0) p[i] = a[0];
    if (a[1] > 0) v[i] = a[1];
  }
  const m = core.minuteOf(live.t);
  live.frame = {t: live.t, m: m == null ? base.m : Math.max(base.m, m), p, v, live: true};
  return live.frame;
}

function current() { return liveFrame() || latest(); }

// 畫走勢線用：每分鐘的資料，有即時就接在最後
function seriesNow() {
  const f = liveFrame();
  return f ? st.series.concat([f]) : st.series;
}

// 即時資料每 5 秒一份：重畫最多每秒一次
let renderTimer = null, lastRender = 0;
function scheduleRender() {
  if (renderTimer) return;
  renderTimer = setTimeout(() => { renderTimer = null; lastRender = Date.now(); render(); },
                           Math.max(0, 1000 - (Date.now() - lastRender)));
}

// ── 事件快訊：每次有新的一格就和上一格比（衝進前 5、漲停／打開、族群換第 1、族群跳升、量比放大）──
const EV_MAX = 30, EV_QUIET_MS = 10 * 60000;
const ev = {list: [], prev: null, t: null, src: null, ranks: [], last: new Map()};

function evPush(key, t, text, target) {
  const now = Date.now();
  if (now - (ev.last.get(key) || 0) < EV_QUIET_MS) return;       // 同一件事 10 分鐘內不重複
  ev.last.set(key, now);
  ev.list.unshift({t, text, target});
  if (ev.list.length > EV_MAX) ev.list.length = EV_MAX;
}

function evalEvents() {
  const snap = current();
  if (!snap || !st.U || st.date !== taipei().date || ev.t === snap.t) return;
  ev.t = snap.t;
  // 資料來源換了（每分鐘 ↔ 即時）：兩邊的量算法不同，這一格只當比較基準，不發快訊
  const src = snap.live ? 'live' : 'min';
  if (ev.src !== src) { ev.src = src; ev.prev = null; ev.ranks = []; }
  const U = st.U, ref = st.ref, t = (snap.t || '').slice(0, 5);
  const frac = U.profile[Math.max(1, Math.min(270, snap.m))] || 1;
  const chg = [], lim = new Set(), surge = new Set();
  U.codes.forEach((c, i) => {
    const p = snap.p[i], y = ref.y[i];
    if (p == null || !y) return;
    const x = (p / y - 1) * 100;
    chg.push([i, x]);
    if (ref.u[i] && p >= ref.u[i]) lim.add(i);
    const tv = snap.v[i] != null ? snap.v[i] * p * 1000 / 1e8 : 0;
    if (x >= 2 && U.avg[i] && tv / (U.avg[i] * frac) >= 3) surge.add(i);
  });
  chg.sort((a, b) => b[1] - a[1]);
  const top5 = chg.slice(0, 5).map(x => x[0]);
  const groups = core.dedupe(U, core.groupStats(U, ref, snap), 8).map(r => r.name);
  const name = i => U.names[i] || U.codes[i];
  const pct = i => signed((snap.p[i] / ref.y[i] - 1) * 100, 1, '%') + '，' + price(snap.p[i]);
  if (ev.prev) {
    top5.forEach((i, k) => {
      if (ev.prev.top5.indexOf(i) < 0) evPush('top|' + i, t, name(i) + ' 衝進漲幅前 5（第 ' + (k + 1) + '，' + pct(i) + '）', {code: U.codes[i]});
    });
    lim.forEach(i => { if (!ev.prev.lim.has(i)) evPush('lim|' + i, t, name(i) + ' 漲停（' + price(snap.p[i]) + '）', {code: U.codes[i]}); });
    ev.prev.lim.forEach(i => { if (!lim.has(i)) evPush('open|' + i, t, name(i) + ' 漲停打開（' + pct(i) + '）', {code: U.codes[i]}); });
    surge.forEach(i => { if (!ev.prev.surge.has(i)) evPush('vr|' + i, t, name(i) + ' 量比放大到 3 倍以上（' + pct(i) + '）', {code: U.codes[i]}); });
    if (groups[0] && groups[0] !== ev.prev.groups[0]) evPush('g1|' + groups[0], t, groups[0] + ' 升到族群第 1', {group: groups[0]});
    // 和大約 1 分鐘前比，族群往前 3 名以上
    const old = ev.ranks.find(r => Date.now() - r.at >= 55000);
    if (old) {
      groups.forEach((g, k) => {
        const was = old.ranks[g];
        if (k > 0 && k < 5 && (was == null || was - k >= 3)) evPush('gup|' + g, t, g + ' 升到族群第 ' + (k + 1) + (was == null ? '' : '（+' + (was - k) + ' 名）'), {group: g});
      });
    }
  }
  ev.prev = {top5, lim, surge, groups};
  const ranks = {};
  groups.forEach((g, k) => { ranks[g] = k; });
  ev.ranks.unshift({at: Date.now(), ranks});
  ev.ranks = ev.ranks.filter(r => Date.now() - r.at < 120000);
}

// 連動用的序列：每 3 分鐘一個點（開盤後補的資料就是 3 分鐘一個），加上最新一份
function corrSeries() {
  const s = st.series.filter(x => x.m % 3 === 0);
  const last = latest();
  if (last && s[s.length - 1] !== last) s.push(last);
  return s;
}

// 30 分鐘前的排名，用來標「轉強」
function oldRanks() {
  const last = current();
  const old = st.series.filter(x => x.m <= last.m - 30).pop();
  if (!old) return null;
  const rows = core.groupStats(st.U, st.ref, old);
  const out = {};
  rows.forEach((r, k) => { out[r.name] = k; });
  return out;
}

function ranking() {
  const snap = current();
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
  const lf = liveFrame();
  if (lf) return '即時 ' + lf.t + '（永豐金）';
  const last = latest();
  if (!last) return '';
  const n = taipei();
  const lag = st.date === n.date && marketOpen() ? n.minute - last.m : 0;
  const day = st.date && st.date !== n.date ? st.date.slice(4, 6) + '/' + st.date.slice(6) + ' ' : '';
  return day + (last.t || core.hhmm(last.m)) + (lag >= 3 ? ' · 資料延遲 ' + lag + ' 分鐘' : ' 更新');
}

// 盤中但沒有即時資料時的說明；有即時、或不在盤中就是空字串
function liveNote() {
  if (liveFrame() || !liveWanted()) return '';
  if (live.state === 'error') return '即時暫停：' + live.why + '（改用每分鐘資料）';
  if (live.state === 'connecting') return '連線即時資料中…';
  if (live.state === 'live' && live.date !== st.date) return '即時資料等待今天第一份每分鐘快照';
  return '即時暫停：目前沒有永豐金即時資料（改用每分鐘資料）';
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
  const ser = seriesNow();
  const end = Math.max(30, Math.min(270, current().m));
  const line = core.groupLine(st.U, st.ref, ser, r.gi);
  const gpts = ser.map((s, k) => [s.m, line[k]]).filter(q => q[1] != null);
  if (gpts.length > 1) box.appendChild(lineSvg(gpts, 0, 300, 46, 'lv-gline', end));
  const mem = core.members(st.U, st.ref, current(), r.gi, corrSeries());
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
    const pts = ser.filter(s => s.p[m.i] != null).map(s => [s.m, s.p[m.i]]);
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
  const last = current();
  const b = core.breadth(st.U, st.ref, last);
  const rows = ranking();
  const hotN = rows.filter(r => r.hot).length;
  body.appendChild(el('p', 'ov-asof', stamp() + '　·　名單內上漲 ' + b.up + '／下跌 ' + b.down +
                                      '　·　強勢族群 ' + hotN + ' 個'));
  const why = liveNote();
  if (why) body.appendChild(el('p', 'lv-paused', why));
  if (ev.list.length) {
    const box = el('div', 'lv-events ov-card');
    box.appendChild(el('h4', null, '剛剛發生'));
    ev.list.slice(0, 8).forEach(x => {
      const b2 = el('button', 'lv-ev');
      b2.type = 'button';
      b2.appendChild(el('span', 'num', x.t));
      b2.appendChild(el('span', null, x.text));
      b2.addEventListener('click', () => {
        if (x.target.code) { if (UI.openStock) UI.openStock(x.target.code); }
        else { st.open = x.target.group; st.memAll = null; renderPane(); }
      });
      box.appendChild(b2);
    });
    body.appendChild(box);
  }
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

// ── 強勢股動畫（排行賽跑）──
// 兩種檢視：即時（預設；畫面開著就跟著即時這一格自己動，有永豐金資料時每 5 秒、沒有時每分鐘）、
// 回放（每 3 分鐘一格，可播放、拖時間軸、換日期；Cloudflare 留最近 5 天的每分鐘資料）。
// 兩種看法：
//   個股  依漲幅排前 RACE_N 名（範圍：全部／自選股／某個族群）
//   族群  上層：最強的 RACE_G 個族群（強度＝漲幅、上漲比例、強勢成員數、量比，和盤中排行一樣）；
//         下層：選定族群的成員依漲幅排前 RACE_M 名。預設跟著當下第 1 名，點族群可以固定看它。
// 今天的資料跟著盤中輪詢更新，其他日子另外讀一次。
const RACE_N = 15, RACE_G = 8, RACE_M = 10;
const RACE_ROW = 38;                       // 每列高度（px），和 CSS .rc-row 一致
const RACE_SPEEDS = [['1×', 600], ['4×', 150], ['10×', 60]];   // 每格幾毫秒（一格＝3 分鐘）
const race = {view: 'live', date: null, data: null, frames: [], idx: -1, playing: false, timer: null, speed: 600,
              scope: 'all', mode: 'stock', pin: null, lists: {}, groupOf: null};

function raceSource() {
  if (race.date && race.data) return race.data;
  return st.U ? {U: st.U, ref: st.ref, series: st.series, date: st.date} : null;
}

function raceFrames(series) {
  const f = series.filter(x => x.m % 3 === 0);
  const last = series[series.length - 1];
  if (last && f[f.length - 1] !== last) f.push(last);
  return f;
}

// 每檔歸到「最新一格排名最前面」的族群，列在名字下面
function raceGroups(src) {
  const out = new Array(src.U.codes.length).fill('');
  const last = src.series[src.series.length - 1];
  if (!last) return out;
  core.groupStats(src.U, src.ref, last).forEach(r => {
    src.U.groups[r.gi][2].forEach(i => { if (!out[i]) out[i] = r.name; });
  });
  return out;
}

function raceScopeIdx(src) {
  const U = src.U;
  if (race.scope === 'watch') return U.watch || [];
  if (race.scope.startsWith('g:')) {
    const g = U.groups.find(x => x[0] === race.scope.slice(2));
    return g ? g[2] : [];
  }
  return U.codes.map((_, i) => i);
}

// 一群股票在這一格的漲幅、量比、漲停，依漲幅排前 n 名
function raceStocks(src, snap, idx, n, sub) {
  const frac = src.U.profile[Math.max(1, Math.min(270, snap.m))] || 1;
  const out = [];
  for (const i of idx) {
    const p = snap.p[i], y = src.ref.y[i];
    if (p == null || !y) continue;
    out.push({i, chg: (p / y - 1) * 100});
  }
  out.sort((a, b) => b.chg - a.chg);
  return out.slice(0, n).map(({i, chg}) => {
    const tv = snap.v[i] != null ? snap.v[i] * snap.p[i] * 1000 / 1e8 : null;
    const vr = tv != null && src.U.avg[i] ? tv / (src.U.avg[i] * frac) : null;
    return {key: 's' + i, name: src.U.names[i] || src.U.codes[i], chg, price: snap.p[i],
            lim: !!(src.ref.u[i] && snap.p[i] >= src.ref.u[i]),
            sub: [sub ? race.groupOf[i] : '', vr == null ? '' : '量比 ' + vr.toFixed(1)].filter(Boolean).join('・'),
            onClick: () => UI.openStock && UI.openStock(src.U.codes[i])};
  });
}

// 一個清單畫一格：同一個 key 的列沿用同一個元素，換名次時用 transform 滑過去；掉出去的淡出
function racePaint(list, items) {
  const L = race.lists[list.dataset.list] || (race.lists[list.dataset.list] = {nodes: new Map(), prev: null});
  const max = Number(list.dataset.max);
  list.style.height = (Math.max(items.length, 1) * RACE_ROW) + 'px';
  const seen = new Set();
  items.forEach((it, k) => {
    seen.add(it.key);
    let row = L.nodes.get(it.key);
    if (!row) {
      row = el('button', 'rc-row');
      row.type = 'button';
      row.innerHTML = '<span class="rc-rank"></span><span class="rc-name"><b></b><small></small></span>' +
                      '<span class="rc-bar"><i></i></span><span class="rc-chg"><b></b><small></small></span>';
      row.style.transform = 'translateY(' + (max * RACE_ROW) + 'px)';
      row.addEventListener('click', () => row._click && row._click());
      list.appendChild(row);
      L.nodes.set(it.key, row);
      void row.offsetWidth;                               // 先停在底下，下一步才滑上來
    }
    row._click = it.onClick;
    row.className = 'rc-row ' + dir(it.chg) + (it.lim ? ' is-lim' : '') + (it.sel ? ' is-sel' : '') +
                    (L.prev && !L.prev.has(it.key) ? ' is-new' : '');
    row.style.transform = 'translateY(' + (k * RACE_ROW) + 'px)';
    row.style.opacity = '1';
    row.querySelector('.rc-rank').textContent = String(k + 1);
    row.querySelector('.rc-name b').textContent = it.name;
    row.querySelector('.rc-name small').textContent = it.sub || '';
    row.querySelector('.rc-bar i').style.width = Math.min(Math.abs(it.chg), 10) * 10 + '%';
    const pc = signed(it.chg, 1, '%') + (it.lim ? ' 漲停' : '');
    row.querySelector('.rc-chg b').textContent = it.price != null ? price(it.price) : pc;
    row.querySelector('.rc-chg small').textContent = it.price != null ? pc : '';
  });
  L.nodes.forEach((row, key) => {
    if (seen.has(key)) return;
    row.style.transform = 'translateY(' + (max * RACE_ROW) + 'px)';
    row.style.opacity = '0';
  });
  L.prev = seen;
}

function raceClear() {
  Object.values(race.lists).forEach(L => L.nodes.forEach(row => row.remove()));
  race.lists = {};
}

function raceDraw() {
  const box = document.querySelector('.lv-race');
  const src = raceSource();
  if (!box || !src || !race.frames.length) return;
  const isLive = race.view === 'live';
  const snap = isLive ? current() : race.frames[race.idx];
  if (!snap) return;
  box.querySelector('.rc-time').textContent = snap.t || core.hhmm(snap.m).replace(/^(..)/, '$1:');
  box.querySelector('.rc-slider').value = String(race.idx);
  box.querySelectorAll('.rc-replay').forEach(x => { x.hidden = isLive; });
  const note = box.querySelector('.rc-livenote');
  note.hidden = !isLive;
  if (isLive) {
    const lf = liveFrame();
    note.textContent = lf ? '● 即時（永豐金，約 5 秒一次）' : '每分鐘資料' + (liveNote() ? '：' + liveNote() : '');
    note.classList.toggle('is-live', !!lf);
  }
  const byStock = race.mode === 'stock';
  box.querySelector('.rc-stock').hidden = !byStock;
  box.querySelector('.rc-group').hidden = byStock;
  box.querySelector('.rc-scope').hidden = !byStock;
  if (byStock) {
    const items = raceStocks(src, snap, raceScopeIdx(src), RACE_N, true);
    racePaint(box.querySelector('.rc-stock .rc-list'), items);
    box.querySelector('.rc-stock .rc-empty').hidden = items.length > 0;
    return;
  }
  // 族群：上層強度排行，下層選定族群的成員
  const rows = core.dedupe(src.U, core.groupStats(src.U, src.ref, snap), RACE_G);
  const sel = race.pin || (rows[0] && rows[0].name);
  racePaint(box.querySelector('.rc-glist'), rows.map(r => ({
    key: 'g' + r.name, name: r.name, chg: r.chg,
    sel: r.name === sel || (r.alias || []).indexOf(sel) >= 0,
    sub: '上漲 ' + r.up + '/' + r.n + '・強勢 ' + r.strong + (r.vr != null ? '・量比 ' + r.vr.toFixed(1) : ''),
    onClick: () => { race.pin = race.pin === r.name ? null : r.name; raceClearList('m'); raceDraw(); }})));
  const g = src.U.groups.find(x => x[0] === sel);
  box.querySelector('.rc-mhead').textContent = !sel ? '' :
    sel + ' 內部排名' + (race.pin ? '（已固定，點同一個族群取消）' : '（跟著第 1 名，點上面的族群可以固定）');
  racePaint(box.querySelector('.rc-mlist'), g ? raceStocks(src, snap, g[2], RACE_M, false) : []);
}

function raceClearList(name) {
  const L = race.lists[name];
  if (!L) return;
  L.nodes.forEach(row => row.remove());
  delete race.lists[name];
}

function raceStop() {
  race.playing = false;
  clearTimeout(race.timer);
  const b = document.querySelector('.lv-race .rc-play');
  if (b) b.textContent = '▶ 播放';
}

function racePlay() {
  if (race.idx >= race.frames.length - 1) { race.idx = 0; raceClear(); }
  race.playing = true;
  document.querySelector('.lv-race .rc-play').textContent = '⏸ 暫停';
  const step = () => {
    if (!race.playing) return;
    raceDraw();
    if (race.idx >= race.frames.length - 1) { raceStop(); return; }
    race.idx++;
    race.timer = setTimeout(step, race.speed);
  };
  step();
}

// 換日期、資料更新後：重算格子與族群；正在看最新一格又沒在播放，就跟到新的最新一格
function raceReset(keepIdx) {
  const src = raceSource();
  const box = document.querySelector('.lv-race');
  if (!box) return;
  box.hidden = !src || !src.series.length;
  if (box.hidden) return;
  const wasEnd = race.idx < 0 || race.idx >= race.frames.length - 1;
  race.frames = raceFrames(src.series);
  race.groupOf = raceGroups(src);
  box.querySelector('.rc-slider').max = String(race.frames.length - 1);
  if (!keepIdx || wasEnd && !race.playing) race.idx = race.frames.length - 1;
  race.idx = Math.min(race.idx, race.frames.length - 1);
  box.style.setProperty('--rc-dur', Math.min(race.speed * 0.85, 450) + 'ms');
  raceScopes(src);
  if (!race.playing) raceDraw();
}

function raceScopes(src) {
  const sel = document.querySelector('.lv-race .rc-scope');
  const want = [['all', '全部名單']].concat(src.U.watch && src.U.watch.length ? [['watch', '自選股']] : [])
    .concat(core.dedupe(src.U, core.groupStats(src.U, src.ref, src.series[src.series.length - 1]), 20)
      .map(r => ['g:' + r.name, r.name]));
  if (!want.some(x => x[0] === race.scope)) race.scope = 'all';
  const sig = want.map(x => x[0]).join('|');
  if (sel.dataset.sig === sig) { sel.value = race.scope; return; }
  sel.dataset.sig = sig;
  sel.textContent = '';
  want.forEach(([v, t]) => {
    const o = el('option', null, t);
    o.value = v;
    o.selected = v === race.scope;
    sel.appendChild(o);
  });
}

const mdOf = d => Number(d.slice(4, 6)) + '/' + Number(d.slice(6));      // 20261006 → 10/6

// 最近 5 個平日（含今天）；點了才讀那天的資料
function raceDays() {
  const out = [];
  for (let k = 0; out.length < 5 && k < 10; k++) {
    const d = new Date(Date.now() + 8 * 3600 * 1000 - k * 86400 * 1000);
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    out.push(d.toISOString().slice(0, 10).replace(/-/g, ''));
  }
  return out;
}

async function raceDate(date) {
  raceStop();
  const msg = document.querySelector('.lv-race .rc-msg');
  msg.textContent = '';
  if (!date || date === st.date) {
    race.date = null; race.data = null;
  } else {
    msg.textContent = '載入中…';
    try {
      const d = await api('/day?date=' + date + '&step=3&u=1');
      if (!d.universe || !d.snaps || !d.snaps.length) {
        msg.textContent = mdOf(date) + ' 沒有資料（休市，或已超過 5 天）';
        return;
      }
      race.date = date;
      race.data = {U: d.universe, ref: d.ref, series: core.fillForward(d.snaps), date};
      msg.textContent = '';
    } catch (e) {
      msg.textContent = e.message || '讀取失敗';
      return;
    }
  }
  raceClear();
  race.pin = null;
  raceReset(false);
  document.querySelectorAll('.lv-race .rc-day').forEach(b => {
    b.setAttribute('aria-pressed', String(b.dataset.date === (race.date || st.date)));
  });
}

function chipGroup(box, items, isOn, onPick) {
  items.forEach(([label, value]) => {
    const b = el('button', 'chip', label);
    b.type = 'button';
    b.setAttribute('aria-pressed', String(isOn(value)));
    b.addEventListener('click', () => {
      box.querySelectorAll('.chip').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      onPick(value);
    });
    box.appendChild(b);
  });
}

function setupRace() {
  const pane = document.querySelector('.subpanel[data-sub="live"]');
  if (!pane || pane.querySelector('.lv-race')) return;
  const box = el('section', 'lv-race ov-card');
  box.hidden = true;
  const list = (name, max) => '<div class="rc-list" data-list="' + name + '" data-max="' + max + '"></div>';
  box.innerHTML =
    '<div class="rc-head"><h3>強勢股動畫</h3><span class="rc-time num"></span></div>' +
    '<div class="rc-ctrl"><span class="rc-view"></span><span class="rc-mode"></span>' +
    '<select class="rc-scope" aria-label="範圍"></select></div>' +
    '<p class="rc-livenote sd-note"></p>' +
    '<div class="rc-days rc-replay"></div>' +
    '<div class="rc-ctrl rc-replay"><button type="button" class="rc-play chip">▶ 播放</button><span class="rc-speed"></span></div>' +
    '<input type="range" class="rc-slider rc-replay" min="0" max="0" value="0" aria-label="時間">' +
    '<p class="rc-msg sd-note"></p>' +
    '<div class="rc-stock"><p class="rc-empty ov-empty" hidden>這個範圍沒有股票。</p>' + list('s', RACE_N) +
    '<p class="sd-note">依當下漲幅排前 ' + RACE_N + ' 名；名字下面是所屬族群（今天排名最前的那個）與量比。點股票看個股頁。</p></div>' +
    '<div class="rc-group" hidden><h4 class="rc-sub">族群強度</h4>' + list('g', RACE_G).replace('rc-list', 'rc-list rc-glist') +
    '<h4 class="rc-sub rc-mhead"></h4>' + list('m', RACE_M).replace('rc-list', 'rc-list rc-mlist') +
    '<p class="sd-note">族群依強度排名（漲幅、上漲比例、強勢成員數、量比，和下面的盤中排行一樣，重疊太多的只留一個）；' +
    '條形是族群的加權漲幅。點族群固定看它的內部排名，點個股看個股頁。</p></div>' +
    '<p class="sd-note rc-replay">回放每格 3 分鐘。</p>';
  pane.insertBefore(box, pane.querySelector('.lv-body'));
  const days = box.querySelector('.rc-days');
  raceDays().forEach((d, k) => {
    const b = el('button', 'chip rc-day', k ? mdOf(d) : '今天');
    b.type = 'button';
    b.dataset.date = d;
    b.addEventListener('click', () => raceDate(d));
    days.appendChild(b);
  });
  chipGroup(box.querySelector('.rc-view'), [['即時', 'live'], ['回放', 'replay']], v => v === race.view, v => {
    race.view = v;
    raceStop();
    if (v === 'live' && race.date) {            // 回到即時：換回今天的資料
      race.date = null; race.data = null;
      raceClear();
      raceReset(false);
      box.querySelectorAll('.rc-day').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.date === st.date)));
    }
    raceDraw();
  });
  chipGroup(box.querySelector('.rc-mode'), [['個股', 'stock'], ['族群', 'group']], v => v === race.mode, v => {
    race.mode = v;
    raceDraw();
  });
  const sp = box.querySelector('.rc-speed');
  chipGroup(sp, RACE_SPEEDS, v => v === race.speed, v => {
    race.speed = v;
    box.style.setProperty('--rc-dur', Math.min(v * 0.85, 450) + 'ms');
  });
  box.querySelector('.rc-play').addEventListener('click', () => (race.playing ? raceStop() : racePlay()));
  box.querySelector('.rc-slider').addEventListener('input', e => {
    raceStop();
    race.idx = Number(e.target.value);
    raceDraw();
  });
  box.querySelector('.rc-scope').addEventListener('change', e => {
    race.scope = e.target.value;
    raceClearList('s');
    raceDraw();
  });
}

// 盤中資料更新時（今天）跟著更新；看的是別天就不動
function renderRace() {
  const pane = document.querySelector('.subpanel[data-sub="live"]');
  if (!pane || pane.hidden) return;
  setupRace();
  const box = pane.querySelector('.lv-race');
  if (!configured()) { box.hidden = true; return; }
  if (race.date) return;
  box.querySelectorAll('.rc-day').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.date === st.date)));
  raceReset(true);
}

function render() {
  evalEvents();
  renderCard();
  renderPane();
  renderRace();
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
  btn.addEventListener('click', () => setTimeout(() => { renderPane(); renderRace(); if (!st.U) refresh(true); }, 0));
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
    liveClose('off');
    url.value = cfg.url;
    saveCfg(cfg);
    if (!configured()) { msg.textContent = '已清除：盤中功能關閉'; setupTab(); render(); return; }
    msg.textContent = '測試連線中…';
    try {
      const s = await api('/status');
      msg.textContent = '連線成功' + (s.latest ? '（最近資料 ' + s.latest.slice(4, 6) + '/' + s.latest.slice(6) + '）' : '（還沒有資料，開盤後會開始收）');
      setupTab();
      refresh(true);
      liveSync();
    } catch (e) {
      msg.textContent = '連線失敗：' + e.message;
    }
  });
}

// 每分鐘一次：盤中抓新快照；收盤後第一次回到頁面補到 13:33；其他時候只重畫（14:30 收起今日卡、更新時間標示）
function tick() {
  if (live.ws && Date.now() - live.seen > LIVE_DEAD_MS) liveClose('idle');   // 半開的連線
  liveSync();
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
  liveSync();
  // 對齊到每分鐘第 30 秒左右：Worker 的快照大約第 15 秒才寫好
  setTimeout(() => { tick(); setInterval(tick, POLL_MS); }, ((90 - new Date().getSeconds()) % 60) * 1000);
  document.addEventListener('visibilitychange', tick);
}

start();
