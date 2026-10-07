// 盤中強勢族群的計算（純函式，Cloudflare Worker 與網站共用；網站版由 build_static 複製成 site/intraday_core.js）
//
// 名詞（和計畫書一致）：
//   U    今日名單 site/data/intraday_universe.json：codes、avg（20 日均成交值，億）、groups、yday、profile
//   ref  當天的參考資料：y 昨收（除權息日是參考價）、u 漲停價，順序同 U.codes
//   snap 某一分鐘的快照：{t: "10:32", p: [成交價], v: [累計成交量（張）]}，順序同 U.codes
//
// 族群強度＝漲幅、上漲比例、強勢成員數（漲 3% 以上）、量比 四項在所有族群裡的百分位平均；
// 至少 MIN_STRONG 檔強勢成員才算「強勢族群」。成員重疊太多的族群只留分數高的那個。

export const STRONG = 3;          // 強勢成員：漲幅 ≥ 3%
export const MIN_STRONG = 3;      // 強勢族群：至少 3 檔強勢成員
export const OVERLAP = 0.6;       // 兩個族群重疊 ≥ 60%（以小的那個為分母）視為同一群
export const BATCH = 100;         // 證交所即時行情一次最多查 100 檔

// "10:32" → 從 09:00 起算的分鐘數
export function minuteOf(t) {
  const m = /^(\d{1,2}):(\d{2})/.exec(t || '');
  return m ? (Number(m[1]) - 9) * 60 + Number(m[2]) : null;
}

export function hhmm(minute) {
  const h = 9 + Math.floor(minute / 60), m = minute % 60;
  return String(h).padStart(2, '0') + String(m).padStart(2, '0');
}

// 證交所 MIS 的查詢代號：t → tse_2330.tw、o → otc_4979.tw，每 BATCH 檔一組
export function misBatches(U) {
  const out = [];
  for (let i = 0; i < U.codes.length; i += BATCH) {
    out.push(U.codes.slice(i, i + BATCH).map((c, k) => (U.mk[i + k] === 'o' ? 'otc_' : 'tse_') + c + '.tw').join('|'));
  }
  return out;
}

function num(x) {
  const v = parseFloat(x);
  return Number.isFinite(v) && v > 0 ? v : null;
}

function first(x) { return typeof x === 'string' ? num(x.split('_')[0]) : null; }

// MIS 的 msgArray 轉成 價／量／昨收／漲停價／當天開高低（依 U.codes 的順序）。
// date 給了就只收那一天的列（開盤前還沒換日的舊資料不要）。
// z（成交價）是 "-" 時（最近一次揭示沒有成交），prev（上一分鐘的快照）有的話：
//   成交量沒變，或上一分鐘的價還在買賣價之間 → 沿用上一分鐘的價
//   否則買賣價都有取中間；只有買價（漲停鎖住）用買價；只有賣價時，跌停鎖住或有上一分鐘的價才用賣價
//   都沒有就沿用上一分鐘的價（還是沒有就留 null）
export function fromMis(U, rows, date, prev) {
  const at = new Map(U.codes.map((c, i) => [c, i]));
  const n = U.codes.length;
  const out = {p: new Array(n).fill(null), v: new Array(n).fill(null), y: new Array(n).fill(null),
               u: new Array(n).fill(null), o: new Array(n).fill(null), h: new Array(n).fill(null),
               l: new Array(n).fill(null), date: '', time: ''};
  for (const r of rows || []) {
    const i = at.get(r.c);
    if (i === undefined || (date && r.d !== date)) continue;
    const v = Number.isFinite(parseInt(r.v, 10)) ? parseInt(r.v, 10) : null;
    let p = num(r.z);
    if (p == null) {
      const p0 = prev && prev.p ? prev.p[i] : null, v0 = prev && prev.v ? prev.v[i] : null;
      const bid = first(r.b), ask = first(r.a), lo = num(r.w);
      if (p0 != null && ((v != null && v === v0) || (p0 >= (bid ?? -Infinity) && p0 <= (ask ?? Infinity)))) p = p0;
      else if (bid != null && ask != null) p = (bid + ask) / 2;
      else if (bid != null) p = bid;
      else if (ask != null && (p0 != null || (lo != null && ask <= lo))) p = ask;
      else p = p0;
    }
    out.p[i] = p;
    out.v[i] = v;
    out.y[i] = num(r.y);
    out.u[i] = num(r.u);
    out.o[i] = num(r.o);
    out.h[i] = num(r.h);
    out.l[i] = num(r.l);
    if (r.d && r.d > out.date) out.date = r.d;
    if (r.t && r.t > out.time) out.time = r.t;
  }
  return out;
}

function pct(p, y) { return p != null && y ? (p / y - 1) * 100 : null; }

