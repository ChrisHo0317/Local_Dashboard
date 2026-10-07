// node intraday/test_core.js：盤中族群計算與 Worker 的測試（不連網路，fetch 與 KV 都是假的）
import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as core from './core.js';
import worker, { collect, pushCheck, LiveHub } from './worker.js';
import * as mainModule from './worker.js';
import { dispatch, plan, NEWS_CRON, SLOT_CRON, SLOTS, PUSH_CRON } from './dispatch.js';

// ── 計算 ──
const U = {
  codes: ['A', 'B', 'C', 'D', 'E', 'F', 'G'],
  names: ['甲', '乙', '丙', '丁', '戊', '己', '庚'],
  mk: ['t', 't', 'o', 't', 'o', 't', 't'],
  avg: [10, 5, 3, 2, 1, 4, 6],
  groups: [['光通訊', '手動補充', [0, 1, 2, 3]], ['光通訊元件', '通信網路', [0, 1, 2]], ['水泥', '水泥', [4, 5, 6]]],
  yday: ['光通訊'],
  profile: Array.from({length: 271}, (_, m) => m / 270),
};
const ref = {y: [100, 100, 100, 100, 100, 100, 100], u: [110, 110, 110, 110, 110, 110, 110]};
const snap = {t: '10:30', p: [110, 106, 104, 101, 99, 100.5, 98], v: [1000, 800, 600, 100, 50, 300, 400]};

assert.equal(core.minuteOf('10:30'), 90);
assert.equal(core.hhmm(90), '1030');
assert.equal(core.misBatches({codes: Array.from({length: 250}, (_, i) => String(1000 + i)), mk: new Array(250).fill('o')}).length, 3);

const rows = core.groupStats(U, ref, snap);
assert.equal(rows[0].name.startsWith('光通訊'), true);
const top = rows.find(r => r.name === '光通訊');
assert.equal(top.n, 4); assert.equal(top.up, 4); assert.equal(top.strong, 3); assert.equal(top.limit, 1);
assert.equal(top.hot, true);
assert.equal(rows.find(r => r.name === '水泥').hot, false);
// 光通訊元件的成員全在光通訊裡：合併成一個，名字記在 alias
const kept = core.dedupe(U, rows, 10);
assert.equal(kept.filter(r => r.name.startsWith('光通訊')).length, 1);
assert.ok((kept[0].alias || []).length === 1);

// 成員：領漲與連動
const series = [];
const px = [100, 100, 100, 100, 99, 100, 98];
for (let k = 0; k <= 20; k++) {
  if (k) {
    const f = Math.sin(k * 1.7), g = Math.cos(k * 2.9), h = Math.sin(k * 0.9 + 1);
    const r = [0.004 + 0.006 * f, 0.003 + 0.005 * f + 0.001 * g, 0.002 + 0.004 * f, 0.003 * h, 0, 0, 0];
    for (let i = 0; i < px.length; i++) px[i] *= 1 + r[i];
  }
  series.push({t: '09:' + String(10 + k).padStart(2, '0'), m: 10 + k, p: px.slice(), v: [1, 1, 1, 1, 1, 1, 1]});
}
const mem = core.members(U, ref, series[series.length - 1], 0, series);
assert.equal(mem[0].code, 'A');                       // 漲最多排第一
assert.equal(mem.find(m => m.first).code, 'A');       // 最先到 +3%
assert.ok(mem.find(m => m.code === 'B').corr > 0.5);
assert.ok(core.groupLine(U, ref, series, 0).length === series.length);
// 族群走勢的最後一點和排行用的加權漲幅一致（有成員還沒成交時也一樣）
const half = {t: '10:30', p: snap.p.slice(), v: snap.v.slice()};
half.v[2] = null;
assert.ok(Math.abs(core.groupLine(U, ref, [half], 0)[0] - core.groupStats(U, ref, half).find(r => r.gi === 0).chg) < 1e-9);

// 推播去重：同名或成員重疊的族群算推過
assert.equal(core.seen(U, {gi: 1, name: '光通訊元件'}, ['光通訊']), true);
assert.equal(core.seen(U, {gi: 2, name: '水泥'}, ['光通訊']), false);

