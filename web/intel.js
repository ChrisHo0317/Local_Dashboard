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

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
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

  // ════════════════════ 總覽 ════════════════════
  (function () {
    var panel = document.getElementById('panel-overview');
    if (!panel) return;
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

    function events(box, list) {
      box.textContent = '';
      if (!list || !list.length) { box.appendChild(el('p', 'ov-empty', '接下來一週沒有高影響事件。')); return; }
      var ul = el('ul', 'ov-list');
      list.forEach(function (e) {
        var li = el('li');
        li.appendChild(el('span', 'ov-when', md(e.date) + (e.time ? ' ' + e.time : '')));
        li.appendChild(el('span', 'ov-kind' + (e.kind === '總經' ? '' : ' k-tw'), e.kind));
        li.appendChild(document.createTextNode(e.text));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }

    function sigs(box, list) {
      box.textContent = '';
      var ul = el('ul', 'ov-list');
      (list || []).forEach(function (s) {
        var li = el('li');
        var row = el('div', 'ov-sig');
        var a = el('a', null, s.name);
        a.href = '#';
        a.addEventListener('click', function (e) { e.preventDefault(); openScreen(s.id); });
        row.appendChild(a);
        row.appendChild(el('b', null, s.note ? '累積中' : s.total + ' 檔'));
        li.appendChild(row);
        if (s.note) li.appendChild(el('span', 'ov-news-s', s.note));
        ul.appendChild(li);
      });
      box.appendChild(ul);
      box.appendChild(el('p', 'ov-empty', '條件尚未回測，只能當觀察名單。'));
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

    function today(pane, d) {
      pane.querySelector('.ov-asof').textContent = '資料日期 ' + d.asof + '（盤後）';
      kpis(pane.querySelector('.ov-kpis'), d.kpi || []);
      watch(pane.querySelector('.ov-watch .ov-body'), d);
      events(pane.querySelector('.ov-events .ov-body'), d.events);
      sigs(pane.querySelector('.ov-signals .ov-body'), d.signals);
      news(pane.querySelector('.ov-news .ov-body'), d.news);
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
        return up;
      }
      var w = windowFor(n, marketDays);
      var init = rescale(w.from, w.to);
      var L = layout({
        xaxis: {type: 'category', gridcolor: c.grid, linecolor: c.grid, nticks: 7,
                tickangle: 0, automargin: true, showspikes: true, spikemode: 'across',
                spikethickness: 1, spikedash: 'dot', spikecolor: c.gray,
                range: [w.from - 0.5, w.to + 0.5]},
        yaxis: {domain: [0.42, 1], gridcolor: c.grid, tickformat: ',.0f', automargin: true,
                title: {text: ''}, range: init['yaxis.range']},
        yaxis2: {domain: [0, 0.34], gridcolor: c.grid, zeroline: true, zerolinecolor: c.grid,
                 automargin: true, tickformat: ',.0f', range: init['yaxis2.range']},
        barmode: 'group',
        annotations: [
          {text: '加權指數', xref: 'paper', yref: 'paper', x: 0, y: 1, xanchor: 'left',
           yanchor: 'bottom', showarrow: false, font: {size: 11, color: c.fg}},
          {text: '法人買賣超（億元，估算）', xref: 'paper', yref: 'paper', x: 0, y: 0.35,
           xanchor: 'left', yanchor: 'bottom', showarrow: false, font: {size: 11, color: c.fg}}
        ],
        margin: {l: 56, r: 14, t: 20, b: 34}
      });
      plotZoom('ov-market', [
        {type: 'scatter', mode: 'lines', x: m.t, y: m.taiex, name: '加權指數',
         line: {color: c.blue, width: 2}, hovertemplate: '%{y:,.2f}<extra>加權指數</extra>'},
        {type: 'bar', x: m.t, y: m.fi, name: '外資', yaxis: 'y2', marker: {color: c.orange},
         hovertemplate: '%{y:+,.1f} 億<extra>外資</extra>'},
        {type: 'bar', x: m.t, y: m.tr, name: '投信', yaxis: 'y2', marker: {color: c.purple},
         hovertemplate: '%{y:+,.1f} 億<extra>投信</extra>'}
      ], L, n, rescale);
    }

    bindChips(panel.querySelector('.ov-range'), function (chip) {
      marketDays = Number(chip.dataset.days);
      setWindow(document.getElementById('ov-market'), marketDays);
    });

    // ── 類股：熱力圖可以點進產業，下方清單列出產業裡每一檔，可依成交值或漲跌排序 ──
    var LEAF = 30;            // 熱力圖每個產業最多畫幾檔（清單裡是全部）
    var SEC_PAGE = 30;        // 清單一次列幾檔
    var sec = {data: null, pick: -1, sort: 'turnover', shown: SEC_PAGE};

    function secTreemap(pane) {
      var d = sec.data, c = palette();
      var ids = ['all'], labels = ['全市場'], parents = [''], values = [0], colors = [0],
          custom = [[0, '', 0, 0]];
      var total = 0, wsum = 0;
      d.industries.forEach(function (s, i) {
        var leaves = d.stocks.filter(function (x) { return x[2] === i; }).slice(0, LEAF);
        var v = leaves.reduce(function (a, x) { return a + (x[5] || 0); }, 0);
        if (!v) return;
        ids.push('I' + i); labels.push(s.industry); parents.push('all'); values.push(v);
        colors.push(s.chg); custom.push([s.chg, '', s.up, s.down]);
        leaves.forEach(function (x) {
          ids.push('S' + x[0]); labels.push(x[1] || x[0]); parents.push('I' + i);
          values.push(x[5] || 0); colors.push(x[4]); custom.push([x[4], x[0], 0, 0]);
        });
        total += v;
        wsum += (s.chg || 0) * v;
      });
      values[0] = total;
      colors[0] = total ? wsum / total : 0;
      custom[0][0] = colors[0];
      var gd = plot('ov-sectors', [{
        type: 'treemap', ids: ids, labels: labels, parents: parents, values: values,
        branchvalues: 'total', maxdepth: 3, customdata: custom,
        level: sec.pick >= 0 ? 'I' + sec.pick : 'all',
        texttemplate: '<b>%{label}</b><br>%{customdata[0]:+.2f}%',
        hovertemplate: '%{label}　%{customdata[1]}<br>成交值 %{value:,.2f} 億' +
                       '<br>漲跌 %{customdata[0]:+.2f}%<extra></extra>',
        marker: {colors: colors,
                 colorscale: [[0, c.down], [0.5, dark ? '#3a3f55' : '#e9ecef'], [1, c.up]],
                 cmin: -5, cmax: 5, cmid: 0,
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
          var p = ev && ev.points && ev.points[0];
          if (!p) return;
          if (String(p.id).charAt(0) === 'S') {
            openStock(String(p.id).slice(1));
            return false;
          }
          var next = String(ev.nextLevel || 'all');
          sec.pick = next.charAt(0) === 'I' ? Number(next.slice(1)) : -1;
          pane.querySelector('.sec-pick').value = String(sec.pick);
          sec.shown = SEC_PAGE;
          secList(pane);
        });
      }
    }

    function secPicker(pane) {
      var sel = pane.querySelector('.sec-pick');
      if (sel.options.length) return;
      var all = el('option', null, '全部產業（全市場排行）');
      all.value = '-1';
      sel.appendChild(all);
      sec.data.industries.forEach(function (s, i) {
        var o = el('option', null, s.industry + '（' + s.n + ' 檔）');
        o.value = String(i);
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () {
        sec.pick = Number(sel.value);
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
    }

    function secList(pane) {
      var d = sec.data;
      var rows = d.stocks.filter(function (x) { return sec.pick < 0 || x[2] === sec.pick; });
      if (sec.sort === 'up') rows = rows.slice().sort(function (a, b) { return (b[4] || 0) - (a[4] || 0); });
      else if (sec.sort === 'down') rows = rows.slice().sort(function (a, b) { return (a[4] || 0) - (b[4] || 0); });
      var sum = pane.querySelector('.sec-sum');
      sum.textContent = '';
      if (sec.pick >= 0) {
        var s = d.industries[sec.pick];
        sum.appendChild(document.createTextNode(s.industry + '　加權漲跌 '));
        sum.appendChild(el('b', dir(s.chg), signed(s.chg, 2, '%')));
        sum.appendChild(document.createTextNode('　上漲 ' + s.up + ' 家、下跌 ' + s.down +
                                                ' 家　成交值 ' + fmt(s.turnover, 1) + ' 億'));
      } else {
        sum.textContent = '全市場 ' + rows.length + ' 檔（不含 ETF）';
      }
      var box = pane.querySelector('.sec-table');
      box.textContent = '';
      var t = el('table', 'ov-table');
      var h = el('tr');
      ['股票', '收盤', '漲跌', '成交值（億）'].forEach(function (x) { h.appendChild(el('th', null, x)); });
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
        tr.appendChild(el('td', dir(x[4]), signed(x[4], 2, '%')));
        tr.appendChild(el('td', null, fmt(x[5], 2)));
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

    function sectors(pane) {
      return getJSON('data/sectors.json').then(function (d) {
        sec.data = d;
        pane.querySelector('.ov-asof').textContent = '資料日期 ' + d.asof + '（盤後）　·　' +
          '點產業放大，點最上方的標題回到上一層，點個股看深度頁';
        secPicker(pane);
        secTreemap(pane);
        secList(pane);
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
      rows.forEach(function (r) {
        var tr = el('tr', 'go');
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
    }

    function flows(pane, d) {
      var f = d.flows || {};
      Array.prototype.slice.call(pane.querySelectorAll('.ov-flow')).forEach(function (box) {
        flowTable(box, f[flowSide + '_' + box.dataset.side]);
      });
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

    var RENDER = {today: today, market: market, sectors: sectors, flows: flows};

    function show(sub) {
      if (!sub || !RENDER[sub]) return;
      var pane = panel.querySelector('.subpanel[data-sub="' + sub + '"]');
      if (!shown(pane)) return;
      load().then(function (d) { return RENDER[sub](pane, d); })
        .then(function () { syncSticky(); })
        .catch(function () {
          failMsg(pane.querySelector('.ov-body') || pane.querySelector('.sec-table') ||
                  pane.querySelector('.ichart') || pane);
        });
    }

    onShow(panel, show);
    window.addEventListener('dash-theme', function () { show(currentSub(panel)); });
    show(currentSub(panel));
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
        xaxis: {type: 'category', gridcolor: c.grid, linecolor: c.grid, nticks: 6, tickangle: 0,
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
        xaxis: {type: 'category', gridcolor: c.grid, nticks: 7, tickangle: 0, automargin: true},
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
      (s.ann || []).forEach(function (a) {
        var t = String(a[1] || '');
        while (t.length < 6) t = '0' + t;
        items.push({when: a[0] + ' ' + t.slice(0, 2) + ':' + t.slice(2, 4), text: a[2]});
      });
      if (!section('sd-ann', items.length)) return;
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
    var panel = document.getElementById('panel-stock');
    if (!panel) return;
    var pane = panel.querySelector('.subpanel[data-sub="screen"]');
    if (!pane) return;
    var body = pane.querySelector('.scr-body');
    var drawn = false;
    var SHOW = 15;

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

      t.appendChild(tb); wrap.appendChild(t); sec.appendChild(wrap);
      if (c.hits.length > SHOW) {
        more = el('button', 'scr-more', '顯示全部 ' + c.hits.length + ' 檔');
        more.type = 'button';
        more.addEventListener('click', function () { state.all = true; fill(); });
        sec.appendChild(more);
      }
      fill();
      return sec;
    }

    function show() {
      if (drawn || !shown(pane)) return Promise.resolve();
      return getJSON('data/screen.json').then(function (d) {
        body.textContent = '';
        body.appendChild(el('p', 'ov-asof', '資料日期 ' + d.asof + '（盤後）'));
        d.conditions.forEach(function (c) { body.appendChild(card(c)); });
        drawn = true;
        syncSticky();
      }).catch(function () { failMsg(body); });
    }

    openScreen = function (id) {
      if (document.getElementById('panel-stock').hidden) selectTab('stock', true);
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