// 成交值（億）：張 × 價 × 1000
function turnover(s, i) { return s.p[i] != null && s.v[i] != null ? s.v[i] * s.p[i] * 1000 / 1e8 : null; }

// 族群加權漲幅的權重：目前累積成交值；還沒成交的用 20 日均值 × 這個時間點的量能比例
function weight(U, s, i) {
  const frac = U.profile[Math.max(1, Math.min(270, minuteOf(s.t) ?? 270))] || 1;
  return turnover(s, i) || (U.avg[i] || 0) * frac || 0.01;
}

// 百分位（0～1），同分取平均
function ranks(values) {
  const idx = values.map((v, i) => [v, i]).filter(x => x[0] != null).sort((a, b) => a[0] - b[0]);
  const out = new Array(values.length).fill(null);
  const n = idx.length;
  for (let k = 0; k < n;) {
    let j = k;
    while (j + 1 < n && idx[j + 1][0] === idx[k][0]) j++;
    const r = n > 1 ? ((k + j) / 2) / (n - 1) : 1;
    for (let q = k; q <= j; q++) out[idx[q][1]] = r;
    k = j + 1;
  }
  return out;
}

// 某一分鐘所有族群的數字，依強度排序（含沒達門檻的，strong 欄位自己判斷）
export function groupStats(U, ref, snap) {
  const minute = Math.max(1, Math.min(270, minuteOf(snap.t) ?? 270));
  const frac = U.profile[minute] || 1;
  const chg = U.codes.map((_, i) => pct(snap.p[i], ref.y[i]));
  const tv = U.codes.map((_, i) => turnover(snap, i));
  const rows = [];
  U.groups.forEach((g, gi) => {
    let n = 0, up = 0, strong = 0, limit = 0, wsum = 0, csum = 0, tvs = 0, exp = 0;
    for (const i of g[2]) {
      if (chg[i] == null) continue;
      n++;
      if (chg[i] > 0) up++;
      if (chg[i] >= STRONG) strong++;
      if (ref.u[i] && snap.p[i] >= ref.u[i]) limit++;
      const w = weight(U, snap, i);
      wsum += w; csum += chg[i] * w;
      tvs += tv[i] || 0; exp += (U.avg[i] || 0) * frac;
    }
    if (n < 3) return;
    rows.push({gi, name: g[0], chain: g[1], n, up, strong, limit, chg: csum / wsum, breadth: up / n,
               vr: exp > 0 ? tvs / exp : null, tv: tvs});
  });
  const rc = ranks(rows.map(r => r.chg)), rb = ranks(rows.map(r => r.breadth)),
        rs = ranks(rows.map(r => r.strong)), rv = ranks(rows.map(r => r.vr));
  rows.forEach((r, k) => {
    const parts = [rc[k], rb[k], rs[k], rv[k]].filter(x => x != null);
    r.score = parts.reduce((a, b) => a + b, 0) / parts.length;
    r.hot = r.strong >= MIN_STRONG;
  });
  rows.sort((a, b) => (b.hot - a.hot) || (b.score - a.score));
  return rows;
}

// 兩個族群的成員重疊 ≥ OVERLAP（以小的那個為分母）
export function overlaps(U, a, b) {
  const A = U.groups[a][2], B = new Set(U.groups[b][2]);
  return A.filter(i => B.has(i)).length / Math.min(A.length, B.size) >= OVERLAP;
}

// 成員重疊太多的族群合併：只留排前面的，被併掉的名字記在 alias
export function dedupe(U, rows, limit = 30) {
  const kept = [];
  for (const r of rows) {
    if (kept.length >= limit) break;
    const dup = kept.find(k => overlaps(U, k.gi, r.gi));
    if (dup) { (dup.alias = dup.alias || []).push(r.name); continue; }
    kept.push(Object.assign({}, r));
  }
  return kept;
}

// 族群 r 是否和 names 裡的某個族群是同一群（同名或成員重疊）：推播一天只推一次用
export function seen(U, r, names) {
  const at = new Map(U.groups.map((g, i) => [g[0], i]));
  return names.some(n => n === r.name || (at.has(n) && overlaps(U, r.gi, at.get(n))));
}

