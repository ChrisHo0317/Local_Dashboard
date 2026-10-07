// 盤中強勢族群：Cloudflare Worker
//
// 排程（wrangler.toml 的 crons，UTC 01:00～05:59 週一到週五＝台北 09:00～13:59）每分鐘：
//   1. 讀今日名單（網站的 data/intraday_universe.json，每天第一次讀完存進 KV，整天用同一份）
//   2. 分批向證交所即時行情（MIS）查價量：每批 100 檔、間隔 1.2 秒
//   3. 存一份快照到 KV：s:{日期}:{HHMM}；昨收與漲停價存在 r:{日期}（第一次收到就存，之後缺的再補）
// 推播（PUSH_CRON，每 5 分鐘；有設 BARK_KEY 時）另一個 cron 跑：讀上一分鐘的快照算族群，新族群衝進前 3 名就推。
// 和收資料分開，是因為免費方案每次只有 10 毫秒 CPU：收資料約 5 毫秒、算族群約 4 毫秒，放在一起太接近上限。
// 計算幾乎都在網站端做。另外兩個 cron 準時觸發 GitHub Actions 的資料排程（dispatch.js）。
//
// 讀取（網站用，要帶 Authorization: Bearer {ACCESS_CODE}）：
//   GET /status                     服務狀態
//   GET /health                     不用存取碼：今天有沒有在收、最新一份的時間、推播結果（不含任何價格）
//   GET /day?from=HHMM&step=N&u=1   當天（或最近一個交易日）的快照；u=1 連今日名單一起給
//   /feed、/stream                  即時轉播站（WebSocket，見 livehub.js；永豐金行情程式送進來、網站連上去收）
//
// 即時行情只給帶存取碼的人看（證交所即時行情不能公開轉載）。

import { misBatches, fromMis, groupStats, dedupe, seen, hhmm, MIN_STRONG } from './core.js';
// 主程式只能匯出處理函式與類別（Workers 會把每個具名匯出當成進入點，匯出字串會讓它無法啟動），所以常數放在 dispatch.js
import { dispatch, NEWS_CRON, SLOT_CRON, PUSH_CRON } from './dispatch.js';
import { LiveHub } from './livehub.js';

