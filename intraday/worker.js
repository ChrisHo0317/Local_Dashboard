// 盤中強勢族群：Cloudflare Worker
//
// 排程（wrangler.toml 的 crons，UTC 01:00～05:59 週一到週五＝台北 09:00～13:59）每分鐘：
//   1. 讀今日名單（網站的 data/intraday_universe.json，每天第一次讀完存進 KV，整天用同一份）
//   2. 分批向證交所即時行情（MIS）查價量：每批 100 檔、間隔 1.2 秒
//   3. 存一份快照到 KV：s:{日期}:{HHMM}；昨收與漲停價存在 r:{日期}（第一次收到就存，之後缺的再補）
//   4. 每 5 分鐘（有設 BARK_KEY 時）算一次族群，新族群衝進前 3 名就推播
// 計算幾乎都在網站端做（Worker 免費方案每次只有 10 毫秒 CPU）。
//
// 讀取（網站用，要帶 Authorization: Bearer {ACCESS_CODE}）：
//   GET /status                     服務狀態
//   GET /day?from=HHMM&step=N&u=1   當天（或最近一個交易日）的快照；u=1 連今日名單一起給
//
// 即時行情只給帶存取碼的人看（證交所即時行情不能公開轉載）。

import { misBatches, fromMis, groupStats, dedupe, seen, hhmm, MIN_STRONG } from './core.js';

const MIS = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp';
const LAST_MINUTE = 273;          // 13:33：13:30 收盤集合競價的結果要幾十秒才出來
const TTL = 86400 * 5;            // 快照留 5 天
const PUSH_FROM = 15;             // 09:15 以前不推播（開盤前幾分鐘排名不穩）
const PUSH_MIN_STRONG = 4;
const WRITTEN_BY = 25;            // 每分鐘的快照大約第 10～15 秒才寫好；第 25 秒以前不讀這一分鐘