// 一個族群的成員明細：漲幅、量比、是否漲停；series（依時間的快照）給了就算連動與領漲
export function members(U, ref, snap, gi, series) {
  const minute = Math.max(1, Math.min(270, minuteOf(snap.t) ?? 270));
  const frac = U.profile[minute] || 1;
  const idx = U.groups[gi][2];
  const out = idx.map(i => {
    const c = pct(snap.p[i], ref.y[i]);
    const tv = turnover(snap, i);
    return {i, code: U.codes[i], name: U.names[i], chg: c, price: snap.p[i],
            vr: tv != null && U.avg[i] ? tv / (U.avg[i] * frac) : null,
            limit: !!(ref.u[i] && snap.p[i] >= ref.u[i]), corr: null, lead: null};
  }).filter(m => m.chg != null);
  if (series && series.length) {
    // 領漲：最先漲到 +3% 的時間
    for (const m of out) {
      for (const s of series) {
        const c = pct(s.p[m.i], ref.y[m.i]);
        if (c != null && c >= STRONG) { m.lead = s.t; break; }
      }
    }
    // 連動：每一段的漲跌和族群其他成員平均的相關係數（至少 10 段）
    const rets = out.map(m => series.slice(1).map((s, k) => {
      const a = series[k].p[m.i], b = s.p[m.i];
      return a && b ? b / a - 1 : null;
    }));
    out.forEach((m, j) => {
      const peer = rets[0].map((_, k) => {
        let s = 0, n = 0;
        rets.forEach((r, q) => { if (q !== j && r[k] != null) { s += r[k]; n++; } });
        return n ? s / n : null;
      });
      m.corr = corr(rets[j], peer);
    });
    const leads = out.filter(m => m.lead).sort((a, b) => (a.lead < b.lead ? -1 : 1));
    if (leads.length) leads[0].first = true;
  }
  return out.sort((a, b) => b.chg - a.chg);
}

export function corr(a, b) {
  const xs = [], ys = [];
  for (let k = 0; k < a.length; k++) if (a[k] != null && b[k] != null) { xs.push(a[k]); ys.push(b[k]); }
  if (xs.length < 10) return null;
  const mx = xs.reduce((s, x) => s + x, 0) / xs.length, my = ys.reduce((s, y) => s + y, 0) / ys.length;
  let sxy = 0, sxx = 0, syy = 0;
  for (let k = 0; k < xs.length; k++) {
    const dx = xs[k] - mx, dy = ys[k] - my;
    sxy += dx * dy; sxx += dx * dx; syy += dy * dy;
  }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}

// 族群的盤中走勢（每個快照的加權漲幅）
export function groupLine(U, ref, series, gi) {
  return series.map(s => {
    let w = 0, c = 0;
    for (const i of U.groups[gi][2]) {
      const x = pct(s.p[i], ref.y[i]);
      if (x == null) continue;
      const wt = weight(U, s, i);
      w += wt; c += x * wt;
    }
    return w ? c / w : null;
  });
}

// 價格缺值（那一分鐘沒成交）沿用前一個快照，讓每一分鐘都有完整的價
export function fillForward(series) {
  for (let k = 1; k < series.length; k++) {
    const prev = series[k - 1], cur = series[k];
    for (let i = 0; i < cur.p.length; i++) {
      if (cur.p[i] == null) cur.p[i] = prev.p[i];
      if (cur.v[i] == null) cur.v[i] = prev.v[i];
    }
  }
  return series;
}

// 大盤概況：上漲／下跌家數（名單內）
export function breadth(U, ref, snap) {
  let up = 0, down = 0;
  U.codes.forEach((_, i) => {
    const c = pct(snap.p[i], ref.y[i]);
    if (c == null) return;
    if (c > 0) up++; else if (c < 0) down++;
  });
  return {up, down};
}


