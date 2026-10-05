// node intraday/test_core.js：盤中族群計算與 Worker 的測試（不連網路，fetch 與 KV 都是假的）
import assert from 'node:assert/strict';
import * as core from './core.js';
import worker, { collect } from './worker.js';

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

// fromMis：z 是 "-" 時用最佳買價
const q = core.fromMis(U, [{c: 'A', z: '-', b: '109.5_109_', v: '120', y: '100', u: '110', d: '20261005', t: '10:30:05'},
                           {c: 'B', z: '106.00', v: '80', y: '100', u: '110', d: '20261005', t: '10:30:00'}]);
assert.equal(q.p[0], 109.5); assert.equal(q.p[1], 106); assert.equal(q.p[2], null);
assert.equal(q.date, '20261005'); assert.equal(q.time, '10:30:05');

// ── Worker ──
class KV {
  constructor() { this.m = new Map(); }
  async get(k) { return this.m.has(k) ? this.m.get(k) : null; }
  async put(k, v) { this.m.set(k, v); }
}
const env = {KV: new KV(), UNIVERSE_URL: 'https://example/u.json', ACCESS_CODE: 'secret', MIS_GAP_MS: '0'};
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.startsWith('https://example/u.json')) return new Response(JSON.stringify(U));
  if (url.startsWith('https://mis.twse.com.tw')) {
    const msg = U.codes.map((c, i) => ({c, z: String(snap.p[i]), v: String(snap.v[i]), y: '100', u: '110',
                                        d: '20261005', t: '10:30:00'}));
    return new Response('\n\n' + JSON.stringify({msgArray: msg}));
  }
  throw new Error('unexpected ' + url);
};
const now = {date: '20261005', minute: 90, dow: 1};
assert.equal(await collect(env, now), 'ok:7');
assert.ok(env.KV.m.has('s:20261005:1030') && env.KV.m.has('r:20261005') && env.KV.m.has('u:20261005'));
assert.equal(await collect(env, {date: '20261005', minute: 300, dow: 1}), 'closed');
assert.equal(await collect(env, {date: '20261004', minute: 90, dow: 0}), 'closed');
assert.equal(await collect(env, {date: '20261006', minute: 90, dow: 2}), 'no-data');   // 行情日期不是今天

// 讀取：沒帶存取碼 401；帶了拿得到快照與名單
let r = await worker.fetch(new Request('https://w/day?date=20261005'), env);
assert.equal(r.status, 401);
r = await worker.fetch(new Request('https://w/day?date=20261005&u=1', {headers: {Authorization: 'Bearer secret'}}), env);
const d = await r.json();
assert.equal(d.date, '20261005'); assert.equal(d.snaps.length, 1); assert.equal(d.snaps[0].m, 90);
assert.deepEqual(d.universe.codes, U.codes); assert.equal(d.ref.y.length, 7);
assert.equal(r.headers.get('Access-Control-Allow-Origin'), '*');

console.log('intraday tests ok');