// fromMis：z 是 "-"（最近一次揭示沒有成交）時
const day0 = {d: '20261005', t: '10:30:05', y: '100', u: '110', w: '90'};
const mis = [
  {...day0, c: 'A', z: '-', b: '110.00_109.5_', a: '-', v: '120'},           // 漲停鎖住：只有買價
  {...day0, c: 'B', z: '106.00', b: '105.5_', a: '106_', v: '80', t: '10:30:00'},
  {...day0, c: 'C', z: '-', b: '-', a: '90.00_90.5_', v: '300'},             // 跌停鎖住：只有賣價＝跌停價
  {...day0, c: 'D', z: '-', b: '100.5_', a: '101_', v: '50'},                // 沒有上一分鐘：買賣價中間
  {...day0, c: 'E', z: '-', b: '-', a: '95_', v: '10'},                      // 冷門股只有賣價：不猜
  {...day0, c: 'F', z: '-', b: '99_', a: '99.5_', v: '40'},                  // 量沒變：沿用上一分鐘
  {...day0, c: 'G', z: '-', b: '97_', a: '97.5_', v: '60', d: '20261002'},   // 還沒換日的舊資料
];
const prevF = (p, v) => ({p: [null, null, null, null, null, p, null], v: [null, null, null, null, null, v, null]});
let q = core.fromMis(U, mis, '20261005', prevF(100, 40));
assert.deepEqual(q.p, [110, 106, 90, 100.75, null, 100, null]);
assert.equal(q.y[6], null);                            // 舊日期那列的昨收也不要
assert.equal(q.date, '20261005'); assert.equal(q.time, '10:30:05');
// 量變了但上一分鐘的價還在買賣價之間：沿用；跑出去了：取中間
assert.equal(core.fromMis(U, mis, '20261005', prevF(99.5, 30)).p[5], 99.5);
assert.equal(core.fromMis(U, mis, '20261005', prevF(101, 30)).p[5], 99.25);
assert.equal(core.fromMis(U, mis, '20261006').date, '');  // 行情不是今天的

// ── Worker ──
class KV {
  constructor() { this.m = new Map(); }
  async get(k) { return this.m.has(k) ? this.m.get(k) : null; }
  async put(k, v) { this.m.set(k, v); }
}
const env = {KV: new KV(), UNIVERSE_URL: 'https://example/u.json', ACCESS_CODE: 'secret', MIS_GAP_MS: '0'};
let misSkip = new Set();                               // 模擬某一批查詢失敗：這些代號不回
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.startsWith('https://example/u.json')) return new Response(JSON.stringify(U));
  if (url.startsWith('https://mis.twse.com.tw')) {
    const msg = U.codes.map((c, i) => ({c, z: String(snap.p[i]), v: String(snap.v[i]), y: '100', u: '110',
                                        o: '100', h: String(snap.p[i] + 1), l: '-',
                                        d: '20261005', t: '10:30:00'})).filter(r => !misSkip.has(r.c));
    return new Response('\n\n' + JSON.stringify({msgArray: msg}));
  }
  throw new Error('unexpected ' + url);
};
const now = {date: '20261005', minute: 89, dow: 1};
misSkip = new Set(['C']);
assert.equal(await collect(env, now), 'ok:6');
assert.ok(env.KV.m.has('s:20261005:1029') && env.KV.m.has('r:20261005') && env.KV.m.has('u:20261005'));
assert.equal(JSON.parse(env.KV.m.get('r:20261005')).y[2], null);
misSkip = new Set();
assert.equal(await collect(env, {...now, minute: 90}), 'ok:7');
assert.equal(JSON.parse(env.KV.m.get('r:20261005')).y[2], 100);   // 開盤那次沒查到的昨收，之後補上
assert.equal(await collect(env, {date: '20261005', minute: 300, dow: 1}), 'closed');
assert.equal(await collect(env, {date: '20261004', minute: 90, dow: 0}), 'closed');
assert.equal(await collect(env, {date: '20261006', minute: 90, dow: 2}), 'no-data');   // 行情日期不是今天

// 讀取：沒帶存取碼 401；帶了拿得到快照與名單
let r = await worker.fetch(new Request('https://w/day?date=20261005'), env);
assert.equal(r.status, 401);
r = await worker.fetch(new Request('https://w/day?date=20261005&u=1', {headers: {Authorization: 'Bearer secret'}}), env);
const d = await r.json();
assert.equal(d.date, '20261005'); assert.equal(d.snaps.length, 2); assert.equal(d.snaps[1].m, 90);
// 開高低只有最新一份帶（個股頁的盤中 K 棒用），其他的切掉
assert.ok(!('o' in d.snaps[0]) && !('h' in d.snaps[0]));
assert.deepEqual(d.snaps[1].h, snap.p.map(x => x + 1)); assert.equal(d.snaps[1].o[0], 100); assert.equal(d.snaps[1].l[0], null);
assert.deepEqual(d.universe.codes, U.codes); assert.equal(d.ref.y.length, 7);
assert.equal(r.headers.get('Access-Control-Allow-Origin'), '*');
// KV 出錯（例如額度用完）：回 503，一樣帶 CORS
r = await worker.fetch(new Request('https://w/status', {headers: {Authorization: 'Bearer secret'}}),
                       {...env, KV: {get: async () => { throw new Error('KV GET failed: 429'); }}});
