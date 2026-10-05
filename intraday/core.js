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

// MIS 的 msgArray 轉成 價／量／昨收／漲停價（依 U.codes 的順序）。
// z（成交價）是 "-" 時（那幾秒沒成交）用最佳買價，再沒有就留 null，前端沿用上一分鐘的價。
export function fromMis(U, rows) {
  const at = new Map(U.codes.map((c, i) => [c, i]));
  const n = U.codes.length;
  const out = {p: new Array(n).fill(null), v: new Array(n).fill(null), y: new Array(n).fill(null),
               u: new Array(n).fill(null), date: '', time: ''};
  for (const r of rows || []) {
    const i = at.get(r.c);
    if (i === undefined) continue;
    const bid = typeof r.b === 'string' ? num(r.b.split('_')[0]) : null;
    out.p[i] = num(r.z) ?? bid;
    out.v[i] = Number.isFinite(parseInt(r.v, 10)) ? parseInt(r.v, 10) : null;
    out.y[i] = num(r.y);
    out.u[i] = num(r.u);
    if (r.d && r.d > out.date) out.date = r.d;
    if (r.t && r.t > out.time) out.time = r.t;
  }
  return out;
}

function pct(p, y) { return p != null && y ? (p / y - 1) * 100 : null; }

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
  const tv = U.codes.map((_, i) => (snap.p[i] != null && snap.v[i] != null ? snap.v[i] * snap.p[i] * 1000 / 1e8 : null));
  const rows = [];
  U.groups.forEach((g, gi) => {
    let n = 0, up = 0, strong = 0, limit = 0, wsum = 0, csum = 0, tvs = 0, exp = 0;
    for (const i of g[2]) {
      if (chg[i] == null) continue;
      n++;
      if (chg[i] > 0) up++;
      if (chg[i] >= STRONG) strong++;
      if (ref.u[i] && snap.p[i] >= ref.u[i]) limit++;
      const w = tv[i] || U.avg[i] * frac || 0.01;
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

// 成員重疊太多的族群合併：只留排前面的，被併掉的名字記在 alias
export function dedupe(U, rows, limit = 30) {
  const kept = [];
  for (const r of rows) {
    if (kept.length >= limit) break;
    const mine = new Set(U.groups[r.gi][2]);
    const dup = kept.find(k => {
      const other = U.groups[k.gi][2];
      const both = other.filter(i => mine.has(i)).length;
      return both / Math.min(other.length, mine.size) >= OVERLAP;
    });
    if (dup) { (dup.alias = dup.alias || []).push(r.name); continue; }
    kept.push(Object.assign({}, r));
  }
  return kept;
}

// 一個族群的成員明細：漲幅、量比、是否漲停；series（依時間的快照）給了就算連動與領漲
export function members(U, ref, snap, gi, series) {
  const minute = Math.max(1, Math.min(270, minuteOf(snap.t) ?? 270));
  const frac = U.profile[minute] || 1;
  const idx = U.groups[gi][2];
  const out = idx.map(i => {
    const c = pct(snap.p[i], ref.y[i]);
    const tv = snap.p[i] != null && snap.v[i] != null ? snap.v[i] * snap.p[i] * 1000 / 1e8 : null;
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
      const wt = s.v[i] != null ? s.v[i] * s.p[i] : U.avg[i];
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