export { LiveHub };              // Durable Object 的類別要從主程式匯出

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
  const rows = [], http = [];
  const batches = misBatches(U);
  for (let k = 0; k < batches.length; k++) {
    if (k) await sleep(env.MIS_GAP_MS ? Number(env.MIS_GAP_MS) : 1200);
    try {
      const r = await fetch(MIS + '?ex_ch=' + batches[k] + '&json=1&delay=0&_=' + Date.now(), {
        headers: {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://mis.twse.com.tw/stock/index.jsp'}});
      http.push(r.status);
      if (!r.ok) continue;
      const j = JSON.parse(await r.text());
      if (Array.isArray(j.msgArray)) rows.push(...j.msgArray);
    } catch (e) {
      http.push('err');                                           // 單批失敗不影響其他批
    }
  }
  const prev = now.minute > 0 ? await env.KV.get('s:' + now.date + ':' + hhmm(now.minute - 1)) : null;
  const q = fromMis(U, rows, now.date, prev ? JSON.parse(prev) : null);
  if (!q.date) {
    // 休市、還沒開盤（行情不是今天的），或證交所擋掉：記下來給 /health 看（正常的交易日不會寫）
    await env.KV.put('h:' + now.date, JSON.stringify({at: hhmm(now.minute), rows: rows.length, http: http.join(',')}),
                     {expirationTtl: TTL});
    return 'no-data';
  }
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
  const r2 = a => a.map(x => (x == null ? null : Math.round(x * 100) / 100));
  // 開高低放最後：個股頁的盤中 K 棒用，/day 只有最新一份帶（其他的切掉，下載量和原本一樣）
  const snap = {t: (q.time || '').slice(0, 5), p: r2(q.p), v: q.v, o: r2(q.o), h: r2(q.h), l: r2(q.l)};
  await env.KV.put('s:' + now.date + ':' + hhmm(now.minute), JSON.stringify(snap), {expirationTtl: TTL});
  return 'ok:' + rows.length;
}

// 推播檢查（PUSH_CRON）：讀上一分鐘的快照算族群
export async function pushCheck(env, now = taipei()) {
  const m = now.minute - 1;
  if (!env.BARK_KEY) return 'no-bark';
  if (now.dow === 0 || now.dow === 6 || m < PUSH_FROM || m > LAST_MINUTE) return 'closed';
  const [u, ref, snap] = await Promise.all(['u:' + now.date, 'r:' + now.date, 's:' + now.date + ':' + hhmm(m)]
    .map(k => env.KV.get(k)));
  if (!u || !ref || !snap) return 'no-snap';
  return push(env, JSON.parse(u), JSON.parse(ref), JSON.parse(snap), now.date);
}

// 至少 PUSH_MIN_STRONG 檔強勢成員的族群裡，排名前 3 的（成員重疊的算一個）有新面孔：推一則。
// 先篩再合併：先合併的話，重疊的一群可能由成員較少、強勢不到 4 檔的那個代表，整群就推不出去。
// 同一族群一天只推一次；成員重疊的族群（例如「光通訊」和「光通訊元件」）算同一個
async function push(env, U, ref, snap, date) {
  const min = Math.max(PUSH_MIN_STRONG, MIN_STRONG);
  const top = dedupe(U, groupStats(U, ref, snap).filter(r => r.hot && r.strong >= min), 3);
  if (!top.length) return 'none';
  const key = 'b:' + date;
  const done = JSON.parse((await env.KV.get(key)) || '[]');
  const fresh = top.filter(r => !seen(U, r, done));
  if (!fresh.length) return 'none';
  const results = [];
  for (const r of fresh) {
    const title = '盤中強勢族群：' + r.name;
    const body = (r.chg >= 0 ? '+' : '') + r.chg.toFixed(1) + '%，' + r.up + '/' + r.n + ' 上漲、' +
                 r.strong + ' 檔漲 3% 以上' + (r.limit ? '、' + r.limit + ' 檔漲停' : '') + '（' + snap.t + '）';
    const url = 'https://api.day.app/' + encodeURIComponent(env.BARK_KEY) + '/' + encodeURIComponent(title) + '/' +
                encodeURIComponent(body) + '?group=' + encodeURIComponent('盤中族群') +
                (env.SITE_URL ? '&url=' + encodeURIComponent(env.SITE_URL) +
                                '&icon=' + encodeURIComponent(env.SITE_URL + 'icon-180.png') : '');   // 圖示＝網站 App 圖示
    let status = 0;
    try {
      const res = await fetch(url);
      const body = await res.json().catch(() => ({}));
      status = res.status === 200 && body.code === 200 ? 200 : (res.status || -2);
    } catch (e) {
      status = -1;
    }
    results.push(r.name + ':' + status);
    if (status === 200) done.push(r.name);          // Bark 確認收到才算推過；失敗的 5 分鐘後再試
  }
  await env.KV.put(key, JSON.stringify(done), {expirationTtl: TTL});
  await env.KV.put('p:' + date, JSON.stringify({at: snap.t, results}), {expirationTtl: TTL});
  return results.join(',');
}

// 不用存取碼的健康檢查：今天有沒有收到資料、最新一份的時間、推播結果；不含任何價格
async function health(env) {
  const now = taipei();
  const top = Math.min(now.minute - 1, LAST_MINUTE);         // 這一分鐘可能還沒寫好，不讀（免得 KV 快取「不存在」）
  let latest = null;
  for (let m = top; m >= Math.max(0, top - 4) && !latest; m--) {
    if (await env.KV.get('s:' + now.date + ':' + hhmm(m))) latest = hhmm(m);
  }
  const [ref, b, p, h] = await Promise.all(['r:', 'b:', 'p:', 'h:'].map(k => env.KV.get(k + now.date)));
  const colon = t => t && t.slice(0, 2) + ':' + t.slice(2);
  return {date: now.date, collected_today: !!ref, latest: colon(latest), bark: !!env.BARK_KEY, dispatch: !!env.GH_TOKEN,
          pushed_today: b ? JSON.parse(b) : [], last_push: p ? JSON.parse(p) : null, issue: h ? JSON.parse(h) : null};
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
  let lastK = -1;
  texts.forEach((t, k) => { if (t) lastK = k; });
  const slim = t => { const k = t.indexOf(',"o":'); return k < 0 ? t : t.slice(0, k) + '}'; };
  texts.forEach((t, k) => { if (t) snaps.push('{"m":' + want[k] + ',' + (k === lastK ? t : slim(t)).slice(1)); });
  let out = '{"date":"' + date + '","ref":' + ref + ',"snaps":[' + snaps.join(',') + ']';
  if (url.searchParams.get('u') === '1') {
    const u = await env.KV.get('u:' + date);
    if (u) out += ',"universe":' + u;
  }
  return reply(env, out + '}');
}

function hub(env) {
  return env.HUB ? env.HUB.get(env.HUB.idFromName('live')) : null;
}

// 轉播站狀態（不含價格）；還沒有轉播站或讀取失敗就是 null
async function liveStatus(env) {
  const h = hub(env);
  if (!h) return null;
  try { return await (await h.fetch('https://hub/status')).json(); } catch (e) { return null; }
}

async function handle(request, env) {
  if (request.method === 'OPTIONS') return new Response(null, {status: 204, headers: cors(env)});
  const url = new URL(request.url);
  // 即時轉播站：WebSocket，存取碼與行情程式的密鑰由轉播站自己檢查
  if (url.pathname === '/feed' || url.pathname === '/stream') {
    const h = hub(env);
    return h ? h.fetch(request) : reply(env, {error: '還沒有即時轉播站'}, 503);
  }
  if (url.pathname === '/health') return reply(env, Object.assign(await health(env), {live: await liveStatus(env)}));
  const auth = request.headers.get('Authorization') || '';
  if (!env.ACCESS_CODE || auth !== 'Bearer ' + env.ACCESS_CODE) return reply(env, {error: '存取碼不對'}, 401);
  if (url.pathname === '/status') {
    const now = taipei();
    const g = await env.KV.get('g:last');
    return reply(env, {ok: true, date: now.date, minute: now.minute, latest: await latestDate(env, now),
                       dispatch: g ? JSON.parse(g) : null});
  }
  if (url.pathname === '/day') return day(env, url);
  // 手動觸發一次收集（測試用）：/collect
  if (url.pathname === '/collect') return reply(env, {result: await collect(env)});
  return reply(env, {error: 'not found'}, 404);
}

export default {
  // 每個 cron 各自觸發一次：叫 GitHub 跑排程的兩個交給 dispatch、推播檢查交給 pushCheck，其餘（每分鐘那個）收盤中行情
  async scheduled(event, env, ctx) {
    if (event.cron === NEWS_CRON || event.cron === SLOT_CRON) ctx.waitUntil(dispatch(env, event.cron, event.scheduledTime));
    else if (event.cron === PUSH_CRON) ctx.waitUntil(pushCheck(env, taipei(event.scheduledTime)));
    else ctx.waitUntil(collect(env));
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