assert.equal(r.status, 503); assert.equal(r.headers.get('Access-Control-Allow-Origin'), '*');
assert.match((await r.json()).error, /429/);

// 推播檢查（另一個 cron）：讀上一分鐘的快照；Bark 確認收到才算推過
env.KV.m.set('s:20261005:1031', JSON.stringify({t: '10:31', p: [110, 106, 105, 104, 99, 100.5, 98], v: snap.v}));
const pnow = {date: '20261005', minute: 92, dow: 1};
assert.equal(await pushCheck(env, pnow), 'no-bark');
const benv = {...env, BARK_KEY: 'bk', SITE_URL: 'https://site/'};
let barkCode = 400;
const barkCalls = [];
globalThis.fetch = async (url) => {
  barkCalls.push(String(url));
  return new Response(JSON.stringify({code: barkCode, message: 'x'}), {status: barkCode === 200 ? 200 : 400});
};
assert.equal(await pushCheck(benv, pnow), '光通訊:400');                 // 失敗：不算推過
assert.deepEqual(JSON.parse(env.KV.m.get('b:20261005')), []);
barkCode = 200;
assert.equal(await pushCheck(benv, pnow), '光通訊:200');
assert.deepEqual(JSON.parse(env.KV.m.get('b:20261005')), ['光通訊']);
assert.equal(await pushCheck(benv, pnow), 'none');                        // 同一族群一天一次
assert.equal(barkCalls.length, 2);
assert.ok(barkCalls[0].includes('icon=' + encodeURIComponent('https://site/icon-180.png')));   // 通知圖示＝網站 App 圖示
assert.equal(await pushCheck(benv, {...pnow, minute: 10}), 'closed');      // 09:15 以前不推
// 健康檢查：不用存取碼、不含價格
r = await worker.fetch(new Request('https://w/health'), env);
const hj = await r.json();
assert.equal(r.status, 200);
assert.ok('collected_today' in hj && 'latest' in hj && 'pushed_today' in hj && !('ref' in hj) && !('snaps' in hj));

// ── 準時觸發 GitHub 排程（dispatch.js）──
// wrangler.toml 的 crons 要和程式裡的字串一字不差，不然 scheduled 分不出是哪一個
const toml = fs.readFileSync(new URL('./wrangler.toml', import.meta.url), 'utf8');
const crons = JSON.parse(/^crons\s*=\s*(\[[\s\S]*?\])/m.exec(toml)[1]);
assert.ok(crons.includes(NEWS_CRON) && crons.includes(SLOT_CRON) && crons.includes(PUSH_CRON) && crons.length <= 5);
const at = (iso) => Date.parse(iso);
assert.deepEqual(plan(NEWS_CRON, at('2026-10-06T09:33:00Z')), [['news.yml', null]]);
assert.deepEqual(plan(SLOT_CRON, at('2026-10-06T09:30:00Z')), [['update.yml', {slot: '30 9 * * 1-5'}]]);   // 週二 17:30
assert.deepEqual(plan(SLOT_CRON, at('2026-10-06T09:40:00Z')), []);                                        // 不是時段
assert.deepEqual(plan(SLOT_CRON, at('2026-10-10T09:30:00Z')), []);                                        // 週六不跑盤後
assert.deepEqual(plan(SLOT_CRON, at('2026-10-10T01:00:00Z')), [['update.yml', {slot: '0 1 * * *'}]]);      // 09:00 每天
assert.deepEqual(plan('* 1-5 * * mon-fri', at('2026-10-06T01:00:00Z')), []);
// update.yml 的四個時段都有對應
const yml = fs.readFileSync(new URL('../.github/workflows/update.yml', import.meta.url), 'utf8');
for (const s of Object.values(SLOTS)) assert.ok(yml.includes('- cron: "' + s[0] + '"'), s[0]);

