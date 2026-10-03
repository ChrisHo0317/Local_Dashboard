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
    // sectors.json 的 stocks：[代號, 名稱, 產業序號, 收盤, 成交值億, 1日%, 5日%, 10日%, 20日%, 60日%]
    var LEAF = 30;            // 熱力圖每個產業最多畫幾檔（清單裡是全部）
    var SEC_PAGE = 30;        // 清單一次列幾檔
    var PERIOD_LABEL = ['1 日', '5 日', '10 日', '20 日', '60 日'];
    var PERIOD_SCALE = [5, 10, 15, 20, 30];     // 熱力圖顏色到底的漲跌幅（%）
    var sec = {data: null, pick: -1, sort: 'turnover', shown: SEC_PAGE, period: 0};

    function ret(x) { return x[5 + sec.period]; }

    function secTreemap(pane) {
      var d = sec.data, c = palette(), p = sec.period;
      var ids = ['all'], labels = ['全市場'], parents = [''], values = [0], colors = [0],
          custom = [[0, '']];
      var total = 0, wsum = 0;
      d.industries.forEach(function (s, i) {
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
      bindChips(pane.querySelector('.sec-period'), function (chip) {
        sec.period = Number(chip.dataset.period);
        sec.shown = SEC_PAGE;
        secTreemap(pane);
        secList(pane);
      });
    }

    function secList(pane) {
      var d = sec.data, p = sec.period, label = PERIOD_LABEL[p];
      var rows = d.stocks.filter(function (x) { return sec.pick < 0 || x[2] === sec.pick; });
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
      if (sec.pick >= 0) {
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

    // ── 強勢股：強度（20 日漲幅）× 加速度（近 5 日 − 前 5 日漲幅）──────────
    // momentum.json 的 stocks：[代號, 名稱, 產業序號, 20 日均成交值億, [近 41 日收盤]]
    var MO_TOP = 10;          // 畫軌跡、畫累積漲幅曲線的檔數
    var MO_TAIL = 5;          // 軌跡往回畫幾天
    var MO_PAGE = 30;
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
        return (mo.ind < 0 || x[2] === mo.ind) && (x[3] || 0) >= mo.min;
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
        c0.appendChild(el('span', 'scr-reason', mo.data.industries[r.ind] + '　·　均量 ' + fmt(r.tv, 1) + ' 億'));
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
      t.appendChild(tb);
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
        xaxis: {type: 'category', gridcolor: c.grid, nticks: 6, tickangle: 0, automargin: true},
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
      sel.addEventListener('change', function () {
        mo.ind = Number(sel.value);
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
      // 新聞另外載入：抓不到也不影響圖表，晚到就補畫排行
      getJSON('data/stocknews.json').then(function (n) {
        if (mo.newsMeta === n) return;
        mo.newsMeta = n;
        mo.news = (n && n.stocks) || {};
        moNewsMeta(pane);
        if (mo.data) moTable(pane, mo.strong);
      }, function () {});
      return getJSON('data/momentum.json').then(function (d) {
        mo.data = d;
        pane.querySelector('.ov-asof').textContent = '資料日期 ' + d.asof + '（盤後）';
        var hint = pane.querySelector('.zoom-hint');
        hint.textContent = COARSE ? '點圓點看那一檔的數字。'
                                  : '點圓點打開個股頁；拖曳框選放大、雙擊還原（再雙擊看全部）。';
        moControls(pane);
        moPlayControls(pane);
        moDraw(pane);
      });
    }

    var RENDER = {today: today, market: market, sectors: sectors, momentum: momentum,
                  flows: flows};

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