// ── 族群強度時間軸（網站的強勢股動畫與收盤存檔共用）──
// 每 step 分鐘一格；挑當天任何時候進過前 top 名的族群，成員重疊的併成一個（用全天強度最高的那個名字，整天固定），
// 最多 rows 個。每一格記：強度（0～100，和族群排行同一套分數）、名次（重疊的算一個）、加權漲幅、強勢檔數、
// 那一刻實際代表的族群名稱（重疊的另一個比較強時會是它）。
// cache（Map，選填）：同一格的快照沒變就沿用上次的排行（即時資料每 5 秒只重算最新一格）。
export function timeline(U, ref, series, opt = {}) {
  const step = opt.step || 3, rows = opt.rows || 15, top = opt.top || 5, cache = opt.cache;
  const last = series[series.length - 1];
  if (!last) return null;
  const nb = Math.floor(Math.min(270, last.m) / step) + 1;
  const frames = [];
  let j = 0;
  for (let k = 0; k < nb; k++) {
    const m = k * step;
    while (j + 1 < series.length && series[j + 1].m <= m) j++;
    frames.push(series[j].m <= m ? series[j] : null);
  }
  if (last.m > (nb - 1) * step) frames[nb - 1] = last;          // 最後一格用最新一份（含即時）
  const bins = frames.map((f, k) => {
    if (!f) return null;
    const key = f.t + '|' + f.m;
    const hit = cache && cache.get(k);
    if (hit && hit.key === key) return hit.rows;
    const r = dedupe(U, groupStats(U, ref, f), 30);
    if (cache) cache.set(k, {key, rows: r});
    return r;
  });
  // 代表的族群：依全天最高強度挑，和已經挑到的重疊就併進去
  const peak = new Map();
  bins.forEach(b => b && b.slice(0, top).forEach(r => peak.set(r.gi, Math.max(peak.get(r.gi) || 0, r.score))));
  const reps = [];
  for (const [gi] of [...peak].sort((a, b) => b[1] - a[1])) {
    if (reps.length >= rows) break;
    if (!reps.some(x => overlaps(U, x, gi))) reps.push(gi);
  }
  const same = new Map();                                         // 'rep|gi' → 是不是同一群
  const isSame = (rep, gi) => {
    if (rep === gi) return true;
    const k = rep + '|' + gi;
    if (!same.has(k)) same.set(k, overlaps(U, rep, gi));
    return same.get(k);
  };
  const out = reps.map(gi => ({gi, name: U.groups[gi][0], s: [], r: [], c: [], st: [], act: []}));
  bins.forEach((b, k) => {
    out.forEach(row => {
      const idx = b ? b.findIndex(x => isSame(row.gi, x.gi)) : -1;
      const x = idx >= 0 ? b[idx] : null;
      row.s[k] = x ? Math.round(x.score * 100) : null;
      row.r[k] = x ? idx + 1 : null;
      row.c[k] = x ? Math.round(x.chg * 100) / 100 : null;
      row.st[k] = x ? x.strong : null;
      row.act[k] = x && x.gi !== row.gi ? x.name : null;
    });
  });
  // 排列：第一次進前 3 名的時間（同時間比全天最高強度）；沒進過前 3 的放後面
  const firstTop = (row, n) => { const k = row.r.findIndex(r => r != null && r <= n); return k < 0 ? 1e9 : k; };
  out.forEach(row => { row.first = firstTop(row, 3); row.first5 = firstTop(row, top); row.peak = Math.max(...row.s.map(v => v || 0)); });
  out.sort((a, b) => (a.first - b.first) || (a.first5 - b.first5) || (b.peak - a.peak));
  const leader = bins.map((b, k) => out.findIndex(row => row.r[k] === 1));
  return {step, n: nb, t: Array.from({length: nb}, (_, k) => hhmm(k * step).replace(/^(..)/, '$1:')), rows: out, leader};
}

// 時間軸的文字摘要與轉強／轉弱：當第 1 名連續 2 格以上的時段（中間被打斷 2 格以內算同一段）；
// 當過第 1 名的族群之後第一次掉出前 3 的時間；每格和 15 分鐘前比（只看和前 5 名有關的變化，後段班的名次晃動不算）：
// 衝進前 3、或往前 3 名以上而且進到前 5，算轉強（1）；掉出前 3、或從前 5 往後 3 名以上，算轉弱（-1）。同一段只標第一格。
// leads 依當第 1 名的總格數排（給顏色用）。
export function timelineNotes(tl) {
  const back = Math.max(1, Math.round(15 / tl.step));
  const runs = [];
  tl.leader.forEach((i, k) => {
    const lastRun = runs[runs.length - 1];
    if (i < 0) return;
    if (lastRun && lastRun.i === i && lastRun.to === k - 1) lastRun.to = k;
    else runs.push({i, from: k, to: k});
  });
  const leads = [];
  runs.filter(x => x.to > x.from).forEach(x => {
    const prev = leads[leads.length - 1];
    if (prev && prev.i === x.i && x.from - prev.to <= 3) prev.to = x.to; else leads.push(Object.assign({}, x));
  });
  const total = new Map();
  tl.leader.forEach(i => { if (i >= 0) total.set(i, (total.get(i) || 0) + 1); });
  const byTime = [...total].sort((a, b) => b[1] - a[1]).map(x => x[0]);
  const weak = [];
  [...new Set(leads.map(x => x.i))].forEach(i => {
    const row = tl.rows[i];
    const firstEnd = leads.find(x => x.i === i).to;
    const k = row.r.findIndex((r, kk) => kk > firstEnd && (r == null || r > 3));
    if (k > 0) weak.push({i, k, r: row.r[k]});
  });
  const marks = tl.rows.map(row => {
    const m = [];
    for (let k = back; k < tl.n; k++) {
      const a = row.r[k - back], b = row.r[k];
      if (a == null || b == null) continue;
      if ((a > 3 && b <= 3) || (a - b >= 3 && b <= 5)) m[k] = 1;
      else if ((a <= 3 && b > 3) || (b - a >= 3 && a <= 5)) m[k] = -1;
    }
    for (let k = tl.n - 1; k > 0; k--) if (m[k] && m[k - 1] === m[k]) m[k] = 0;
    return m;
  });
  return {leads, weak, marks, byTime};
}