const calls = [];
const genv = {KV: new KV(), GH_REPO: 'me/repo', GH_TOKEN: 'tok', BARK_KEY: 'bk'};
let ghStatus = 204;
globalThis.fetch = async (url, opt = {}) => {
  calls.push([String(url), opt.body ? JSON.parse(opt.body) : null, opt.headers || {}]);
  return new Response(null, {status: String(url).startsWith('https://api.github.com') ? ghStatus : 200});
};
assert.equal(await dispatch({KV: new KV()}, NEWS_CRON, at('2026-10-06T09:33:00Z')), 'no-token');
assert.equal(calls.length, 0);
assert.equal(await dispatch(genv, SLOT_CRON, at('2026-10-06T09:30:00Z')), 'update.yml:204');
assert.equal(calls[0][0], 'https://api.github.com/repos/me/repo/actions/workflows/update.yml/dispatches');
assert.deepEqual(calls[0][1], {ref: 'main', inputs: {slot: '30 9 * * 1-5'}});
assert.equal(calls[0][2].Authorization, 'Bearer tok'); assert.ok(calls[0][2]['User-Agent']);
assert.equal(JSON.parse(genv.KV.m.get('g:last')).slot, '30 9 * * 1-5');
// 新聞成功不寫 KV；token 失效：記下來、一天只推播一次
genv.KV.m.delete('g:last');
assert.equal(await dispatch(genv, NEWS_CRON, at('2026-10-06T09:33:00Z')), 'news.yml:204');
assert.ok(!genv.KV.m.has('g:last'));
ghStatus = 401; calls.length = 0;
await dispatch(genv, NEWS_CRON, at('2026-10-06T09:43:00Z'));
await dispatch(genv, NEWS_CRON, at('2026-10-06T09:53:00Z'));
assert.equal(JSON.parse(genv.KV.m.get('g:last')).status, 401);
assert.equal(calls.filter(c => c[0].startsWith('https://api.day.app/')).length, 1);
// scheduled：依 cron 分派
ghStatus = 204; calls.length = 0;
const waits = [];
await worker.scheduled({cron: SLOT_CRON, scheduledTime: at('2026-10-06T00:10:00Z')}, genv, {waitUntil: p => waits.push(p)});
await Promise.all(waits);
assert.deepEqual(calls.map(c => c[1]), [{ref: 'main', inputs: {slot: '10 0 * * 1-5'}}]);
r = await worker.fetch(new Request('https://w/status', {headers: {Authorization: 'Bearer secret'}}), {...genv, ACCESS_CODE: 'secret'});
assert.equal((await r.json()).dispatch.slot, '10 0 * * 1-5');

// ── 即時轉播站（livehub.js）：訊息處理（WebSocket 連線本身要在 Cloudflare 上才有，這裡用假的） ──
class FakeWS {
  constructor() { this.sent = []; this.att = null; this.closed = null; }
  send(t) { this.sent.push(JSON.parse(t)); }
  close(code, why) { this.closed = [code, why]; }
  serializeAttachment(a) { this.att = a; }
  deserializeAttachment() { return this.att; }
}
const hubState = {socks: [], getWebSockets(tag) { return this.socks.filter(s => s.tag === tag).map(s => s.ws); }};
const join = (tag, ok) => { const ws = new FakeWS(); ws.att = {role: tag, ok}; hubState.socks.push({tag, ws}); return ws; };
const hubObj = new LiveHub(hubState, {ACCESS_CODE: 'secret', FEED_TOKEN: 'ft'});
const feedWs = join('feed', true), bad = join('view', false), v1 = join('view', false);
await hubObj.webSocketMessage(bad, JSON.stringify({auth: 'nope'}));
assert.equal(bad.closed[0], 4001);
await hubObj.webSocketMessage(v1, JSON.stringify({auth: 'secret'}));
assert.equal(v1.sent[0].type, 'idle');                                // 還沒有資料
await hubObj.webSocketMessage(feedWs, JSON.stringify({type: 'full', date: '20261007', t: '10:00:00', ts: 1,
                                                      q: {'2330': [2585, 1000, 2580, 2585, 25.8, 1]}}));
assert.equal(v1.sent[1].type, 'full'); assert.equal(bad.sent.length, 0);   // 沒過存取碼的收不到
await hubObj.webSocketMessage(feedWs, JSON.stringify({type: 'delta', date: '20261007', t: '10:00:05', ts: 2,
                                                      q: {'2317': [256, 900, 255.5, 256, 2.3, 2]}}));