function taipei(ts = Date.now()) {
  const d = new Date(ts + 8 * 3600 * 1000);
  return {date: d.toISOString().slice(0, 10).replace(/-/g, ''), minute: (d.getUTCHours() - 9) * 60 + d.getUTCMinutes(),
          second: d.getUTCSeconds(), dow: d.getUTCDay()};
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function loadUniverse(env, date) {
  const key = 'u:' + date;
  let text = await env.KV.get(key);
  if (!text) {
    const r = await fetch(env.UNIVERSE_URL + '?d=' + date, {cf: {cacheTtl: 0}});
    if (!r.ok) throw new Error('今日名單讀取失敗 ' + r.status);
    text = await r.text();
    JSON.parse(text);                                // 壞掉就不要存
    await env.KV.put(key, text, {expirationTtl: TTL});
  }
  return text;
}

export async function collect(env, now = taipei()) {
  if (now.dow === 0 || now.dow === 6 || now.minute < 0 || now.minute > LAST_MINUTE) return 'closed';
  const uText = await loadUniverse(env, now.date);
  const U = JSON.parse(uText);
  const rows = [];
  const batches = misBatches(U);
  for (let k = 0; k < batches.length; k++) {
    if (k) await sleep(env.MIS_GAP_MS ? Number(env.MIS_GAP_MS) : 1200);
    try {
      const r = await fetch(MIS + '?ex_ch=' + batches[k] + '&json=1&delay=0&_=' + Date.now(), {
        headers: {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://mis.twse.com.tw/stock/index.jsp'}});
      if (!r.ok) continue;
      const j = JSON.parse(await r.text());
      if (Array.isArray(j.msgArray)) rows.push(...j.msgArray);
    } catch (e) { /* 單批失敗不影響其他批 */ }
  }
  const prev = now.minute > 0 ? await env.KV.get('s:' + now.date + ':' + hhmm(now.minute - 1)) : null;
  const q = fromMis(U, rows, now.date, prev ? JSON.parse(prev) : null);
  if (!q.date) return 'no-data';                                  // 休市或還沒開盤（行情不是今天的）
  // 昨收與漲停價：第一次收到就存；某一批那時沒查到的，之後查到再補
  const refKey = 'r:' + now.date;
  let ref = await env.KV.get(refKey);
  const R = ref ? JSON.parse(ref) : {y: q.y, u: q.u};
  let dirty = !ref;
  for (let i = 0; ref && i < q.y.length; i++) {
    if (R.y[i] == null && q.y[i] != null) { R.y[i] = q.y[i]; dirty = true; }
    if (R.u[i] == null && q.u[i] != null) { R.u[i] = q.u[i]; dirty = true; }
  }
  if (dirty) {
    ref = JSON.stringify(R);
    await env.KV.put(refKey, ref, {expirationTtl: TTL});
  }
  const snap = {t: (q.time || '').slice(0, 5), p: q.p.map(x => (x == null ? null : Math.round(x * 100) / 100)), v: q.v};
  await env.KV.put('s:' + now.date + ':' + hhmm(now.minute), JSON.stringify(snap), {expirationTtl: TTL});
  if (env.BARK_KEY && now.minute >= PUSH_FROM && now.minute % 5 === 0) {
    await push(env, U, R, snap, now.date);
  }
  return 'ok:' + rows.length;
}

// 新族群衝進前 3 名、而且至少 PUSH_MIN_STRONG 檔強勢成員：推一則。
// 同一族群一天只推一次；成員重疊的族群（例如「光通訊」和「光通訊元件」）算同一個
async function push(env, U, ref, snap, date) {
  const top = dedupe(U, groupStats(U, ref, snap), 3).filter(r => r.hot && r.strong >= Math.max(PUSH_MIN_STRONG, MIN_STRONG));
  if (!top.length) return;
  const key = 'b:' + date;
  const done = JSON.parse((await env.KV.get(key)) || '[]');
  const fresh = top.filter(r => !seen(U, r, done));
  if (!fresh.length) return;
  for (const r of fresh) {
    const title = '盤中強勢族群：' + r.name;
    const body = (r.chg >= 0 ? '+' : '') + r.chg.toFixed(1) + '%，' + r.up + '/' + r.n + ' 上漲、' +
                 r.strong + ' 檔漲 3% 以上' + (r.limit ? '、' + r.limit + ' 檔漲停' : '') + '（' + snap.t + '）';
    const url = 'https://api.day.app/' + encodeURIComponent(env.BARK_KEY) + '/' + encodeURIComponent(title) + '/' +
                encodeURIComponent(body) + '?group=' + encodeURIComponent('盤中族群') +
                (env.SITE_URL ? '&url=' + encodeURIComponent(env.SITE_URL) : '');
    try { await fetch(url); } catch (e) { /* 推播失敗不影響收資料 */ }
    done.push(r.name);
  }
  await env.KV.put(key, JSON.stringify(done), {expirationTtl: TTL});
}

function cors(env) {
  return {'Access-Control-Allow-Origin': env.ALLOW_ORIGIN || '*',
          'Access-Control-Allow-Headers': 'Authorization',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Max-Age': '86400'};
}

function reply(env, body, status = 200) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status, headers: Object.assign({'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}, cors(env))});
}

// 最近一個有資料的日期：今天沒有（還沒開盤、休市）就往前找，最多 7 天
async function latestDate(env, now) {
  for (let k = 0; k < 7; k++) {
    const d = taipei(Date.now() - k * 86400 * 1000).date;
    if (k === 0 && now.minute < 0) continue;
    if (await env.KV.get('r:' + d)) return d;
  }
  return null;
}

async function day(env, url) {
  const now = taipei();
  const date = url.searchParams.get('date') || await latestDate(env, now);
  if (!date) return reply(env, {date: null, snaps: []});
  const ref = await env.KV.get('r:' + date);
  if (!ref) return reply(env, {date, snaps: []});
  const step = Math.max(1, Math.min(30, Number(url.searchParams.get('step')) || 1));
  const fromText = url.searchParams.get('from') || '0900';
  const from = Math.max(0, (Number(fromText.slice(0, 2)) - 9) * 60 + Number(fromText.slice(2, 4)));
  // 今天：這一分鐘的快照還沒寫好就不讀（讀了 KV 會把「不存在」快取約 60 秒，網站反而更慢拿到）
  const cur = now.second < WRITTEN_BY ? now.minute - 1 : now.minute;
  const last = date === now.date ? Math.min(cur, LAST_MINUTE) : LAST_MINUTE;
  const want = [];
  for (let m = from; m <= last; m += step) want.push(m);
  // 最後幾分鐘一定要有（step 跳過的話補上），前端才拿得到最新一份
  for (let m = Math.max(from, last - 3); m <= last; m++) if (want.indexOf(m) < 0) want.push(m);
  want.sort((a, b) => a - b);
  const texts = await Promise.all(want.map(m => env.KV.get('s:' + date + ':' + hhmm(m))));
  const snaps = [];
  texts.forEach((t, k) => { if (t) snaps.push('{"m":' + want[k] + ',' + t.slice(1)); });
  let out = '{"date":"' + date + '","ref":' + ref + ',"snaps":[' + snaps.join(',') + ']';
  if (url.searchParams.get('u') === '1') {
    const u = await env.KV.get('u:' + date);
    if (u) out += ',"universe":' + u;
  }
  return reply(env, out + '}');
}

async function handle(request, env) {
  if (request.method === 'OPTIONS') return new Response(null, {status: 204, headers: cors(env)});
  const url = new URL(request.url);
  const auth = request.headers.get('Authorization') || '';
  if (!env.ACCESS_CODE || auth !== 'Bearer ' + env.ACCESS_CODE) return reply(env, {error: '存取碼不對'}, 401);
  if (url.pathname === '/status') {
    const now = taipei();
    return reply(env, {ok: true, date: now.date, minute: now.minute, latest: await latestDate(env, now)});
  }
  if (url.pathname === '/day') return day(env, url);
  // 手動觸發一次收集（測試用）：/collect
  if (url.pathname === '/collect') return reply(env, {result: await collect(env)});
  return reply(env, {error: 'not found'}, 404);
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(collect(env));
  },

  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (e) {
      // KV 額度用完等錯誤：一樣帶 CORS，網站才看得到原因
      return reply(env, {error: '盤中服務錯誤：' + String((e && e.message) || e)}, 503);
    }
  },
};
