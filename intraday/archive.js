// node intraday/archive.js：收盤後把當天的盤中族群排行存進 repo（update.yml 盤後那次跑）
//
// 讀盤中服務的 /day（每 3 分鐘一份快照），每一份算族群排行，寫 data/intraday/{日期}.json：
//   timeline  [{t, tv（名單內累積成交值，億）, top: [[族群, 漲幅, 強勢成員, 檔數]…前 5]}]
//   groups    每個進過前 3 名的族群：第一次進前 3 的時間、最好名次、收盤時的數字、領漲股
//   heat      族群強度時間軸（core.timeline，和網站同一套）：每 3 分鐘一格、最多 15 個族群的強度、名次、漲幅、強勢檔數，
//             網站的強勢股動畫用它看超過 5 天前的日子
// tv 給 intraday_universe.py 校正盤中量能曲線；groups 之後拿來回測「盤中強勢族群」隔天的表現。
// 沒有設定 INTRADAY_URL／INTRADAY_ACCESS_CODE、或服務沒有今天的資料，就什麼都不做。
import fs from 'node:fs';
import * as core from './core.js';

const url = process.env.INTRADAY_URL, code = process.env.INTRADAY_ACCESS_CODE;
if (!url || !code) {
  console.log('盤中存檔：沒有設定 INTRADAY_URL／INTRADAY_ACCESS_CODE，略過');
  process.exit(0);
}

let d;
try {
  const r = await fetch(url.replace(/\/+$/, '') + '/day?step=3&u=1', {headers: {Authorization: 'Bearer ' + code}});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  d = await r.json();
} catch (e) {
  console.log('盤中存檔：讀取失敗 ' + e.message);
  process.exit(0);
}
if (!d.universe || !d.snaps || d.snaps.length < 10) {
  console.log('盤中存檔：沒有足夠的資料（' + (d.snaps ? d.snaps.length : 0) + ' 份快照）');
  process.exit(0);
}

const date = d.date.slice(0, 4) + '-' + d.date.slice(4, 6) + '-' + d.date.slice(6);
const U = d.universe, ref = d.ref, series = core.fillForward(d.snaps);
const groups = {};
const timeline = series.map(s => {
  const rows = core.dedupe(U, core.groupStats(U, ref, s), 10);
  let tv = 0;
  U.codes.forEach((_, i) => { if (s.p[i] != null && s.v[i] != null) tv += s.v[i] * s.p[i] * 1000 / 1e8; });
  rows.slice(0, 3).forEach((r, k) => {
    if (!r.hot) return;
    const g = groups[r.name] || (groups[r.name] = {first: s.t, best: k + 1, gi: r.gi});
    g.best = Math.min(g.best, k + 1);
  });
  return {t: s.t, tv: Math.round(tv), top: rows.filter(r => r.hot).slice(0, 5)
    .map(r => [r.name, Math.round(r.chg * 100) / 100, r.strong, r.n])};
});
const last = series[series.length - 1];
const final = {};
core.groupStats(U, ref, last).forEach(r => { final[r.name] = r; });
const out = Object.entries(groups).map(([name, g]) => {
  const f = final[name] || {};
  const mem = core.members(U, ref, last, g.gi, series);
  const lead = mem.find(m => m.first);
  return {name, first: g.first, best: g.best, chg: f.chg != null ? Math.round(f.chg * 100) / 100 : null,
          up: f.up, n: f.n, strong: f.strong, limit: f.limit,
          lead: lead ? [lead.code, lead.name, lead.lead] : null,
          top: mem.slice(0, 5).map(m => [m.code, m.name, Math.round(m.chg * 100) / 100])};
}).sort((a, b) => a.best - b.best || (a.first < b.first ? -1 : 1));

const tl = core.timeline(U, ref, series, {step: 3, rows: 15});
const heat = tl && {step: tl.step, t: tl.t, leader: tl.leader,
                    rows: tl.rows.map(r => ({name: r.name, s: r.s, r: r.r, c: r.c, st: r.st}))};
fs.mkdirSync('data/intraday', {recursive: true});
fs.writeFileSync('data/intraday/' + date + '.json', JSON.stringify({date, timeline, groups: out, heat}));
console.log('盤中存檔：' + date + '，' + series.length + ' 份快照，' + out.length + ' 個族群進過前 3');