const v2 = join('view', false);
await hubObj.webSocketMessage(v2, JSON.stringify({auth: 'secret'}));
assert.deepEqual(Object.keys(v2.sent[0].q).sort(), ['2317', '2330']);     // 後連上的拿到合併後的全部
assert.equal(v2.sent[0].t, '10:00:05');
await hubObj.webSocketMessage(feedWs, JSON.stringify({type: 'hb', date: '20261007', t: '10:00:10', ts: 3}));
assert.equal(hubObj.status().time, '10:00:10'); assert.equal(hubObj.status().viewers, 2);
assert.equal(hubObj.status().codes, 2); assert.equal(hubObj.status().feed_connected, true);
// 換日：delta 先記著（標 partial），等 full
await hubObj.webSocketMessage(feedWs, JSON.stringify({type: 'delta', date: '20261008', t: '09:00:05', ts: 4, q: {'2330': [2600, 10, 0, 0, 0.3, 1]}}));
assert.equal(hubObj.latest.partial, true); assert.equal(Object.keys(hubObj.latest.q).length, 1);
// 行情程式斷線：還有另一個行情程式連著就不通知；最後一個斷了才通知網站
const feed2 = join('feed', true);
const n0 = v1.sent.length;
await hubObj.webSocketClose(feedWs, 1006);
assert.equal(v1.sent.length, n0);
assert.equal(feedWs.closed[0], 1000);                                     // 有回覆關閉
hubState.socks = hubState.socks.filter(x => x.ws !== feedWs);
await hubObj.webSocketClose(feed2, 1000);
assert.equal(v1.sent[v1.sent.length - 1].type, 'idle');
// Worker 轉給轉播站：沒有 HUB 綁定時回 503
r = await worker.fetch(new Request('https://w/stream'), {...env});
assert.equal(r.status, 503);

// ── 族群強度時間軸：A 先強、後來換 E；A 和 A2 重疊算同一群 ──
{
  const n = 16;
  const U2 = {codes: Array.from({length: n}, (_, i) => 'S' + i), names: Array.from({length: n}, (_, i) => '股' + i),
              mk: new Array(n).fill('t'), avg: new Array(n).fill(1), profile: new Array(271).fill(1),
              groups: [['A', 'x', [0, 1, 2]], ['A2', 'x', [0, 1, 2, 3]], ['B', 'x', [4, 5, 6]], ['C', 'x', [7, 8, 9]],
                       ['D', 'x', [10, 11, 12]], ['E', 'x', [13, 14, 15]]]};
  const ref2 = {y: new Array(n).fill(100), u: new Array(n).fill(110)};
  const ser = [];
  for (let k = 0; k <= 20; k++) {
    const p = new Array(n).fill(100);
    const a = k < 10 ? 6 : Math.max(-3, 6 - (k - 10) * 1.5), e = Math.max(0, (k - 6) * 0.9);
    [0, 1, 2, 3].forEach(i => { p[i] = 100 + a; });
    [4, 5, 6].forEach(i => { p[i] = 101; }); [7, 8, 9].forEach(i => { p[i] = 102; }); [10, 11, 12].forEach(i => { p[i] = 100.5; });
    [13, 14, 15].forEach(i => { p[i] = 100 + e; });
    ser.push({t: core.hhmm(k * 3).replace(/^(..)/, '$1:'), m: k * 3, p, v: new Array(n).fill(100)});
  }
  const cache = new Map();
  const tl = core.timeline(U2, ref2, ser, {step: 3, rows: 15, cache});
  assert.equal(tl.n, 21); assert.equal(tl.t[1], '09:03');
  const names = tl.rows.map(r => r.name);
  assert.equal(names.filter(x => x === 'A' || x === 'A2').length, 1);    // 重疊的併成一列
  assert.equal(tl.rows.length, 5);
  assert.ok(names[0] === 'A' || names[0] === 'A2');                       // 先進前 3 的排上面
  assert.equal(tl.rows[tl.leader[0]].name, names[0]);                     // 開盤第 1 名是 A
  assert.equal(tl.rows[tl.leader[20]].name, 'E');                         // 最後換 E
  const notes = core.timelineNotes(tl);
  assert.ok(notes.leads.length >= 2);
  assert.ok(notes.weak.some(w => tl.rows[w.i].name === names[0]));        // A 轉弱有記到
  assert.ok(notes.marks[tl.rows.findIndex(r => r.name === 'E')].some(x => x === 1));   // E 有轉強標記
  // 快取：同一份資料再算一次，結果一樣（只重算最後一格）
  const again = core.timeline(U2, ref2, ser, {step: 3, rows: 15, cache});
  assert.deepEqual(again.rows.map(r => r.s), tl.rows.map(r => r.s));
}

// 主程式的具名匯出只能是函式或類別（Workers 會把它們當進入點；匯出字串會無法啟動）
for (const [k, v] of Object.entries(mainModule)) if (k !== 'default') assert.equal(typeof v, 'function', '主程式匯出了非函式：' + k);

console.log('intraday tests ok');
