// 情報中心：總覽、個股深度頁、選股
// 資料都是產生頁面時整理好的 JSON（data/overview.json、data/stock/{代號}.json、
// data/screen.json、data/stocks.json），要看的時候才下載，同一份只下載一次。
// 依賴 app.js 的全域：dark、MOBILE_Q、selectTab、setStockFocus、initTouch、syncSticky、VERSION。
(function () {
  'use strict';

  var EDIT_URL = 'https://github.com/ChrisHo0317/Local_Dashboard/edit/main/watchlist.csv';
  var WEEK = ['日', '一', '二', '三', '四', '五', '六'];
  var cache = {};

  function getJSON(path) {
    if (!cache[path]) {
      cache[path] = fetch(path + '?v=' + VERSION).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).catch(function (e) { delete cache[path]; throw e; });
    }
    return cache[path];
  }

  // 細產業（data/chains.json）：tags=[[名稱, 產業鏈, 上中下游, 手動, 檔數]]、codes={代號: [標籤序號（主要的排第一）]}
  var CHAINS = {tags: [], codes: {}};
  function loadChains() {
    return getJSON('data/chains.json').then(function (c) { CHAINS = c || CHAINS; }, function () {});
  }
  function chainTags(code) { return (CHAINS.codes[code] || []).map(function (i) { return CHAINS.tags[i]; }); }
  function inTag(code, i) { return (CHAINS.codes[code] || []).indexOf(i) >= 0; }
  // 細產業的下拉選項：依產業鏈分組，只列 counts 裡有的（counts：標籤序號 → 檔數）
  function tagOptions(sel, counts, prefix) {
    var byChain = {};
    Object.keys(counts).forEach(function (i) {
      var t = CHAINS.tags[i];
      if (!t) return;
      (byChain[t[1]] = byChain[t[1]] || []).push(Number(i));
    });
    Object.keys(byChain).sort(function (a, b) {
      return (a === '手動補充' ? -1 : b === '手動補充' ? 1 : a.localeCompare(b, 'zh-Hant'));
    }).forEach(function (chain) {
      var g = document.createElement('optgroup');
      g.label = '細產業：' + chain;
      byChain[chain].sort(function (a, b) { return counts[b] - counts[a]; }).forEach(function (i) {
        var o = el('option', null, CHAINS.tags[i][0] + '（' + counts[i] + ' 檔）');
        o.value = prefix + i;
        g.appendChild(o);
      });
      sel.appendChild(g);
    });
  }

  // 注意股、處置股（data/flags.json）：{代號: [注意|處置, 起, 迄, 說明]}
  var FLAGS = {};
  function loadFlags() {
    return getJSON('data/flags.json').then(function (f) { FLAGS = f || {}; }, function () {});
  }
  function flagBadge(code, kind) {
    var f = kind ? [kind] : FLAGS[code];
    if (!f || !f[0]) return null;
    var b = document.createElement('span');
    b.className = 'flag-badge' + (f[0] === '處置' ? ' is-disp' : '');
    b.textContent = f[0];
    if (f[3]) b.title = (f[0] === '處置' ? '處置期間 ' + f[1] + ' ～ ' + f[2] + '\n' : '') + f[3];
    return b;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // 手機上寬表格改成卡片：每一格依表頭加 data-label，窄螢幕時 CSS 用它當小標（.tbl-stack）
  function stackTable(t) {
    t.classList.add('tbl-stack');
    var heads = Array.prototype.slice.call(t.querySelectorAll('thead th')).map(function (th) {
      return th.textContent.replace(/[▲▼↑↓⇅]/g, '').trim();
    });
    Array.prototype.slice.call(t.querySelectorAll('tbody tr')).forEach(function (tr) {
      Array.prototype.slice.call(tr.children).forEach(function (td, i) {
        if (heads[i]) td.dataset.label = heads[i];
      });
    });
    return t;
  }

  function fmt(v, d) {
    if (v == null || v !== v) return '—';
    return Number(v).toLocaleString('zh-TW', {minimumFractionDigits: d || 0,
                                               maximumFractionDigits: d || 0});
  }

  function signed(v, d, suffix) {
    if (v == null || v !== v) return '—';
    return (v > 0 ? '+' : '') + fmt(v, d) + (suffix || '');
  }

  function dir(v) { return v > 0 ? 'up' : (v < 0 ? 'down' : ''); }

  function md(iso) {
    var p = String(iso).split('-');
    if (p.length < 3) return iso;
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    return (+p[1]) + '/' + (+p[2]) + '（' + WEEK[d.getDay()] + '）';
  }

  function palette() {
    return dark ? {up: '#ff6b6b', down: '#51cf66', grid: '#333849', fg: '#9aa0ac',
                   text: '#e8e8e8', blue: '#74c0fc', orange: '#ffa94d', purple: '#b197fc',
                   gray: '#868e96', hover: '#242839', band: 'rgba(116,192,252,'}
                : {up: '#e03131', down: '#1f9d55', grid: '#e9ecef', fg: '#6c757d',
                   text: '#212529', blue: '#1c7ed6', orange: '#e8590c', purple: '#7048e8',
                   gray: '#adb5bd', hover: '#ffffff', band: 'rgba(28,126,214,'};
  }

  function layout(extra) {
    var c = palette();
    var L = {
      margin: {l: 52, r: 14, t: 10, b: 34},
      showlegend: false,
      dragmode: false,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: {color: c.fg, size: 11},
      hovermode: 'x unified',
      hoverdistance: -1,
      hoverlabel: {bgcolor: c.hover, bordercolor: c.grid, font: {color: c.text, size: 12}},
      xaxis: {gridcolor: c.grid, linecolor: c.grid, zeroline: false, automargin: true},
      yaxis: {gridcolor: c.grid, linecolor: c.grid, zeroline: false, automargin: true}
    };
    return Object.assign(L, extra || {});
  }

  var CONFIG = {displayModeBar: false, responsive: true, scrollZoom: false, doubleClick: false};
  // 窄螢幕的日期軸只放 4 個刻度：完整日期（2026-09-14）放 7 個會疊在一起
  var TICKS = window.innerWidth < 600 ? 4 : 7;
  var COARSE = window.matchMedia('(pointer: coarse)').matches;

  function plot(id, traces, L, touchOpts) {
    var gd = document.getElementById(id);
    if (!gd) return null;
    Plotly.react(gd, traces, L, CONFIG);
    if (!gd._touchBound && typeof initTouch === 'function') {
      initTouch(gd, touchOpts);
      gd._touchBound = true;
    }
    return gd;
  }

  // ── 可縮放的時間序列圖（大盤、個股價量）─────────────────────
  // 電腦：拖曳框選放大（只放大時間軸）、滾輪縮放、雙擊還原。
  // 手機：雙指縮放、單指拖曳平移（initTouch）。
  // 縱軸一律鎖住，改由程式依「看得到的那一段」重算，線才不會被一年內的高低點壓扁。
  function zoomHint(box) {
    if (box) {
      box.textContent = COARSE ? '雙指可以放大縮小，單指左右拖曳看更早的資料。'
                               : '在圖上拖曳框選可以放大，滾輪可以縮放，雙擊還原。';
    }
  }

  function plotZoom(id, traces, L, n, rescale) {
    var gd = document.getElementById(id);
    if (!gd) return null;
    L.dragmode = COARSE ? false : 'zoom';
    Object.keys(L).forEach(function (k) {
      if (k.indexOf('yaxis') === 0) L[k].fixedrange = true;
    });
    Plotly.react(gd, traces, L, {displayModeBar: false, responsive: true,
                                 scrollZoom: !COARSE, doubleClick: COARSE ? false : 'reset'});
    gd._n = n;
    gd._rescale = rescale;
    if (!gd._touchBound && typeof initTouch === 'function') {
      initTouch(gd, {pan: true});
      gd._touchBound = true;
    }
    if (!gd._windowBound) {
      gd._windowBound = true;
      gd.on('plotly_relayout', function (ev) {
        if (gd._busy) return;
        if (!Object.keys(ev || {}).some(function (k) { return k.indexOf('xaxis') === 0; })) return;
        var r = gd._fullLayout.xaxis.range;
        var from = Math.max(0, Math.ceil(r[0])), to = Math.min(gd._n - 1, Math.floor(r[1]));
        if (to < from) return;
        gd._busy = true;
        var done = function () { gd._busy = false; };
        Plotly.relayout(gd, gd._rescale(from, to)).then(done, done);
      });
    }
    return gd;
  }

  // 一組序列在 [from, to] 之間的最小、最大值，上下各留一點空間
  function span(arrays, from, to, withZero) {
    var lo = withZero ? 0 : Infinity, hi = withZero ? 0 : -Infinity;
    arrays.forEach(function (a) {
      for (var i = from; i <= to && i < a.length; i++) {
        var v = a[i];
        if (v == null) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    });
    if (lo === Infinity) return null;
    var pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.02 || 1;
    return [lo - pad, hi + pad];
  }

  // 區間鈕：days＝最近幾個交易日，0＝全部
  function windowFor(n, days) {
    var from = days && n > days ? n - days : 0;
    return {from: from, to: n - 1};
  }

  function setWindow(gd, days) {
    if (!gd || !gd._fullLayout || !gd._n) return;
    var w = windowFor(gd._n, days);
    var up = gd._rescale(w.from, w.to);
    up['xaxis.range'] = [w.from - 0.5, w.to + 0.5];
    gd._busy = true;
    var done = function () { gd._busy = false; };
    Plotly.relayout(gd, up).then(done, done);
  }

  function bindChips(group, onPick) {
    var chips = Array.prototype.slice.call(group.querySelectorAll('.chip'));
    chips.forEach(function (c) {
      c.addEventListener('click', function () {
        chips.forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
        onPick(c);
      });
    });
  }

  function failMsg(box, text) {
    box.textContent = '';
    box.appendChild(el('p', 'cal-empty', text || '資料載入失敗，請確認網路連線後下拉重新整理。'));
  }

  function shown(node) { return node && node.offsetParent !== null; }

  function currentSub(panel) {
    var b = panel.querySelector('.subtab[aria-selected="true"]');
    return b ? b.dataset.sub : null;
  }

  // 子分頁或主分頁被點到之後才畫：容器還藏著的時候 Plotly 量不到寬度
  function onShow(panel, fn) {
    Array.prototype.slice.call(panel.querySelectorAll('.subtab')).forEach(function (b) {
      b.addEventListener('click', function () { setTimeout(function () { fn(b.dataset.sub); }, 0); });
    });
    var tab = document.querySelector('.tab[data-tab="' + panel.id.replace('panel-', '') + '"]');
    if (tab) {
      tab.addEventListener('click', function () {
        setTimeout(function () { fn(currentSub(panel)); }, 0);
      });
    }
  }

  function sparkSvg(values) {
    var v = (values || []).filter(function (x) { return x != null; });
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 72 22');
    svg.setAttribute('class', 'spark ' + (v.length > 1 && v[v.length - 1] >= v[0] ? 'up' : 'down'));
    svg.setAttribute('aria-hidden', 'true');
    if (v.length > 1) {
      var lo = Math.min.apply(null, v), hi = Math.max.apply(null, v), span = hi - lo || 1;
      var d = v.map(function (x, i) {
        return (i ? 'L' : 'M') + (i / (v.length - 1) * 70 + 1).toFixed(1) + ' ' +
               (21 - (x - lo) / span * 20).toFixed(1);
      }).join(' ');
      var path = document.createElementNS(ns, 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    }
    return svg;
  }

  // ── 跳到某一檔的深度頁（總覽、選股、推播網址都會用到）─────────
  var openStock = function () {};
  var openScreen = function () {};

  // 跳到某個子分頁（可能在別的底部分頁裡）：先切底部分頁，再點子分頁
  function goSub(sub) {
    var b = document.querySelector('.subtab[data-sub="' + sub + '"]');
    if (!b) return;
    var host = b.closest('.panel');
    if (host && host.hidden && typeof selectTab === 'function') selectTab(host.id.replace('panel-', ''), true);
    b.click();
    window.scrollTo(0, 0);
  }

  // ════════════════════ 今日、市場、選股、我的持股 ════════════════════
  // v0.3.063 起原本的「總覽」拆成三個底部分頁（我的持股在個股底下），程式共用這一段：
  // 各子分頁依 data-sub 找面板（data-sub 全站唯一），panel 指 document 讓既有的查詢照舊。
  (function () {
    var HOSTS = ['today', 'market', 'picks', 'stock'].map(function (id) {
      return document.getElementById('panel-' + id);
    }).filter(Boolean);
    if (!HOSTS.length) return;
    var panel = document;
    var flowSide = 'fi';

    function load() { return getJSON('data/overview.json'); }

    function kpis(box, list) {
      box.textContent = '';
      list.forEach(function (k) {
        var t = el('div', 'kpi');
        t.appendChild(el('span', 'kpi-l', k.label));
        t.appendChild(el('span', 'kpi-v', k.value));
        if (k.delta) t.appendChild(el('span', 'kpi-d ' + dir(k.dir), k.delta));
        if (k.note) t.appendChild(el('span', 'kpi-n', k.note));
        box.appendChild(t);
      });
    }

    function watch(box, d) {
      box.textContent = '';
      var rows = d.watch || [];
      if (!rows.length) {
        var p = el('p', 'ov-empty', '還沒有自選股。在 GitHub 上編輯 watchlist.csv，一列一檔。 ');
        var a = el('a', null, '編輯自選清單 ↗');
        a.href = d.edit_url || EDIT_URL; a.target = '_blank'; a.rel = 'noopener';
        p.appendChild(a);
        box.appendChild(p);
        return;
      }
      var wrap = el('div', 'ov-table-wrap');
      var t = el('table', 'ov-table');
      var h = el('tr');
      ['股票', '收盤', '漲跌', '量比', '外資', '投信'].forEach(function (x) { h.appendChild(el('th', null, x)); });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      rows.forEach(function (r) {
        var tr = el('tr', 'go');
        var c0 = el('td');
        c0.appendChild(el('span', 'ov-code', r.code));
        c0.appendChild(el('span', 'ov-name', r.name));
        if (r.ann) c0.appendChild(el('span', 'ov-flag', '重訊'));
        var fb = flagBadge(r.code, r.flag);
        if (fb) c0.appendChild(fb);
        tr.appendChild(c0);
        tr.appendChild(el('td', null, fmt(r.close, 2)));
        tr.appendChild(el('td', dir(r.chg), signed(r.chg, 2, '%')));
        tr.appendChild(el('td', null, r.volr == null ? '—' : fmt(r.volr, 1)));
        tr.appendChild(el('td', dir(r.fi), signed(r.fi, 0)));
        tr.appendChild(el('td', dir(r.tr), signed(r.tr, 0)));
        tr.addEventListener('click', function () { openStock(r.code); });
        tb.appendChild(tr);
      });
      t.appendChild(tb); wrap.appendChild(t); box.appendChild(wrap);
      var foot = el('p', 'ov-empty', '法人單位：張　·　量比＝今日量 ÷ 前 20 日均量　·　');
      var a2 = el('a', null, '編輯自選清單 ↗');
      a2.href = d.edit_url || EDIT_URL; a2.target = '_blank'; a2.rel = 'noopener';
      foot.appendChild(a2);
      box.appendChild(foot);
    }



    function news(box, list) {
      box.textContent = '';
      if (!list || !list.length) { box.appendChild(el('p', 'ov-empty', '目前沒有新聞。')); return; }
      var ul = el('ul', 'ov-list');
      list.forEach(function (n) {
        var li = el('li');
        var a = el('a', 'ov-news-t', n.title);
        a.href = n.url; a.target = '_blank'; a.rel = 'noopener';
        li.appendChild(a);
        var meta = (n.sources || []).join('、') + ((n.topics || []).length ? '　·　' + n.topics.join('、') : '');
        li.appendChild(el('span', 'ov-news-s', meta));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }

    // ── 決策首頁：摘要、市場溫度、主流族群、自選股警示、訊號績效、接下來兩天 ────
    function ckDigest(box, dg) {
      box.textContent = '';
      var pick = null;
      ['pre', 'post'].forEach(function (k) {
        if (dg && dg[k] && (!pick || dg[k].generated > pick.generated)) pick = dg[k];
      });
      if (!pick) {
        box.appendChild(el('p', 'sd-note', '摘要還沒產生：每天開盤前與盤後各整理一次。'));
        return;
      }
      var head = el('p', 'ck-label', (pick.mode === 'pre' ? '盤前摘要' : '盤後摘要') + '　' +
                    pick.generated.slice(5).replace('-', '/') + '　·　' +
                    (pick.method === 'claude' ? pick.model + ' 整理' : '依數字整理（尚未設定 Claude）'));
      box.appendChild(head);
      box.appendChild(el('h3', 'ck-headline', pick.headline));
      var ul = el('ul', 'ck-bullets');
      pick.bullets.slice(0, 3).forEach(function (b) { ul.appendChild(el('li', null, b)); });
      box.appendChild(ul);
      var extra = el('div', 'ck-extra');
      extra.hidden = true;
      if (pick.bullets.length > 3) {
        var ul2 = el('ul', 'ck-bullets');
        pick.bullets.slice(3).forEach(function (b) { ul2.appendChild(el('li', null, b)); });
        extra.appendChild(ul2);
      }
      if (pick.watch && pick.watch.length) {
        var w = el('ul', 'ck-bullets ck-watch');
        pick.watch.forEach(function (b) { w.appendChild(el('li', null, b)); });
        extra.appendChild(el('p', 'ck-sub', '自選股'));
        extra.appendChild(w);
      }
      (pick.risks || []).forEach(function (r) { extra.appendChild(el('p', 'ck-risk', r)); });
      if (extra.childNodes.length) {
        box.appendChild(extra);
        var more = el('button', 'ck-more', '看完整摘要 ›');
        more.type = 'button';
        more.addEventListener('click', function () {
          extra.hidden = !extra.hidden;
          more.textContent = extra.hidden ? '看完整摘要 ›' : '收起 ›';
        });
        box.appendChild(more);
      }
    }

    function ckTemp(pane, t) {
      var box = pane.querySelector('.ck-temp');
      if (!t || t.temp == null) { box.hidden = true; return; }
      box.hidden = false;
      var c = palette();
      var big = pane.querySelector('.ck-gauge');
      big.textContent = '';
      var top = el('div', 'ck-temp-top');
      top.appendChild(el('span', 'ck-temp-k', '市場溫度'));
      top.appendChild(el('b', 'ck-temp-v', fmt(t.temp, 0)));
      top.appendChild(el('span', 'ck-pill ' + (t.label === '偏多' ? 'is-hot' : t.label === '偏空' ? 'is-cold' : ''), t.label));
      top.appendChild(el('span', 'ck-temp-d', '5 日前 ' + fmt(t.temp_5d, 0)));
      big.appendChild(top);
      var bar = el('div', 'ck-bar');
      var mark = el('i');
      mark.style.left = Math.max(0, Math.min(100, t.temp)) + '%';
      bar.appendChild(mark);
      big.appendChild(bar);
      big.appendChild(el('p', 'ck-scale', '0 偏空　35　中性　65　偏多 100'));
      var tiles = pane.querySelector('.ck-tiles');
      tiles.textContent = '';
      [['上漲家數', fmt(t.adv_ratio, 0) + '%', t.adv + ' 漲 / ' + t.dec + ' 跌'],
       ['站上 20 日', fmt(t.above20, 0) + '%', '60 日線 ' + fmt(t.above60, 0) + '%'],
       ['新高／新低', t.nh + ' / ' + t.nl, '52 週，家數'],
       ['漲停／跌停', t.limit_up + ' / ' + t.limit_down, '漲跌 ≥ 9.5%']].forEach(function (x) {
        var b = el('div', 'ck-tile');
        b.appendChild(el('span', 'ck-tile-k', x[0]));
        b.appendChild(el('b', null, x[1]));
        b.appendChild(el('span', 'ck-tile-d', x[2]));
        tiles.appendChild(b);
      });
      var gd = document.getElementById('ov-temp');
      var tbtn = pane.querySelector('.ck-temp-more');
      if (tbtn && !tbtn.dataset.bound) {
        tbtn.dataset.bound = '1';
        tbtn.addEventListener('click', function () {
          gd.hidden = !gd.hidden;
          tbtn.setAttribute('aria-expanded', String(!gd.hidden));
          tbtn.textContent = gd.hidden ? '看近 60 日走勢 ›' : '收起走勢 ›';
          if (!gd.hidden) Plotly.Plots.resize(gd);
        });
      }
      var s = t.series || {t: [], temp: []};
      Plotly.react(gd, [{
        type: 'scatter', mode: 'lines', x: s.t.map(function (d) { return d.slice(5).replace('-', '/'); }),
        y: s.temp, line: {color: c.blue, width: 2}, fill: 'tozeroy', fillcolor: 'rgba(0,0,0,0)',
        hovertemplate: '%{x}　溫度 %{y:.0f}<extra></extra>'
      }], layout({
        margin: {l: 30, r: 8, t: 6, b: 24},
        xaxis: {type: 'category', nticks: 6, fixedrange: true, showgrid: false},
        yaxis: {range: [0, 100], tickvals: [35, 65], gridcolor: c.grid, fixedrange: true},
        shapes: [{type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 65, y1: 100, fillcolor: c.up,
                  opacity: 0.07, line: {width: 0}},
                 {type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 35, fillcolor: c.down,
                  opacity: 0.07, line: {width: 0}}]
      }), {displayModeBar: false, responsive: true});
    }

    function ckGroups(box, groups) {
      box.textContent = '';
      if (!groups || !groups.length) {
        box.appendChild(el('p', 'ov-empty', '還沒有族群連動的紀錄。'));
        return;
      }
      groups.forEach(function (g) {
        var b = el('button', 'ck-group');
        b.type = 'button';
        var h = el('span', 'ck-group-h');
        h.appendChild(el('b', null, g.group));
        h.appendChild(el('span', 'rec-n', '強勢股 ' + g.n + ' 檔'));
        b.appendChild(h);
        b.appendChild(el('span', 'ck-group-names', g.names.join('、')));
        if (g.why) b.appendChild(el('span', 'ck-group-why', g.why));
        b.addEventListener('click', function () {
          rec.theme = g.group;
          rec.query = '';
          rec.date = null;
          goSub('record');
        });
        box.appendChild(b);
      });
    }

    function ckAlerts(box, list) {
      box.textContent = '';
      if (!list || !list.length) {
        box.appendChild(el('p', 'ov-empty', '自選股這幾天沒有新事件。'));
        return;
      }
      var ul = el('ul', 'ck-list');
      list.slice(0, 6).forEach(function (a) {
        var li = el('li', a.urgent ? 'is-urgent' : null);
        var b = el('button', 'ck-link', a.text);
        b.type = 'button';
        b.addEventListener('click', function () { openStock(a.code); });
        li.appendChild(b);
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }



    // 熱門新聞分析（國際、台灣各前三個事件），點了到新聞分頁
    function ckHot(box, h) {
      box.textContent = '';
      if (!h || !h.generated) {
        box.appendChild(el('p', 'ov-empty', '熱門新聞分析還沒產生（每天 08:00、14:00、21:00）。'));
        return;
      }
      if (h.headline) box.appendChild(el('p', 'ck-hot-head', h.headline));
      [['國際', h.intl], ['台灣', h.tw]].forEach(function (x) {
        if (!x[1] || !x[1].length) return;
        var ul = el('ul', 'ck-list');
        x[1].forEach(function (t) {
          var li = el('li');
          li.appendChild(el('span', 'ck-when', x[0]));
          li.appendChild(el('span', 'ck-hot-t', t[0]));
          li.appendChild(el('span', 'hot-impact ' + (t[1] === '利多' ? 'up' : t[1] === '利空' ? 'down' : ''), t[1]));
          ul.appendChild(li);
        });
        box.appendChild(ul);
      });
      if (h.method !== 'claude') box.appendChild(el('p', 'sd-note', '尚未設定 Claude，只有熱門排行。'));
      var more = el('button', 'ck-more', '看熱門新聞分析 ›（' + h.label + ' ' + h.generated.slice(5) + '）');
      more.type = 'button';
      more.addEventListener('click', function () { goSub('hot'); });
      box.appendChild(more);
    }

    function ckGlobal(box, g) {
      box.textContent = '';
      if (!g || !g.key || !g.key.length) {
        box.appendChild(el('p', 'ov-empty', '還沒有國際市場資料。'));
        return;
      }
      var ul = el('ul', 'ck-list ck-gl');
      g.key.forEach(function (k) {
        var li = el('li');
        li.appendChild(el('span', 'ck-gl-n', k.name));
        li.appendChild(el('span', 'num', fmt(k.last, k.dec)));
        li.appendChild(el('span', 'num ck-gl-d ' + dir(k.d1),
                          k.unit === 'pt' ? signed(k.d1, 2) : signed(k.d1, 2, '%')));
        ul.appendChild(li);
      });
      box.appendChild(ul);
      var more = el('button', 'ck-more', '看國際市場 ›' + (g.asof ? '（' + g.asof.slice(5) + '）' : ''));
      more.type = 'button';
      more.addEventListener('click', function () { goSub('global'); });
      box.appendChild(more);
    }

    // 今天要注意：自選股警示＋自選股今日異動＋接下來 7 天的事件（原本分在四張卡）
    var EVENT_SHOW = 6;
    function tdEvents(box, list) {
      box.textContent = '';
      var all = list || [];
      if (!all.length) { box.appendChild(el('p', 'ov-empty', '接下來一週沒有高影響事件。')); return; }
      var ul = el('ul', 'ck-list td-ev');
      all.forEach(function (e, i) {
        var li = el('li', i >= EVENT_SHOW ? 'is-extra' : null);
        li.hidden = i >= EVENT_SHOW;
        li.appendChild(el('span', 'ck-when', md(e.date).replace(/（.）/, '') + (e.time ? ' ' + e.time : '')));
        var t = el('span', 'td-ev-t');
        t.appendChild(el('span', 'ov-kind' + (e.kind === '總經' ? '' : ' k-tw'), e.kind));
        t.appendChild(document.createTextNode(e.text));
        li.appendChild(t);
        ul.appendChild(li);
      });
      box.appendChild(ul);
      if (all.length > EVENT_SHOW) {
        var more = el('button', 'ck-more', '再看 ' + (all.length - EVENT_SHOW) + ' 筆 ›');
        more.type = 'button';
        more.addEventListener('click', function () {
          Array.prototype.slice.call(ul.querySelectorAll('.is-extra')).forEach(function (x) { x.hidden = false; });
          more.remove();
        });
        box.appendChild(more);
      }
    }

    // 市場數字：先放 6 個最常看的，其餘收在「更多」
    var KPI_MAIN = ['加權指數', '成交值', '外資買賣超', '投信買賣超', '台指期夜盤', '融資維持率（估）'];
    function tdKpis(pane, list) {
      var main = [], rest = [];
      (list || []).forEach(function (k) { (KPI_MAIN.indexOf(k.label) >= 0 ? main : rest).push(k); });
      main.sort(function (a, b) { return KPI_MAIN.indexOf(a.label) - KPI_MAIN.indexOf(b.label); });
      var box = pane.querySelector('.ov-kpis');
      kpis(box, main.concat(rest));
      var tiles = Array.prototype.slice.call(box.children);
      var btn = pane.querySelector('.td-kpi-more');
      function apply(open) {
        tiles.forEach(function (t, i) { t.hidden = !open && i >= main.length; });
        btn.textContent = open ? '收起 ›' : '更多 ' + rest.length + ' 項 ›';
        btn.setAttribute('aria-expanded', String(open));
      }
      btn.hidden = !rest.length;
      if (!btn.dataset.bound) {
        btn.dataset.bound = '1';
        btn.addEventListener('click', function () { apply(btn.getAttribute('aria-expanded') !== 'true'); });
      }
      apply(btn.getAttribute('aria-expanded') === 'true');
    }

    function tdNews(pane, d) {
      ckHot(pane.querySelector('.nw-hot'), d.hot);
      news(pane.querySelector('.nw-digest'), d.news);
      var hasHot = d.hot && ((d.hot.intl || []).length || (d.hot.tw || []).length);
      var chips = Array.prototype.slice.call(pane.querySelectorAll('.td-seg .chip'));
      function pick(which) {
        chips.forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.nw === which)); });
        pane.querySelector('.nw-hot').hidden = which !== 'hot';
        pane.querySelector('.nw-digest').hidden = which !== 'digest';
      }
      if (!pane.dataset.nwBound) {
        pane.dataset.nwBound = '1';
        chips.forEach(function (c) { c.addEventListener('click', function () { pick(c.dataset.nw); }); });
        pick(hasHot ? 'hot' : 'digest');
      }
    }

    function cockpit(pane, d) {
      ckDigest(pane.querySelector('.ck-digest'), d.digest);
      ckTemp(pane, d.temp);
      ckGroups(pane.querySelector('.ck-groups .ov-body'), d.groups);
      ckAlerts(pane.querySelector('.td-alerts'), d.alerts);
      watch(pane.querySelector('.td-watch'), d);
      tdEvents(pane.querySelector('.td-events'), d.events);
      ckGlobal(pane.querySelector('.ck-global .ov-body'), d.global);
      tdNews(pane, d);
      var q = d.quality || {};
      var qa = pane.querySelector('.ck-quality');
      qa.textContent = !q.status ? '' : q.status === 'ok'
        ? '資料狀態：正常' + (q.generated ? '（' + q.generated.slice(5) + ' 檢查）' : '')
        : '資料狀態：' + q.issues.join('；') + '（詳細在設定頁）';
      qa.className = 'ck-quality sd-note' + (q.status === 'error' ? ' is-error' : q.status === 'warn' ? ' is-warn' : '');
    }

    function today(pane, d) {
      pane.querySelector('.ov-asof').textContent = '資料日期 ' + md(d.asof) + ' 盤後';
      cockpit(pane, d);
      tdKpis(pane, d.kpi || []);
    }

    var marketDays = 130;

    function market(pane, d) {
      var m = d.market || {};
      var c = palette();
      var n = (m.t || []).length;
      if (!n) { failMsg(document.getElementById('ov-market'), '沒有大盤資料。'); return; }
      zoomHint(pane.querySelector('.zoom-hint'));
      function rescale(from, to) {
        var up = {};
        var a = span([m.taiex], from, to);
        if (a) up['yaxis.range'] = a;
        var b = span([m.fi, m.tr], from, to, true);
        if (b) up['yaxis2.range'] = b;
        if (hasMr) {
          // 下緣固定留到 135%，看得出離 160%／140% 警戒線還有多遠
          var r = span([m.mr], from, to);
          if (r) up['yaxis3.range'] = [Math.min(r[0], 135), Math.max(r[1], 165)];
        }
        return up;
      }
      var hasMr = (m.mr || []).some(function (v) { return v != null; });
      var w = windowFor(n, marketDays);
      var init = rescale(w.from, w.to);
      var L = layout({
        xaxis: {type: 'category', gridcolor: c.grid, linecolor: c.grid, nticks: TICKS,
                tickangle: 0, automargin: true, showspikes: true, spikemode: 'across',
                spikethickness: 1, spikedash: 'dot', spikecolor: c.gray,
                range: [w.from - 0.5, w.to + 0.5]},
        yaxis: {domain: hasMr ? [0.5, 1] : [0.42, 1], gridcolor: c.grid, tickformat: ',.0f', automargin: true,
                title: {text: ''}, range: init['yaxis.range']},
        yaxis2: {domain: hasMr ? [0.24, 0.43] : [0, 0.34], gridcolor: c.grid, zeroline: true, zerolinecolor: c.grid,
                 automargin: true, tickformat: ',.0f', range: init['yaxis2.range']},
        yaxis3: hasMr ? {domain: [0, 0.17], gridcolor: c.grid, automargin: true, ticksuffix: '%',
                         tickformat: '.0f', range: init['yaxis3.range']} : undefined,
        barmode: 'group',
        annotations: [
          {text: '加權指數', xref: 'paper', yref: 'paper', x: 0, y: 1, xanchor: 'left',
           yanchor: 'bottom', showarrow: false, font: {size: 11, color: c.fg}},
          {text: '法人買賣超（億元，估算）', xref: 'paper', yref: 'paper', x: 0, y: hasMr ? 0.44 : 0.35,
           xanchor: 'left', yanchor: 'bottom', showarrow: false, font: {size: 11, color: c.fg}}
        ].concat(hasMr ? [{text: '融資維持率（估，%）', xref: 'paper', yref: 'paper', x: 0, y: 0.18,
                           xanchor: 'left', yanchor: 'bottom', showarrow: false,
                           font: {size: 11, color: c.fg}}] : []),
        shapes: hasMr ? [140, 160].map(function (v) {
          return {type: 'line', xref: 'paper', yref: 'y3', x0: 0, x1: 1, y0: v, y1: v,
                  line: {color: v === 140 ? c.down : c.gray, width: 1, dash: 'dot'}};
        }) : [],
        margin: {l: 56, r: 14, t: 20, b: 34}
      });
      plotZoom('ov-market', [
        {type: 'scatter', mode: 'lines', x: m.t, y: m.taiex, name: '加權指數',
         line: {color: c.blue, width: 2}, hovertemplate: '%{y:,.2f}<extra>加權指數</extra>'},
        {type: 'bar', x: m.t, y: m.fi, name: '外資', yaxis: 'y2', marker: {color: c.orange},
         hovertemplate: '%{y:+,.1f} 億<extra>外資</extra>'},
        {type: 'bar', x: m.t, y: m.tr, name: '投信', yaxis: 'y2', marker: {color: c.purple},
         hovertemplate: '%{y:+,.1f} 億<extra>投信</extra>'}
      ].concat(hasMr ? [{type: 'scatter', mode: 'lines+markers', x: m.t, y: m.mr, name: '融資維持率',
                         yaxis: 'y3', connectgaps: false, line: {color: c.blue, width: 2},
                         marker: {size: 4}, hovertemplate: '%{y:.1f}%<extra>融資維持率（估）</extra>'}] : []),
      L, n, rescale);
    }

    // ── 國際：美股、期貨、亞股、供應鏈龍頭、原物料、匯率、美債（data/global.json）──
    var gl = {data: null, pick: '標普500', days: 130, cmp: false};

    function glChg(r, v) { return r.unit === 'pt' ? signed(v, 2) : signed(v, 2, '%'); }

    function glChart(pane) {
      var d = gl.data, s = d.series[gl.pick];
      var gd = document.getElementById('ov-global');
      if (!s || !s[0].length) { failMsg(gd, '沒有資料。'); return; }
      var row = null;
      d.groups.forEach(function (g) { g.items.forEach(function (r) { if (r.name === gl.pick) row = r; }); });
      var dec = row ? row.dec : 2, c = palette();
      var x = s[0], y = s[1], n = x.length;
      var head = pane.querySelector('.gl-head');
      head.textContent = '';
      head.appendChild(el('b', null, gl.pick + '　'));
      if (row) {
        head.appendChild(document.createTextNode(fmt(row.last, dec) + '　'));
        head.appendChild(el('span', dir(row.d1), glChg(row, row.d1)));
        head.appendChild(document.createTextNode('　' + md(row.date)));
      }
      var traces = [{type: 'scatter', mode: 'lines', x: x, y: y, name: gl.pick,
                     line: {color: c.blue, width: 2},
                     hovertemplate: '%{y:,.' + dec + 'f}<extra>' + gl.pick + '</extra>'}];
      var tw = null;
      if (gl.cmp && gl.pick !== '加權指數' && d.series['加權指數']) {
        // 對齊到這個項目的日期：用那天以前最後一個台股收盤
        var ts = d.series['加權指數'], j = 0, last = null;
        tw = x.map(function (day) {
          while (j < ts[0].length && ts[0][j] <= day) { last = ts[1][j]; j++; }
          return last;
        });
        traces.push({type: 'scatter', mode: 'lines', x: x, y: tw, name: '加權指數', yaxis: 'y2',
                     line: {color: c.gray, width: 1.5, dash: 'dot'},
                     hovertemplate: '%{y:,.0f}<extra>加權指數</extra>'});
      }
      function rescale(from, to) {
        var up = {};
        var a = span([y], from, to);
        if (a) up['yaxis.range'] = a;
        if (tw) {
          var b = span([tw], from, to);
          if (b) up['yaxis2.range'] = b;
        }
        return up;
      }
      var w = windowFor(n, gl.days);
      var init = rescale(w.from, w.to);
      var L = layout({
        xaxis: {type: 'category', gridcolor: c.grid, linecolor: c.grid, nticks: TICKS, tickangle: 0,
                automargin: true, showspikes: true, spikemode: 'across', spikethickness: 1,
                spikedash: 'dot', spikecolor: c.gray, range: [w.from - 0.5, w.to + 0.5]},
        yaxis: {gridcolor: c.grid, automargin: true, tickformat: ',.' + Math.min(dec, 2) + 'f',
                range: init['yaxis.range']},
        margin: {l: 56, r: tw ? 56 : 14, t: 10, b: 34},
        showlegend: !!tw, legend: {orientation: 'h', y: 1.12, x: 0, font: {size: 11}}
      });
      if (tw) {
        L.yaxis2 = {overlaying: 'y', side: 'right', showgrid: false, automargin: true,
                    tickformat: ',.0f', range: init['yaxis2.range']};
      }
      plotZoom('ov-global', traces, L, n, rescale);
    }

    function glTables(pane) {
      var box = pane.querySelector('.gl-groups');
      box.textContent = '';
      gl.data.groups.forEach(function (g) {
        box.appendChild(el('h3', 'sd-h', g.name));
        if (g.note) box.appendChild(el('p', 'sd-note', g.note));
        // 這一組多數項目的日期；不一樣的（休市）才在名稱下標出來
        var cnt = {}, common = null;
        g.items.forEach(function (r) { cnt[r.date] = (cnt[r.date] || 0) + 1; });
        Object.keys(cnt).forEach(function (k) { if (!common || cnt[k] > cnt[common]) common = k; });
        var t = el('table', 'ov-table scr-table gl-tbl');
        var h = el('tr');
        [['名稱'], ['最新'], ['日'], ['週'], ['月'], ['季', 'gl-wide'], ['今年', 'gl-wide'],
         ['連動'], ['近 60 日']].forEach(function (x) { h.appendChild(el('th', x[1] || null, x[0])); });
        var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
        var tb = el('tbody');
        g.items.forEach(function (r) {
          var tr = el('tr', 'go' + (r.name === gl.pick ? ' is-picked' : ''));
          tr.dataset.name = r.name;
          var c0 = el('td');
          c0.appendChild(el('span', 'ov-code', r.name));
          if (r.date !== common) c0.appendChild(el('span', 'scr-reason', md(r.date)));
          tr.appendChild(c0);
          tr.appendChild(el('td', null, fmt(r.last, r.dec)));
          [['d1'], ['d5'], ['d20'], ['d60', 'gl-wide'], ['ytd', 'gl-wide']].forEach(function (k) {
            tr.appendChild(el('td', (dir(r[k[0]]) + ' ' + (k[1] || '')).trim() || null, glChg(r, r[k[0]])));
          });
          var cc = el('td', 'gl-corr');
          if (r.corr != null) {
            cc.appendChild(el('b', Math.abs(r.corr) >= 0.5 ? 'gl-strong' : null, signed(r.corr, 2)));
            cc.appendChild(el('span', 'gl-mode', r.mode === 'lead' ? '隔日' : '同日'));
          } else {
            cc.textContent = '—';
          }
          tr.appendChild(cc);
          var sp = el('td');
          sp.appendChild(sparkSvg(r.spark));
          tr.appendChild(sp);
          tr.addEventListener('click', function () {
            gl.pick = r.name;
            Array.prototype.slice.call(box.querySelectorAll('tr.is-picked')).forEach(function (x) {
              x.classList.remove('is-picked');
            });
            tr.classList.add('is-picked');
            glChart(pane);
            var gd = document.getElementById('ov-global');
            if (gd.getBoundingClientRect().top < 0) gd.scrollIntoView({behavior: 'smooth', block: 'center'});
          });
          tb.appendChild(tr);
        });
        t.appendChild(tb); stackTable(t);
        var wrap = el('div', 'ov-table-wrap');
        wrap.appendChild(t);
        box.appendChild(wrap);
      });
    }

    function globalMkt(pane) {
      return getJSON('data/global.json').then(function (d) {
        gl.data = d;
        pane.querySelector('.ov-asof').textContent = d.asof ? '資料更新到 ' + md(d.asof) : '';
        zoomHint(pane.querySelector('.zoom-hint'));
        if (!d.groups || !d.groups.length) {
          failMsg(pane.querySelector('.gl-groups'), '還沒有國際市場資料。');
          return;
        }
        if (!d.series[gl.pick]) gl.pick = d.groups[0].items[0].name;
        if (!pane.dataset.bound) {
          pane.dataset.bound = '1';
          bindChips(pane.querySelector('.gl-range'), function (chip) {
            gl.days = Number(chip.dataset.days);
            setWindow(document.getElementById('ov-global'), gl.days);
          });
          var cmp = pane.querySelector('.gl-cmp');
          cmp.addEventListener('click', function () {
            gl.cmp = !gl.cmp;
            cmp.setAttribute('aria-pressed', String(gl.cmp));
            glChart(pane);
          });
        }
        glTables(pane);
        glChart(pane);
      });
    }

    // ── 走勢：DRAM、美債、黃金、BTC、美股、匯率（原本底部的「走勢圖」分頁）──
    // 卡片用 data/trend.json；完整圖是 app.js 的 CHARTS（data/charts/{key}.json），用 activateCharts 畫
    var tr = {pick: null};

    function trShow(pane) {
      Array.prototype.slice.call(pane.querySelectorAll('.tr-card')).forEach(function (b) {
        b.classList.toggle('is-picked', b.dataset.key === tr.pick);
      });
      var box = null;
      Array.prototype.slice.call(pane.querySelectorAll('.tr-chart')).forEach(function (x) {
        x.hidden = x.dataset.key !== tr.pick;
        if (!x.hidden) box = x;
      });
      pane.querySelector('.tr-title').textContent = box ? box.dataset.title : '';
      pane.querySelector('.tr-meta').innerHTML = box ? box.dataset.meta : '';   // meta 含 <br>，產生頁面時已跳脫
      if (box && typeof activateCharts === 'function') activateCharts(box);
    }

    function trend(pane) {
      return getJSON('data/trend.json').then(function (cards) {
        var wrap = pane.querySelector('.tr-cards');
        if (!tr.pick && cards.length) tr.pick = cards[0].id;
        wrap.textContent = '';
        cards.forEach(function (c) {
          var b = el('button', 'tr-card mc-card');
          b.type = 'button';
          b.dataset.key = c.id;
          var h = el('span', 'tr-head');
          h.appendChild(el('span', 'tr-tab', c.tab));
          if (c.date) h.appendChild(el('span', 'mc-sub', md(c.date)));
          b.appendChild(h);
          c.rows.forEach(function (r) {
            var row = el('span', 'tr-row');
            row.appendChild(el('span', 'tr-name', r.name));
            row.appendChild(el('span', 'tr-last num', fmt(r.last, r.dec) + (c.id === 'bond' ? '%' : '')));
            var ch = r.unit === 'pt' ? signed(r.d1, 2) : signed(r.d1, 2, '%');
            row.appendChild(el('span', 'tr-chg num ' + dir(r.d1), ch));
            var m20 = r.unit === 'pt' ? signed(r.d20, 2) : signed(r.d20, 1, '%');
            row.appendChild(el('span', 'tr-chg tr-m num ' + dir(r.d20), m20));
            b.appendChild(row);
          });
          if (c.more) b.appendChild(el('span', 'mc-sub', '另有 ' + c.more + ' 個' + (c.id === 'dram' ? '型號' : '項目')));
          b.appendChild(sparkSvg(c.spark));
          b.addEventListener('click', function () {
            tr.pick = c.id;
            trShow(pane);
            var t = pane.querySelector('.tr-title');
            if (t.getBoundingClientRect().top > window.innerHeight * 0.6) t.scrollIntoView({behavior: 'smooth', block: 'start'});
          });
          wrap.appendChild(b);
        });
        trShow(pane);
      });
    }

    // ── 總經：台灣、美國的經濟數據卡片＋走勢＋經濟日曆公布值（data/macro.json）──
    var mc = {data: null, pick: 'tw_signal'};
    var LIGHT_COLOR = {'紅燈': '#e03131', '黃紅燈': '#f08c00', '綠燈': '#2f9e44',
                       '黃藍燈': '#66a80f', '藍燈': '#1c7ed6'};

    function mcUnit(c) { return c.unit === '%' ? '%' : ''; }

    function mcChart(pane) {
      var c = null;
      mc.data.cards.forEach(function (x) { if (x.id === mc.pick) c = x; });
      if (!c) return;
      var p = palette(), gd = document.getElementById('ov-macro');
      pane.querySelector('.mc-chart-h').textContent = c.name + '　' + fmt(c.last, c.dec) + mcUnit(c) +
        (c.light ? ' ' + c.light : '') + '（' + c.period + '）';
      pane.querySelector('.mc-chart-note').textContent = c.note || '';
      var hv = '%{x|%Y-%m}　%{y:,.' + c.dec + 'f}' + mcUnit(c);
      var traces, shapes = [];
      if (c.id === 'tw_signal') {
        traces = [{type: 'bar', x: c.t, y: c.v, name: c.name,
                   marker: {color: c.lights.map(function (l) { return LIGHT_COLOR[l] || p.gray; })},
                   customdata: c.lights, hovertemplate: '%{x|%Y-%m}　%{y} 分 %{customdata}<extra></extra>'}];
      } else {
        traces = [{type: 'scatter', mode: 'lines', x: c.t, y: c.v, name: c.id === 'tw_money' ? 'M1B 年增率' : c.name,
                   line: {color: p.blue, width: 2}, hovertemplate: hv + '<extra></extra>'}];
        if (c.v2) {
          traces.push({type: 'scatter', mode: 'lines', x: c.t, y: c.v2, name: c.name2,
                       line: {color: p.orange, width: 2}, hovertemplate: '%{x|%Y-%m}　M2 %{y:.2f}%<extra></extra>'});
        }
      }
      var ref = c.id === 'tw_pmi' || c.id === 'tw_nmi' ? 50 : (c.unit === '%' && /年增|月增|GDP/.test(c.name) ? 0 : null);
      if (c.id === 'us_core_pce') ref = 2;
      if (ref != null) {
        shapes.push({type: 'line', xref: 'paper', x0: 0, x1: 1, y0: ref, y1: ref,
                     line: {color: p.gray, width: 1, dash: 'dot'}});
      }
      Plotly.react(gd, traces, layout({
        xaxis: {type: 'date', gridcolor: p.grid, linecolor: p.grid, automargin: true, fixedrange: true},
        yaxis: {gridcolor: p.grid, automargin: true, fixedrange: true,
                ticksuffix: mcUnit(c), range: c.id === 'tw_signal' ? [0, 46] : undefined},
        shapes: shapes, hovermode: 'x unified',
        showlegend: !!c.v2, legend: {orientation: 'h', y: 1.12, x: 0, font: {size: 11}},
        margin: {l: 48, r: 12, t: c.v2 ? 24 : 10, b: 34}
      }), CONFIG);
    }

    function mcCards(pane) {
      Array.prototype.slice.call(pane.querySelectorAll('.mc-cards')).forEach(function (box) {
        box.textContent = '';
        mc.data.cards.filter(function (c) { return c.region === box.dataset.region; }).forEach(function (c) {
          var b = el('button', 'mc-card' + (c.id === mc.pick ? ' is-picked' : ''));
          b.type = 'button';
          b.appendChild(el('span', 'mc-name', c.name));
          var v = el('span', 'mc-val', fmt(c.last, c.dec) + mcUnit(c));
          if (c.light) {
            var lt = el('span', 'mc-light', c.light);
            lt.style.background = LIGHT_COLOR[c.light] || '';
            v.appendChild(lt);
          }
          b.appendChild(v);
          var sub = el('span', 'mc-sub', c.period);
          if (c.chg != null) {
            sub.appendChild(document.createTextNode('　'));
            sub.appendChild(el('span', c.good ? dir(c.chg * c.good) : '', '比前期 ' + signed(c.chg, c.dec)));
          }
          b.appendChild(sub);
          if (c.last2 != null) b.appendChild(el('span', 'mc-sub', 'M2 ' + fmt(c.last2, 2) + '%'));
          b.appendChild(sparkSvg(c.spark));
          b.addEventListener('click', function () {
            mc.pick = c.id;
            Array.prototype.slice.call(pane.querySelectorAll('.mc-card.is-picked')).forEach(function (x) {
              x.classList.remove('is-picked');
            });
            b.classList.add('is-picked');
            mcChart(pane);
            var h = pane.querySelector('.mc-chart-h');
            if (h.getBoundingClientRect().top < 0) h.scrollIntoView({behavior: 'smooth', block: 'start'});
          });
          box.appendChild(b);
        });
      });
    }

    function mcCal(box, rows, withActual) {
      box.textContent = '';
      if (!rows || !rows.length) { box.appendChild(el('p', 'ov-empty', '沒有資料。')); return; }
      var MC_FIRST = window.innerWidth < 820 ? 5 : 8;
      var t = el('table', 'ov-table scr-table mc-tbl');
      var h = el('tr');
      (withActual ? ['時間', '事件', '公布', '預估', '前值'] : ['時間', '事件', '預估', '前值']).forEach(function (x) {
        h.appendChild(el('th', null, x));
      });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      rows.forEach(function (e, k) {
        var tr = el('tr', e.impact === 'High' ? 'mc-high-imp' : null);
        tr.hidden = k >= MC_FIRST;
        tr.appendChild(el('td', 'ov-when', e.when));
        var ev = el('td');
        ev.appendChild(el('span', 'ov-kind', e.country));
        ev.appendChild(document.createTextNode(e.title));
        tr.appendChild(ev);
        if (withActual) {
          var a = el('td');
          var b = el('b', 'cal-act' + (e.better === '1' ? ' cal-good' : e.better === '0' ? ' cal-bad' : ''),
                     e.actual + (e.surprise > 0 ? '▲' : e.surprise < 0 ? '▼' : ''));
          b.title = (e.surprise > 0 ? '高於預期' : e.surprise < 0 ? '低於預期' : e.forecast ? '符合預期' : '沒有預估值') +
                    (e.better === '1' ? '（對經濟偏正面）' : e.better === '0' ? '（對經濟偏負面）' : '');
          a.appendChild(b);
          tr.appendChild(a);
        }
        tr.appendChild(el('td', null, e.forecast || '—'));
        tr.appendChild(el('td', null, e.previous || '—'));
        tb.appendChild(tr);
      });
      t.appendChild(tb); stackTable(t);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
      moreRows(box, tb);
    }

    function macro(pane) {
      return getJSON('data/macro.json').then(function (d) {
        mc.data = d;
        pane.querySelector('.ov-asof').textContent = d.generated ? '更新時間 ' + d.generated : '';
        var hb = pane.querySelector('.mc-high .ov-body');
        hb.textContent = '';
        if (d.highlights && d.highlights.length) {
          var ul = el('ul', 'ck-list');
          d.highlights.forEach(function (x, i) {
            var li = el('li', null, x);
            li.hidden = i >= 5;
            ul.appendChild(li);
          });
          hb.appendChild(ul);
          moreRows(hb, ul);
        } else {
          hb.appendChild(el('p', 'ov-empty', '還沒有總經資料。'));
        }
        if (!d.cards || !d.cards.length) return;
        if (!d.cards.some(function (c) { return c.id === mc.pick; })) mc.pick = d.cards[0].id;
        mcCards(pane);
        mcChart(pane);
        mcCal(pane.querySelector('.mc-recent'), (d.calendar || {}).recent, true);
        mcCal(pane.querySelector('.mc-next'), (d.calendar || {}).next, false);
      });
    }

    bindChips(panel.querySelector('.ov-range'), function (chip) {
      marketDays = Number(chip.dataset.days);
      setWindow(document.getElementById('ov-market'), marketDays);
    });

    // ── 類股：熱力圖可以點進產業，下方清單列出產業裡每一檔，可依成交值或漲跌排序 ──
    // sectors.json 的 stocks：[代號, 名稱, 產業序號, 收盤, 成交值億, 1日%, 5日%, 10日%, 20日%, 60日%]
    var LEAF = 30;            // 熱力圖每個產業最多畫幾檔（清單裡是全部）
    var SEC_PAGE = 30;        // 清單一次列幾檔
    var PERIOD_LABEL = ['1 日', '5 日', '10 日', '20 日', '60 日'];
    var PERIOD_SCALE = [5, 10, 15, 20, 30];     // 熱力圖顏色到底的漲跌幅（%）
    var sec = {data: null, raw: null, mode: 'official', pick: -1, tag: null, sort: 'turnover', shown: SEC_PAGE, period: 0};
    var FINE_TREEMAP = 40;    // 細產業模式的熱力圖只畫成交值前 40 個細產業（清單與選單是全部）

    // 細產業模式：產業清單換成細產業，每一檔的產業序號換成主要細產業
    function secApplyMode() {
      var d = sec.raw;
      if (sec.mode === 'fine' && d.fine) {
        sec.data = {asof: d.asof, periods: d.periods, industries: d.fine.industries,
                    stocks: d.stocks.map(function (x, k) { var y = x.slice(); y[2] = d.fine.idx[k]; return y; })};
      } else {
        sec.data = d;
      }
    }

    function ret(x) { return x[5 + sec.period]; }

    function secTreemap(pane) {
      var d = sec.data, c = palette(), p = sec.period;
      var ids = ['all'], labels = ['全市場'], parents = [''], values = [0], colors = [0],
          custom = [[0, '']];
      var total = 0, wsum = 0;
      d.industries.forEach(function (s, i) {
        if (sec.mode === 'fine' && i >= FINE_TREEMAP && i !== sec.pick) return;
        var leaves = d.stocks.filter(function (x) { return x[2] === i; }).slice(0, LEAF);
        var v = leaves.reduce(function (a, x) { return a + (x[4] || 0); }, 0);
        if (!v) return;
        var chg = s.chg[p];
        ids.push('I' + i); labels.push(s.industry); parents.push('all'); values.push(v);
        colors.push(chg); custom.push([chg, '']);
        leaves.forEach(function (x) {
          ids.push('S' + x[0]); labels.push(x[1] || x[0]); parents.push('I' + i);
          values.push(x[4] || 0); colors.push(ret(x)); custom.push([ret(x), x[0]]);
        });
        total += v;
        if (chg != null) wsum += chg * v;
      });
      values[0] = total;
      colors[0] = total ? wsum / total : 0;
      custom[0][0] = colors[0];
      var lim = PERIOD_SCALE[p];
      var gd = plot('ov-sectors', [{
        type: 'treemap', ids: ids, labels: labels, parents: parents, values: values,
        branchvalues: 'total', maxdepth: 3, customdata: custom,
        level: sec.pick >= 0 ? 'I' + sec.pick : 'all',
        // 漲跌先在這裡排成字串：上市不到 N 天的沒有 N 日漲跌，交給 Plotly 格式化會出警告
        text: custom.map(function (cd) { return cd[0] == null ? '—' : signed(cd[0], 2, '%'); }),
        texttemplate: '<b>%{label}</b><br>%{text}',
        hovertemplate: '%{label}　%{customdata[1]}<br>成交值 %{value:,.2f} 億' +
                       '<br>' + PERIOD_LABEL[p] + '漲跌 %{text}<extra></extra>',
        marker: {colors: colors,
                 colorscale: [[0, c.down], [0.5, dark ? '#3a3f55' : '#e9ecef'], [1, c.up]],
                 cmin: -lim, cmax: lim, cmid: 0,
                 line: {width: 1, color: dark ? '#1e2130' : '#ffffff'}},
        tiling: {pad: 2},
        pathbar: {visible: true, thickness: 22, textfont: {size: 12, color: c.text}},
        textfont: {color: dark ? '#ffffff' : '#212529'},
        sort: true
      }], layout({margin: {l: 0, r: 0, t: 0, b: 0}, hovermode: 'closest'}));
      if (gd && !gd._secBound) {
        gd._secBound = true;
        // 點個股＝打開深度頁（不放大）；點產業＝放大並讓下方清單換成那個產業
        gd.on('plotly_treemapclick', function (ev) {
          var pt = ev && ev.points && ev.points[0];
          if (!pt) return;
          if (String(pt.id).charAt(0) === 'S') {
            openStock(String(pt.id).slice(1));
            return false;
          }
          var next = String(ev.nextLevel || 'all');
          sec.pick = next.charAt(0) === 'I' ? Number(next.slice(1)) : -1;
          sec.tag = null;
          pane.querySelector('.sec-pick').value = String(sec.pick);
          sec.shown = SEC_PAGE;
          secList(pane);
        });
      }
    }

    function secOptions(pane) {
      var sel = pane.querySelector('.sec-pick');
      sel.textContent = '';
      var all = el('option', null, sec.mode === 'fine' ? '全部細產業（全市場排行）' : '全部產業（全市場排行）');
      all.value = '-1';
      sel.appendChild(all);
      if (sec.mode === 'fine') {
        // 依產業鏈分組
        var groups = {};
        sec.data.industries.forEach(function (s, i) { (groups[s.chain] = groups[s.chain] || []).push(i); });
        Object.keys(groups).sort(function (a, b) { return a.localeCompare(b, 'zh-Hant'); }).forEach(function (ch) {
          var g = document.createElement('optgroup');
          g.label = ch;
          groups[ch].forEach(function (i) {
            var s = sec.data.industries[i];
            var o = el('option', null, s.industry + '（' + s.n + ' 檔）');
            o.value = String(i);
            g.appendChild(o);
          });
          sel.appendChild(g);
        });
      } else {
        sec.data.industries.forEach(function (s, i) {
          var o = el('option', null, s.industry + '（' + s.n + ' 檔）');
          o.value = String(i);
          sel.appendChild(o);
        });
      }
      sel.value = String(sec.pick);
    }

    function secPicker(pane) {
      var sel = pane.querySelector('.sec-pick');
      secOptions(pane);
      if (sel._bound) return;
      sel._bound = true;
      bindChips(pane.querySelector('.sec-mode'), function (chip) {
        secSetMode(pane, chip.dataset.mode, null);
      });
      sel.addEventListener('change', function () {
        sec.pick = Number(sel.value);
        sec.tag = null;
        sec.shown = SEC_PAGE;
        var gd = document.getElementById('ov-sectors');
        if (gd && gd.data) Plotly.restyle(gd, {level: sec.pick >= 0 ? 'I' + sec.pick : 'all'});
        secList(pane);
      });
      bindChips(pane.querySelector('.sec-sort'), function (chip) {
        sec.sort = chip.dataset.sort;
        sec.shown = SEC_PAGE;
        secList(pane);
      });
      bindChips(pane.querySelector('.sec-period'), function (chip) {
        sec.period = Number(chip.dataset.period);
        sec.shown = SEC_PAGE;
        secTreemap(pane);
        secList(pane);
      });
    }

    function secList(pane) {
      var d = sec.data, p = sec.period, label = PERIOD_LABEL[p];
      // 從個股頁的細產業標籤點過來：列出所有歸在這一類的公司（不只主要分類在這類的）
      var rows = d.stocks.filter(function (x) {
        return sec.tag != null ? inTag(x[0], sec.tag) : (sec.pick < 0 || x[2] === sec.pick);
      });
      // 上市不到 N 天、算不出 N 日漲跌的排到最後
      function cmp(sign) {
        return function (a, b) {
          var x = ret(a), y = ret(b);
          if (x == null) return y == null ? 0 : 1;
          if (y == null) return -1;
          return sign * (y - x);
        };
      }
      if (sec.sort === 'up') rows = rows.slice().sort(cmp(1));
      else if (sec.sort === 'down') rows = rows.slice().sort(cmp(-1));
      var sum = pane.querySelector('.sec-sum');
      sum.textContent = '';
      if (sec.tag != null) {
        sum.appendChild(document.createTextNode('細產業「' + CHAINS.tags[sec.tag][0] + '」的所有公司 ' + rows.length +
                                                ' 檔（含主要分類在別類的）　'));
        var clr = el('button', 'chip', '看全部');
        clr.type = 'button';
        clr.addEventListener('click', function () { sec.tag = null; sec.shown = SEC_PAGE; secList(pane); });
        sum.appendChild(clr);
      } else if (sec.pick >= 0) {
        var s = d.industries[sec.pick];
        sum.appendChild(document.createTextNode(s.industry + '　' + label + '加權漲跌 '));
        sum.appendChild(el('b', dir(s.chg[p]), signed(s.chg[p], 2, '%')));
        sum.appendChild(document.createTextNode('　上漲 ' + s.up[p] + ' 家、下跌 ' + s.down[p] +
                                                ' 家　今日成交值 ' + fmt(s.turnover, 1) + ' 億'));
      } else {
        sum.textContent = '全市場 ' + rows.length + ' 檔（不含 ETF）';
      }
      if (p > 0) {
        sum.appendChild(el('span', 'sec-note',
          '　·　' + label + '漲跌以收盤價計算，沒有還原除權息'));
      }
      var box = pane.querySelector('.sec-table');
      box.textContent = '';
      var t = el('table', 'ov-table');
      var h = el('tr');
      ['股票', '收盤', label + '漲跌', '今日成交值（億）'].forEach(function (x) { h.appendChild(el('th', null, x)); });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      rows.slice(0, sec.shown).forEach(function (x, i) {
        var tr = el('tr', 'go');
        var c0 = el('td');
        c0.appendChild(el('span', 'ov-name', (i + 1) + '.'));
        c0.appendChild(el('span', 'ov-code', ' ' + x[0]));
        c0.appendChild(el('span', 'ov-name', x[1]));
        if (sec.pick < 0) c0.appendChild(el('span', 'scr-reason', d.industries[x[2]].industry));
        tr.appendChild(c0);
        tr.appendChild(el('td', null, fmt(x[3], 2)));
        tr.appendChild(el('td', dir(ret(x)), signed(ret(x), 2, '%')));
        tr.appendChild(el('td', null, fmt(x[4], 2)));
        tr.addEventListener('click', function () { openStock(x[0]); });
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
      if (rows.length > sec.shown) {
        var more = el('button', 'scr-more', '再顯示 ' + Math.min(SEC_PAGE * 2, rows.length - sec.shown) +
                      ' 檔（共 ' + rows.length + ' 檔）');
        more.type = 'button';
        more.addEventListener('click', function () { sec.shown += SEC_PAGE * 2; secList(pane); });
        box.appendChild(more);
      }
    }

    // 切換官方產業／細產業；pickName 給了就直接選那個細產業（個股頁的標籤點過來）
    function secSetMode(pane, mode, pickName) {
      sec.mode = mode;
      Array.prototype.slice.call(pane.querySelectorAll('.sec-mode .chip')).forEach(function (c) {
        c.setAttribute('aria-pressed', String(c.dataset.mode === mode));
      });
      secApplyMode();
      sec.pick = -1;
      sec.tag = null;
      if (pickName) {
        sec.data.industries.forEach(function (s, i) { if (s.industry === pickName) sec.pick = i; });
        CHAINS.tags.forEach(function (t, i) { if (t[0] === pickName) sec.tag = i; });
      }
      sec.shown = SEC_PAGE;
      pane.querySelector('.sec-mode-note').textContent = mode === 'fine'
        ? '細產業：櫃買中心產業價值鏈＋手動補充表；一檔屬於好幾類時放在股價走勢最接近的那一類'
          + '（熱力圖只畫成交值前 ' + FINE_TREEMAP + ' 類）' : '';
      secOptions(pane);
      secTreemap(pane);
      secList(pane);
    }

    window.openFineSector = function (name) {
      goSub('sectors');
      var pane = document.querySelector('.subpanel[data-sub="sectors"]');
      Promise.all([getJSON('data/sectors.json'), loadChains()]).then(function () {
        setTimeout(function () { if (sec.raw) secSetMode(pane, 'fine', name); }, 50);
      });
    };

    function sectors(pane) {
      return getJSON('data/sectors.json').then(function (d) {
        sec.raw = d;
        secApplyMode();
        if (!d.fine) pane.querySelector('.sec-mode').hidden = true;
        pane.querySelector('.ov-asof').textContent = '資料日期 ' + d.asof + '（盤後）　·　' +
          '點產業放大，點最上方的標題回到上一層，點個股看深度頁';
        secPicker(pane);
        secTreemap(pane);
        secList(pane);
      });
    }

    // 長表格先列 FIRST_ROWS 筆，底下一顆「再看 N 筆」
    var FIRST_ROWS = 10;
    function moreRows(box, tbody) {
      var hidden = Array.prototype.slice.call(tbody.children).filter(function (r) { return r.hidden; });
      if (!hidden.length) return;
      var b = el('button', 'scr-more', '再看 ' + hidden.length + ' 筆');
      b.type = 'button';
      b.addEventListener('click', function () {
        hidden.forEach(function (r) { r.hidden = false; });
        b.remove();
      });
      box.appendChild(b);
    }

    // 手機上兩張表改成切換（買超／賣超、增加／減少）；電腦版兩張並排，切換鈕不顯示
    function bindSideSegs(pane) {
      Array.prototype.slice.call(pane.querySelectorAll('.side-seg')).forEach(function (seg) {
        if (seg._bound) return;
        seg._bound = true;
        var grid = seg.nextElementSibling;
        bindChips(seg, function (chip) { grid.classList.toggle('show-b', chip.dataset.side === '1'); });
      });
    }

    function flowTable(box, rows) {
      box.textContent = '';
      if (!rows || !rows.length) { box.appendChild(el('p', 'ov-empty', '沒有資料。')); return; }
      var t = el('table', 'ov-table');
      var h = el('tr');
      ['股票', '張數', '金額（億）'].forEach(function (x) { h.appendChild(el('th', null, x)); });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      rows.forEach(function (r, i) {
        var tr = el('tr', 'go');
        tr.hidden = i >= FIRST_ROWS;
        var c0 = el('td');
        c0.appendChild(el('span', 'ov-code', r[0]));
        c0.appendChild(el('span', 'ov-name', r[1]));
        tr.appendChild(c0);
        tr.appendChild(el('td', dir(r[2]), signed(r[2], 0)));
        tr.appendChild(el('td', dir(r[3]), signed(r[3], 2)));
        tr.addEventListener('click', function () { openStock(r[0]); });
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      box.appendChild(t);
      moreRows(box, tb);
    }

    function optionsChart(pane, o) {
      var c = palette(), box = pane.querySelector('.ov-opt-latest');
      if (!o.t || !o.t.length) {
        failMsg(document.getElementById('ov-options'), '選擇權資料累積中。');
        return;
      }
      plot('ov-options', [
        {type: 'scatter', mode: 'lines+markers', x: o.t, y: o.pc_oi, name: 'P/C 比（未平倉）',
         line: {color: c.orange, width: 2}, hovertemplate: '%{y:.1f}%<extra>未平倉 P/C</extra>'},
        {type: 'scatter', mode: 'lines', x: o.t, y: o.pc_vol, name: 'P/C 比（成交量）',
         line: {color: c.gray, width: 1, dash: 'dot'}, hovertemplate: '%{y:.1f}%<extra>成交量 P/C</extra>'}
      ], layout({showlegend: true, legend: {orientation: 'h', x: 0, y: 1.14, font: {size: 11}},
                 xaxis: {type: 'category', nticks: 6, automargin: true},
                 yaxis: {ticksuffix: '%', gridcolor: c.grid, automargin: true},
                 shapes: [{type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100, y1: 100,
                           line: {color: c.gray, width: 1, dash: 'dash'}}],
                 margin: {l: 48, r: 14, t: 26, b: 34}}));
      box.textContent = '';
      var n = o.t.length - 1;
      [['外資 買權淨未平倉', o.fi_call[n], '口'], ['外資 賣權淨未平倉', o.fi_put[n], '口'],
       ['前十大交易人 買權淨部位', o.top10_call[n], '口'], ['前十大交易人 賣權淨部位', o.top10_put[n], '口']]
        .forEach(function (x) {
          var b = el('div', 'ck-tile');
          b.appendChild(el('span', 'ck-tile-k', x[0]));
          b.appendChild(el('b', dir(x[1]), x[1] == null ? '—' : signed(x[1], 0) + ' ' + x[2]));
          b.appendChild(el('span', 'ck-tile-d', md(o.t[n])));
          box.appendChild(b);
        });
    }

    function qfiiTables(pane, q) {
      var note = pane.querySelector('.qf-note');
      if (!q || !q.asof) {
        note.textContent = '外資持股資料累積中。';
        Array.prototype.slice.call(pane.querySelectorAll('.qf-tbl')).forEach(function (b) { b.textContent = ''; });
        return;
      }
      note.textContent = '近 ' + q.window + ' 個交易日（' + md(q.from) + ' → ' + md(q.asof) + '）外資及陸資持股比率的變化，'
        + '單位是百分點；只列近 20 日平均成交值 0.5 億以上的股票。持股比率持續增加代表外資在累積部位。';
      Array.prototype.slice.call(pane.querySelectorAll('.qf-tbl')).forEach(function (box) {
        var rows = q[box.dataset.side] || [];
        box.textContent = '';
        if (!rows.length) { box.appendChild(el('p', 'ov-empty', '沒有資料。')); return; }
        var t = el('table', 'ov-table');
        var h = el('tr');
        ['股票', '持股比率', '變化'].forEach(function (x) { h.appendChild(el('th', null, x)); });
        var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
        var tb = el('tbody');
        rows.forEach(function (r) {
          var tr = el('tr', 'go');
          var c0 = el('td');
          c0.appendChild(el('span', 'ov-code', r[0]));
          c0.appendChild(el('span', 'ov-name', r[1]));
          tr.appendChild(c0);
          tr.appendChild(el('td', null, fmt(r[3], 2) + '%'));
          tr.appendChild(el('td', dir(r[4]), signed(r[4], 2)));
          tr.addEventListener('click', function () { openStock(r[0]); });
          tr.hidden = tb.children.length >= FIRST_ROWS;
          tb.appendChild(tr);
        });
        t.appendChild(tb);
        box.appendChild(t);
        moreRows(box, tb);
      });
    }

    function flows(pane, d) {
      bindSideSegs(pane);
      qfiiTables(pane, d.qfii);
      var f = d.flows || {};
      Array.prototype.slice.call(pane.querySelectorAll('.ov-flow')).forEach(function (box) {
        flowTable(box, f[flowSide + '_' + box.dataset.side]);
      });
      optionsChart(pane, d.options || {});
      var fu = d.futures || {};
      var c = palette();
      if (!fu.t || !fu.t.length) {
        failMsg(document.getElementById('ov-futures'), '期貨資料累積中。');
        return;
      }
      plot('ov-futures', [
        {type: 'bar', x: fu.t, y: fu.foreign, name: '外資', marker: {color: c.orange},
         hovertemplate: '%{y:+,.0f} 口<extra>外資</extra>'},
        {type: 'bar', x: fu.t, y: fu.trust, name: '投信', marker: {color: c.purple},
         hovertemplate: '%{y:+,.0f} 口<extra>投信</extra>'},
        {type: 'bar', x: fu.t, y: fu.dealer, name: '自營商', marker: {color: c.gray},
         hovertemplate: '%{y:+,.0f} 口<extra>自營商</extra>'}
      ], layout({barmode: 'group', showlegend: true,
                 legend: {orientation: 'h', x: 0, y: 1.12, font: {size: 11}},
                 xaxis: {type: 'category', gridcolor: c.grid, nticks: 6, automargin: true},
                 yaxis: {gridcolor: c.grid, zeroline: true, zerolinecolor: c.grid,
                         tickformat: ',.0f', automargin: true},
                 margin: {l: 56, r: 14, t: 26, b: 34}}));
    }

    Array.prototype.slice.call(panel.querySelectorAll('.ov-flow-tabs .chip')).forEach(function (chip) {
      chip.addEventListener('click', function () {
        flowSide = chip.dataset.flow;
        Array.prototype.slice.call(panel.querySelectorAll('.ov-flow-tabs .chip')).forEach(function (x) {
          x.setAttribute('aria-pressed', String(x === chip));
        });
        load().then(function (d) { flows(panel.querySelector('.subpanel[data-sub="flows"]'), d); });
      });
    });

    // ── 強勢股：強度（20 日漲幅）× 加速度（近 5 日 − 前 5 日漲幅）──────────
    // momentum.json 的 stocks：[代號, 名稱, 產業序號, 20 日均成交值億, [近 41 日收盤]]
    var MO_TOP = 10;          // 畫軌跡、畫累積漲幅曲線的檔數
    var MO_TAIL = 5;          // 軌跡往回畫幾天
    var MO_PAGE = window.innerWidth < 820 ? 15 : 30;
    var MO_COLORS = ['#e03131', '#1c7ed6', '#f08c00', '#7048e8', '#2f9e44',
                     '#d6336c', '#0c8599', '#5c940d', '#ae3ec9', '#495057'];
    var mo = {data: null, ind: -1, min: 1, sort: 'a', desc: true, shown: MO_PAGE,
              t: null, k: null, playing: false, render: null,
              ext: 0, full: false,
              news: null, newsMeta: null, strong: []};   // news：{代號: 近五日新聞與上漲原因}   // ext：只看最極端的比例（0＝全部）；full：播放中所有點都要畫

    // 第 i 天的強度與加速度
    function moAt(c, i) {
      var r5 = (c[i] / c[i - 5] - 1) * 100;
      var p5 = (c[i - 5] / c[i - 10] - 1) * 100;
      return {s: (c[i] / c[i - 20] - 1) * 100, r5: r5, p5: p5, a: r5 - p5};
    }

    function moRows() {
      var d = mo.data, last = d.dates.length - 1;
      return d.stocks.filter(function (x) {
        var okInd = typeof mo.ind === 'string' ? inTag(x[0], Number(mo.ind.slice(1)))
                                               : (mo.ind < 0 || x[2] === mo.ind);
        return okInd && (x[3] || 0) >= mo.min;
      }).map(function (x) {
        var m = moAt(x[4], last);
        return {code: x[0], name: x[1], ind: x[2], tv: x[3], c: x[4],
                s: m.s, r5: m.r5, p5: m.p5, a: m.a};
      }).filter(function (r) { return isFinite(r.s) && isFinite(r.a); });
    }

    // 越來越強：已經在漲（強度 > 0），而且最近漲得比之前快（加速度 > 0），依加速度排
    function moStrong(rows) {
      return rows.filter(function (r) { return r.s > 0 && r.a > 0; })
        .sort(function (a, b) { return b.a - a.a; });
    }

    function quantile(values, q) {
      var v = values.slice().sort(function (a, b) { return a - b; });
      if (!v.length) return 0;
      var i = (v.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
      return v[lo] + (v[hi] - v[lo]) * (i - lo);
    }

    // 一行「最可能原因」：分類標籤＋原因（沒有整理就回傳 null）
    function moWhy(code) {
      var n = mo.news && mo.news[code];
      if (!n || !n.why) return null;
      var w = el('span', 'mo-why');
      w.appendChild(el('b', 'mo-tag', n.tag));
      w.appendChild(document.createTextNode(n.why));
      return w;
    }

    function moNewsLink(it) {
      if (it.k === 'a') return el('span', 'mo-item-t', it.t);       // 重大訊息沒有連結
      // Google 新聞的轉址連結太長的沒有存，改連到標題搜尋
      var a = el('a', 'mo-item-t', it.t);
      a.href = it.u || 'https://www.google.com/search?tbm=nws&q=' + encodeURIComponent('"' + it.t + '"');
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      return a;
    }

    // 點排行的一列展開：最可能原因、重點整理、近五日新聞與重大訊息
    function moDetail(r, span) {
      var tr = el('tr', 'mo-detail');
      var td = el('td');
      td.colSpan = span;
      var box = el('div', 'mo-news');
      var n = mo.news && mo.news[r.code];
      var meta = mo.newsMeta || {};
      if (n) {
        var head = el('p', 'mo-news-why');
        head.appendChild(el('b', 'mo-tag', n.tag));
        head.appendChild(document.createTextNode(n.why || '找不到明確消息'));
        head.appendChild(el('span', 'mo-conf mo-conf-' + (n.conf === '高' ? 'hi' : n.conf === '中' ? 'mid' : 'lo'),
                            '可信度 ' + n.conf));
        box.appendChild(head);
        if (n.points && n.points.length) {
          var ul = el('ul', 'mo-points');
          n.points.forEach(function (t) { ul.appendChild(el('li', null, t)); });
          box.appendChild(ul);
        }
        if (n.items && n.items.length) {
          var list = el('ul', 'mo-items');
          n.items.forEach(function (it) {
            var li = el('li', it.key ? 'is-key' : null);
            if (it.key) li.appendChild(el('span', 'mo-key', '關鍵'));
            li.appendChild(el('span', 'mo-item-d', it.d));
            li.appendChild(el('span', 'mo-item-src', it.src));
            li.appendChild(moNewsLink(it));
            list.appendChild(li);
          });
          box.appendChild(list);
        } else {
          box.appendChild(el('p', 'sd-note', '近五個交易日沒有找到這檔的新聞或重大訊息。'));
        }
        var how = n.method === 'claude'
          ? (meta.model || 'Claude') + ' 依近五個交易日的新聞與重大訊息整理，AI 判讀僅供參考'
          : '尚未設定 Claude，暫以標題關鍵字挑出最可能的一則，僅供參考';
        box.appendChild(el('p', 'mo-news-foot', how + (meta.generated ? '　·　' + meta.generated : '') +
                           (n.total > (n.items || []).length ? '　·　共找到 ' + n.total + ' 則，只列相關的' : '')));
      } else {
        box.appendChild(el('p', 'sd-note', mo.news && Object.keys(mo.news).length
          ? '這檔不在新聞整理名單（越來越強前 60 檔＋自選股），沒有整理新聞。'
          : '新聞整理還沒有資料。'));
      }
      var go = el('button', 'chip', '看個股 ›');
      go.type = 'button';
      go.addEventListener('click', function () { openStock(r.code); });
      box.appendChild(go);
      td.appendChild(box);
      tr.appendChild(td);
      return tr;
    }

    function moPicked(pane, r) {
      var box = pane.querySelector('.mo-pick');
      box.textContent = '';
      box.appendChild(el('b', null, r.code + ' ' + r.name));
      box.appendChild(el('span', null, '　強度 ' + signed(r.s, 1, '%') + '　近 5 日 ' + signed(r.r5, 1, '%') +
                                       '　前 5 日 ' + signed(r.p5, 1, '%') + '　加速 ' + signed(r.a, 1, ' 點')));
      var go = el('button', 'chip', '看個股 ›');
      go.type = 'button';
      go.addEventListener('click', function () { openStock(r.code); });
      box.appendChild(go);
      var why = moWhy(r.code);
      if (why) box.appendChild(why);
      box.hidden = false;
    }

    var MO_FIRST = 20;        // 第一個算得出 20 日強度的位置（momentum.json 有 41 天）
    var MO_DAY = 600;         // 播放時每一天花的毫秒數
    var MO_SUB = 4;           // 軌跡折線每一天取幾個點
    var MO_MARKS = [-4, -3, -2, -1, -0.25, 0];   // 軌跡上的點（往回幾天）；-0.25 不畫，只決定箭頭方向
    var MO_END = MO_MARKS.length - 1;
    var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function moColor(c, s, a) {
      if (s > 0 && a > 0) return c.up;          // 越來越強
      if (s <= 0 && a > 0) return c.orange;     // 弱轉強
      if (s > 0) return c.blue;                 // 強但減速
      return c.gray;                            // 弱且續弱
    }

    function moSize(r) { return 5 + Math.min(16, Math.sqrt(r.tv || 0) * 1.2); }

    function moDays() { return mo.data.dates.length - 1 - MO_FIRST; }

    // 一檔股票從 MO_FIRST 到今天每一天的（強度, 加速度）；缺值的那天是 null
    function moPath(r, last) {
      var xs = [], ys = [];
      for (var k = MO_FIRST; k <= last; k++) {
        var m = moAt(r.c, k), ok = isFinite(m.s) && isFinite(m.a);
        xs.push(ok ? m.s : null);
        ys.push(ok ? m.a : null);
      }
      return {x: xs, y: ys};
    }

    // 第 t 天（從 MO_FIRST 起算，可以有小數）的位置。
    // 整數天就是當天的真實數字；兩天之間用 Catmull-Rom 曲線補，會經過每一天的點，轉彎也是圓的
    function moPos(p, t) {
      var n = p.x.length - 1;
      t = Math.max(0, Math.min(n, t));
      var i = Math.floor(t), f = t - i;
      if (f < 1e-9 || i >= n) return p.x[i] == null ? null : [p.x[i], p.y[i]];
      if (p.x[i] == null || p.x[i + 1] == null) {          // 缺值那段不補，停在有值的那天
        var j = p.x[i] == null ? i + 1 : i;
        return p.x[j] == null ? null : [p.x[j], p.y[j]];
      }
      var i0 = i > 0 && p.x[i - 1] != null ? i - 1 : i;
      var i3 = i + 2 <= n && p.x[i + 2] != null ? i + 2 : i + 1;
      var cr = function (a) {
        var p0 = a[i0], p1 = a[i], p2 = a[i + 1], p3 = a[i3];
        return 0.5 * (2 * p1 + (p2 - p0) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f +
                      (3 * p1 - p0 - 3 * p2 + p3) * f * f * f);
      };
      return [cr(p.x), cr(p.y)];
    }

    // 軌跡在第 t 天的樣子：折線（每天 MO_SUB 個點）與 MO_MARKS 上的點。
    // 還沒有那麼多天可以往回畫時就疊在第一天，陣列長度固定、中間沒有空洞
    function moTrail(p, t, conv) {
      var at = function (dt) {
        var q = moPos(p, Math.max(0, t + dt));
        return q ? conv(q) : null;
      };
      var line = [], marks = [];
      for (var s = -(MO_TAIL - 1) * MO_SUB; s <= 0; s++) line.push(at(s / MO_SUB));
      MO_MARKS.forEach(function (dt) { marks.push(at(dt)); });
      return {line: line, marks: marks};
    }

    // 每一檔離中心多遠：強度、加速度各自扣掉中位數，除以 MAD×1.4826（穩健的標準差，
    // 不會被少數暴漲股撐大），再算距離。四個方向都算，暴漲、暴跌、急轉強、急轉弱都會被挑出來。
    // 回傳每一檔的距離（缺值是 -1）與門檻：距離 ≥ thr 就是最極端的那 mo.ext
    function moSpread(pts) {
      var xs = [], ys = [];
      pts.forEach(function (q) { if (q) { xs.push(q[0]); ys.push(q[1]); } });
      var cx = quantile(xs, 0.5), cy = quantile(ys, 0.5);
      var scale = function (v, mid) {
        return quantile(v.map(function (x) { return Math.abs(x - mid); }), 0.5) * 1.4826 || 1;
      };
      var sx = scale(xs, cx), sy = scale(ys, cy);
      var d = pts.map(function (q) {
        return q ? Math.sqrt(Math.pow((q[0] - cx) / sx, 2) + Math.pow((q[1] - cy) / sy, 2)) : -1;
      });
      var sorted = d.filter(function (v) { return v >= 0; }).sort(function (a, b) { return b - a; });
      var n = Math.max(1, Math.ceil(sorted.length * mo.ext));
      return {d: d, thr: sorted.length ? sorted[Math.min(n, sorted.length) - 1] : Infinity};
    }

    // 播放中進出極端名單的點用淡入淡出：門檻以上全亮，門檻的 90%～100% 之間漸變
    function moFade(d, thr) {
      if (d < 0) return 0;
      var lo = thr * 0.9;
      return d >= thr ? 0.75 : d <= lo ? 0 : 0.75 * (d - lo) / (thr - lo);
    }

    // 今天（最後一天）的極端名單：{代號: true}
    function moExtreme(rows) {
      var sp = moSpread(rows.map(function (r) { return [r.s, r.a]; }));
      var keep = {};
      rows.forEach(function (r, i) { if (sp.d[i] >= sp.thr) keep[r.code] = true; });
      return keep;
    }

    // Plotly 用的資料：第 t 天（靜止時一定是整數天）所有點與軌跡。
    // 只看極端時，靜止狀態不在名單內的點給 null（不畫、滑過去也不會跳出來）；
    // 播放中（full）全部都畫，不在名單內的透明度是 0，才能淡入
    function moData(t, c, full) {
      var xs = [], ys = [], cs = [], op = [];
      var pts = mo.paths.map(function (p) { return moPos(p, t); });
      var sp = mo.ext ? moSpread(pts) : null;
      pts.forEach(function (q, i) {
        var keep = q && (!sp || sp.d[i] >= sp.thr);
        xs.push(q && (keep || full) ? q[0] : null);
        ys.push(q && (keep || full) ? q[1] : null);
        cs.push(q ? moColor(c, q[0], q[1]) : c.gray);
        op.push(keep ? 0.75 : 0);
      });
      var k = MO_FIRST + Math.round(t);
      var data = [{x: xs, y: ys, color: cs, opacity: op, customdata: mo.rows.map(function (r) {
        var m = moAt(r.c, k);
        return [r.code, r.name, m.r5, m.p5, r.tv];
      })}];
      var same = function (q) { return q; };
      var xy = function (list) {
        return {x: list.map(function (q) { return q ? q[0] : null; }),
                y: list.map(function (q) { return q ? q[1] : null; })};
      };
      mo.tpaths.forEach(function (p) {
        var tr = moTrail(p, t, same);
        data.push(xy(tr.line));
        data.push(xy(tr.marks));
      });
      return data;
    }

    // 座標範圍對整段期間固定（播放時軸不會跳），取所有天的 2%～98%（只看極端時取極端名單的），
    // 少數暴漲暴跌（或除權、減資造成的假跳動）不會把其他點擠成一團，雙擊可看全部；
    // 並確保前幾名每一天的位置都在圖內
    function moRange() {
      var xs = [], ys = [], lo = 0.02, hi = 0.98;
      for (var t = 0; t <= moDays(); t++) {
        var pts = mo.paths.map(function (p) { return moPos(p, t); });
        var sp = mo.ext ? moSpread(pts) : null;
        pts.forEach(function (q, i) {
          if (q && (!sp || sp.d[i] >= sp.thr)) { xs.push(q[0]); ys.push(q[1]); }
        });
      }
      var xr = [quantile(xs, lo), quantile(xs, hi)], yr = [quantile(ys, lo), quantile(ys, hi)];
      mo.tpaths.forEach(function (p) {
        for (var t = 0; t <= moDays(); t++) {
          var q = moPos(p, t);
          if (!q) continue;
          xr = [Math.min(xr[0], q[0]), Math.max(xr[1], q[0])];
          yr = [Math.min(yr[0], q[1]), Math.max(yr[1], q[1])];
        }
      });
      var px = (xr[1] - xr[0]) * 0.06 || 1, py = (yr[1] - yr[0]) * 0.08 || 1;
      return {x: [Math.min(xr[0] - px, -px), Math.max(xr[1] + px, px)],
              y: [Math.min(yr[0] - py, -py), Math.max(yr[1] + py * 1.5, py)]};
    }

    var moRev = 0;

    function moScatter(pane, rows, top) {
      var c = palette(), d = mo.data, last = d.dates.length - 1;
      var narrow = window.innerWidth < 600;
      mo.paths = rows.map(function (r) { return moPath(r, last); });
      mo.tpaths = top.map(function (r) { return moPath(r, last); });
      var now = moData(mo.t, c, mo.full);
      var traces = [{
        type: 'scatter', mode: 'markers', ids: rows.map(function (r) { return r.code; }),
        x: now[0].x, y: now[0].y, customdata: now[0].customdata,
        marker: {color: now[0].color, size: rows.map(moSize), line: {width: 0},
                 opacity: mo.ext && mo.full ? now[0].opacity : 0.75},
        hovertemplate: '%{customdata[1]} %{customdata[0]}<br>強度（20 日）%{x:+.1f}%' +
                       '<br>近 5 日 %{customdata[2]:+.1f}%　前 5 日 %{customdata[3]:+.1f}%' +
                       '<br>加速 %{y:+.1f} 點　均量 %{customdata[4]:,.1f} 億<extra></extra>',
        showlegend: false
      }];
      top.forEach(function (r, n) {
        // 手機只標前 5 名，名字才不會疊在一起
        var name = (!narrow || n < 5) ? r.name : '';
        traces.push({type: 'scatter', mode: 'lines', x: now[1 + n * 2].x, y: now[1 + n * 2].y,
                     showlegend: false, line: {color: c.up, width: 1}, opacity: 0.45,
                     hoverinfo: 'skip'});
        traces.push({type: 'scatter', mode: 'markers+text', x: now[2 + n * 2].x, y: now[2 + n * 2].y,
                     showlegend: false,
                     marker: {color: c.up, angleref: 'previous',
                              symbol: MO_MARKS.map(function (_, i) { return i === MO_END ? 'arrow' : 'circle'; }),
                              size: MO_MARKS.map(function (dt, i) {
                                return i === MO_END ? 13 : (dt % 1 ? 0 : 3);
                              })},
                     text: MO_MARKS.map(function (_, i) { return i === MO_END ? name : ''; }),
                     textposition: 'top center', textfont: {size: 11, color: c.text},
                     customdata: MO_MARKS.map(function () { return [r.code, r.name]; }),
                     hovertemplate: '%{customdata[1]} %{customdata[0]}<br>強度 %{x:+.1f}%' +
                                    '　加速 %{y:+.1f} 點<extra></extra>'});
      });
      var range = moRange();
      var corner = function (text, x, y, xa, ya) {
        return {text: text, xref: 'paper', yref: 'paper', x: x, y: y, xanchor: xa, yanchor: ya,
                showarrow: false, font: {size: 12, color: c.fg}};
      };
      var L = layout({
        hovermode: 'closest',
        dragmode: COARSE ? false : 'zoom',
        // 播放時直接移動畫面上的點，停下來後一定要整張重畫，把位置與滑過去的數字對回來
        datarevision: ++moRev,
        uirevision: mo.ind + '|' + mo.min + '|' + mo.ext,                     // 暫停後重畫不要把放大的範圍還原；換篩選才還原
        xaxis: {title: {text: '強度：近 20 日漲幅（%）', font: {size: 11}}, gridcolor: c.grid,
                zeroline: true, zerolinecolor: c.gray, zerolinewidth: 1.5, range: range.x,
                ticksuffix: '%', automargin: true},
        yaxis: {title: {text: '加速度：近 5 日 − 前 5 日（點）', font: {size: 11}}, gridcolor: c.grid,
                zeroline: true, zerolinecolor: c.gray, zerolinewidth: 1.5, range: range.y,
                automargin: true},
        annotations: [corner('越來越強 ↗', 1, 1, 'right', 'top'), corner('弱轉強', 0, 1, 'left', 'top'),
                      corner('強但減速', 1, 0, 'right', 'bottom'), corner('弱且續弱', 0, 0, 'left', 'bottom')],
        margin: {l: 58, r: 14, t: 12, b: 48}
      });
      var gd = document.getElementById('ov-momentum');
      Plotly.react(gd, traces, L, {displayModeBar: false, responsive: true, scrollZoom: !COARSE,
                                   doubleClick: COARSE ? false : 'reset+autosize'});
      if (!gd._moBound) {
        gd._moBound = true;
        gd.on('plotly_click', function (ev) {
          var p = ev && ev.points && ev.points[0];
          if (!p || !p.customdata) return;
          var row = mo.rows.filter(function (r) { return r.code === p.customdata[0]; })[0];
          if (!row) return;
          // 手機：先顯示這一檔當天的數字，按鈕再打開；電腦直接打開
          if (COARSE) {
            var m = moAt(row.c, mo.k), last = mo.data.dates.length - 1;
            var when = mo.k === last ? '' : '（' + md(mo.data.dates[mo.k]) + '）';
            moPicked(pane, {code: row.code, name: row.name + when, s: m.s, r5: m.r5, p5: m.p5, a: m.a});
          } else {
            openStock(row.code);
          }
        });
        // 播放中圖被重畫（例如視窗大小改變）就重新抓畫面上的點
        gd.on('plotly_afterplot', function () { if (mo.render) mo.render = moPrep(); });
      }
      moLabel(pane);
    }

    function moLabel(pane) {
      var last = mo.data.dates.length - 1;
      var k = MO_FIRST + Math.round(mo.t);                    // 最接近的那一天
      var slider = pane.querySelector('.mo-slider');
      slider.max = String(moDays());
      slider.value = String(mo.t);
      if (k !== mo.k || !pane.querySelector('.mo-date').textContent) {
        mo.k = k;
        pane.querySelector('.mo-date').textContent = md(mo.data.dates[k]) + (k === last ? '　今天' : '');
      }
    }

    // ── 播放：每一個畫面直接移動 SVG 上的點（不經過 Plotly 重算），所以很順；
    //    停下來後再用 Plotly 重畫一次，滑過去的數字才對得上 ──
    function moAngle(a, b) { return Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI + 90; }

    // 記下畫面上每個點的 SVG 節點；結構對不上就回傳 null（改成一天一天重畫）
    function moPrep() {
      var gd = document.getElementById('ov-momentum');
      var fl = gd && gd._fullLayout;
      var tr = gd ? gd.querySelectorAll('.scatterlayer .trace') : [];
      if (!fl || tr.length !== 1 + mo.tpaths.length * 2) return null;
      var xa = fl.xaxis, ya = fl.yaxis;
      var cloud = [];
      for (var i = 0; i < mo.paths.length; i++) cloud.push(null);
      Array.prototype.forEach.call(tr[0].querySelectorAll('.point'), function (n) {
        var d = n.__data__;
        if (d && d.i != null) cloud[d.i] = n;
      });
      var trails = mo.tpaths.map(function (_, n) {
        var pts = [];
        Array.prototype.forEach.call(tr[2 + n * 2].querySelectorAll('.point'), function (node) {
          var d = node.__data__;
          if (d && d.i != null) pts[d.i] = node;
        });
        var texts = tr[2 + n * 2].querySelectorAll('.textpoint text');
        // Plotly 畫箭頭時已經把方向轉進圖形裡；播放時再轉「現在方向 − 當時方向」
        var src = gd.data[2 + n * 2], base = 0;
        if (src.x[MO_END - 1] != null && src.x[MO_END] != null) {
          base = moAngle([xa.l2p(src.x[MO_END - 1]), ya.l2p(src.y[MO_END - 1])],
                         [xa.l2p(src.x[MO_END]), ya.l2p(src.y[MO_END])]);
        }
        return {line: tr[1 + n * 2].querySelector('.js-line'), pts: pts,
                text: texts.length ? texts[texts.length - 1] : null, base: base};
      });
      return {gd: gd, root: tr[0], cloud: cloud, fill: [], op: [], trails: trails, c: palette()};
    }

    function moRender(t) {
      var R = mo.render;
      if (R && !R.root.isConnected) R = mo.render = moPrep();
      if (!R) return;
      var xa = R.gd._fullLayout.xaxis, ya = R.gd._fullLayout.yaxis, c = R.c;
      var px = function (q) { return [xa.l2p(q[0]), ya.l2p(q[1])]; };
      var f2 = function (v) { return Math.round(v * 100) / 100; };
      var pts = mo.paths.map(function (p) { return moPos(p, t); });
      var sp = mo.ext ? moSpread(pts) : null;              // 只看極端：每一格都重算名單
      R.cloud.forEach(function (node, i) {
        if (!node) return;
        var q = pts[i];
        if (!q) { node.style.visibility = 'hidden'; return; }
        node.style.visibility = '';
        node.setAttribute('transform', 'translate(' + f2(xa.l2p(q[0])) + ',' + f2(ya.l2p(q[1])) + ')');
        var col = moColor(c, q[0], q[1]);
        if (R.fill[i] !== col) { node.style.fill = col; R.fill[i] = col; }
        if (sp) {
          var o = f2(moFade(sp.d[i], sp.thr));
          if (R.op[i] !== o) { node.style.opacity = o; R.op[i] = o; }
        }
      });
      R.trails.forEach(function (T, n) {
        var tr = moTrail(mo.tpaths[n], t, px);
        if (T.line) {
          var d = tr.line.filter(Boolean).map(function (q) { return f2(q[0]) + ',' + f2(q[1]); });
          T.line.setAttribute('d', d.length ? 'M' + d.join('L') : '');
        }
        tr.marks.forEach(function (q, i) {
          var node = T.pts[i];
          if (!node || !q) return;
          var tf = 'translate(' + f2(q[0]) + ',' + f2(q[1]) + ')';
          if (i === MO_END && tr.marks[i - 1]) tf += ' rotate(' + f2(moAngle(tr.marks[i - 1], q) - T.base) + ')';
          node.setAttribute('transform', tf);
        });
        var head = tr.marks[MO_END];
        if (T.text && head) {
          T.text.setAttribute('x', f2(head[0]));
          T.text.setAttribute('y', f2(head[1]));
        }
      });
    }

    var moRaf = 0;

    function moCancel() {
      if (moRaf) cancelAnimationFrame(moRaf);
      moRaf = 0;
    }

    // 開始直接操作畫面：抓節點、播放中不給滑鼠互動（滑過去的數字此時對不上）
    function moBegin(pane) {
      if (!mo.render && mo.ext && !mo.full) {
        mo.full = true;
        moScatter(pane, mo.rows, mo.top);
      }
      if (!mo.render) mo.render = moPrep();
      var gd = document.getElementById('ov-momentum');
      if (gd) gd.classList.add('mo-busy');
      return !!mo.render;
    }

    // 停在整數天，交回 Plotly 重畫
    function moSettle(pane) {
      moCancel();
      mo.t = Math.round(mo.t);
      mo.render = null;
      mo.full = false;
      var gd = document.getElementById('ov-momentum');
      if (gd) gd.classList.remove('mo-busy');
      moScatter(pane, mo.rows, mo.top);
    }

    // 從目前位置滑到第 to 天（暫停、放開滑桿、按方向鍵）
    function moEase(pane, to, ms) {
      moCancel();
      var from = mo.t;
      if (REDUCED || Math.abs(to - from) < 1e-6 || !moBegin(pane)) {
        mo.t = to;
        moSettle(pane);
        return;
      }
      var start = performance.now();
      var tick = function (now) {
        var f = Math.min(1, (now - start) / ms);
        mo.t = from + (to - from) * (1 - Math.pow(1 - f, 3));
        moRender(mo.t);
        moLabel(pane);
        if (f < 1) moRaf = requestAnimationFrame(tick);
        else moSettle(pane);
      };
      moRaf = requestAnimationFrame(tick);
    }

    function moButton(pane, playing) {
      mo.playing = playing;
      var btn = pane.querySelector('.mo-btn');
      btn.textContent = playing ? '❚❚ 暫停' : '▶ 播放';
      btn.setAttribute('aria-pressed', playing ? 'true' : 'false');
    }

    // 暫停：滑回最近的一天，滑過去看到的才是那一天真正的數字
    function moPause(pane) {
      if (!mo.playing) return;
      moButton(pane, false);
      moEase(pane, Math.round(mo.t), 250);
    }

    function moPlay(pane) {
      moCancel();
      var end = moDays();
      if (mo.t >= end - 1e-6) mo.t = 0;                      // 已經在今天就從頭播
      moButton(pane, true);
      var smooth = !REDUCED && moBegin(pane);
      var gd = document.getElementById('ov-momentum');
      var prev = null, shownDay = Math.round(mo.t);
      if (smooth) moRender(mo.t);
      var tick = function (now) {
        // 切到別的分頁就停，不要在看不到的地方一直重畫
        if (!shown(gd) || document.hidden) { moPause(pane); return; }
        // 每格最多走 0.1 秒：電腦卡一下時不會整段跳過
        var dt = prev == null ? 0 : Math.min(100, now - prev);
        prev = now;
        mo.t = Math.min(end, mo.t + dt / MO_DAY);
        if (smooth) {
          moRender(mo.t);
        } else if (Math.floor(mo.t) !== shownDay) {
          // 不做動畫（系統設定減少動態效果）時一天換一次
          shownDay = Math.floor(mo.t);
          var keep = mo.t;
          mo.t = shownDay;
          moScatter(pane, mo.rows, mo.top);
          mo.t = keep;
        }
        moLabel(pane);
        if (mo.t >= end) {
          moButton(pane, false);
          moSettle(pane);
          return;
        }
        moRaf = requestAnimationFrame(tick);
      };
      moRaf = requestAnimationFrame(tick);
    }

    function moPlayControls(pane) {
      var btn = pane.querySelector('.mo-btn');
      if (btn._bound) return;
      btn._bound = true;
      btn.addEventListener('click', function () { if (mo.playing) moPause(pane); else moPlay(pane); });
      var slider = pane.querySelector('.mo-slider');
      // 拖動時點跟著手連續移動；放開後滑到最近的那一天
      slider.addEventListener('input', function () {
        moCancel();
        moButton(pane, false);
        mo.t = Number(slider.value);
        if (!REDUCED && moBegin(pane)) {
          moRender(mo.t);
          moLabel(pane);
        } else {
          moSettle(pane);
        }
      });
      slider.addEventListener('change', function () { moEase(pane, Math.round(Number(slider.value)), 200); });
      // 滑桿可以停在兩天中間，方向鍵自己處理成一次一天
      slider.addEventListener('keydown', function (e) {
        var to = {ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1}[e.key];
        if (e.key === 'Home') to = -Infinity;
        if (e.key === 'End') to = Infinity;
        if (to === undefined) return;
        e.preventDefault();
        moButton(pane, false);
        moEase(pane, Math.max(0, Math.min(moDays(), Math.round(mo.t) + to)), 200);
      });
      // 瀏覽器切到背景就停
      document.addEventListener('visibilitychange', function () { if (document.hidden) moPause(pane); });
    }

    function moTable(pane, strong) {
      var box = pane.querySelector('.mo-table');
      box.textContent = '';
      var rows = strong.slice();
      if (mo.sort !== 'a' || !mo.desc) {
        rows.sort(function (a, b) { return mo.desc ? b[mo.sort] - a[mo.sort] : a[mo.sort] - b[mo.sort]; });
      }
      var cols = [['股票', null], ['強度', 's'], ['近 5 日', 'r5'], ['前 5 日', 'p5'], ['加速', 'a'],
                  ['近 20 日', undefined]];
      var t = el('table', 'ov-table scr-table');
      var h = el('tr');
      cols.forEach(function (col) {
        var th = el('th');
        if (!col[1]) { th.textContent = col[0]; h.appendChild(th); return; }
        var on = mo.sort === col[1];
        var b = el('button', 'th-sort', col[0] + (on ? (mo.desc ? ' ↓' : ' ↑') : ''));
        b.type = 'button';
        th.setAttribute('aria-sort', on ? (mo.desc ? 'descending' : 'ascending') : 'none');
        b.addEventListener('click', function () {
          if (mo.sort === col[1]) mo.desc = !mo.desc; else { mo.sort = col[1]; mo.desc = true; }
          moTable(pane, strong);
        });
        th.appendChild(b);
        h.appendChild(th);
      });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      rows.slice(0, mo.shown).forEach(function (r, i) {
        var tr = el('tr', 'go');
        var c0 = el('td');
        c0.appendChild(el('span', 'ov-name', (i + 1) + '.'));
        c0.appendChild(el('span', 'ov-code', ' ' + r.code));
        c0.appendChild(el('span', 'ov-name', r.name));
        var ft = chainTags(r.code)[0];
        c0.appendChild(el('span', 'scr-reason', (ft ? ft[0] : mo.data.industries[r.ind]) + '　·　均量 ' + fmt(r.tv, 1) + ' 億'));
        var fb = flagBadge(r.code);
        if (fb) c0.insertBefore(fb, c0.querySelector('.scr-reason'));
        var why = moWhy(r.code);
        if (why) c0.appendChild(why);
        tr.appendChild(c0);
        [r.s, r.r5, r.p5].forEach(function (v) { tr.appendChild(el('td', dir(v), signed(v, 1, '%'))); });
        tr.appendChild(el('td', dir(r.a), signed(r.a, 1)));
        var c5 = el('td');
        c5.appendChild(sparkSvg(r.c.slice(-21)));
        tr.appendChild(c5);
        tr.setAttribute('aria-expanded', 'false');
        tr.addEventListener('click', function () {
          var next = tr.nextSibling;
          if (next && next.classList.contains('mo-detail')) {
            next.remove();
            tr.setAttribute('aria-expanded', 'false');
          } else {
            tr.parentNode.insertBefore(moDetail(r, cols.length), tr.nextSibling);
            tr.setAttribute('aria-expanded', 'true');
          }
        });
        tb.appendChild(tr);
      });
      t.appendChild(tb); stackTable(t);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
      if (rows.length > mo.shown) {
        var more = el('button', 'scr-more', '再顯示 ' + Math.min(MO_PAGE * 2, rows.length - mo.shown) +
                      ' 檔（共 ' + rows.length + ' 檔）');
        more.type = 'button';
        more.addEventListener('click', function () { mo.shown += MO_PAGE * 2; moTable(pane, strong); });
        box.appendChild(more);
      }
    }

    function moLines(top) {
      var d = mo.data, c = palette(), last = d.dates.length - 1, base = last - 20;
      var x = d.dates.slice(base);
      var traces = top.map(function (r, k) {
        return {type: 'scatter', mode: 'lines', x: x, name: r.name,
                y: r.c.slice(base).map(function (v) { return (v / r.c[base] - 1) * 100; }),
                line: {width: 2, color: MO_COLORS[k % MO_COLORS.length]},
                hovertemplate: '%{y:+.1f}%<extra>' + r.name + '</extra>'};
      });
      if (d.bench && d.bench[base]) {
        traces.push({type: 'scatter', mode: 'lines', x: x, name: '加權指數',
                     y: d.bench.slice(base).map(function (v) { return v == null ? null : (v / d.bench[base] - 1) * 100; }),
                     line: {width: 2, dash: 'dash', color: c.gray},
                     hovertemplate: '%{y:+.1f}%<extra>加權指數</extra>'});
      }
      plot('ov-mo-lines', traces, layout({
        showlegend: true, legend: {orientation: 'h', x: 0, y: -0.18, font: {size: 11}},
        xaxis: {type: 'category', gridcolor: c.grid, nticks: Math.min(6, TICKS), tickangle: 0, automargin: true},
        yaxis: {gridcolor: c.grid, ticksuffix: '%', zeroline: true, zerolinecolor: c.gray,
                automargin: true},
        margin: {l: 52, r: 14, t: 10, b: 30}
      }));
    }

    function moDraw(pane) {
      var rows = moRows();
      var ext = mo.ext ? moExtreme(rows) : null;
      var picked = ext ? rows.filter(function (r) { return ext[r.code]; }) : rows;
      var strong = moStrong(picked);
      var top = strong.slice(0, MO_TOP);
      // 換篩選時先停掉播放，停在最近的整數天
      moCancel();
      mo.render = null;
      var gd = document.getElementById('ov-momentum');
      if (gd) gd.classList.remove('mo-busy');
      moButton(pane, false);
      mo.t = mo.t == null ? moDays() : Math.round(mo.t);
      mo.full = false;
      mo.rows = rows;
      mo.top = top;
      mo.strong = strong;
      pane.querySelector('.mo-count').textContent = ext
        ? '符合 ' + strong.length + ' 檔（今天最極端 ' + Math.round(mo.ext * 100) + '%：' + picked.length +
          ' 檔／目前篩選共 ' + rows.length + ' 檔）'
        : '符合 ' + strong.length + ' 檔（目前篩選共 ' + rows.length + ' 檔）';
      pane.querySelector('.mo-pick').hidden = true;
      moScatter(pane, rows, top);
      moTable(pane, strong);
      moLines(top);
    }

    function moControls(pane) {
      var sel = pane.querySelector('.mo-ind');
      if (sel.options.length) return;
      var all = el('option', null, '全部產業');
      all.value = '-1';
      sel.appendChild(all);
      mo.data.industries.forEach(function (name, i) {
        var n = mo.data.stocks.filter(function (x) { return x[2] === i; }).length;
        if (!n) return;
        var o = el('option', null, name + '（' + n + ' 檔）');
        o.value = String(i);
        sel.appendChild(o);
      });
      var counts = {};
      mo.data.stocks.forEach(function (x) {
        (CHAINS.codes[x[0]] || []).forEach(function (i) { counts[i] = (counts[i] || 0) + 1; });
      });
      Object.keys(counts).forEach(function (i) { if (counts[i] < 2) delete counts[i]; });
      tagOptions(sel, counts, 'f');
      sel.addEventListener('change', function () {
        mo.ind = sel.value.charAt(0) === 'f' ? sel.value : Number(sel.value);
        mo.shown = MO_PAGE;
        moDraw(pane);
      });
      bindChips(pane.querySelector('.mo-liq'), function (chip) {
        mo.min = Number(chip.dataset.min);
        mo.shown = MO_PAGE;
        moDraw(pane);
      });
      bindChips(pane.querySelector('.mo-ext'), function (chip) {
        mo.ext = Number(chip.dataset.ext);
        mo.shown = MO_PAGE;
        pane.querySelector('.mo-ext-note').hidden = !mo.ext;
        moDraw(pane);
      });
    }

    function moNewsMeta(pane) {
      var m = mo.newsMeta, note = pane.querySelector('.mo-news-meta');
      if (!m || !m.stocks || !Object.keys(m.stocks).length) { note.hidden = true; return; }
      note.textContent = '上漲原因：' + (m.model ? m.model + ' 整理' : '標題關鍵字挑選（尚未設定 Claude）') +
        '，近五個交易日（' + md(m.since) + ' 起）的新聞與重大訊息　·　更新於 ' + m.generated;
      note.hidden = false;
    }

    function momentum(pane) {
      loadFlags().then(function () { if (mo.data) moTable(pane, mo.strong); });
      // 新聞另外載入：抓不到也不影響圖表，晚到就補畫排行
      getJSON('data/stocknews.json').then(function (n) {
        if (mo.newsMeta === n) return;
        mo.newsMeta = n;
        mo.news = (n && n.stocks) || {};
        moNewsMeta(pane);
        if (mo.data) moTable(pane, mo.strong);
      }, function () {});
      return Promise.all([getJSON('data/momentum.json'), loadChains()]).then(function (res) {
        var d = res[0];
        mo.data = d;
        pane.querySelector('.ov-asof').textContent = '資料日期 ' + md(d.asof) + ' 盤後';
        var hint = pane.querySelector('.zoom-hint');
        hint.textContent = COARSE ? '點圓點看那一檔的數字。'
                                  : '點圓點打開個股頁；拖曳框選放大、雙擊還原（再雙擊看全部）。';
        moControls(pane);
        moPlayControls(pane);
        moDraw(pane);
      });
    }

    // ── 強勢紀錄：每天強勢股的上漲原因、是否族群連動、同族群個股 ────────────
    // record/{日期}.json 的 rows 欄位
    var R_CODE = 0, R_NAME = 1, R_RANK = 2, R_S = 4, R_R5 = 5, R_TAG = 7, R_WHY = 8,
        R_METHOD = 10, R_GROUP = 11, R_LINKED = 12, R_MEMBERS = 13, R_KEY_T = 14, R_KEY_U = 15,
        R_KEY_SRC = 16;
    var rec = {index: null, date: null, theme: null, query: ''};

    function recDay(d) { return getJSON('data/record/' + d + '.json'); }

    function rgba(hex, a) {
      var n = parseInt(hex.slice(1), 16);
      return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
    }

    function recStockLink(code, name, extra) {
      var b = el('button', 'rec-stock', name + ' ' + code + (extra || ''));
      b.type = 'button';
      b.addEventListener('click', function (e) { e.stopPropagation(); openStock(code); });
      return b;
    }

    function recKeyNews(row) {
      if (!row[R_KEY_T]) return null;
      var p = el('p', 'rec-key');
      p.appendChild(el('span', 'mo-item-src', row[R_KEY_SRC] || '新聞'));
      // 原因就是這則標題時（沒有 Claude 的關鍵字挑選）只留來源與原文連結，不重複一次
      var same = row[R_KEY_T].slice(0, 30) === String(row[R_WHY] || '').slice(0, 30);
      if (row[R_KEY_SRC] === '重大訊息') {
        if (!same) p.appendChild(el('span', null, row[R_KEY_T]));
      } else {
        var a = el('a', null, same ? '原文 ↗' : row[R_KEY_T]);
        a.href = row[R_KEY_U] || 'https://www.google.com/search?tbm=nws&q=' +
                 encodeURIComponent('"' + row[R_KEY_T] + '"');
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        p.appendChild(a);
      }
      return p;
    }

    // 一檔強勢股：名稱、漲幅、原因、關鍵新聞
    function recRow(row, showGroup) {
      var box = el('div', 'rec-row');
      var head = el('div', 'rec-row-head');
      head.appendChild(recStockLink(row[R_CODE], row[R_NAME]));
      head.appendChild(el('span', 'rec-num ' + dir(row[R_R5]), '近 5 日 ' + signed(row[R_R5], 1, '%')));
      head.appendChild(el('span', 'rec-num', '20 日 ' + signed(row[R_S], 1, '%')));
      if (row[R_RANK]) head.appendChild(el('span', 'rec-num', '第 ' + row[R_RANK] + ' 名'));
      var fb = flagBadge(row[R_CODE]);
      if (fb) head.appendChild(fb);
      if (showGroup && row[R_GROUP]) {
        head.appendChild(el('span', row[R_LINKED] ? 'rec-badge is-linked' : 'rec-badge',
                            row[R_GROUP] + (row[R_LINKED] ? '・族群連動' : '・個股')));
      }
      box.appendChild(head);
      var why = el('p', 'rec-why');
      why.appendChild(el('b', 'mo-tag', row[R_TAG]));
      why.appendChild(document.createTextNode(row[R_WHY] || '—'));
      box.appendChild(why);
      var key = recKeyNews(row);
      if (key) box.appendChild(key);
      return box;
    }

    // 同族群但不在強勢股名單的個股（新聞提到或股價同步）
    var REC_CHIPS = 20;

    function recMembers(members, skip) {
      var wrap = el('div', 'rec-members');
      var seen = {}, more = 0;
      members.slice().sort(function (a, b) { return (b[5] - a[5]) || ((b[2] || 0) - (a[2] || 0)); })
        .forEach(function (m) {
        if (skip[m[0]] || seen[m[0]]) return;
        seen[m[0]] = true;
        if (Object.keys(seen).length > REC_CHIPS) { more++; return; }
        var chip = recStockLink(m[0], m[1], ' ' + signed(m[2], 1, '%'));
        chip.title = (m[3] == null ? '' : '近 20 日相關係數 ' + m[3]) + (m[5] ? '　新聞有提到' : '');
        if (m[5]) chip.classList.add('is-named');
        wrap.appendChild(chip);
      });
      if (more) wrap.appendChild(el('span', 'rec-more', '還有 ' + more + ' 檔'));
      wrap.total = Object.keys(seen).length;
      return wrap.childNodes.length ? wrap : null;
    }

    function recGroups(rows) {
      var groups = {}, order = [];
      rows.forEach(function (row) {
        if (!row[R_LINKED] || !row[R_GROUP]) return;
        var g = row[R_GROUP];
        if (!groups[g]) { groups[g] = {name: g, rows: [], members: []}; order.push(g); }
        groups[g].rows.push(row);
        groups[g].members = groups[g].members.concat(row[R_MEMBERS] || []);
      });
      return order.map(function (g) { return groups[g]; })
        .sort(function (a, b) { return b.rows.length - a.rows.length; });
    }

    // 一檔一行：排名、名稱、族群、原因（一行）、20 日漲幅；點一下展開原因、關鍵新聞與同族群
    var REC_PAGE = 15;
    rec.shown = REC_PAGE;

    function recLine(row, skip) {
      var item = el('div', 'rec-item');
      var line = el('button', 'rec-line');
      line.type = 'button';
      line.setAttribute('aria-expanded', 'false');
      line.appendChild(el('span', 'rec-rk num', row[R_RANK] ? String(row[R_RANK]) : '自選'));
      var nm = el('span', 'rec-nm');
      var top = el('span', 'rec-top');
      top.appendChild(el('b', null, row[R_CODE] + ' ' + row[R_NAME]));
      if (row[R_LINKED] && row[R_GROUP]) top.appendChild(el('span', 'rec-tag', row[R_GROUP]));
      var fb = flagBadge(row[R_CODE]);
      if (fb) top.appendChild(fb);
      nm.appendChild(top);
      nm.appendChild(el('span', 'rec-why1', (row[R_TAG] ? row[R_TAG] + '：' : '') + (row[R_WHY] || '—')));
      line.appendChild(nm);
      line.appendChild(el('span', 'rec-r20 num ' + dir(row[R_S]), signed(row[R_S], 1, '%')));
      item.appendChild(line);
      var detail = el('div', 'rec-detail');
      detail.hidden = true;
      line.addEventListener('click', function () {
        if (!detail.childNodes.length) {
          detail.appendChild(recRow(row, true));
          var others = recMembers(row[R_MEMBERS] || [], skip);
          if (others) {
            detail.appendChild(el('p', 'rec-label', '同族群也在漲（不在強勢股名單；粗體是新聞有提到的）'));
            detail.appendChild(others);
          }
        }
        detail.hidden = !detail.hidden;
        line.setAttribute('aria-expanded', String(!detail.hidden));
      });
      item.appendChild(detail);
      return item;
    }

    function recShowDay(pane, day) {
      var body = pane.querySelector('.rec-body');
      body.textContent = '';
      var rows = day.rows.slice().sort(function (a, b) { return (a[R_RANK] || 999) - (b[R_RANK] || 999); });
      var groups = recGroups(rows);
      var linked = rows.filter(function (r) { return r[R_LINKED]; }).length;
      var solo = rows.length - linked;
      var rules = rows.length && rows.every(function (r) { return r[R_METHOD] !== 'claude'; });
      pane.querySelector('.rec-sum').textContent = md(day.date) + '：強勢股 ' + rows.length + ' 檔，族群連動 ' +
        linked + ' 檔、' + groups.length + ' 個族群' +
        (rules ? '（尚未設定 Claude，族群暫以官方產業別＋股價相關判斷）' : '');
      // 族群篩選：全部／各族群／個股行情
      var bar = el('div', 'rec-filter');
      var opts = [[null, '全部', rows.length]].concat(groups.map(function (g) { return [g.name, g.name, g.rows.length]; }));
      if (solo) opts.push(['__solo', '個股行情', solo]);
      if (rec.theme && !opts.some(function (o) { return o[0] === rec.theme; })) rec.theme = null;
      opts.forEach(function (o) {
        var c = el('button', 'chip');
        c.type = 'button';
        c.setAttribute('aria-pressed', String(rec.theme === o[0]));
        c.appendChild(document.createTextNode(o[1] + ' '));
        c.appendChild(el('b', null, String(o[2])));
        c.addEventListener('click', function () {
          rec.theme = o[0];
          rec.shown = REC_PAGE;
          recShowDay(pane, day);
        });
        bar.appendChild(c);
      });
      body.appendChild(bar);
      var list = rows.filter(function (r) {
        if (!rec.theme) return true;
        if (rec.theme === '__solo') return !r[R_LINKED];
        return r[R_LINKED] && r[R_GROUP] === rec.theme;
      });
      var skip = {};
      rows.forEach(function (r) { skip[r[R_CODE]] = true; });
      var box = el('div', 'rec-list ov-card');
      list.slice(0, rec.shown).forEach(function (r) { box.appendChild(recLine(r, skip)); });
      body.appendChild(box);
      if (list.length > rec.shown) {
        var more = el('button', 'scr-more', '再看 ' + Math.min(REC_PAGE, list.length - rec.shown) + ' 檔（共 ' + list.length + ' 檔）');
        more.type = 'button';
        more.addEventListener('click', function () { rec.shown += REC_PAGE; recShowDay(pane, day); });
        body.appendChild(more);
      }
    }

    // 查一檔股票：列出它每一次上榜的原因與族群（新到舊，最多 20 次）
    function recSearch(pane) {
      var body = pane.querySelector('.rec-body');
      var ix = rec.index, q = rec.query.trim();
      var hits = Object.keys(ix.stocks).filter(function (code) {
        return code.indexOf(q) === 0 || ix.stocks[code][0].indexOf(q) >= 0;
      }).slice(0, 5);
      pane.querySelector('.rec-sum').textContent = hits.length
        ? '「' + q + '」：' + hits.map(function (c) { return ix.stocks[c][0] + ' ' + c; }).join('、')
        : '「' + q + '」在有新聞紀錄的日子（' + md(ix.dates[0]) + ' 起）沒有上過強勢股名單。';
      body.textContent = '';
      var want = {};
      hits.forEach(function (code) {
        ix.stocks[code][1].slice(-20).forEach(function (i) { want[ix.dates[i]] = true; });
      });
      var dates = Object.keys(want).sort().reverse();
      return Promise.all(dates.map(recDay)).then(function (days) {
        if (rec.query.trim() !== q) return;
        body.textContent = '';
        days.forEach(function (day) {
          day.rows.forEach(function (row) {
            if (hits.indexOf(row[R_CODE]) < 0) return;
            var item = el('div', 'rec-hist');
            item.appendChild(el('p', 'rec-date', md(day.date)));
            item.appendChild(recRow(row, true));
            var members = recMembers(row[R_MEMBERS] || [], {});
            if (members) item.appendChild(members);
            body.appendChild(item);
          });
        });
      });
    }

    // 上榜次數排行：依收盤重算的每日名單（近 20／60／120 個交易日）
    // rows：[代號, 名稱, 產業, 20日次數, 60日次數, 120日次數, 連續天數, 最後上榜序號, 族群連動次數, 常見族群]
    var REC_FREQ_PAGE = window.innerWidth < 820 ? 15 : 30;
    rec.win = 1;                 // 預設看近 60 日
    rec.freqShown = REC_FREQ_PAGE;

    function recFreqRows() {
      var f = rec.index.freq, col = 3 + rec.win;
      return f.rows.filter(function (r) { return r[col] > 0; }).sort(function (a, b) {
        return (b[col] - a[col]) || (b[6] - a[6]) || (b[7] - a[7]);
      });
    }

    function recFreqChart(rows) {
      var gd = document.getElementById('ov-record-freq'), c = palette();
      var f = rec.index.freq, n = f.windows[rec.win], col = 3 + rec.win;
      var top = rows.slice(0, 15).reverse();
      if (!top.length) { gd.hidden = true; return; }
      gd.hidden = false;
      gd.style.height = (50 + 26 * top.length) + 'px';
      Plotly.react(gd, [{
        type: 'bar', orientation: 'h',
        y: top.map(function (r) { return r[1] + ' ' + r[0]; }),
        x: top.map(function (r) { return r[col]; }),
        marker: {color: top.map(function (r) { return r[6] > 0 ? c.up : c.blue; })},
        text: top.map(function (r) { return r[col] + ' 次' + (r[6] > 0 ? '・連續 ' + r[6] + ' 天' : ''); }),
        textposition: 'outside', cliponaxis: false, textfont: {size: 11, color: c.text},
        hovertemplate: '%{y}<br>近 ' + n + ' 日上榜 %{x} 次<extra></extra>'
      }], layout({
        margin: {l: 10, r: 110, t: 6, b: 28},
        xaxis: {range: [0, Math.max.apply(null, top.map(function (r) { return r[col]; })) * 1.15 + 1],
                gridcolor: c.grid, fixedrange: true, title: {text: '上榜次數', font: {size: 11}}},
        yaxis: {automargin: true, fixedrange: true}
      }), {displayModeBar: false, responsive: true});
    }

    function recFreqTable(pane, rows) {
      var box = pane.querySelector('.rec-freq');
      box.textContent = '';
      var f = rec.index.freq, n = f.windows[rec.win], col = 3 + rec.win;
      var t = el('table', 'ov-table rec-freq-tbl');
      var h = el('tr');
      ['股票', '近 ' + n + ' 日上榜', '連續', '最近上榜', '族群連動', '常見族群'].forEach(function (x) {
        h.appendChild(el('th', null, x));
      });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      rows.slice(0, rec.freqShown).forEach(function (r, i) {
        var tr = el('tr', 'go');
        var c0 = el('td');
        c0.appendChild(el('span', 'ov-name', (i + 1) + '.'));
        c0.appendChild(recStockLink(r[0], r[1]));
        var fb = flagBadge(r[0]);
        if (fb) c0.appendChild(fb);
        c0.appendChild(el('span', 'scr-reason', r[2]));
        tr.appendChild(c0);
        var cnt = el('td');
        cnt.appendChild(el('b', null, String(r[col])));
        cnt.appendChild(el('span', 'scr-reason', '占 ' + Math.round(r[col] / n * 100) + '% 的交易日'));
        tr.appendChild(cnt);
        tr.appendChild(el('td', r[6] > 0 ? 'up' : null, r[6] > 0 ? r[6] + ' 天' : '—'));
        tr.appendChild(el('td', null, r[7] >= 0 ? md(f.dates[r[7]]) : '—'));
        tr.appendChild(el('td', null, r[8] ? r[8] + ' 次' : '—'));
        tr.appendChild(el('td', null, r[9] || '—'));
        // 點一列：在下面列出這檔的強勢紀錄（有新聞紀錄的日子）
        tr.addEventListener('click', function () {
          var input = pane.querySelector('.rec-search');
          input.value = r[0];
          rec.query = r[0];
          rec.theme = null;
          recShow(pane);
          pane.querySelector('.rec-sum').scrollIntoView({block: 'center', behavior: 'smooth'});
        });
        tb.appendChild(tr);
      });
      t.appendChild(tb); stackTable(t);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
      if (rows.length > rec.freqShown) {
        var more = el('button', 'scr-more', '再顯示 ' + Math.min(REC_FREQ_PAGE, rows.length - rec.freqShown) +
                      ' 檔（共 ' + rows.length + ' 檔）');
        more.type = 'button';
        more.addEventListener('click', function () { rec.freqShown += REC_FREQ_PAGE; recFreqTable(pane, rows); });
        box.appendChild(more);
      }
    }

    function recFreq(pane) {
      var f = rec.index.freq;
      var sec = pane.querySelector('.rec-freq-sec');
      if (!f || !f.rows || !f.rows.length) { sec.hidden = true; return; }
      sec.hidden = false;
      pane.querySelector('.rec-freq-note').textContent =
        '名單依每天收盤重算（和強勢紀錄相同的條件：近 20 日上漲、近 5 日漲得比前 5 日多、均量 0.3 億以上、' +
        '依加速度前 60 名），所以能往回看 ' + md(f.dates[0]) + ' 起的 ' + f.dates.length + ' 個交易日。' +
        '紅色是到最新一天仍連續在榜。族群連動次數只算有新聞紀錄的日子' + (f.since ? '（' + md(f.since) + ' 起）' : '') +
        '。點一列在下面看它的強勢紀錄。';
      var chips = pane.querySelector('.rec-win');
      if (!chips._bound) {
        chips._bound = true;
        bindChips(chips, function (chip) {
          rec.win = Number(chip.dataset.win);
          rec.freqShown = REC_FREQ_PAGE;
          recFreq(pane);
        });
      }
      var rows = recFreqRows();
      recFreqChart(rows);
      recFreqTable(pane, rows);
    }

    function recShow(pane) {
      if (rec.query.trim()) return recSearch(pane);
      return recDay(rec.date).then(function (day) { recShowDay(pane, day); });
    }

    function recHeat(pane) {
      var ix = rec.index, c = palette();
      var gd = document.getElementById('ov-record-heat');
      var note = pane.querySelector('.rec-heat-note');
      if (!ix.themes.length) {
        gd.hidden = true;
        note.textContent = '還沒有被判定為族群連動的紀錄。';
        return;
      }
      gd.hidden = false;
      note.textContent = '每一格是那天被判定為族群連動的強勢股檔數；點一格看那天那個族群。';
      var x = ix.dates.map(function (d) { return d.slice(5).replace('-', '/'); });
      var y = ix.themes.map(function (t) { return t[0]; });
      var z = ix.themes.map(function (t) { return t[1].map(function (v) { return v || null; }); });
      gd.style.height = (70 + 26 * y.length) + 'px';
      var L = layout({
        margin: {l: 10, r: 10, t: 6, b: 40},
        xaxis: {type: 'category', tickangle: 0, nticks: COARSE ? 6 : 12, gridcolor: 'rgba(0,0,0,0)',
                fixedrange: true},
        yaxis: {type: 'category', autorange: 'reversed', automargin: true, fixedrange: true,
                gridcolor: 'rgba(0,0,0,0)'},
        hovermode: 'closest'
      });
      Plotly.react(gd, [{
        type: 'heatmap', x: x, y: y, z: z, zmin: 1, xgap: 2, ygap: 2, showscale: false,
        colorscale: [[0, rgba(c.up, 0.25)], [1, c.up]],
        texttemplate: '%{z}', textfont: {size: 10, color: c.text},
        hovertemplate: '%{y}　%{x}<br>族群連動 %{z} 檔<extra></extra>'
      }], L, {displayModeBar: false, responsive: true});
      if (!gd._recBound) {
        gd._recBound = true;
        gd.on('plotly_click', function (ev) {
          var p = ev && ev.points && ev.points[0];
          if (!p || p.z == null) return;
          rec.date = rec.index.dates[p.pointIndex[1]];
          rec.theme = p.y;
          rec.query = '';
          rec.shown = REC_PAGE;
          pane.querySelector('.rec-search').value = '';
          pane.querySelector('.rec-date').value = rec.date;
          recShow(pane).then(function () {
            pane.querySelector('.rec-sum').scrollIntoView({block: 'center', behavior: 'smooth'});
          });
        });
      }
    }

    function recControls(pane) {
      var sel = pane.querySelector('.rec-date');
      var ix = rec.index;
      sel.textContent = '';
      ix.dates.slice().reverse().forEach(function (d) {
        var sm = ix.summary[ix.dates.indexOf(d)] || [0, 0, 0];
        var o = el('option', null, md(d) + '　強勢股 ' + sm[0] + ' 檔・連動 ' + sm[1]);
        o.value = d;
        sel.appendChild(o);
      });
      sel.value = rec.date;
      if (sel._bound) return;
      sel._bound = true;
      sel.addEventListener('change', function () {
        rec.date = sel.value;
        rec.theme = null;
        rec.query = '';
        pane.querySelector('.rec-search').value = '';
        recShow(pane);
      });
      var input = pane.querySelector('.rec-search'), timer = null;
      input.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          rec.query = input.value;
          rec.theme = null;
          recShow(pane);
        }, 250);
      });
    }

    function recToggles(pane) {
      Array.prototype.slice.call(pane.querySelectorAll('.sec-toggle')).forEach(function (b) {
        if (b._bound) return;
        b._bound = true;
        b.addEventListener('click', function () {
          var box = pane.querySelector('.' + b.dataset.box);
          box.hidden = !box.hidden;
          b.setAttribute('aria-expanded', String(!box.hidden));
          if (box.hidden) return;
          if (b.dataset.box === 'rec-heat-box') recHeat(pane); else recFreq(pane);
        });
      });
    }

    function record(pane) {
      return loadFlags().then(function () { return getJSON('data/record/index.json'); }).then(function (ix) {
        rec.index = ix;
        if (!ix.dates.length) {
          pane.querySelector('.rec-sum').textContent = '還沒有紀錄：每天盤後整理強勢股新聞時會自動累積。';
          document.getElementById('ov-record-heat').hidden = true;
          return;
        }
        if (!rec.date || ix.dates.indexOf(rec.date) < 0) rec.date = ix.dates[ix.dates.length - 1];
        pane.querySelector('.ov-asof').textContent = '紀錄 ' + md(ix.dates[0]) + ' ～ ' +
          md(ix.dates[ix.dates.length - 1]) + '，共 ' + ix.dates.length + ' 個交易日';
        recControls(pane);
        recToggles(pane);
        if (!pane.querySelector('.rec-heat-box').hidden) recHeat(pane);
        if (!pane.querySelector('.rec-freq-sec').hidden) recFreq(pane);
        return recShow(pane);
      });
    }

    // ── 訊號績效：新進榜後 5／10／20 日的報酬、勝率、超額報酬 ────────────
    var pf = {data: null, h: '20', pick: null};

    function pfSignals() {
      return pf.data.signals.filter(function (s) { return (s.stats[pf.h] || {}).n; });
    }

    function pfVerdictClass(v) {
      return v === '優於大盤' ? 'is-good' : v === '輸給大盤' ? 'is-bad' : '';
    }

    function perfBars(pane) {
      var c = palette(), gd = document.getElementById('ov-perf-bars');
      var list = pfSignals().slice().reverse();          // 橫條由上往下照原本順序
      if (!list.length) { gd.hidden = true; return; }
      gd.hidden = false;
      var x = list.map(function (s) { return s.stats[pf.h].exc; });
      gd.style.height = (60 + 34 * list.length) + 'px';
      Plotly.react(gd, [{
        type: 'bar', orientation: 'h', y: list.map(function (s) { return s.name; }), x: x,
        marker: {color: x.map(function (v) { return v >= 0 ? c.up : c.down; })},
        text: x.map(function (v) { return signed(v, 2, '%'); }),
        customdata: list.map(function (s) { var st = s.stats[pf.h]; return [st.beat, st.n, st.win]; }),
        textposition: 'outside', cliponaxis: false, textfont: {size: 11, color: c.text},
        hovertemplate: '%{y}<br>平均超額報酬 %{x:+.2f}%<br>勝過大盤 %{customdata[0]:.0f}%　勝率 ' +
                       '%{customdata[2]:.0f}%　%{customdata[1]} 次<extra></extra>'
      }], layout({
        margin: {l: 10, r: 20, t: 8, b: 30},
        // 左右留空間給數字標籤，負的長條標籤才不會壓到訊號名稱
        xaxis: {ticksuffix: '%', zeroline: true, zerolinecolor: c.gray, gridcolor: c.grid, fixedrange: true,
                range: [Math.min(0, Math.min.apply(null, x)) * 1.6 - 0.4, Math.max(0, Math.max.apply(null, x)) * 1.35 + 0.4]},
        yaxis: {automargin: true, fixedrange: true}
      }), {displayModeBar: false, responsive: true});
    }

    function perfTable(pane) {
      var box = pane.querySelector('.pf-table');
      box.textContent = '';
      var t = el('table', 'ov-table scr-table pf-tbl');
      var h = el('tr');
      ['訊號', '方式', '次數', '平均報酬', '平均超額', '勝率', '勝過大盤', '判讀'].forEach(function (x) {
        h.appendChild(el('th', null, x));
      });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      pf.data.signals.forEach(function (s) {
        var st = s.stats[pf.h] || {n: 0};
        var tr = el('tr', 'go' + (pf.pick === s.id ? ' is-picked' : ''));
        var c0 = el('td');
        c0.appendChild(el('span', 'ov-name', s.name));
        c0.appendChild(el('span', 'scr-reason', s.desc));
        tr.appendChild(c0);
        tr.appendChild(el('td', null, s.mode + (s.mode === '追蹤' && s.since ? '（' + md(s.since) + ' 起）' : '')));
        tr.appendChild(el('td', null, st.n ? String(st.n) : '—'));
        tr.appendChild(el('td', dir(st.ret), st.n ? signed(st.ret, 2, '%') : '—'));
        tr.appendChild(el('td', dir(st.exc), st.n ? signed(st.exc, 2, '%') : '—'));
        tr.appendChild(el('td', null, st.n ? fmt(st.win, 1) + '%' : '—'));
        tr.appendChild(el('td', null, st.n ? fmt(st.beat, 1) + '%' : '—'));
        var v = el('td');
        v.appendChild(el('span', 'pf-verdict ' + pfVerdictClass(st.verdict),
                         st.n ? st.verdict : (s.mode === '追蹤' ? '累積中' : '—')));
        tr.appendChild(v);
        tr.addEventListener('click', function () { pf.pick = s.id; perfTable(pane); perfRecent(pane); });
        tb.appendChild(tr);
      });
      t.appendChild(tb); stackTable(t);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
    }

    function perfMonthly(pane) {
      var c = palette(), gd = document.getElementById('ov-perf-monthly');
      var hi = pf.data.horizons.indexOf(Number(pf.h)) + 1;
      var colors = [c.up, c.blue, c.orange, c.purple, c.gray, '#0c8599', '#5c940d', '#ae3ec9', '#d6336c'];
      var traces = [];
      pf.data.signals.forEach(function (s, i) {
        if (!s.monthly.some(function (m) { return m[hi] != null; })) return;   // 還在累積、沒有到期的不畫
        traces.push({type: 'scatter', mode: 'lines+markers', name: s.name,
                     x: s.monthly.map(function (m) { return m[0]; }),
                     y: s.monthly.map(function (m) { return m[hi]; }),
                     line: {color: colors[i % colors.length], width: 2}, marker: {size: 5},
                     hovertemplate: s.name + '　%{x}<br>平均超額 %{y:+.2f}%<extra></extra>'});
      });
      if (!traces.length) { gd.hidden = true; return; }
      gd.hidden = false;
      Plotly.react(gd, traces, layout({
        showlegend: true, legend: {orientation: 'h', y: -0.25, font: {size: 11}},
        margin: {l: 48, r: 10, t: 8, b: 70},
        xaxis: {type: 'category', fixedrange: true},
        yaxis: {ticksuffix: '%', zeroline: true, zerolinecolor: c.gray, gridcolor: c.grid, fixedrange: true},
        hovermode: 'closest'
      }), {displayModeBar: false, responsive: true});
    }

    function perfRecent(pane) {
      var box = pane.querySelector('.pf-recent');
      box.textContent = '';
      var s = pf.data.signals.filter(function (x) { return x.id === pf.pick; })[0];
      pane.querySelector('.pf-recent-h').textContent = s ? '最近的訊號：' + s.name : '最近的訊號';
      if (!s || !s.recent.length) {
        box.appendChild(el('p', 'sd-note', s && s.mode === '追蹤' ? '還在累積：每天盤後記錄，之後才看得到報酬。' : '沒有資料。'));
        return;
      }
      var t = el('table', 'ov-table');
      var h = el('tr');
      ['日期', '股票', '5 日', '10 日', '20 日'].forEach(function (x) { h.appendChild(el('th', null, x)); });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var tb = el('tbody');
      s.recent.forEach(function (r, i) {
        var tr = el('tr', 'go');
        tr.hidden = i >= FIRST_ROWS;
        tr.appendChild(el('td', null, md(r[0])));
        var c1 = el('td');
        c1.appendChild(el('span', 'ov-code', r[1]));
        c1.appendChild(el('span', 'ov-name', r[2]));
        tr.appendChild(c1);
        [r[3], r[4], r[5]].forEach(function (v) {
          tr.appendChild(el('td', dir(v), v == null ? '未到期' : signed(v, 1, '%')));
        });
        tr.addEventListener('click', function () { openStock(r[1]); });
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
      moreRows(box, tb);
      box.appendChild(el('p', 'sd-note', '報酬已扣來回成本；「未到期」是持有天數還沒滿。'));
    }

    function perfDraw(pane) {
      perfBars(pane);
      perfTable(pane);
      var mbox = pane.querySelector('.pf-monthly-box'), mbtn = pane.querySelector('.pf-monthly-toggle');
      if (mbtn && !mbtn._bound) {
        mbtn._bound = true;
        mbtn.addEventListener('click', function () {
          mbox.hidden = !mbox.hidden;
          mbtn.setAttribute('aria-expanded', String(!mbox.hidden));
          if (!mbox.hidden) perfMonthly(pane);
        });
      }
      if (!mbox || !mbox.hidden) perfMonthly(pane);
      perfRecent(pane);
    }

    function perf(pane) {
      return getJSON('data/perf.json').then(function (d) {
        pf.data = d;
        if (!d.signals || !d.signals.length) {
          pane.querySelector('.ov-asof').textContent = '還沒有資料。';
          return;
        }
        if (!pf.pick) pf.pick = d.signals[0].id;
        pane.querySelector('.ov-asof').textContent = '回測 ' + md(d.start) + ' ～ ' + md(d.asof) +
          '　·　來回成本 ' + d.cost + '%';
        var chips = pane.querySelector('.pf-h');
        if (!chips._bound) {
          chips._bound = true;
          bindChips(chips, function (chip) { pf.h = chip.dataset.h; perfDraw(pane); });
        }
        perfDraw(pane);
      });
    }

    // ── 持股風控：持股只存在這個瀏覽器（localStorage），不會上傳 ─────────────
    var HOLD_KEY = 'dash-holdings-v1', RISK_KEY = 'dash-risk-v1';
    var hd = {list: [], risk: {capital: 0, riskPct: 1, groupMax: 30}, shards: {}, names: null,
              groups: {}, editing: null, confirmClear: false};

    function hdLoad() {
      try { hd.list = JSON.parse(localStorage.getItem(HOLD_KEY) || '[]') || []; } catch (e) { hd.list = []; }
      try {
        var r = JSON.parse(localStorage.getItem(RISK_KEY) || 'null');
        if (r) hd.risk = {capital: +r.capital || 0, riskPct: +r.riskPct || 1, groupMax: +r.groupMax || 30};
      } catch (e) { /* 沒有設定就用預設 */ }
    }
    function hdSave() {
      try {
        localStorage.setItem(HOLD_KEY, JSON.stringify(hd.list));
        localStorage.setItem(RISK_KEY, JSON.stringify(hd.risk));
      } catch (e) { /* 私密瀏覽等情況存不了，畫面照常 */ }
    }

    function hdShard(code) {
      if (!hd.shards[code]) {
        hd.shards[code] = fetch('data/stock/' + encodeURIComponent(code) + '.json?v=' + VERSION)
          .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .catch(function (e) { delete hd.shards[code]; throw e; });
      }
      return hd.shards[code];
    }

    // 近 14 日平均真實波幅（ATR）
    function hdAtr(d, n) {
      n = n || 14;
      var c = d.c, h = d.h, l = d.l, tr = [];
      for (var i = 1; i < c.length; i++) {
        if (h[i] == null || l[i] == null || c[i - 1] == null) continue;
        tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1])));
      }
      var last = tr.slice(-n);
      return last.length ? last.reduce(function (a, b) { return a + b; }, 0) / last.length : null;
    }

    // 一檔持股的現況（價格用最新收盤；報酬沒有計入已領股利）
    function hdRow(h, s) {
      var d = s.d, n = d.c.length - 1, last = d.c[n], prev = d.c[n - 1];
      var atr = hdAtr(d);
      var stop = h.stop > 0 ? h.stop : (atr ? Math.max(0, h.cost - 2 * atr) : null);
      var value = last * h.qty, pnl = (last - h.cost) * h.qty;
      var g = hd.groups[h.code];
      return {h: h, name: s.name, last: last, chg: prev ? (last / prev - 1) * 100 : null,
              value: value, pnl: pnl, pnlPct: (last / h.cost - 1) * 100, atr: atr, stop: stop,
              stopAuto: !(h.stop > 0), gap: stop ? (last / stop - 1) * 100 : null,
              group: g ? g[0] : (s.industry || '其他'), groupLinked: g ? g[1] : false,
              flag: s.flag || null, d: d};
    }

    function hdStatus(r) {
      if (r.stop && r.last <= r.stop) return ['觸及停損', 'is-bad'];
      if (r.gap != null && r.gap < 3) return ['接近停損', 'is-warn'];
      return null;
    }

    function hdSummary(pane, rows) {
      var box = pane.querySelector('.hd-summary');
      box.textContent = '';
      var value = 0, cost = 0;
      rows.forEach(function (r) { value += r.value; cost += r.h.cost * r.h.qty; });
      var pnl = value - cost;
      var tiles = [['持股市值', fmt(value, 0) + ' 元', rows.length + ' 檔'],
                   ['未實現損益', signed(pnl, 0) + ' 元', signed(cost ? pnl / cost * 100 : null, 2, '%'), dir(pnl)]];
      if (hd.risk.capital > 0) {
        tiles.push(['持股比重', fmt(value / hd.risk.capital * 100, 1) + '%',
                    '總資金 ' + fmt(hd.risk.capital, 0) + ' 元']);
      }
      tiles.forEach(function (t) {
        var b = el('div', 'ck-tile');
        b.appendChild(el('span', 'ck-tile-k', t[0]));
        b.appendChild(el('b', t[3] || '', t[1]));
        b.appendChild(el('span', 'ck-tile-d', t[2]));
        box.appendChild(b);
      });
      return {value: value, cost: cost};
    }

    function hdAlerts(pane, rows, total) {
      var box = pane.querySelector('.hd-alerts');
      box.textContent = '';
      var msgs = [];
      rows.forEach(function (r) {
        var st = hdStatus(r);
        if (st) msgs.push([st[1], r.h.code + ' ' + r.name + ' ' + st[0] + '：收盤 ' + fmt(r.last, 2) +
                                  '，停損 ' + fmt(r.stop, 2) + (r.stopAuto ? '（預設：成本 − 2 × ATR）' : '')]);
        if (r.flag) msgs.push(['is-warn', r.h.code + ' ' + r.name + ' 是' + r.flag[0] + '股' +
                               (r.flag[0] === '處置' ? '（' + r.flag[1] + '～' + r.flag[2] + '，交易受限）' : '')]);
      });
      var by = {};
      rows.forEach(function (r) { by[r.group] = (by[r.group] || 0) + r.value; });
      Object.keys(by).forEach(function (g) {
        var pct = total.value ? by[g] / total.value * 100 : 0;
        if (pct > hd.risk.groupMax && rows.length > 1) {
          msgs.push(['is-warn', '「' + g + '」占持股 ' + fmt(pct, 1) + '%，超過上限 ' + hd.risk.groupMax + '%']);
        }
      });
      if (!msgs.length) {
        box.appendChild(el('p', 'sd-note', rows.length ? '沒有觸及停損、沒有超過族群上限。' : ''));
        return;
      }
      var ul = el('ul', 'ck-list hd-warn');
      msgs.forEach(function (m) { ul.appendChild(el('li', m[0], m[1])); });
      box.appendChild(ul);
    }

    function hdTable(pane, rows) {
      var box = pane.querySelector('.hd-table');
      box.textContent = '';
      if (!rows.length) {
        box.appendChild(el('p', 'ov-empty', '還沒有持股。用下面的表單加入第一筆（只會存在這個瀏覽器）。'));
        return;
      }
      var t = el('table', 'ov-table');
      var hr = el('tr');
      ['股票', '股數', '成本', '收盤', '損益', '停損', '族群', ''].forEach(function (x) { hr.appendChild(el('th', null, x)); });
      var thead = el('thead'); thead.appendChild(hr); t.appendChild(thead);
      var tb = el('tbody');
      rows.forEach(function (r) {
        var tr = el('tr');
        var c0 = el('td');
        var link = el('button', 'rec-stock', r.h.code + ' ' + r.name);
        link.type = 'button';
        link.addEventListener('click', function () { openStock(r.h.code); });
        c0.appendChild(link);
        var fb = flagBadge(r.h.code, r.flag && r.flag[0]);
        if (fb) c0.appendChild(fb);
        var st = hdStatus(r);
        if (st) c0.appendChild(el('span', 'hd-state ' + st[1], st[0]));
        if (r.h.note) c0.appendChild(el('span', 'scr-reason', r.h.note));
        tr.appendChild(c0);
        tr.appendChild(el('td', null, fmt(r.h.qty, 0)));
        tr.appendChild(el('td', null, fmt(r.h.cost, 2)));
        tr.appendChild(el('td', dir(r.chg), fmt(r.last, 2)));
        var pl = el('td', dir(r.pnl));
        pl.appendChild(el('span', null, signed(r.pnl, 0)));
        pl.appendChild(el('span', 'scr-reason', signed(r.pnlPct, 2, '%')));
        tr.appendChild(pl);
        var sp = el('td');
        sp.appendChild(el('span', null, r.stop ? fmt(r.stop, 2) : '—'));
        sp.appendChild(el('span', 'scr-reason', (r.stopAuto ? '預設　' : '') +
                          (r.gap == null ? '' : '距離 ' + signed(r.gap, 1, '%'))));
        tr.appendChild(sp);
        tr.appendChild(el('td', null, r.group + (r.groupLinked ? '（族群連動）' : '')));
        var act = el('td');
        var edit = el('button', 'chip', '編輯');
        edit.type = 'button';
        edit.addEventListener('click', function () { hdEdit(pane, r.h); });
        var del = el('button', 'chip', '刪除');
        del.type = 'button';
        del.addEventListener('click', function () {
          if (del.dataset.armed) {
            hd.list = hd.list.filter(function (x) { return x.id !== r.h.id; });
            hdSave();
            hdDraw(pane);
          } else {
            del.dataset.armed = '1';
            del.textContent = '確定刪除？';
          }
        });
        act.appendChild(edit);
        act.appendChild(del);
        tr.appendChild(act);
        tb.appendChild(tr);
      });
      t.appendChild(tb); stackTable(t);
      var wrap = el('div', 'ov-table-wrap');
      wrap.appendChild(t);
      box.appendChild(wrap);
    }

    function hdGroups(rows, total) {
      var gd = document.getElementById('ov-hold-groups'), c = palette();
      if (!rows.length) { gd.hidden = true; return; }
      gd.hidden = false;
      var by = {};
      rows.forEach(function (r) { by[r.group] = (by[r.group] || 0) + r.value; });
      var keys = Object.keys(by).sort(function (a, b) { return by[a] - by[b]; });
      var pct = keys.map(function (k) { return by[k] / total.value * 100; });
      gd.style.height = (50 + 30 * keys.length) + 'px';
      Plotly.react(gd, [{
        type: 'bar', orientation: 'h', y: keys, x: pct,
        marker: {color: pct.map(function (p) { return p > hd.risk.groupMax ? c.orange : c.blue; })},
        text: pct.map(function (p) { return fmt(p, 1) + '%'; }), textposition: 'outside', cliponaxis: false,
        hovertemplate: '%{y}　%{x:.1f}%<extra></extra>'
      }], layout({
        margin: {l: 10, r: 40, t: 6, b: 28},
        xaxis: {ticksuffix: '%', range: [0, Math.max(100, Math.max.apply(null, pct) * 1.1)], gridcolor: c.grid, fixedrange: true},
        yaxis: {automargin: true, fixedrange: true},
        shapes: [{type: 'line', x0: hd.risk.groupMax, x1: hd.risk.groupMax, yref: 'paper', y0: 0, y1: 1,
                  line: {color: c.orange, dash: 'dot', width: 1}}]
      }), {displayModeBar: false, responsive: true});
    }

    // 未實現損益走勢：假設每一筆從買進日起一直持有（價格已還原權值，等於股利再投入）
    function hdCurve(pane, rows) {
      var gd = document.getElementById('ov-hold-curve'), c = palette();
      var note = pane.querySelector('.hd-curve-note');
      if (!rows.length) { gd.hidden = true; note.textContent = ''; return; }
      var dates = {};
      rows.forEach(function (r) { r.d.t.forEach(function (t) { dates[t] = true; }); });
      var axis = Object.keys(dates).sort();
      var start = rows.reduce(function (m, r) { return r.h.date && r.h.date < m ? r.h.date : m; }, axis[axis.length - 1]);
      axis = axis.filter(function (t) { return t >= start; }).slice(-250);
      var pnl = axis.map(function (t) {
        var v = 0, held = false;
        rows.forEach(function (r) {
          if (r.h.date && t < r.h.date) return;
          var i = r.d.t.indexOf(t);
          if (i < 0) {                                       // 停牌：用之前最近的收盤
            for (var k = r.d.t.length - 1; k >= 0; k--) { if (r.d.t[k] <= t) { i = k; break; } }
          }
          if (i < 0 || r.d.c[i] == null) return;
          v += (r.d.c[i] - r.h.cost) * r.h.qty;
          held = true;
        });
        return held ? v : null;
      });
      var peak = -Infinity, mdd = 0, base = rows.reduce(function (s, r) { return s + r.h.cost * r.h.qty; }, 0);
      pnl.forEach(function (v) {
        if (v == null) return;
        peak = Math.max(peak, v);
        mdd = Math.max(mdd, peak - v);
      });
      gd.hidden = false;
      note.textContent = '最大回落 ' + fmt(mdd, 0) + ' 元（成本的 ' + fmt(base ? mdd / base * 100 : 0, 1) +
        '%）。假設每筆從買進日起持有到今天；價格已還原權值（等於股利再投入）。';
      Plotly.react(gd, [{
        type: 'scatter', mode: 'lines', x: axis.map(function (t) { return t.slice(5).replace('-', '/'); }), y: pnl,
        line: {color: c.blue, width: 2}, connectgaps: true,
        hovertemplate: '%{x}　%{y:,.0f} 元<extra></extra>'
      }], layout({
        margin: {l: 64, r: 10, t: 8, b: 30},
        xaxis: {type: 'category', nticks: 8, fixedrange: true},
        yaxis: {zeroline: true, zerolinecolor: c.gray, gridcolor: c.grid, fixedrange: true, tickformat: ',.0f'}
      }), {displayModeBar: false, responsive: true});
    }

    function hdDraw(pane) {
      var list = hd.list.slice();
      Promise.all(list.map(function (h) {
        return hdShard(h.code).then(function (s) { return hdRow(h, s); }, function () { return null; });
      })).then(function (rows) {
        var missing = list.filter(function (h, i) { return !rows[i]; }).map(function (h) { return h.code; });
        rows = rows.filter(Boolean).sort(function (a, b) { return b.value - a.value; });
        var total = hdSummary(pane, rows);
        hdAlerts(pane, rows, total);
        hdTable(pane, rows);
        if (missing.length) {
          pane.querySelector('.hd-table').appendChild(el('p', 'sd-note', '查不到資料：' + missing.join('、')));
        }
        hdGroups(rows, total);
        hdCurve(pane, rows);
      });
    }

    function hdEdit(pane, h) {
      hd.editing = h ? h.id : null;
      var f = pane.querySelector('.hd-form');
      f.querySelector('#hd-code').value = h ? h.code : '';
      f.querySelector('#hd-qty').value = h ? h.qty : '';
      f.querySelector('#hd-cost').value = h ? h.cost : '';
      f.querySelector('#hd-date').value = h ? (h.date || '') : '';
      f.querySelector('#hd-stop').value = h && h.stop > 0 ? h.stop : '';
      f.querySelector('#hd-note').value = h ? (h.note || '') : '';
      f.querySelector('.hd-submit').textContent = h ? '儲存修改' : '加入持股';
      f.querySelector('.hd-cancel').hidden = !h;
      if (h) f.scrollIntoView({block: 'nearest'});
    }

    function hdForm(pane) {
      var f = pane.querySelector('.hd-form');
      if (f._bound) return;
      f._bound = true;
      var msg = f.querySelector('.hd-msg');
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        var code = f.querySelector('#hd-code').value.trim().split(/\s+/)[0].toUpperCase();
        var qty = Number(f.querySelector('#hd-qty').value), cost = Number(f.querySelector('#hd-cost').value);
        var date = f.querySelector('#hd-date').value, stop = Number(f.querySelector('#hd-stop').value) || 0;
        if (!code || !(qty > 0) || !(cost > 0)) {
          msg.textContent = '請填代號、股數與成本（股數要大於 0；1 張＝1000 股）。';
          return;
        }
        if (stop && stop >= cost) {
          msg.textContent = '停損價要低於成本；不填就用預設（成本 − 2 × ATR）。';
          return;
        }
        hdShard(code).then(function () {
          var item = {id: hd.editing || String(Date.now()), code: code, qty: qty, cost: cost, date: date,
                      stop: stop, note: f.querySelector('#hd-note').value.trim().slice(0, 60)};
          if (hd.editing) {
            hd.list = hd.list.map(function (x) { return x.id === hd.editing ? item : x; });
          } else {
            hd.list.push(item);
          }
          hdSave();
          msg.textContent = (hd.editing ? '已修改 ' : '已加入 ') + code;
          hdEdit(pane, null);
          hdDraw(pane);
        }, function () {
          msg.textContent = '查不到「' + code + '」，請確認是上市櫃股票或 ETF 代號。';
        });
      });
      f.querySelector('.hd-cancel').addEventListener('click', function () { hdEdit(pane, null); msg.textContent = ''; });
    }

    // 部位大小：每筆最多虧總資金的 riskPct%，股數＝可承受虧損 ÷（進場價 − 停損價）
    function hdCalc(pane) {
      var f = pane.querySelector('.hd-calc');
      if (f._bound) return;
      f._bound = true;
      var out = pane.querySelector('.hd-calc-out');
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        var code = f.querySelector('#hc-code').value.trim().split(/\s+/)[0].toUpperCase();
        var entry = Number(f.querySelector('#hc-entry').value), stop = Number(f.querySelector('#hc-stop').value);
        var k = Number(f.querySelector('#hc-k').value) || 2;
        var capital = hd.risk.capital, risk = hd.risk.riskPct;
        if (!(capital > 0)) { out.textContent = '先在下面「設定」填總資金。'; return; }
        var finish = function (entry, stop, atrText) {
          if (!(entry > 0) || !(stop > 0) || stop >= entry) {
            out.textContent = '進場價要大於停損價。';
            return;
          }
          var loss = capital * risk / 100, per = entry - stop;
          var shares = Math.floor(loss / per);
          var lots = Math.floor(shares / 1000);
          out.textContent = '';
          [['可承受虧損', fmt(loss, 0) + ' 元（總資金的 ' + risk + '%）'],
           ['每股風險', fmt(per, 2) + ' 元（' + fmt(per / entry * 100, 1) + '%）' + (atrText || '')],
           ['建議股數', fmt(shares, 0) + ' 股（' + lots + ' 張＋' + (shares - lots * 1000) + ' 股零股）'],
           ['部位金額', fmt(shares * entry, 0) + ' 元，占總資金 ' + fmt(shares * entry / capital * 100, 1) + '%' +
                       (shares * entry > capital * 0.2 ? '（超過 20%，一檔押太重，可以把停損放寬一點或少買）' : '')]
          ].forEach(function (x) {
            var p = el('p', 'hd-calc-row');
            p.appendChild(el('span', 'ck-tile-k', x[0]));
            p.appendChild(el('b', null, x[1]));
            out.appendChild(p);
          });
        };
        if (code && !(stop > 0)) {
          hdShard(code).then(function (s) {
            var atr = hdAtr(s.d), last = s.d.c[s.d.c.length - 1];
            var e2 = entry > 0 ? entry : last;
            finish(e2, atr ? e2 - k * atr : 0, '，停損＝進場 − ' + k + ' × ATR（' + fmt(atr, 2) + '）');
          }, function () { out.textContent = '查不到「' + code + '」。'; });
        } else {
          finish(entry, stop);
        }
      });
    }

    function hdSettings(pane) {
      var f = pane.querySelector('.hd-settings');
      f.querySelector('#hs-capital').value = hd.risk.capital || '';
      f.querySelector('#hs-risk').value = hd.risk.riskPct;
      f.querySelector('#hs-group').value = hd.risk.groupMax;
      if (f._bound) return;
      f._bound = true;
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        hd.risk = {capital: Math.max(0, Number(f.querySelector('#hs-capital').value) || 0),
                   riskPct: Math.min(10, Math.max(0.1, Number(f.querySelector('#hs-risk').value) || 1)),
                   groupMax: Math.min(100, Math.max(5, Number(f.querySelector('#hs-group').value) || 30))};
        hdSave();
        f.querySelector('.hd-msg').textContent = '已儲存';
        hdDraw(pane);
      });
      var io = pane.querySelector('.hd-io');
      io.querySelector('.hd-export').addEventListener('click', function () {
        var blob = new Blob([JSON.stringify({holdings: hd.list, risk: hd.risk}, null, 1)], {type: 'application/json'});
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'holdings-' + new Date().toISOString().slice(0, 10) + '.json';
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      });
      io.querySelector('#hd-import').addEventListener('change', function (e) {
        var file = e.target.files && e.target.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function () {
          try {
            var data = JSON.parse(reader.result);
            var list = (data.holdings || []).filter(function (h) { return h && h.code && h.qty > 0 && h.cost > 0; });
            hd.list = list.map(function (h, i) { return {id: h.id || String(Date.now() + i), code: String(h.code),
              qty: +h.qty, cost: +h.cost, date: h.date || '', stop: +h.stop || 0, note: h.note || ''}; });
            if (data.risk) hd.risk = {capital: +data.risk.capital || 0, riskPct: +data.risk.riskPct || 1,
                                      groupMax: +data.risk.groupMax || 30};
            hdSave();
            io.querySelector('.hd-msg').textContent = '已匯入 ' + hd.list.length + ' 筆';
            hdSettings(pane);
            hdDraw(pane);
          } catch (err) {
            io.querySelector('.hd-msg').textContent = '檔案格式不對，請用這裡匯出的 JSON。';
          }
        };
        reader.readAsText(file);
        e.target.value = '';
      });
      io.querySelector('.hd-clear').addEventListener('click', function (e) {
        var b = e.currentTarget;
        if (!b.dataset.armed) { b.dataset.armed = '1'; b.textContent = '確定清除全部持股？'; return; }
        hd.list = [];
        hdSave();
        delete b.dataset.armed;
        b.textContent = '清除全部持股';
        io.querySelector('.hd-msg').textContent = '已清除';
        hdDraw(pane);
      });
    }

    function hold(pane) {
      hdLoad();
      // 族群：強勢紀錄最新一天的判定；沒有的話用產業別
      var groupsP = getJSON('data/record/index.json').then(function (ix) {
        if (!ix.dates || !ix.dates.length) return null;
        return getJSON('data/record/' + ix.dates[ix.dates.length - 1] + '.json');
      }).then(function (day) {
        hd.groups = {};
        (day && day.rows || []).forEach(function (r) { if (r[11]) hd.groups[r[0]] = [r[11], r[12]]; });
      }, function () {});
      return Promise.all([loadFlags(), groupsP]).then(function () {
        hdForm(pane);
        hdCalc(pane);
        hdSettings(pane);
        hdDraw(pane);
      });
    }

    var RENDER = {today: today, market: market, global: globalMkt, trend: trend, macro: macro, sectors: sectors, momentum: momentum,
                  record: record, perf: perf, hold: hold, flows: flows};

    function show(sub) {
      if (!sub || !RENDER[sub]) return;
      var pane = document.querySelector('.subpanel[data-sub="' + sub + '"]');
      if (!shown(pane)) return;
      load().then(function (d) { return RENDER[sub](pane, d); })
        .then(function () { syncSticky(); })
        .catch(function () {
          failMsg(pane.querySelector('.ov-body') || pane.querySelector('.sec-table') ||
                  pane.querySelector('.ichart') || pane);
        });
    }

    // 沒有子分頁的分頁（今日）就是第一個面板
    function subOf(host) {
      var s = currentSub(host);
      if (s) return s;
      var first = host.querySelector('.subpanel');
      return first ? first.dataset.sub : null;
    }
    HOSTS.forEach(function (host) {
      onShow(host, function () { show(subOf(host)); });
    });
    window.addEventListener('dash-theme', function () {
      HOSTS.forEach(function (host) { if (!host.hidden) show(subOf(host)); });
    });
    HOSTS.forEach(function (host) { if (!host.hidden) show(subOf(host)); });
  })();

  // ════════════════════ 個股深度頁 ════════════════════
  (function () {
    var panel = document.getElementById('panel-stock');
    if (!panel) return;
    var pane = panel.querySelector('.subpanel[data-sub="query"]');
    if (!pane) return;
    var input = pane.querySelector('.sq-input');
    var sug = pane.querySelector('.sq-suggest');
    var hint = pane.querySelector('.sq-hint');
    var box = pane.querySelector('.sd');
    var watchBox = pane.querySelector('.sd-watch');
    var days = 66;
    var current = null;     // 目前這一檔的 JSON
    var seq = 0;

    function list() { return getJSON('data/stocks.json'); }

    // 自選股晶片：點了直接看那一檔
    getJSON('data/overview.json').then(function (d) {
      var rows = d.watch || [];
      if (!rows.length) return;
      watchBox.textContent = '';
      rows.forEach(function (r) {
        var b = el('button', 'chip', r.code + ' ' + r.name);
        b.type = 'button';
        b.addEventListener('click', function () { openStock(r.code); });
        watchBox.appendChild(b);
      });
      watchBox.hidden = false;
    }).catch(function () {});

    var timer = null;
    input.addEventListener('input', function () {
      var q = input.value.trim();
      if (timer) clearTimeout(timer);
      if (!q) { sug.hidden = true; return; }
      timer = setTimeout(function () {
        list().then(function (all) {
          var ql = q.toLowerCase();
          var hits = all.filter(function (s) { return s[0].indexOf(q) === 0; })
            .concat(all.filter(function (s) {
              return s[0].indexOf(q) !== 0 && String(s[1]).toLowerCase().indexOf(ql) >= 0;
            })).slice(0, 8);
          sug.textContent = '';
          hits.forEach(function (s) {
            var b = el('button', 'sq-opt', s[0] + '　' + s[1] + '　' + (s[2] === 'tpex' ? '上櫃' : '上市'));
            b.type = 'button';
            b.setAttribute('role', 'option');
            b.addEventListener('click', function () { openStock(s[0]); });
            sug.appendChild(b);
          });
          sug.hidden = !hits.length;
        }).catch(function () { sug.hidden = true; });
      }, 150);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      var first = sug.querySelector('.sq-opt');
      if (first) { first.click(); return; }
      var code = input.value.trim().split(/\s+/)[0];
      if (code) openStock(code.toUpperCase());
    });
    document.addEventListener('click', function (e) { if (!pane.contains(e.target)) sug.hidden = true; });

    bindChips(pane.querySelector('.sq-range'), function (c) {
      days = Number(c.dataset.days);
      setWindow(document.getElementById('sd-price'), days);
    });

    // 四個縱軸都依「看得到的那一段」重算，否則一年內的高低點會把線壓扁
    function priceRescale(d) {
      return function (from, to) {
        var up = {};
        var price = span([d.l, d.h], from, to);
        if (price) up['yaxis.range'] = price;
        var vol = span([d.v], from, to, true);
        if (vol) up['yaxis2.range'] = [0, vol[1]];
        // 法人是堆疊長條：用同一天正、負各自加總的最大值，才不會被切掉
        var pos = 0, neg = 0;
        for (var i = from; i <= to; i++) {
          var p = 0, q = 0;
          [d.fi[i], d.tr[i], d.de[i]].forEach(function (v) { if (v > 0) p += v; else if (v < 0) q += v; });
          if (p > pos) pos = p;
          if (q < neg) neg = q;
        }
        var pad = (pos - neg) * 0.06 || 1;
        up['yaxis3.range'] = [neg - pad, pos + pad];
        var mb = span([d.mb], from, to);
        if (mb) up['yaxis4.range'] = mb;
        return up;
      };
    }

    // 細產業標籤：主要的排第一（實心），點了到類股頁看同一類
    function sdTags(box, code) {
      box.textContent = '';
      loadChains().then(function () {
        var ts = chainTags(code);
        if (!ts.length) return;
        ts.slice(0, 12).forEach(function (t, i) {
          var b = el('button', 'sd-tag' + (i === 0 ? ' is-main' : ''), t[0] + (t[3] ? '（手動）' : ''));
          b.type = 'button';
          b.title = t[1] + (t[2] ? ' › ' + t[2] : '') + '　·　' + t[4] + ' 檔' + (i === 0 ? '　·　主要細產業' : '');
          b.addEventListener('click', function () {
            if (typeof window.openFineSector === 'function') window.openFineSector(t[0]);
          });
          box.appendChild(b);
        });
        if (ts.length > 12) box.appendChild(el('span', 'sd-tag-more', '還有 ' + (ts.length - 12) + ' 類'));
      });
    }

    function stat(label, value, cls) {
      var b = el('div', 'sq-stat');
      b.appendChild(el('span', 'sq-stat-l', label));
      b.appendChild(el('b', cls || '', value));
      return b;
    }

    function sma(arr, n) {
      var out = [], sum = 0, cnt = 0, q = [];
      arr.forEach(function (v) {
        q.push(v);
        if (v != null) { sum += v; cnt++; }
        if (q.length > n) { var o = q.shift(); if (o != null) { sum -= o; cnt--; } }
        out.push(q.length === n && cnt === n ? sum / n : null);
      });
      return out;
    }

    function section(id, visible) {
      var s = pane.querySelector('.sd-sec[data-sec="' + id + '"]');
      if (s) s.hidden = !visible;
      return !!visible;
    }

    function drawPrice(s) {
      var c = palette(), d = s.d;
      var up = d.c.map(function (v, i) { return i && d.c[i - 1] != null ? v >= d.c[i - 1] : true; });
      var L = layout({
        xaxis: {type: 'category', gridcolor: c.grid, linecolor: c.grid, nticks: Math.min(6, TICKS), tickangle: 0,
                automargin: true, rangeslider: {visible: false}, showspikes: true,
                spikemode: 'across', spikethickness: 1, spikedash: 'dot', spikecolor: c.gray},
        yaxis: {domain: [0.5, 1], gridcolor: c.grid, tickformat: ',.2~f', automargin: true},
        yaxis2: {domain: [0.36, 0.47], gridcolor: c.grid, tickformat: ',.0f', automargin: true},
        yaxis3: {domain: [0.17, 0.33], gridcolor: c.grid, zeroline: true, zerolinecolor: c.grid,
                 tickformat: ',.0f', automargin: true},
        yaxis4: {domain: [0, 0.14], gridcolor: c.grid, tickformat: ',.0f', automargin: true},
        barmode: 'relative',
        margin: {l: 56, r: 14, t: 18, b: 34},
        annotations: [
          ['K 線・均線 5／20／60', 1], ['成交量（張）', 0.475], ['三大法人（張）', 0.335],
          ['融資餘額（張）', 0.145]
        ].map(function (a) {
          return {text: a[0], xref: 'paper', yref: 'paper', x: 0, y: a[1], xanchor: 'left',
                  yanchor: 'bottom', showarrow: false, font: {size: 11, color: c.fg}};
        })
      });
      var traces = [
        {type: 'candlestick', x: d.t, open: d.o, high: d.h, low: d.l, close: d.c, name: '股價',
         increasing: {line: {color: c.up, width: 1}, fillcolor: c.up},
         decreasing: {line: {color: c.down, width: 1}, fillcolor: c.down},
         hoverinfo: 'x+y', showlegend: false},
        {type: 'scatter', mode: 'lines', x: d.t, y: sma(d.c, 5), name: '5 日',
         line: {color: c.orange, width: 1}, hovertemplate: '%{y:,.2f}<extra>5 日</extra>'},
        {type: 'scatter', mode: 'lines', x: d.t, y: sma(d.c, 20), name: '20 日',
         line: {color: c.blue, width: 1}, hovertemplate: '%{y:,.2f}<extra>20 日</extra>'},
        {type: 'scatter', mode: 'lines', x: d.t, y: sma(d.c, 60), name: '60 日',
         line: {color: c.purple, width: 1}, hovertemplate: '%{y:,.2f}<extra>60 日</extra>'},
        {type: 'bar', x: d.t, y: d.v, yaxis: 'y2', name: '成交量',
         marker: {color: up.map(function (u) { return u ? c.up : c.down; })},
         hovertemplate: '%{y:,.0f} 張<extra>成交量</extra>'},
        {type: 'bar', x: d.t, y: d.fi, yaxis: 'y3', name: '外資', marker: {color: c.orange},
         hovertemplate: '%{y:+,.0f}<extra>外資</extra>'},
        {type: 'bar', x: d.t, y: d.tr, yaxis: 'y3', name: '投信', marker: {color: c.purple},
         hovertemplate: '%{y:+,.0f}<extra>投信</extra>'},
        {type: 'bar', x: d.t, y: d.de, yaxis: 'y3', name: '自營商', marker: {color: c.gray},
         hovertemplate: '%{y:+,.0f}<extra>自營商</extra>'},
        {type: 'scatter', mode: 'lines', x: d.t, y: d.mb, yaxis: 'y4', name: '融資',
         line: {color: c.blue, width: 1.5}, hovertemplate: '%{y:,.0f} 張<extra>融資</extra>'}
      ];
      var n = d.t.length, rescale = priceRescale(d), w = windowFor(n, days);
      var init = rescale(w.from, w.to);
      L.xaxis.range = [w.from - 0.5, w.to + 0.5];
      ['yaxis', 'yaxis2', 'yaxis3', 'yaxis4'].forEach(function (k) {
        if (init[k + '.range']) L[k].range = init[k + '.range'];
      });
      plotZoom('sd-price', traces, L, n, rescale);
    }

    function drawRevenue(s) {
      if (!section('sd-rev', s.rev && s.rev.ym.length)) return;
      var c = palette();
      plot('sd-rev', [
        {type: 'bar', x: s.rev.ym, y: s.rev.v, name: '營收', marker: {color: c.blue},
         hovertemplate: '%{y:,.2f} 億<extra>營收</extra>'},
        {type: 'scatter', mode: 'lines+markers', x: s.rev.ym, y: s.rev.yoy, yaxis: 'y2',
         name: '年增率', line: {color: c.orange, width: 2}, marker: {size: 4},
         hovertemplate: '%{y:+.1f}%<extra>年增率</extra>'}
      ], layout({
        xaxis: {type: 'category', gridcolor: c.grid, nticks: 8, tickangle: 0, automargin: true},
        yaxis: {gridcolor: c.grid, tickformat: ',.0f', automargin: true, title: {text: '億元'}},
        yaxis2: {overlaying: 'y', side: 'right', zeroline: true, zerolinecolor: c.grid,
                 showgrid: false, ticksuffix: '%', automargin: true},
        margin: {l: 52, r: 44, t: 10, b: 34}
      }));
    }

    function drawEps(s) {
      if (!section('sd-eps', s.q && s.q.q.length)) return;
      var c = palette();
      plot('sd-eps', [
        {type: 'bar', x: s.q.q, y: s.q.eps, name: 'EPS',
         marker: {color: s.q.eps.map(function (v) { return v != null && v < 0 ? c.down : c.up; })},
         hovertemplate: '%{y:.2f} 元<extra>EPS</extra>'},
        {type: 'scatter', mode: 'lines+markers', x: s.q.q, y: s.q.gm, yaxis: 'y2', name: '毛利率',
         line: {color: c.blue, width: 2}, marker: {size: 4}, hovertemplate: '%{y:.1f}%<extra>毛利率</extra>'},
        {type: 'scatter', mode: 'lines+markers', x: s.q.q, y: s.q.om, yaxis: 'y2', name: '營益率',
         line: {color: c.orange, width: 2}, marker: {size: 4}, hovertemplate: '%{y:.1f}%<extra>營益率</extra>'}
      ], layout({
        xaxis: {type: 'category', gridcolor: c.grid, tickangle: 0, automargin: true},
        yaxis: {gridcolor: c.grid, zeroline: true, zerolinecolor: c.grid, automargin: true,
                title: {text: '元'}},
        yaxis2: {overlaying: 'y', side: 'right', showgrid: false, ticksuffix: '%', automargin: true},
        margin: {l: 48, r: 44, t: 10, b: 34}
      }));
    }

    function percentile(sorted, p) {
      var i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
      return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
    }

    function drawPe(s) {
      var pe = s.pe;
      var valid = pe ? pe.pe.filter(function (v) { return v != null && v > 0; }) : [];
      var box = document.getElementById('sd-pe');
      if (!section('sd-pe', pe && pe.ym.length)) return;
      if (valid.length < 12) {
        Plotly.purge(box);
        failMsg(box, '本益比資料不足（虧損期間不計算本益比，或上市時間太短）。');
        return;
      }
      if (box.querySelector('.cal-empty')) box.textContent = '';
      var c = palette();
      var sorted = valid.slice().sort(function (a, b) { return a - b; });
      var levels = [0.1, 0.3, 0.5, 0.7, 0.9].map(function (p) { return percentile(sorted, p); });
      var eps = pe.c.map(function (price, i) {
        var v = pe.pe[i];
        return v != null && v > 0 && price != null ? price / v : null;
      });
      var traces = levels.map(function (lv, k) {
        return {type: 'scatter', mode: 'lines', x: pe.ym,
                y: eps.map(function (e) { return e == null ? null : e * lv; }),
                name: lv.toFixed(1) + ' 倍', line: {width: 0.8, color: c.band + '0.6)'},
                fill: k ? 'tonexty' : 'none', fillcolor: c.band + (0.06 + k * 0.03) + ')',
                connectgaps: false, hovertemplate: '%{y:,.1f}<extra>' + lv.toFixed(1) + ' 倍</extra>'};
      });
      traces.push({type: 'scatter', mode: 'lines', x: pe.ym, y: pe.c, name: '股價',
                   line: {color: c.up, width: 2}, hovertemplate: '%{y:,.2f}<extra>股價</extra>'});
      plot('sd-pe', traces, layout({
        showlegend: true, legend: {orientation: 'h', x: 0, y: 1.14, font: {size: 10}},
        xaxis: {type: 'category', gridcolor: c.grid, nticks: TICKS, tickangle: 0, automargin: true},
        yaxis: {gridcolor: c.grid, tickformat: ',.0f', automargin: true},
        margin: {l: 52, r: 14, t: 30, b: 34}
      }));
    }

    function drawTdcc(s) {
      if (!section('sd-tdcc', s.tdcc && s.tdcc.t.length)) return;
      var c = palette();
      plot('sd-tdcc', [
        {type: 'scatter', mode: 'lines+markers', x: s.tdcc.t, y: s.tdcc.big, name: '千張以上',
         line: {color: c.up, width: 2, shape: 'hv'}, marker: {size: 6},
         hovertemplate: '%{y:.2f}%<extra>千張以上</extra>'},
        {type: 'scatter', mode: 'lines+markers', x: s.tdcc.t, y: s.tdcc.big400, name: '400 張以上',
         line: {color: c.blue, width: 1.5, dash: 'dot', shape: 'hv'}, marker: {size: 5},
         hovertemplate: '%{y:.2f}%<extra>400 張以上</extra>'}
      ], layout({
        showlegend: true, legend: {orientation: 'h', x: 0, y: 1.14, font: {size: 10}},
        xaxis: {type: 'category', gridcolor: c.grid, automargin: true},
        yaxis: {gridcolor: c.grid, ticksuffix: '%', automargin: true},
        margin: {l: 52, r: 14, t: 30, b: 34}
      }));
    }

    function drawAnn(s) {
      var ul = pane.querySelector('.sd-ann');
      ul.textContent = '';
      var items = [];
      (s.exdiv || []).forEach(function (x) {
        items.push({when: x[0], text: '除' + String(x[1]).replace('除', '') +
                    (x[2] && Number(x[2]) > 0 ? '　現金 ' + Number(x[2]) + ' 元' : '') + '（預告）'});
      });
      (s.calls || []).forEach(function (x) {
        items.push({when: x[0] + (x[1] ? ' ' + x[1] : ''), text: '法說會' + (x[2] ? '：' + x[2] : '')});
      });
      (s.ann || []).forEach(function (a) {
        var t = String(a[1] || '');
        while (t.length < 6) t = '0' + t;
        items.push({when: a[0] + ' ' + t.slice(0, 2) + ':' + t.slice(2, 4), text: a[2]});
      });
      if (!section('sd-ann', items.length)) return;
      // 還沒到的（除權息預告、法說會）排前面，其餘新的在上
      var now = new Date().toISOString().slice(0, 10);
      var future = items.filter(function (it) { return it.when.slice(0, 10) >= now; })
        .sort(function (a, b) { return a.when < b.when ? -1 : 1; });
      var past = items.filter(function (it) { return it.when.slice(0, 10) < now; })
        .sort(function (a, b) { return a.when < b.when ? 1 : -1; });
      items = future.concat(past);
      items.forEach(function (it) {
        var li = el('li');
        li.appendChild(el('span', 'ov-when', it.when));
        li.appendChild(document.createTextNode(it.text));
        ul.appendChild(li);
      });
    }

    function render(s) {
      var d = s.d, n = d.t.length;
      var last = d.c[n - 1], prev = n > 1 ? d.c[n - 2] : null;
      var chg = last != null && prev ? last - prev : null;
      pane.querySelector('.sq-name').textContent = s.code + '　' + s.name;
      pane.querySelector('.sd-sub').textContent =
        (s.market === 'tpex' ? '上櫃' : '上市') + (s.industry ? '　·　' + s.industry : '') +
        '　·　資料日期 ' + s.asof;
      sdTags(pane.querySelector('.sd-tags'), s.code);
      pane.querySelector('.sd-edit').href = EDIT_URL;
      zoomHint(pane.querySelector('.zoom-hint'));
      var st = pane.querySelector('.sq-stats');
      st.textContent = '';
      st.appendChild(stat('收盤', fmt(last, 2)));
      st.appendChild(stat('漲跌', chg == null ? '—' :
                          signed(chg, 2) + '（' + signed(chg / prev * 100, 2, '%') + '）', dir(chg)));
      st.appendChild(stat('成交量', fmt(d.v[n - 1], 0) + ' 張'));
      st.appendChild(stat('外資', signed(d.fi[n - 1], 0) + ' 張', dir(d.fi[n - 1])));
      st.appendChild(stat('投信', signed(d.tr[n - 1], 0) + ' 張', dir(d.tr[n - 1])));
      st.appendChild(stat('本益比', s.val && s.val.per ? fmt(s.val.per, 2) : '—'));
      st.appendChild(stat('殖利率', s.val && s.val.yield != null ? fmt(s.val.yield, 2) + '%' : '—'));
      st.appendChild(stat('股價淨值比', s.val && s.val.pbr ? fmt(s.val.pbr, 2) : '—'));
      if (s.lend) {
        st.appendChild(stat('借券賣出餘額', fmt(s.lend.bal, 0) + ' 張' +
                            (s.lend.chg == null ? '' : '（20 日 ' + signed(s.lend.chg, 0) + '）'),
                            s.lend.chg > 0 ? 'down' : null));
      }
      if (s.dt) st.appendChild(stat('當沖比', fmt(s.dt.pct, 1) + '%'));
      if (s.qfii) {
        st.appendChild(stat('外資持股', fmt(s.qfii.pct, 2) + '%' +
                            (s.qfii.chg == null ? '' : '（20 日 ' + signed(s.qfii.chg, 2) + '）'),
                            dir(s.qfii.chg)));
      }
      if (s.flag) {
        st.appendChild(stat(s.flag[0] === '處置' ? '處置股' : '注意股',
                            s.flag[0] === '處置' ? md(s.flag[1]) + '～' + md(s.flag[2]) : md(s.flag[1]),
                            null));
      }
      drawPrice(s);
      drawRevenue(s);
      drawEps(s);
      drawPe(s);
      drawTdcc(s);
      drawAnn(s);
      syncSticky();
    }

    function load(code) {
      var my = ++seq;
      sug.hidden = true;
      hint.hidden = false;
      hint.textContent = '載入中…';
      fetch('data/stock/' + encodeURIComponent(code) + '.json?v=' + VERSION).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (s) {
        if (my !== seq) return;
        current = s;
        input.value = s.code + ' ' + s.name;
        hint.hidden = true;
        box.hidden = false;
        setStockFocus({code: s.code, name: s.name});
        render(s);
      }).catch(function () {
        if (my !== seq) return;
        box.hidden = true;
        hint.hidden = false;
        hint.textContent = '查不到「' + code + '」。可能是代號有誤，或不是上市櫃股票與 ETF。';
      });
    }

    openStock = function (code) {
      var tab = document.querySelector('.tab[data-tab="stock"]');
      if (tab && document.getElementById('panel-stock').hidden) selectTab('stock', true);
      var sub = panel.querySelector('.subtab[data-sub="query"]');
      if (sub && sub.getAttribute('aria-selected') !== 'true') sub.click();
      window.scrollTo(0, 0);
      load(String(code).trim().toUpperCase());
    };

    window.addEventListener('dash-theme', function () {
      if (current && shown(box)) render(current);
    });

    // 推播通知裡的連結：?stock=2330 直接打開那一檔
    var m = /[?&]stock=([0-9A-Za-z]+)/.exec(location.search);
    if (m) setTimeout(function () { openStock(m[1]); }, 0);
  })();

  // ════════════════════ 選股 ════════════════════
  (function () {
    var panel = document.getElementById('panel-picks');
    if (!panel) return;
    var pane = panel.querySelector('.subpanel[data-sub="screen"]');
    if (!pane) return;
    var body = pane.querySelector('.scr-body');
    var drawn = false;
    var SHOW = window.innerWidth < 820 ? 5 : 15;

    function card(c) {
      var sec = el('section', 'scr-card');
      sec.id = 'scr-' + c.id;
      var head = el('div', 'scr-head');
      head.appendChild(el('h3', null, c.name));
      head.appendChild(el('span', 'scr-count',
        c.note ? '累積中' : (c.total > c.hits.length ? '共 ' + c.total + ' 檔，列出前 ' + c.hits.length
                                                     : c.total + ' 檔')));
      sec.appendChild(head);
      sec.appendChild(el('p', 'scr-rule', c.rule + '（資料：' + c.data + '）'));
      if (c.note) { sec.appendChild(el('p', 'ov-empty', c.note)); return sec; }
      if (!c.hits.length) { sec.appendChild(el('p', 'ov-empty', '今天沒有符合的股票。')); return sec; }
      var wrap = el('div', 'ov-table-wrap');
      var t = el('table', 'ov-table scr-table');
      var h = el('tr');
      var tb = el('tbody');
      var state = {key: null, desc: true, all: false};
      // 表頭可以點：收盤、漲跌依數字排序（再點一次反過來）；點「股票」回到條件本身的排序
      var cols = [['股票', null], ['收盤', 'close'], ['漲跌', 'chg'], ['近 20 日', undefined]];
      var heads = cols.map(function (col) {
        var th = el('th');
        if (col[1] === undefined) { th.textContent = col[0]; h.appendChild(th); return th; }
        var b = el('button', 'th-sort', col[0]);
        b.type = 'button';
        b.addEventListener('click', function () {
          if (col[1] === null) { state.key = null; }
          else if (state.key === col[1]) { state.desc = !state.desc; }
          else { state.key = col[1]; state.desc = true; }
          fill();
        });
        th.appendChild(b);
        h.appendChild(th);
        return th;
      });
      var thead = el('thead'); thead.appendChild(h); t.appendChild(thead);
      var more = null;

      function fill() {
        var rows = c.hits.slice();
        if (state.key) {
          rows.sort(function (a, b) {
            var x = a[state.key], y = b[state.key];
            if (x == null) return 1;
            if (y == null) return -1;
            return state.desc ? y - x : x - y;
          });
        }
        heads.forEach(function (th, i) {
          var key = cols[i][1];
          if (key === undefined) return;
          var on = key === null ? !state.key : state.key === key;
          th.setAttribute('aria-sort', on && key ? (state.desc ? 'descending' : 'ascending') : 'none');
          th.querySelector('button').textContent = cols[i][0] +
            (on && key ? (state.desc ? ' ↓' : ' ↑') : (on ? ' ·' : ''));
        });
        tb.textContent = '';
        rows.forEach(function (r, i) {
          var tr = el('tr', 'go');
          if (i >= SHOW && !state.all) tr.hidden = true;
          var c0 = el('td');
          c0.appendChild(el('span', 'ov-code', r.code));
          c0.appendChild(el('span', 'ov-name', r.name));
          c0.appendChild(el('span', 'scr-reason', r.reason + (r.industry ? '　·　' + r.industry : '')));
          tr.appendChild(c0);
          tr.appendChild(el('td', null, fmt(r.close, 2)));
          tr.appendChild(el('td', dir(r.chg), signed(r.chg, 2, '%')));
          var c3 = el('td');
          c3.appendChild(sparkSvg(r.spark));
          tr.appendChild(c3);
          tr.addEventListener('click', function () { openStock(r.code); });
          tb.appendChild(tr);
        });
        if (more) more.hidden = state.all || c.hits.length <= SHOW;
      }

      t.appendChild(tb); stackTable(t); wrap.appendChild(t); sec.appendChild(wrap);
      if (c.hits.length > SHOW) {
        more = el('button', 'scr-more', '顯示全部 ' + c.hits.length + ' 檔');
        more.type = 'button';
        more.addEventListener('click', function () { state.all = true; fill(); });
        sec.appendChild(more);
      }
      fill();
      return sec;
    }

    // 產業篩選：官方產業或細產業（只影響列出的股票，不改條件本身）
    function filterBar(d, onPick) {
      var sel = el('select', 'sec-pick scr-filter');
      sel.setAttribute('aria-label', '產業篩選');
      var all = el('option', null, '全部產業');
      all.value = '';
      sel.appendChild(all);
      var inds = {}, counts = {};
      d.conditions.forEach(function (c) {
        (c.hits || []).forEach(function (h) {
          if (h.industry) inds[h.industry] = (inds[h.industry] || 0) + 1;
          (CHAINS.codes[h.code] || []).forEach(function (i) { counts[i] = (counts[i] || 0) + 1; });
        });
      });
      var g = document.createElement('optgroup');
      g.label = '官方產業';
      Object.keys(inds).sort(function (a, b) { return inds[b] - inds[a]; }).forEach(function (n) {
        var o = el('option', null, n + '（' + inds[n] + '）');
        o.value = 'i:' + n;
        g.appendChild(o);
      });
      sel.appendChild(g);
      Object.keys(counts).forEach(function (i) { if (counts[i] < 2) delete counts[i]; });
      tagOptions(sel, counts, 'f:');
      sel.addEventListener('change', function () { onPick(sel.value); });
      var bar = el('div', 'sec-bar');
      bar.appendChild(sel);
      return bar;
    }

    function draw(d, pick) {
      Array.prototype.slice.call(body.querySelectorAll('.scr-card')).forEach(function (x) { x.remove(); });
      d.conditions.forEach(function (c) {
        var keep = function (h) {
          if (!pick) return true;
          if (pick.indexOf('i:') === 0) return h.industry === pick.slice(2);
          return inTag(h.code, Number(pick.slice(2)));
        };
        var hits = (c.hits || []).filter(keep);
        var cc = Object.assign({}, c, {hits: hits});
        if (pick) cc.total = hits.length;
        body.appendChild(card(cc));
      });
      syncSticky();
    }

    function show() {
      if (drawn || !shown(pane)) return Promise.resolve();
      return Promise.all([getJSON('data/screen.json'), loadChains()]).then(function (res) {
        var d = res[0];
        body.textContent = '';
        body.appendChild(el('p', 'ov-asof', '資料日期 ' + md(d.asof) + ' 盤後'));
        body.appendChild(filterBar(d, function (v) { draw(d, v); }));
        draw(d, '');
        drawn = true;
      }).catch(function () { failMsg(body); });
    }

    openScreen = function (id) {
      if (document.getElementById('panel-picks').hidden) selectTab('picks', true);
      var sub = panel.querySelector('.subtab[data-sub="screen"]');
      if (sub && sub.getAttribute('aria-selected') !== 'true') sub.click();
      setTimeout(function () {
        show().then(function () {
          var target = document.getElementById('scr-' + id);
          if (target) {
            var top = target.getBoundingClientRect().top + window.pageYOffset -
                      (document.querySelector('header').offsetHeight + 12);
            window.scrollTo(0, top);
          }
        });
      }, 0);
    };

    onShow(panel, function (sub) { if (sub === 'screen') show(); });
  })();
})();
