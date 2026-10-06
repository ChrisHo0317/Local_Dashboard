// 走勢圖的線條資料不嵌在頁面裡（首頁會大到手機要等很久），第一次顯示那張圖時
// 才下載 data/charts/{key}.json。每張圖只存一份 traces：淺色與深色的線條顏色
// 完全相同，只有 layout 不同。
const MOBILE_Q = window.matchMedia('(max-width: 820px)');

let dark = false;

Object.keys(CHARTS).forEach(function (k) { CHARTS[k].hidden = new Set(); });

// 窄螢幕：縮小邊界、拿掉 y 軸標題（單位已寫在頁面標頭）、隱藏工具列
function layoutFor(key, mobile) {
  const L = JSON.parse(JSON.stringify(CHARTS[key].layout[dark ? 'dark' : 'light']));
  if (!mobile) return L;
  L.margin = {l: 46, r: 14, t: 54, b: 34};
  L.yaxis  = Object.assign({}, L.yaxis, {title: {text: ''}});
  L.dragmode = false;
  return L;
}

// Plotly 不會因為 x 縮放而自動調整 y，切到短區間時線會擠成一團。
// 這裡依「目前 x 範圍內、且沒被關掉的線」重算 y 範圍。
// 用 calcdata 而不是原始 data：calcdata 的 x 已經是數值（毫秒），
// y 也解好了（嵌入的資料是 base64 二進位陣列），不必逐點換算。
function rescaleY(gd) {
  var fl = gd._fullLayout;
  if (!fl || !fl.xaxis || !gd.calcdata) return;
  var x0 = fl.xaxis.r2l(fl.xaxis.range[0]);
  var x1 = fl.xaxis.r2l(fl.xaxis.range[1]);
  var lo = Infinity, hi = -Infinity;

  gd.calcdata.forEach(function (cd, i) {
    var tr = (gd._fullData || [])[i];
    if (!tr || tr.visible !== true) return;
    for (var j = 0; j < cd.length; j++) {
      var pt = cd[j];
      var y = pt.y;
      if (y === undefined || y === null || y !== y) continue;   // y!==y 濾 NaN
      if (pt.x < x0 || pt.x > x1) continue;
      if (y < lo) lo = y;
      if (y > hi) hi = y;
    }
  });

  if (lo === Infinity || hi === -Infinity) return;
  var pad = (hi - lo) * 0.04 || Math.abs(hi) * 0.02 || 1;
  // 價格與殖利率都不會是負的，下緣不要因為留白而掉到 0 以下
  var bottom = (lo >= 0) ? Math.max(0, lo - pad) : lo - pad;
  Plotly.relayout(gd, {'yaxis.range': [bottom, hi + pad]});
}

function loadChart(key) {
  const c = CHARTS[key];
  if (c.traces) return Promise.resolve(c);
  if (!c.pending) {
    c.pending = fetch('data/charts/' + key + '.json?v=' + VERSION)
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (d) { c.traces = d.traces; c.layout = d.layout; return c; })
      .catch(function (e) { c.pending = null; throw e; });
  }
  return c.pending;
}

// 資料還沒下載就先下載再畫；下載失敗在圖的位置留一句話，重新整理就會再試。
function renderChart(key) {
  return loadChart(key).then(function () { drawChart(key); }).catch(function () {
    const gd = document.getElementById('chart-' + key);
    if (gd && !CHARTS[key].rendered) {
      gd.textContent = '圖表資料載入失敗，請確認網路連線後下拉重新整理。';
      gd.classList.add('chart-fail');
    }
  });
}

function drawChart(key) {
  const c = CHARTS[key];
  const gd = document.getElementById('chart-' + key);
  if (gd.classList.contains('chart-fail')) {
    gd.textContent = '';
    gd.classList.remove('chart-fail');
  }
  const mobile = MOBILE_Q.matches;
  const data = c.traces.map(function (t, i) {
    return Object.assign({}, t, {visible: c.hidden.has(i) ? 'legendonly' : true});
  });
  const L = layoutFor(key, mobile);

  // 已經畫過的話沿用目前的時間軸範圍：切換型號顯示或深色模式時，
  // 不該把使用者已經縮放好的區間重設回預設值。
  if (c.rendered && gd._fullLayout && gd._fullLayout.xaxis) {
    L.xaxis = Object.assign({}, L.xaxis, {range: gd._fullLayout.xaxis.range.slice()});
  }

  Plotly.react(gd, data, L, {
    responsive: true,
    displaylogo: false,
    displayModeBar: !mobile,  // 手機隱藏工具列，改用原生手勢與下方時間軸縮圖
    // 觸控裝置上 Plotly 會把單次輕觸判成雙擊而重設縮放，直接關掉；
    // 要回到全區間改用左上角的「全部」按鈕。
    doubleClick: mobile ? false : 'reset+autosize'
  });

  if (!c.bound) {
    // 改變時間軸範圍後重算 y。自己的 relayout 也會觸發這個事件，用旗標擋掉遞迴。
    gd.on('plotly_relayout', function (ev) {
      if (c.busy) return;
      var touchedX = Object.keys(ev || {}).some(function (k) { return k.indexOf('xaxis') === 0; });
      if (!touchedX) return;
      c.busy = true;
      rescaleY(gd);
      setTimeout(function () { c.busy = false; }, 0);
    });
    c.bound = true;
  }

  c.rendered = true;
  c.dirty = false;
  rescaleY(gd);            // 型號顯示改變後 y 也要跟著重算
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('toggle').setAttribute('aria-checked', String(dark));
}

// 只重畫已經顯示過的圖；還沒畫的標記為待重畫，等它第一次被開啟時再處理。
// 在隱藏的分頁裡畫圖會量到錯誤的寬度，指標的座標換算就會失準。
function renderAll() {
  applyTheme();
  Object.keys(CHARTS).forEach(function (k) {
    if (CHARTS[k].rendered) { renderChart(k); } else { CHARTS[k].dirty = true; }
  });
  // 個股查詢的圖不在 CHARTS 裡（資料是當場查來的），它自己重畫
  window.dispatchEvent(new Event('dash-theme'));
}

// ── 收合式圖例（每張圖各一份，由 .legend-bar 就地生成）─────────
function buildLegend(bar) {
  const key = bar.dataset.chart;
  const c = CHARTS[key];

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'legend-toggle';
  btn.setAttribute('aria-expanded', 'false');
  const dots = document.createElement('span');
  dots.className = 'legend-dots';
  const label = document.createElement('span');
  const chev = document.createElement('span');
  chev.className = 'chev';
  chev.textContent = '\u25BC';
  btn.appendChild(dots); btn.appendChild(label); btn.appendChild(chev);

  const panel = document.createElement('div');
  panel.className = 'legend-panel';
  panel.hidden = true;
  const actions = document.createElement('div');
  actions.className = 'lg-actions';
  const list = document.createElement('div');
  list.className = 'legend-list';
  panel.appendChild(actions); panel.appendChild(list);

  function sync() {
    c.series.forEach(function (_, i) {
      const off = c.hidden.has(i);
      dots.children[i].classList.toggle('off', off);
      list.children[i].classList.toggle('off', off);
    });
    const shown = c.series.length - c.hidden.size;
    label.textContent = (shown === c.series.length)
      ? c.itemLabel : (c.itemLabel + ' ' + shown + '/' + c.series.length);
  }

  [['show', '全部顯示'], ['hide', '全部隱藏']].forEach(function (a) {
    const ab = document.createElement('button');
    ab.type = 'button'; ab.textContent = a[1];
    ab.addEventListener('click', function () {
      c.hidden.clear();
      if (a[0] === 'hide') c.series.forEach(function (_, i) { c.hidden.add(i); });
      sync(); renderChart(key);
    });
    actions.appendChild(ab);
  });

  c.series.forEach(function (s, i) {
    const dot = document.createElement('i');
    dot.style.background = s.color;
    dots.appendChild(dot);

    const item = document.createElement('div');
    item.className = 'lg-item';
    const sw = document.createElement('span');
    sw.className = 'sw'; sw.style.background = s.color;
    const nm = document.createElement('span');
    nm.textContent = s.name;   // textContent：名稱來自外部資料，不直接當 HTML 插入
    item.appendChild(sw); item.appendChild(nm);
    item.addEventListener('click', function () {
      if (c.hidden.has(i)) { c.hidden.delete(i); } else { c.hidden.add(i); }
      sync(); renderChart(key);
    });
    list.appendChild(item);
  });

  btn.addEventListener('click', function () {
    const open = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!open));
    panel.hidden = open;
  });

  bar.appendChild(btn); bar.appendChild(panel);
  sync();
}

// ── 黏著層：把標題與表頭的實際高度餵給 CSS ─────────────────
// 標題高度會變（分頁不同、捲動後說明文字收起），所以用量到的值設 CSS 變數，
// 下面的表頭與日期列才知道該釘在哪個位置。
var pageHeader = document.querySelector('header');
var stickyTicking = false;

function syncSticky() {
  var root = document.documentElement;
  root.style.setProperty('--head-h', pageHeader.offsetHeight + 'px');
  var thead = document.querySelector('.cal-table thead');
  if (thead) root.style.setProperty('--thead-h', thead.offsetHeight + 'px');
}

window.addEventListener('scroll', function () {
  if (stickyTicking) return;
  stickyTicking = true;
  requestAnimationFrame(function () {
    document.body.classList.toggle('scrolled', window.scrollY > 8);
    syncSticky();
    stickyTicking = false;
  });
}, {passive: true});

window.addEventListener('resize', syncSticky);

// ── 標題列的返回鍵 ─────────────────────────────────────────
// 分頁內部有「進到某一則」的檢視時（新聞內文、筆記編輯）登記回去的動作，
// 按鍵就跟著標題一起釘在畫面上方，捲到內文中段也按得到。
var backBtn = document.getElementById('back');
var backAction = null;

function setBack(fn) {
  backAction = fn;
  backBtn.hidden = !fn;
  syncSticky();
}

backBtn.addEventListener('click', function () { if (backAction) backAction(); });

// 右滑等於按返回鍵 —— 只在有東西可返回時才理會。
(function () {
  var SWIPE = 70;        // 至少要滑這麼多 px 才算
  var IN_FIELD = 130;    // 起點在輸入框裡就要滑更長 —— 那裡也可能是在移游標
  var SLOPE = 1.6;       // 橫向位移要明顯大於縱向，避免捲動時誤觸
  var LIMIT = 700;       // 超過這個時間就當成慢慢拖，不是滑動手勢
  var x0 = 0, y0 = 0, t0 = 0, tracking = false, inField = false;

  // 起點在會橫向捲動的東西上（標籤列、子分頁列）就讓它自己捲
  function scrollsX(node) {
    while (node && node !== document.body) {
      if (node.scrollWidth > node.clientWidth + 4) {
        var ov = getComputedStyle(node).overflowX;
        if (ov === 'auto' || ov === 'scroll') return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  document.addEventListener('touchstart', function (e) {
    tracking = false;
    if (!backAction || e.touches.length !== 1) return;
    var el = e.target;
    if (scrollsX(el)) return;
    // 筆記編輯時畫面中央整片都是輸入框，完全不理會等於滑不動；
    // 改成一樣可以滑，但門檻拉高，才不會跟移游標混在一起
    inField = !!(el.closest && el.closest('input, textarea, select'));
    x0 = e.touches[0].clientX;
    y0 = e.touches[0].clientY;
    t0 = Date.now();
    tracking = true;
  }, {passive: true});

  document.addEventListener('touchend', function (e) {
    if (!tracking) return;
    tracking = false;
    if (!backAction || Date.now() - t0 > LIMIT) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - x0;
    var dy = t.clientY - y0;
    if (dx > (inField ? IN_FIELD : SWIPE) && dx > Math.abs(dy) * SLOPE) backAction();
  }, {passive: true});
})();

// ── 底部標籤列 ─────────────────────────────────────────────
var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
var pill = document.getElementById('tab-pill');

function movePill(btn, animate) {
  if (!animate) pill.classList.add('no-anim');
  pill.style.width = btn.offsetWidth + 'px';
  pill.style.transform = 'translateX(' + btn.offsetLeft + 'px)';
  if (!animate) {
    void pill.offsetWidth;            // 強制 reflow，讓 no-anim 立即生效
    pill.classList.remove('no-anim');
  }
}

function selectTab(name, animate) {
  setBack(null);            // 換分頁就離開內文檢視
  tabs.forEach(function (t) {
    var on = t.dataset.tab === name;
    t.setAttribute('aria-selected', String(on));
    if (on) movePill(t, animate);
    var panel = document.getElementById('panel-' + t.dataset.tab);
    if (panel) panel.hidden = !on;
  });
  var gear = document.getElementById('settings-btn');
  if (gear) gear.setAttribute('aria-pressed', String(name === 'settings'));
  setMetaOpen(false);
  var h = HEAD[name];
  document.getElementById('page-title').textContent = h.title;
  document.getElementById('page-meta-text').innerHTML = h.meta;
  // 有二階分頁的話，回到主分頁時重設回第一個子分頁
  var panel = document.getElementById('panel-' + name);
  var firstSub = panel ? panel.querySelector('.subtab:not([hidden])') : null;
  if (firstSub && firstSub.getAttribute('aria-selected') !== 'true') { firstSub.click(); }
  else { activateCharts(panel); }
  // 圖表第一次顯示（或主題變更後首次顯示）才真正繪製；
  // 已畫過的只要重新丈量寬度即可。
  var c = CHARTS[name];
  if (c) {
    if (!c.rendered || c.dirty) { renderChart(name); }
    else { Plotly.Plots.resize(document.getElementById('chart-' + name)); }
  }
  syncSticky();   // 各分頁的說明文字行數不同，標題高度會跟著變
}

tabs.forEach(function (t) {
  t.addEventListener('click', function () { selectTab(t.dataset.tab, true); });
});

// 頁首右上角的齒輪：設定不佔底部標籤列
(function () {
  var gear = document.getElementById('settings-btn');
  if (gear) gear.addEventListener('click', function () { selectTab('settings', true); });
})();

// 頁首的 ⓘ：手機上說明文字預設收起，點了才展開（電腦版一直顯示，按鈕隱藏）
function setMetaOpen(open) {
  document.body.classList.toggle('meta-open', open);
  var b = document.getElementById('meta-btn');
  if (b) b.setAttribute('aria-expanded', String(open));
}
(function () {
  var b = document.getElementById('meta-btn');
  if (b) b.addEventListener('click', function () {
    setMetaOpen(!document.body.classList.contains('meta-open'));
    syncSticky();
  });
})();

window.addEventListener('resize', function () {
  var cur = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
  if (cur) movePill(cur, false);
});

// ── 分類 ───────────────────────────────────────────────────
// 底部標籤列一次只顯示一組分頁；「設定」的 data-group 是 all，永遠在。
// 分組與歸屬都可以在設定裡改，存在 localStorage，所以分類列的按鈕
// 是依設定產生的，不是產生頁面時寫死的。
var GROUP_KEY = 'dash-groups';
var groupBar = document.getElementById('groupbar');
var grpPill = document.getElementById('grp-pill');
var groups = loadGroups();
var curGroup = groups.length ? groups[0].id : 'all';

function loadGroups() {
  var saved = null;
  try { saved = JSON.parse(localStorage.getItem(GROUP_KEY)); } catch (e) { saved = null; }
  var list = (saved && Array.isArray(saved.groups)) ? saved.groups : null;
  if (list && list.some(function (g) { return g && Array.isArray(g.tabs) && g.tabs.indexOf('overview') >= 0; })) {
    list = null;   // v0.3.063 把總覽拆成今日、市場、選股，舊的排序已經不適用
  }
  if (!list) list = JSON.parse(JSON.stringify(DEFAULT_GROUPS));

  // 只留下真的存在的分頁，並確保每個分頁都有歸屬 ——
  // 改版新增分頁時，舊的設定裡不會有它，沒有這段就會憑空消失。
  var seen = {};
  list = list.filter(function (g) { return g && g.id && Array.isArray(g.tabs); });
  list.forEach(function (g) {
    g.tabs = g.tabs.filter(function (id) {
      if (PANEL_IDS.indexOf(id) < 0 || seen[id]) return false;
      seen[id] = true;
      return true;
    });
  });
  if (!list.length) list = JSON.parse(JSON.stringify(DEFAULT_GROUPS));
  PANEL_IDS.forEach(function (id) {
    if (seen[id]) return;
    var home = DEFAULT_GROUPS.filter(function (d) { return d.tabs.indexOf(id) >= 0; })[0];
    var target = home && list.filter(function (g) { return g.id === home.id; })[0];
    (target || list[0]).tabs.push(id);
  });
  return list;
}

function saveGroups() {
  try { localStorage.setItem(GROUP_KEY, JSON.stringify({v: 1, groups: groups})); }
  catch (e) { /* 隱私模式：這次改動有效，下次開就回到預設 */ }
}

function groupOf(id) {
  for (var i = 0; i < groups.length; i++) {
    if (groups[i].tabs.indexOf(id) >= 0) return groups[i].id;
  }
  return null;
}

function inGroup(tab) {
  return tab.dataset.group === 'all' || groupOf(tab.dataset.tab) === curGroup;
}

// 依設定重畫分類列。只有一組時整列就沒有意義，直接不顯示。
function renderGroupBar() {
  Array.prototype.slice.call(groupBar.querySelectorAll('.grp'))
    .forEach(function (b) { b.remove(); });
  groupBar.hidden = groups.length < 2;
  groups.forEach(function (g) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'grp';
    b.dataset.group = g.id;
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(g.id === curGroup));
    b.textContent = g.label;
    b.addEventListener('click', function () { selectGroup(g.id, true); });
    groupBar.appendChild(b);
  });
}

function selectGroup(name, animate) {
  if (!groups.filter(function (g) { return g.id === name; }).length) {
    name = groups.length ? groups[0].id : 'all';
  }
  curGroup = name;
  Array.prototype.slice.call(groupBar.querySelectorAll('.grp')).forEach(function (g) {
    var on = g.dataset.group === name;
    g.setAttribute('aria-selected', String(on));
    if (on) {
      if (!animate) grpPill.classList.add('no-anim');
      grpPill.style.width = g.offsetWidth + 'px';
      grpPill.style.transform = 'translateX(' + g.offsetLeft + 'px)';
      if (!animate) { void grpPill.offsetWidth; grpPill.classList.remove('no-anim'); }
    }
  });
  grpPill.hidden = groupBar.hidden;
  applyVisibility(true);      // 換組後標籤列的內容變了，可能要換分頁
}

// ── 設定裡的資料卡片：可摺疊 ───────────────────────────────
// 預設全部收起（八張攤開要捲很久），展開哪幾張記在 localStorage。
(function () {
  var KEY = 'dash-cards-open';
  var open = {};
  try { open = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { open = {}; }

  Array.prototype.slice.call(document.querySelectorAll('.card.fold')).forEach(function (card) {
    var id = card.dataset.card;
    var btn = card.querySelector('.card-t');
    function apply(on) {
      card.classList.toggle('open', on);
      btn.setAttribute('aria-expanded', String(on));
    }
    apply(open[id] === true);
    btn.addEventListener('click', function () {
      var on = !card.classList.contains('open');
      apply(on);
      open[id] = on;
      try { localStorage.setItem(KEY, JSON.stringify(open)); } catch (e) { /* 隱私模式 */ }
    });
  });
})();

// ── 設定裡的分類編輯器 ─────────────────────────────────────
// 分組可以新增、改名、刪除；分頁用長按拖曳換組或調順序。
// 觸控裝置沒有 HTML5 的拖放，所以用 pointer 事件自己做：長按才啟動，
// 不然在清單上滑動會變成拖東西而不是捲頁面。
(function () {
  var box = document.getElementById('group-editor');
  if (!box) return;
  var addBtn = document.getElementById('group-add');
  var HOLD = 250;          // 按住這麼久才進入拖曳
  var MOVE_CANCEL = 8;     // 還沒進入拖曳就移動超過這個距離 = 想捲頁面

  function newId() {
    return 'g' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  }

  function commit() {
    saveGroups();
    render();
    renderGroupBar();
    selectGroup(curGroup, false);
  }

  function render() {
    box.textContent = '';
    groups.forEach(function (g, gi) {
      var sec = document.createElement('div');
      sec.className = 'ge-group';
      sec.dataset.group = g.id;

      var head = document.createElement('div');
      head.className = 'ge-head';
      var name = document.createElement('span');
      name.className = 'ge-name';
      name.textContent = g.label;
      head.appendChild(name);

      var acts = document.createElement('span');
      acts.className = 'ge-acts';
      var ren = document.createElement('button');
      ren.type = 'button';
      ren.className = 'ge-btn';
      ren.textContent = '改名';
      ren.addEventListener('click', function () {
        var v = window.prompt('分組名稱', g.label);
        if (v === null) return;
        v = v.trim();
        if (!v) return;
        g.label = v.slice(0, 12);
        commit();
      });
      acts.appendChild(ren);

      if (groups.length > 1) {
        var del = document.createElement('button');
        del.type = 'button';
        del.className = 'ge-btn ge-del';
        del.textContent = '刪除';
        del.addEventListener('click', function () {
          var moved = g.tabs.length;
          if (!window.confirm('刪除分組「' + g.label + '」？' +
              (moved ? '裡面的 ' + moved + ' 個分頁會移到第一個分組。' : ''))) return;
          groups = groups.filter(function (x) { return x !== g; });
          if (moved) groups[0].tabs = groups[0].tabs.concat(g.tabs);
          if (curGroup === g.id) curGroup = groups[0].id;
          commit();
        });
        acts.appendChild(del);
      }
      head.appendChild(acts);
      sec.appendChild(head);

      var list = document.createElement('div');
      list.className = 'ge-list';
      list.dataset.group = g.id;
      if (!g.tabs.length) {
        var empty = document.createElement('p');
        empty.className = 'ge-empty';
        empty.textContent = '這一組還沒有分頁，拖一個過來。';
        list.appendChild(empty);
      }
      g.tabs.forEach(function (id) {
        var row = document.createElement('div');
        row.className = 'ge-item';
        row.dataset.tab = id;
        var handle = document.createElement('span');
        handle.className = 'ge-handle';
        handle.textContent = '≡';
        handle.setAttribute('aria-hidden', 'true');
        var label = document.createElement('span');
        label.className = 'ge-label';
        label.textContent = TAB_LABELS[id] || id;
        row.appendChild(handle);
        row.appendChild(label);
        // 只有把手能拖：整列都能拖的話，手指落在列上想捲頁面會變成拖東西
        handle.addEventListener('pointerdown', function (e) { press(e, row, id); });
        list.appendChild(row);
      });
      sec.appendChild(list);
      box.appendChild(sec);
    });
  }

  // ── 長按拖曳 ────────────────────────────────────────────
  var drag = null;

  function press(e, row, id) {
    if (e.button != null && e.button !== 0) return;
    var startX = e.clientX, startY = e.clientY;
    var timer = setTimeout(function () { begin(row, id, startX, startY); }, HOLD);

    function moveBefore(ev) {
      if (drag) return;
      if (Math.abs(ev.clientX - startX) > MOVE_CANCEL ||
          Math.abs(ev.clientY - startY) > MOVE_CANCEL) cleanup();
    }
    function cleanup() {
      clearTimeout(timer);
      document.removeEventListener('pointermove', moveBefore);
      document.removeEventListener('pointerup', cleanup);
      document.removeEventListener('pointercancel', cleanup);
    }
    document.addEventListener('pointermove', moveBefore);
    document.addEventListener('pointerup', cleanup);
    document.addEventListener('pointercancel', cleanup);
  }

  function begin(row, id, x, y) {
    var rect = row.getBoundingClientRect();
    var ghost = row.cloneNode(true);
    ghost.className = 'ge-item ge-ghost';
    ghost.style.width = rect.width + 'px';
    ghost.style.left = rect.left + 'px';
    ghost.style.top = rect.top + 'px';
    document.body.appendChild(ghost);
    row.classList.add('ge-dragging');
    document.body.classList.add('ge-nosel');
    drag = {row: row, id: id, ghost: ghost,
            dx: x - rect.left, dy: y - rect.top};
    if (navigator.vibrate) { try { navigator.vibrate(10); } catch (e) {} }
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onDrop);
    document.addEventListener('pointercancel', onDrop);
  }

  function onMove(e) {
    if (!drag) return;
    e.preventDefault();
    drag.ghost.style.left = (e.clientX - drag.dx) + 'px';
    drag.ghost.style.top = (e.clientY - drag.dy) + 'px';

    // 找出手指底下的那一組，以及要插在哪一列之前
    var lists = Array.prototype.slice.call(box.querySelectorAll('.ge-list'));
    var target = null;
    lists.forEach(function (l) {
      var r = l.getBoundingClientRect();
      if (e.clientY >= r.top - 8 && e.clientY <= r.bottom + 8) target = l;
    });
    if (!target) return;
    var after = null;
    Array.prototype.slice.call(target.querySelectorAll('.ge-item')).forEach(function (it) {
      if (it === drag.row) return;
      var r = it.getBoundingClientRect();
      if (e.clientY > r.top + r.height / 2) after = it;
    });
    var empty = target.querySelector('.ge-empty');
    if (empty) empty.remove();
    if (after) target.insertBefore(drag.row, after.nextSibling);
    else target.insertBefore(drag.row, target.firstChild);
  }

  function onDrop() {
    if (!drag) return;
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onDrop);
    document.removeEventListener('pointercancel', onDrop);
    drag.ghost.remove();
    drag.row.classList.remove('ge-dragging');
    document.body.classList.remove('ge-nosel');
    drag = null;

    // 以畫面上的實際排列為準寫回設定
    groups.forEach(function (g) {
      var list = box.querySelector('.ge-list[data-group="' + g.id + '"]');
      if (!list) return;
      g.tabs = Array.prototype.slice.call(list.querySelectorAll('.ge-item'))
        .map(function (it) { return it.dataset.tab; });
    });
    commit();
  }

  addBtn.addEventListener('click', function () {
    var v = window.prompt('新分組的名稱', '新分組');
    if (v === null) return;
    v = v.trim();
    if (!v) return;
    groups.push({id: newId(), label: v.slice(0, 12), tabs: []});
    commit();
  });

  render();
})();

// ── 分頁顯示切換（設定分頁裡每張卡片右上角的開關）───────────
var VIS_KEY = 'dash-visible';
var visible = {};
try { visible = JSON.parse(localStorage.getItem(VIS_KEY)) || {}; } catch (e) { visible = {}; }

function isVisible(id) { return visible[id] !== false; }   // 預設全開

// 底部標籤列的排列跟著分組裡的順序走 —— 在設定裡把分頁往上拖，
// 標籤列也應該跟著往左，不然拖了半天看不出差別。
function orderTabs() {
  var g = groups.filter(function (x) { return x.id === curGroup; })[0];
  if (!g) return;
  var bar = document.querySelector('.tabbar');
  var settings = bar.querySelector('.tab[data-tab="settings"]');
  g.tabs.forEach(function (id) {
    var t = bar.querySelector('.tab[data-tab="' + id + '"]');
    if (t) bar.appendChild(t);
  });
  if (settings) bar.appendChild(settings);   // 設定固定在最後
}

// reselect：由開關觸發時要處理「正在看的分頁被關掉」
function applyVisibility(reselect) {
  orderTabs();
  PANEL_IDS.forEach(function (id) {
    var on = isVisible(id);
    var tab = document.querySelector('.tab[data-tab="' + id + '"]');
    if (tab) tab.hidden = !on || !inGroup(tab);   // 關掉的、或不屬於這一組的
    var sw = document.querySelector('.switch[data-panel="' + id + '"]');
    if (sw) sw.setAttribute('aria-checked', String(on));
    if (!on) {
      var panel = document.getElementById('panel-' + id);
      if (panel) panel.hidden = true;
    }
  });

  if (!reselect) return;

  var cur = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
  if (!cur || cur.hidden) {
    var next = firstTabOfGroup();
    if (next) selectTab(next.dataset.tab, false);
  } else {
    movePill(cur, false);   // 分頁數變了，指示器要重新定位
  }
}

// 目前這一組的第一個分頁 —— 依設定裡的排序，不是頁面產生時的順序。
// tabs 這個陣列是初始化時抓的，順序固定；使用者拖曳過之後要看 groups。
function firstTabOfGroup() {
  var g = groups.filter(function (x) { return x.id === curGroup; })[0];
  var ids = g ? g.tabs : [];
  for (var i = 0; i < ids.length; i++) {
    var t = document.querySelector('.tab[data-tab="' + ids[i] + '"]');
    if (t && !t.hidden) return t;
  }
  return document.querySelector('.tab[data-tab="settings"]');
}

document.querySelectorAll('.switch[data-panel]').forEach(function (sw) {
  sw.addEventListener('click', function () {
    var id = sw.dataset.panel;
    visible[id] = !isVisible(id);
    try { localStorage.setItem(VIS_KEY, JSON.stringify(visible)); } catch (e) {}
    applyVisibility(true);
  });
});

// ── 觸控手勢 ───────────────────────────────────────────────
// 單指：按下當下就顯示垂直指標線與該時間點的資料，按住拖曳可移動；
//       指標已顯示時再輕點一下（沒有拖動）就收起。
// 雙指：以兩指中心為錨點縮放時間軸。
//
// 繪圖區內的觸控事件會在捕獲階段被攔下（stopPropagation），不讓 Plotly 自己的
// 拖曳／點按處理接手 —— 否則指標會變成放開手指才出現，輕點也會被判成雙擊而重設縮放。
// 落在時間軸縮圖與區間按鈕上的觸控則放行，那些仍由 Plotly 自己處理。
// 桌機滑鼠完全不受影響。
// opts.pan：單指拖曳要平移時間軸（個股查詢），而不是移動指標。
// 兩種圖的差別只在單指拖曳那一段，其餘（雙指縮放、輕點開關指標、
// 擋掉觸控後補送的相容滑鼠事件）完全一樣，所以共用同一份。
function initTouch(gd, opts) {
  if (!window.matchMedia('(pointer: coarse)').matches) return;
  var panMode = !!(opts && opts.pan);

  var pinch = null, shown = false, wasShown = false, moved = false, taken = false;
  var sx = 0, sy = 0, pan = null;
  var TAP_SLOP = 6;
  var MIN_SPAN = 3 * 864e5;

  function xAxis() { return gd._fullLayout && gd._fullLayout.xaxis; }
  function plotLeft() { return gd.getBoundingClientRect().left + xAxis()._offset; }

  function inPlot(t) {
    var fl = gd._fullLayout;
    if (!fl || !fl.xaxis || !fl.yaxis) return false;
    var r = gd.getBoundingClientRect();
    var px = t.clientX - r.left, py = t.clientY - r.top;
    return px >= fl.xaxis._offset && px <= fl.xaxis._offset + fl.xaxis._length &&
           py >= fl.yaxis._offset && py <= fl.yaxis._offset + fl.yaxis._length;
  }

  function fullExtent() {
    var xa = xAxis(), lo = Infinity, hi = -Infinity;
    (gd.data || []).forEach(function (t) {
      if (!t.x || !t.x.length) return;
      lo = Math.min(lo, xa.d2l(t.x[0]));
      hi = Math.max(hi, xa.d2l(t.x[t.x.length - 1]));
    });
    return (lo < hi) ? [lo, hi] : null;
  }

  function showAt(touch) {
    var xa = xAxis();
    if (!xa) return;
    var px = touch.clientX - plotLeft();
    px = Math.min(Math.max(px, 0), xa._length);
    Plotly.Fx.hover(gd, {xval: xa.p2l(px)}, 'xy');
    shown = true;
  }

  function hide() { Plotly.Fx.unhover(gd); shown = false; }

  // 指標也可能被我們以外的原因清掉（Plotly 內部、其他互動）。
  // 跟著 plotly_unhover 更新旗標，否則「再次輕點收起」會誤判成已顯示而空點一次。
  // 圖表是延後繪製的，gd.on 要等 Plotly 初始化後才有，因此第一次觸控時才綁。
  var unhoverBound = false;
  function bindUnhover() {
    if (unhoverBound || typeof gd.on !== 'function') return;
    gd.on('plotly_unhover', function () { shown = false; });
    unhoverBound = true;
  }

  function dist(e) {
    var dx = e.touches[0].clientX - e.touches[1].clientX;
    var dy = e.touches[0].clientY - e.touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy) || 1;
  }

  gd.addEventListener('touchstart', function (e) {
    var xa = xAxis();
    if (!xa) return;
    bindUnhover();

    if (e.touches.length === 2) {
      if (!inPlot(e.touches[0]) && !inPlot(e.touches[1])) return;
      e.stopPropagation();
      taken = true;
      hide();
      pinch = {
        d: dist(e),
        cx: (e.touches[0].clientX + e.touches[1].clientX) / 2 - plotLeft(),
        r0: xa.d2l(xa.range[0]),
        r1: xa.d2l(xa.range[1]),
        len: xa._length
      };
      return;
    }

    if (e.touches.length !== 1 || !inPlot(e.touches[0])) { taken = false; return; }
    e.stopPropagation();
    taken = true;
    pinch = null;
    wasShown = shown;
    moved = false;
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
    pan = panMode ? {r0: xa.d2l(xa.range[0]), r1: xa.d2l(xa.range[1]), len: xa._length}
                  : null;
    showAt(e.touches[0]);          // 按下當下就顯示，不等放開
  }, {capture: true, passive: true});

  gd.addEventListener('touchmove', function (e) {
    if (pinch && e.touches.length === 2) {
      e.stopPropagation();
      if (e.cancelable) e.preventDefault();
      var scale = pinch.d / dist(e);
      var frac = Math.min(1, Math.max(0, pinch.cx / pinch.len));
      var anchor = pinch.r0 + (pinch.r1 - pinch.r0) * frac;
      var lo = anchor - (anchor - pinch.r0) * scale;
      var hi = anchor + (pinch.r1 - anchor) * scale;
      var ext = fullExtent();
      if (ext) { lo = Math.max(lo, ext[0]); hi = Math.min(hi, ext[1]); }
      if (hi - lo < MIN_SPAN) return;
      Plotly.relayout(gd, {'xaxis.range': [lo, hi]});
      return;
    }

    if (!taken || pinch || e.touches.length !== 1) return;
    var t = e.touches[0];
    if (Math.abs(t.clientX - sx) > TAP_SLOP || Math.abs(t.clientY - sy) > TAP_SLOP) moved = true;
    e.stopPropagation();
    if (e.cancelable) e.preventDefault();

    if (pan) {
      if (!moved) return;
      if (shown) hide();                       // 開始拖了就別留著指標
      var span = pan.r1 - pan.r0;
      var shift = -(t.clientX - sx) / pan.len * span;
      var lo = pan.r0 + shift, hi = pan.r1 + shift;
      var ext = fullExtent();
      if (ext) {                               // 不要拖到資料以外的空白
        if (lo < ext[0]) { lo = ext[0]; hi = lo + span; }
        if (hi > ext[1]) { hi = ext[1]; lo = hi - span; }
      }
      Plotly.relayout(gd, {'xaxis.range': [lo, hi]});
      return;
    }
    showAt(t);
  }, {capture: true, passive: false});

  gd.addEventListener('touchend', function (e) {
    if (!taken) return;
    if (e.touches.length > 0) return;
    e.stopPropagation();
    if (pinch) { pinch = null; taken = false; return; }
    pan = null;
    if (wasShown && !moved) hide();
    taken = false;
  }, {capture: true, passive: true});

  // 觸控裝置上沒有真的滑鼠：輕觸後瀏覽器會補送一串相容滑鼠事件
  // （mousemove → mousedown → mouseup → click → mouseout），
  // 其中的 mouseout 會讓 Plotly 觸發 unhover，把我們剛設好的指標清掉。
  // 只擋主繪圖區（.nsewdrag）內的這類事件，時間軸縮圖與區間按鈕照常運作。
  ['mousemove', 'mousedown', 'mouseup', 'click', 'dblclick', 'mouseover', 'mouseout']
    .forEach(function (type) {
      gd.addEventListener(type, function (e) {
        if (e.target && e.target.closest && e.target.closest('.nsewdrag')) {
          e.stopPropagation();
        }
      }, {capture: true});
    });
}

// ── 行事曆／賽程表：篩選、標出今天、現在時間標示 ─────────────
// 財經行事曆與 F1 賽程共用同一套表格結構，所以逐個 .cal-table 各自初始化。
// 所有跟「現在」有關的東西都在瀏覽器端算，不在產生頁面時寫死 ——
// 頁面會被 CDN 快取，寫死的話隔天再開就會標錯。
// 月曆格狀圖：只有財經行事曆分頁有這個容器（calendar_render.py 才會產生
// .cal-month），其餘沿用 .cal-table 的分頁（F1、SpaceX）沒有就直接跳過。
// 資料不重新查——直接讀同一張表裡既有的 .cal-day / .cal-row，
// 這樣篩選（勾選式影響程度）改變時，格子上的圓點也會跟著更新。
function initMonthGrid(panel, table) {
  var container = panel ? panel.querySelector('.cal-month') : null;
  if (!container) return null;

  var grid = container.querySelector('.cal-month-grid');
  var label = container.querySelector('.cal-month-label');
  var prevBtn = container.querySelector('.cal-month-prev');
  var nextBtn = container.querySelector('.cal-month-next');
  var view = null;   // null＝跟著今天走；使用者按過上／下個月後才固定成 {y, m}
  var DOT_ORDER = [[3, 'i-high'], [2, 'i-mid'], [0, 'i-hol'], [4, 'i-tw']];

  function taipei() {
    return new Date(Date.now() + (8 * 60 + new Date().getTimezoneOffset()) * 60000);
  }
  function pad(n) { return String(n).padStart(2, '0'); }

  // 該天在表格裡有沒有資料：回傳「出現過的影響程度」集合，沒有這一天就是 null
  // （代表超出表格涵蓋的區間，不是「當天沒事件」）。
  function dayRanks(iso) {
    var day = table.querySelector('.cal-day[data-date="' + iso + '"]');
    if (!day) return null;
    var ranks = {};
    Array.prototype.slice.call(day.querySelectorAll('.cal-row')).forEach(function (r) {
      if (r.hidden) return;
      ranks[Number(r.dataset.impact)] = true;
    });
    return ranks;
  }

  function jumpTo(iso) {
    var target = table.querySelector('.cal-day[data-date="' + iso + '"]');
    if (!target) return;
    if (target.hidden && table._reveal) table._reveal(iso);
    var top = target.getBoundingClientRect().top + window.pageYOffset
              - (pageHeader.offsetHeight + 12);
    window.scrollTo({top: top, behavior: 'smooth'});
  }

  function render() {
    var t = taipei();
    var y = view ? view.y : t.getFullYear();
    var m = view ? view.m : t.getMonth();       // 0-based
    var todayIso = t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());

    label.textContent = y + ' 年 ' + (m + 1) + ' 月';

    var first = new Date(y, m, 1);
    var lead = (first.getDay() + 6) % 7;        // 週一為每列第一格
    var daysInMonth = new Date(y, m + 1, 0).getDate();

    var cells = [];
    for (var i = 0; i < lead; i++) cells.push(null);
    for (var d = 1; d <= daysInMonth; d++) cells.push(d);
    while (cells.length % 7 !== 0) cells.push(null);

    grid.innerHTML = '';
    cells.forEach(function (d) {
      var cell = document.createElement('div');
      cell.className = 'cal-month-cell';
      if (d == null) {
        cell.classList.add('empty');
        grid.appendChild(cell);
        return;
      }
      var iso = y + '-' + pad(m + 1) + '-' + pad(d);
      var num = document.createElement('span');
      num.textContent = String(d);
      cell.appendChild(num);
      if (iso === todayIso) cell.classList.add('today');

      var ranks = dayRanks(iso);
      if (ranks) {
        var dots = document.createElement('span');
        dots.className = 'cmd-dots';
        DOT_ORDER.forEach(function (pair) {
          if (ranks[pair[0]]) {
            var dot = document.createElement('i');
            dot.className = 'dot ' + pair[1];
            dots.appendChild(dot);
          }
        });
        if (dots.children.length) cell.appendChild(dots);
        cell.classList.add('clickable');
        cell.addEventListener('click', function () { jumpTo(iso); });
      } else {
        cell.classList.add('no-data');
      }
      grid.appendChild(cell);
    });
  }

  function shift(delta) {
    var t = taipei();
    var y = view ? view.y : t.getFullYear();
    var m = view ? view.m : t.getMonth();
    m += delta;
    if (m < 0) { m = 11; y -= 1; } else if (m > 11) { m = 0; y += 1; }
    view = {y: y, m: m};
    render();
  }

  if (prevBtn) prevBtn.addEventListener('click', function () { shift(-1); });
  if (nextBtn) nextBtn.addEventListener('click', function () { shift(1); });

  return {render: render};
}

function initCalendarTable(table) {
  var days = Array.prototype.slice.call(table.querySelectorAll('.cal-day'));
  var panel = table.closest('.panel');
  var clock = panel ? panel.querySelector('.cal-clock') : null;
  var monthGrid = initMonthGrid(panel, table);
  var chips = panel
    ? Array.prototype.slice.call(panel.querySelectorAll('.cal-filter .chip'))
    : [];
  var cols = table.querySelectorAll('thead th').length;
  var minRank = 0;
  // 勾選式篩選（行事曆）：哪些影響程度要顯示。空的代表這張表不用這種篩選。
  var allowed = {};
  chips.forEach(function (c) {
    if (c.dataset.impact != null && c.getAttribute('aria-pressed') === 'true') {
      allowed[Number(c.dataset.impact)] = true;
    }
  });
  var byImpact = chips.some(function (c) { return c.dataset.impact != null; });
  var nowRow = null;
  // 行事曆：預設只列到今天起 horizon 天（過去幾天照列），按「再看 7 天」往後延
  var horizon = Number(table.dataset.horizon) || 0;
  var moreBtn = null;
  if (horizon) {
    moreBtn = document.createElement('button');
    moreBtn.type = 'button';
    moreBtn.className = 'scr-more cal-more';
    moreBtn.textContent = '再看 7 天';
    moreBtn.addEventListener('click', function () { horizon += 7; refresh(); });
    table.parentNode.insertBefore(moreBtn, table.nextSibling);
  }
  function cutoff() {
    var t = taipei();
    t.setDate(t.getDate() + horizon);
    return t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
  }
  // 月曆格點到還沒列出的日子：先把範圍延到那天
  table._reveal = function (iso) {
    if (!horizon) return;
    while (cutoff() < iso) horizon += 7;
    refresh();
  };

  // 台北時間（UTC+8）：不論使用者裝置在哪個時區，顯示都與表格一致
  function taipei() {
    return new Date(Date.now() + (8 * 60 + new Date().getTimezoneOffset()) * 60000);
  }
  function pad(n) { return String(n).padStart(2, '0'); }

  // 以每一列自己的日期判斷，財經行事曆（一天一組）與 F1（一個賽事週末一組）
  // 都適用：只要組裡有今天的場次就標「今天」，整組都過了才算已過去。
  function markDays() {
    var t = taipei();
    var iso = t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
    days.forEach(function (d) {
      // 置頂區塊（SpaceX 的「進行中的任務」）不套今天／已過去 ——
      // 那是現在的狀態，用發射日期判斷會被標成已過去而淡化
      if (d.dataset.pinned) return;
      var rowDays = Array.prototype.slice.call(d.querySelectorAll('.cal-row'))
        .map(function (r) { return r.dataset.day || d.dataset.date; });
      var hasToday = rowDays.indexOf(iso) >= 0;
      var allPast = rowDays.length > 0 && rowDays.every(function (x) { return x < iso; });
      d.classList.toggle('today', hasToday);
      d.classList.toggle('past', allPast);
      // 有分組標題內層時把「今天」掛在標題文字後面，不要掛在 flex 容器外
      var head = d.querySelector('.grp-main') || d.querySelector('.cal-day-row th');
      var tag = head.querySelector('.cal-today-tag');
      if (hasToday && !tag) {
        tag = document.createElement('span');
        tag.className = 'cal-today-tag';
        tag.textContent = '今天';
        head.appendChild(tag);
      } else if (!hasToday && tag) {
        tag.remove();
      }
    });
    return iso;
  }

  function buildNowRow(text) {
    if (!nowRow) {
      nowRow = document.createElement('tr');
      nowRow.className = 'cal-now';
      var td = document.createElement('td');
      td.colSpan = cols;
      var line = document.createElement('div');
      line.className = 'now-line';
      var tag = document.createElement('span');
      tag.className = 'now-tag';
      line.appendChild(tag);
      td.appendChild(line);
      nowRow.appendChild(td);
      nowRow._tag = tag;
    }
    nowRow._tag.textContent = text;
    return nowRow;
  }

  // 標示線插在「全表第一個還沒到的可見項目」之前。
  // 不綁定今天那一組：F1 是依大獎賽分組，今天不一定有場次。
  function placeNow() {
    var t = taipei();
    var row = buildNowRow(pad(t.getHours()) + ':' + pad(t.getMinutes()));
    var now = Date.now();

    for (var i = 0; i < days.length; i++) {
      if (days[i].hidden || days[i].classList.contains('collapsed')) continue;
      var rows = Array.prototype.slice.call(days[i].querySelectorAll('.cal-row'))
                      .filter(function (r) { return !r.hidden; });
      for (var j = 0; j < rows.length; j++) {
        if (Number(rows[j].dataset.ts) > now) {
          days[i].insertBefore(row, rows[j]);
          return;
        }
      }
    }
    // 全部都過去了就放在最後一組末尾
    var last = days.filter(function (d) { return !d.hidden; }).pop();
    if (last) { last.appendChild(row); } else if (nowRow) { nowRow.remove(); }
  }

  function applyFilter() {
    // 清單模式（F1）看的是大獎賽標題，就算場次全被篩掉也要留著那一列
    var listMode = table.classList.contains('list-mode');
    var until = horizon ? cutoff() : null;
    var later = 0;
    days.forEach(function (d) {
      var shown = 0;
      Array.prototype.slice.call(d.querySelectorAll('.cal-row')).forEach(function (row) {
        var rank = Number(row.dataset.impact);
        var on = byImpact ? allowed[rank] === true : rank >= minRank;
        row.hidden = !on;
        if (on) shown++;
      });
      var beyond = until && d.dataset.date > until;
      if (beyond && shown) later++;
      d.hidden = d.dataset.off === '1' || (!listMode && shown === 0) || beyond;
    });
    if (moreBtn) {
      moreBtn.hidden = !later;
      moreBtn.textContent = '再看 7 天（之後還有 ' + later + ' 天有事件）';
    }
  }

  function refresh() {
    markDays();
    applyFilter();
    placeNow();
    if (monthGrid) monthGrid.render();
    if (clock) {
      var t = taipei();
      clock.textContent = '現在 ' + (t.getMonth() + 1) + '/' + pad(t.getDate()) + ' ' +
                          pad(t.getHours()) + ':' + pad(t.getMinutes()) + '（UTC+8）';
    }
  }

  // 兩種篩選共用同一組 class：
  //   data-impact  每個等級一顆、各自開關（行事曆）
  //   data-min     互斥的「以上」級距（F1 的場次類型）
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      if (c.dataset.impact != null) {
        var on = c.getAttribute('aria-pressed') !== 'true';
        c.setAttribute('aria-pressed', String(on));
        var rank = Number(c.dataset.impact);
        if (on) { allowed[rank] = true; } else { delete allowed[rank]; }
      } else {
        chips.forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
        minRank = Number(c.dataset.min);
      }
      refresh();
    });
  });

  // ── 可鑽入的分組（F1 賽程用）──────────────────────────
  // 清單只列出每一場大獎賽，點進去才看那一站的場次表；整季 20 幾站
  // 全部攤開在同一頁反而難找。用的是同一張表，切換的是要顯示哪些列。
  var drill = days.filter(function (d) { return d.classList.contains('drill'); });
  if (drill.length) {
    var subtab = panel ? panel.querySelector('.subtab[data-sub="sched"]') : null;

    var filterBar = panel ? panel.querySelector('.cal-filter') : null;

    // 只切換要顯示哪些列。不動頁面標頭 —— 切到別的分頁時標頭已經由
    // selectTab 換好了，這裡再寫一次會把它蓋掉。
    function applyRace(target) {
      table.classList.toggle('list-mode', !target);
      drill.forEach(function (d) { d.dataset.off = (target && d !== target) ? '1' : ''; });
      if (filterBar) filterBar.hidden = !target;   // 清單上沒有場次可篩
      setBack(target ? function () { showRace(null); } : null);
      refresh();
    }

    function showRace(target) {
      applyRace(target);
      var src = target || subtab;
      if (src) {
        document.getElementById('page-title').textContent = src.dataset.title;
        document.getElementById('page-meta-text').innerHTML = src.dataset.meta;
      }
      window.scrollTo(0, 0);
      syncSticky();
    }

    drill.forEach(function (d) {
      var th = d.querySelector('.cal-day-row th');
      th.addEventListener('click', function () {
        if (table.classList.contains('list-mode')) showRace(d);
      });
      th.addEventListener('keydown', function (e) {
        if ((e.key === 'Enter' || e.key === ' ') && table.classList.contains('list-mode')) {
          e.preventDefault();
          showRace(d);
        }
      });
    });

    // 切走再回來（換主分頁或子分頁）時回到清單
    if (subtab) subtab.addEventListener('click', function () { showRace(null); });
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        if (!table.classList.contains('list-mode')) applyRace(null);
      });
    });

    applyRace(null);
  }

  refresh();
  setInterval(refresh, 30000);   // 每半分鐘更新時鐘與標示線位置
}

Array.prototype.slice.call(document.querySelectorAll('.cal-table'))
  .forEach(initCalendarTable);

// 行事曆的「月曆」鈕：月曆格預設收起，點了才展開
Array.prototype.slice.call(document.querySelectorAll('.cal-month-toggle')).forEach(function (b) {
  var host = b.closest('.panel') || document;
  var month = host.querySelector('.cal-month');
  if (!month) return;
  b.addEventListener('click', function () {
    month.hidden = !month.hidden;
    b.setAttribute('aria-pressed', String(!month.hidden));
    syncSticky();
  });
});

// ── 二階／三階分頁（目前只有 F1 用）─────────────────────────
// 圖表在隱藏的分頁裡量不到寬度，所以顯示的當下才繪製或重新丈量。
function activateCharts(container) {
  if (!container) return;
  Array.prototype.slice.call(container.querySelectorAll('.chart')).forEach(function (div) {
    if (div.offsetParent === null) return;          // 還藏著就先不畫
    var key = div.id.replace('chart-', '');
    var c = CHARTS[key];
    if (!c) return;
    if (!c.rendered || c.dirty) { renderChart(key); }
    else { Plotly.Plots.resize(div); }
  });
}

function setHead(el) {
  if (!el || !el.dataset.title) return;
  document.getElementById('page-title').textContent = el.dataset.title;
  document.getElementById('page-meta-text').innerHTML = el.dataset.meta || '';
}

function initTabGroup(bar, tabClass, panelClass, dataKey) {
  var scope = bar.parentElement;
  var tabs = Array.prototype.slice.call(bar.querySelectorAll('.' + tabClass));
  var panes = Array.prototype.slice.call(scope.children).filter(function (el) {
    return el.classList.contains(panelClass);
  });
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      tabs.forEach(function (x) { x.setAttribute('aria-selected', String(x === t)); });
      var shown = null;
      panes.forEach(function (p) {
        var on = (p.dataset[dataKey] === t.dataset[dataKey]);
        p.hidden = !on;
        if (on) shown = p;
      });
      setHead(t);
      // 顯示的分頁裡若還有孫分頁，標題以孫分頁為準
      var grand = shown ? shown.querySelector('.grandtab[aria-selected="true"]') : null;
      setHead(grand);
      activateCharts(shown);
      syncSticky();   // 內容換了，黏著層高度要重量
    });
  });
}

Array.prototype.slice.call(document.querySelectorAll('.subtabs')).forEach(function (bar) {
  initTabGroup(bar, 'subtab', 'subpanel', 'sub');
});
Array.prototype.slice.call(document.querySelectorAll('.grandtabs')).forEach(function (bar) {
  initTabGroup(bar, 'grandtab', 'grandpanel', 'grand');
});

// ── 新聞：點標題看內文，返回鍵回清單 ───────────────────────
// 清單寫在頁面裡，內文放在 news/{來源}.json，點開才抓、每個來源只抓一次。
var FIRST_BATCH = 12;   // 一開始排幾則
var BATCH = 10;         // 捲到底再接幾則
var newsBodies = {};    // 來源 → {序號: 內文}
var newsPending = {};   // 來源 → 進行中的請求

function loadBodies(sourceId) {
  if (newsBodies[sourceId]) return Promise.resolve(newsBodies[sourceId]);
  if (!newsPending[sourceId]) {
    newsPending[sourceId] = fetch('news/' + sourceId + '.json')
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (data) { newsBodies[sourceId] = data; return data; })
      .catch(function (e) { delete newsPending[sourceId]; throw e; });
  }
  return newsPending[sourceId];
}

// 新聞清單所在的面板對應的分頁鈕（子分頁或孫分頁）
function newsTab(panel) {
  return panel.dataset.grand
    ? document.querySelector('.grandtab[data-grand="' + panel.dataset.grand + '"]')
    : document.querySelector('.subtab[data-sub="' + panel.dataset.sub + '"]');
}

function initNewsPanel(panel) {
  var list = panel.querySelector('.news-list');
  var sourceId = panel.dataset.sub || panel.dataset.grand;
  var article = panel.querySelector('.news-article');
  var box = article.querySelector('.news-body');

  function note(text) {                 // 內文區的單行提示
    box.textContent = '';
    var p = document.createElement('p');
    p.className = 'news-nobody';
    p.textContent = text;
    box.appendChild(p);
  }

  function fill(li) {
    article.querySelector('.news-h').textContent =
      li.querySelector('.news-title').textContent;
    article.querySelector('.news-meta').textContent =
      li.querySelector('.news-meta').textContent;
    article.querySelector('.news-link').href = li.dataset.url;

    // 重點清單混了各家來源，每一則自己說它是哪一家
    var from = li.dataset.source || sourceId;

    if (li.dataset.body !== '1') {
      note('這則新聞抓不到內文（可能是影音報導或需要訂閱），請點下方連結看原文。');
      return;
    }
    note('載入內文中…');
    var want = li.dataset.n;
    loadBodies(from).then(function (data) {
      if (article.dataset.n !== want || article.dataset.from !== from) return;
      var text = data[want];
      if (!text) { note('這則新聞抓不到內文，請點下方連結看原文。'); return; }
      box.textContent = '';
      text.split(String.fromCharCode(10)).forEach(function (line) {
        if (!line.trim()) return;
        var p = document.createElement('p');
        p.textContent = line.trim();   // 來自新聞網站的文字，一律當純文字處理
        box.appendChild(p);
      });
      syncSticky();
    }).catch(function () {
      // 離線、或用 file:// 直接開（會被 CORS 擋）時走到這裡
      if (article.dataset.n === want && article.dataset.from === from) {
        note('內文載入失敗，請確認網路連線，或點下方連結看原文。');
      }
    });
  }

  function show(li) {
    list.hidden = !!li;
    // 「載入更多」在 ul 外面，看內文時要一起藏
    if (sentinel) sentinel.hidden = !!li || (shown >= items.length);
    article.hidden = !li;
    if (li) {
      article.dataset.n = li.dataset.n;
      article.dataset.from = li.dataset.source || sourceId;
      fill(li);
    }
    setBack(li ? function () { show(null); } : null);
    window.scrollTo(0, 0);
    syncSticky();
  }

  var items = Array.prototype.slice.call(list.querySelectorAll('.news-item'));
  items.forEach(function (li) {
    li.addEventListener('click', function () { show(li); });
    li.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(li); }
    });
  });

  // 捲到底自動接上後面的：全部都已經在頁面裡，只是先藏起來，
  // 一次全顯示會讓清單長到難捲，也沒必要一開始就排版那麼多列。
  var shown = FIRST_BATCH;
  var sentinel = panel.querySelector('.news-more');
  function reveal() {
    items.forEach(function (li, i) { li.hidden = (i >= shown); });
    if (sentinel) sentinel.hidden = (shown >= items.length);
  }
  function extend() {
    if (shown >= items.length) return;
    shown = Math.min(shown + BATCH, items.length);
    reveal();
  }
  reveal();
  if (sentinel) {
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) extend();
      }, {rootMargin: '200px'}).observe(sentinel);
    }
    sentinel.addEventListener('click', extend);   // 沒有 IO 時仍可手動載入
  }

  // 切走再回來時回到清單，不要停在上次看的那一篇
  var subtab = newsTab(panel);
  if (subtab) subtab.addEventListener('click', function () { show(null); });
}

// 各來源的清單不在頁面裡（約三百則，佔首頁一百多 KB），點進子分頁才下載。
// 格式：[[序號, 有無內文, 網址, 標題, 時間與來源], …]
function newsItem(r) {
  var li = document.createElement('li');
  li.className = 'news-item';
  li.dataset.n = r[0];
  li.dataset.body = r[1] ? '1' : '0';
  li.dataset.url = r[2];
  li.setAttribute('role', 'button');
  li.tabIndex = 0;
  var no = document.createElement('span');
  no.className = 'news-no';
  no.textContent = r[0] + 1;
  var main = document.createElement('span');
  main.className = 'news-main';
  var t = document.createElement('span');
  t.className = 'news-title';
  t.textContent = r[3];                 // 來自新聞網站的文字，一律當純文字處理
  var m = document.createElement('span');
  m.className = 'news-meta';
  m.textContent = r[4];
  main.appendChild(t);
  main.appendChild(m);
  li.appendChild(no);
  li.appendChild(main);
  return li;
}

Array.prototype.slice.call(document.querySelectorAll('.subpanel, .grandpanel')).forEach(function (panel) {
  var list = panel.querySelector('.news-list');
  if (!list) return;
  if (panel.classList.contains('subpanel') && panel.querySelector('.grandpanel')) return;
  if (!list.dataset.list) { initNewsPanel(panel); return; }
  var started = false;
  function start() {
    if (started) return;
    started = true;
    fetch('news/list-' + list.dataset.list + '.json?v=' + VERSION).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (rows) {
      list.textContent = '';
      rows.forEach(function (r) { list.appendChild(newsItem(r)); });
      initNewsPanel(panel);
      syncSticky();
    }).catch(function () {
      started = false;
      list.textContent = '';
      var li = document.createElement('li');
      li.className = 'cal-empty';
      li.textContent = '清單載入失敗，請確認網路連線後再點一次。';
      list.appendChild(li);
    });
  }
  var subtab = newsTab(panel);
  if (subtab) subtab.addEventListener('click', start);
  // 孫分頁：點「各家新聞」時，目前選著的那個來源也要開始載
  if (panel.dataset.grand) {
    var host = panel.closest('.subpanel');
    var hostTab = host && document.querySelector('.subtab[data-sub="' + host.dataset.sub + '"]');
    if (hostTab) hostTab.addEventListener('click', function () { if (!panel.hidden) start(); });
  }
});

// ── 筆記：存在 localStorage，不上傳 ─────────────────────────
(function () {
  var panel = document.getElementById('panel-notes');
  if (!panel) return;

  var KEY = 'dash-notes';
  var listBox = panel.querySelector('.notes-list');
  var emptyMsg = panel.querySelector('.notes-empty');
  var newBtn = panel.querySelector('.notes-new');
  var editBox = panel.querySelector('.notes-edit');
  var titleIn = panel.querySelector('.notes-title');
  var bodyIn = panel.querySelector('.notes-body');
  var savedMsg = panel.querySelector('.notes-saved');
  var delBtn = panel.querySelector('.notes-del');
  var notes = [];
  var editing = null;      // 正在編輯的筆記 id
  var timer = null;

  function load() {
    try { notes = JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { notes = []; }
    if (!Array.isArray(notes)) notes = [];
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(notes));
      return true;
    } catch (e) {
      // 隱私模式或空間滿了
      savedMsg.textContent = '存不進去（瀏覽器不允許或空間已滿）';
      return false;
    }
  }

  function stamp(ms) {
    var d = new Date(ms);
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return (d.getMonth() + 1) + '/' + pad(d.getDate()) + ' ' +
           pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function byId(id) {
    for (var i = 0; i < notes.length; i++) { if (notes[i].id === id) return notes[i]; }
    return null;
  }

  function renderCount() {
    var el = document.getElementById('notes-count');
    if (el) el.textContent = notes.length + ' 則';
  }

  function renderList() {
    listBox.textContent = '';
    notes.slice().sort(function (a, b) { return b.updated - a.updated; })
      .forEach(function (n) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'notes-item';
        var t = document.createElement('span');
        t.className = 'notes-t';
        t.textContent = n.title || '未命名筆記';
        var sub = document.createElement('span');
        sub.className = 'notes-sub';
        var preview = (n.body || '').split(String.fromCharCode(10))[0];
        sub.textContent = stamp(n.updated) + (preview ? '　' + preview : '');
        btn.appendChild(t);
        btn.appendChild(sub);
        btn.addEventListener('click', function () { open(n.id); });
        listBox.appendChild(btn);
      });
    emptyMsg.hidden = notes.length > 0;
    renderCount();
  }

  function showList() {
    editing = null;
    if (timer) { clearTimeout(timer); timer = null; flush(); }
    editBox.hidden = true;
    listBox.hidden = false;
    emptyMsg.hidden = notes.length > 0;
    newBtn.hidden = false;
    renderList();
    setBack(null);
    window.scrollTo(0, 0);
    syncSticky();
  }

  function open(id) {
    var n = byId(id);
    if (!n) return;
    editing = id;
    titleIn.value = n.title || '';
    bodyIn.value = n.body || '';
    savedMsg.textContent = '上次編輯 ' + stamp(n.updated);
    listBox.hidden = true;
    emptyMsg.hidden = true;
    newBtn.hidden = true;
    editBox.hidden = false;
    setBack(showList);
    window.scrollTo(0, 0);
    syncSticky();
  }

  function flush() {
    var n = byId(editing);
    if (!n) return;
    n.title = titleIn.value;
    n.body = bodyIn.value;
    n.updated = Date.now();
    if (save()) savedMsg.textContent = '已儲存 ' + stamp(n.updated);
  }

  function touched() {
    if (!editing) return;
    savedMsg.textContent = '編輯中…';
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; flush(); }, 500);
  }

  titleIn.addEventListener('input', touched);
  bodyIn.addEventListener('input', touched);

  newBtn.addEventListener('click', function () {
    var n = {id: String(Date.now()) + Math.random().toString(36).slice(2, 7),
             title: '', body: '', updated: Date.now()};
    notes.push(n);
    save();
    open(n.id);
    titleIn.focus();
  });

  delBtn.addEventListener('click', function () {
    var n = byId(editing);
    if (!n) return;
    var name = n.title || '這則未命名筆記';
    if (!window.confirm('確定要刪除「' + name + '」嗎？刪掉就找不回來了。')) return;
    notes = notes.filter(function (x) { return x.id !== editing; });
    editing = null;
    if (timer) { clearTimeout(timer); timer = null; }
    save();
    showList();
  });

  // 換到別的分頁、或關掉頁面時，把還沒寫進去的內容存好
  window.addEventListener('pagehide', function () { if (editing) flush(); });
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      if (editing) flush();
      // 回到筆記分頁時從清單開始，不要停在上次編輯的那一則
      if (t.dataset.tab === 'notes') showList();
    });
  });

  load();
  renderList();
})();

// ── 個股：目前鎖定的公司 ───────────────────────────────────
// 查過某一檔之後，營收／重訊／財報就只看那一檔 —— 想查台積電的人
// 切過去還要再篩一次很煩。清單上會有一個晶片可以解除。
var stockFocus = null;                 // {code, name}
var stockFocusWatchers = [];

function setStockFocus(target) {
  stockFocus = target;
  stockFocusWatchers.forEach(function (fn) { fn(); });
}

// ── 個股：營收／重訊／財報（排程抓下來的 JSON）─────────────
(function () {
  var panel = document.getElementById('panel-stock');
  if (!panel) return;
  var cache = {};

  function money(text) {          // 千元 → 億元，看得懂比精確重要
    var v = parseFloat(text);
    if (!isFinite(v)) return '—';
    return (v / 100000).toFixed(2) + ' 億';
  }
  function pct(text) {
    var v = parseFloat(text);
    if (!isFinite(v)) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
  }
  function cls(text) {
    var v = parseFloat(text);
    if (!isFinite(v) || v === 0) return '';
    return v > 0 ? ' up' : ' down';
  }
  function rocMonth(v) { return String(v).length === 5 ? v.slice(0, 3) + '/' + v.slice(3) : v; }
  function rocDate(v) {
    v = String(v);
    return v.length === 7 ? v.slice(0, 3) + '/' + v.slice(3, 5) + '/' + v.slice(5) : v;
  }
  // 發言時間是 HHMMSS，早上的會少掉開頭那個 0（70003 就是 07:00:03）
  function hhmm(v) {
    v = String(v || '');
    if (!v) return '';
    while (v.length < 6) v = '0' + v;
    return v.slice(0, 2) + ':' + v.slice(2, 4);
  }

  // 每個資料集怎麼變成一列
  var VIEWS = {
    revenue: {
      match: function (r) { return r.name + r.code + r.industry; },
      sort: function (a, b) { return (parseFloat(b.yoy) || -1e9) - (parseFloat(a.yoy) || -1e9); },
      row: function (r) {
        return {title: r.code + '　' + r.name,
                sub: r.industry + '　·　' + rocMonth(r.month),
                cells: [['當月營收', money(r.revenue), ''],
                        ['年增', pct(r.yoy), cls(r.yoy)],
                        ['月增', pct(r.mom), cls(r.mom)]]};
      }
    },
    income: {
      match: function (r) { return r.name + r.code; },
      sort: function (a, b) { return (parseFloat(b.revenue) || 0) - (parseFloat(a.revenue) || 0); },
      row: function (r) {
        return {title: r.code + '　' + r.name,
                sub: r.year + ' 年第 ' + r.quarter + ' 季　·　年初至今累計',
                cells: [['營收', money(r.revenue), ''],
                        ['營業利益', money(r.operating), ''],
                        ['EPS', (r.eps || '—') + ' 元', cls(r.eps)]]};
      }
    }
  };

  function renderRows(box, rows, view) {
    box.textContent = '';
    if (!rows.length) {
      var none = document.createElement('p');
      none.className = 'cal-empty';
      none.textContent = '沒有符合的資料。';
      box.appendChild(none);
      return;
    }
    rows.slice(0, 200).forEach(function (r) {
      var item = view.row(r);
      var card = document.createElement('div');
      card.className = 'sl-item';
      var head = document.createElement('div');
      head.className = 'sl-head';
      var t = document.createElement('span');
      t.className = 'sl-title';
      t.textContent = item.title;
      var sb = document.createElement('span');
      sb.className = 'sl-sub';
      sb.textContent = item.sub;
      head.appendChild(t);
      head.appendChild(sb);
      card.appendChild(head);
      var grid = document.createElement('div');
      grid.className = 'sl-grid';
      item.cells.forEach(function (c) {
        var cell = document.createElement('div');
        cell.className = 'sl-cell';
        var l = document.createElement('span');
        l.textContent = c[0];
        var v = document.createElement('b');
        v.className = 'sl-v' + c[2];
        v.textContent = c[1];
        cell.appendChild(l);
        cell.appendChild(v);
        grid.appendChild(cell);
      });
      card.appendChild(grid);
      box.appendChild(card);
    });
    if (rows.length > 200) {
      var more = document.createElement('p');
      more.className = 'cal-empty';
      more.textContent = '另有 ' + (rows.length - 200) + ' 筆，用上面的搜尋框縮小範圍。';
      box.appendChild(more);
    }
  }

  // 重大訊息：清單 + 全文，動線跟新聞一樣
  function renderAnnounce(box, rows, sp) {
    box.textContent = '';
    var list = document.createElement('div');
    var article = document.createElement('div');
    article.className = 'news-article';
    article.hidden = true;

    function show(r) {
      list.hidden = !!r;
      article.hidden = !r;
      if (r) {
        article.textContent = '';
        var h = document.createElement('h2');
        h.className = 'news-h';
        h.textContent = r.subject;
        var meta = document.createElement('div');
        meta.className = 'news-meta';
        meta.textContent = r.code + '　' + r.name + '　·　' +
                           rocDate(r.date) + ' ' + hhmm(r.time) +
                           (r.clause ? '　·　' + r.clause : '');
        var body = document.createElement('div');
        body.className = 'news-body';
        (r.body || '').split(String.fromCharCode(10)).forEach(function (line) {
          if (!line.trim()) return;
          var p = document.createElement('p');
          p.textContent = line.trim();
          body.appendChild(p);
        });
        if (!body.childElementCount) {
          var p2 = document.createElement('p');
          p2.className = 'news-nobody';
          p2.textContent = '這則公告沒有說明內容。';
          body.appendChild(p2);
        }
        var link = document.createElement('a');
        link.className = 'news-link';
        link.href = 'https://mops.twse.com.tw/mops/#/web/home';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = '到公開資訊觀測站 ↗';
        article.appendChild(h);
        article.appendChild(meta);
        article.appendChild(body);
        article.appendChild(link);
      }
      setBack(r ? function () { show(null); } : null);
      window.scrollTo(0, 0);
      syncSticky();
    }

    if (!rows.length) {
      var none = document.createElement('p');
      none.className = 'cal-empty';
      none.textContent = '沒有符合的公告。';
      list.appendChild(none);
    }
    rows.slice(0, 200).forEach(function (r) {
      var card = document.createElement('div');
      card.className = 'sl-item sl-click';
      card.setAttribute('role', 'button');
      card.tabIndex = 0;
      var head = document.createElement('div');
      head.className = 'sl-head';
      var t = document.createElement('span');
      t.className = 'sl-title';
      t.textContent = r.subject;
      var sb = document.createElement('span');
      sb.className = 'sl-sub';
      sb.textContent = r.code + '　' + r.name + '　·　' +
                       rocDate(r.date) + ' ' + hhmm(r.time);
      head.appendChild(t);
      head.appendChild(sb);
      card.appendChild(head);
      card.addEventListener('click', function () { show(r); });
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(r); }
      });
      list.appendChild(card);
    });
    box.appendChild(list);
    box.appendChild(article);
    sp._reset = function () { show(null); };
  }

  // 鎖定某一檔時，清單上方掛一個可以解除的晶片
  function focusChip(sp) {
    var old = sp.querySelector('.sl-focus');
    if (old) old.remove();
    if (!stockFocus) return;
    var chip = document.createElement('div');
    chip.className = 'sl-focus';
    var label = document.createElement('span');
    label.textContent = '只看 ' + stockFocus.code +
                        (stockFocus.name ? '　' + stockFocus.name : '');
    var clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'sl-clear';
    clear.setAttribute('aria-label', '顯示全部公司');
    clear.textContent = '✕';
    clear.addEventListener('click', function () { setStockFocus(null); });
    chip.appendChild(label);
    chip.appendChild(clear);
    sp.insertBefore(chip, sp.querySelector('.sl-body'));
  }

  function fill(sp) {
    var set = sp.dataset.sub;
    var box = sp.querySelector('.sl-body');
    var filter = sp.querySelector('.sl-filter');
    var rows = cache[set];
    var q = filter.value.trim().toLowerCase();
    var view = VIEWS[set];
    var shown = rows;

    focusChip(sp);
    if (stockFocus) {
      shown = shown.filter(function (r) { return r.code === stockFocus.code; });
    }
    if (q) {
      shown = shown.filter(function (r) {
        var hay = set === 'announce' ? (r.code + r.name + r.subject) : view.match(r);
        return hay.toLowerCase().indexOf(q) >= 0;
      });
    }
    if (set === 'announce') {
      shown = shown.slice().sort(function (a, b) {
        return (b.date + b.time).localeCompare(a.date + a.time);
      });
      renderAnnounce(box, shown, sp);
    } else {
      renderRows(box, shown.slice().sort(view.sort), view);
    }
    // 鎖定的公司在這份資料裡沒有東西時，講清楚是哪一種空
    if (stockFocus && !shown.length) {
      var note = box.querySelector('.cal-empty');
      if (note) note.textContent = stockFocus.code + ' 在這份資料裡沒有資料。';
    }
  }

  function ensure(sp) {
    var set = sp.dataset.sub;
    if (cache[set]) { fill(sp); return; }
    var box = sp.querySelector('.sl-body');
    fetch('stock/' + set + '.json').then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (data) {
      cache[set] = data;
      fill(sp);
    }).catch(function () {
      box.textContent = '';
      var p = document.createElement('p');
      p.className = 'cal-empty';
      p.textContent = '資料載入失敗，請確認網路連線後重新載入頁面。';
      box.appendChild(p);
    });
  }

  Array.prototype.slice.call(panel.querySelectorAll('.subpanel')).forEach(function (sp) {
    var filter = sp.querySelector('.sl-filter');
    if (!filter) return;
    var timer = null;
    filter.addEventListener('input', function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { if (cache[sp.dataset.sub]) fill(sp); }, 200);
    });
    var subtab = panel.querySelector('.subtab[data-sub="' + sp.dataset.sub + '"]');
    if (subtab) {
      subtab.addEventListener('click', function () {
        if (sp._reset) sp._reset();
        ensure(sp);
      });
    }
    // 查了別檔或解除鎖定時，正在看的那一頁要立刻跟著換
    stockFocusWatchers.push(function () {
      if (!sp.hidden && cache[sp.dataset.sub]) fill(sp);
    });
  });
})();

// ── 重新載入 ───────────────────────────────────────────────
// GitHub Pages 的 CDN 會把頁面快取約 10 分鐘，單純 location.reload() 常常
// 拿回同一份舊的。改成帶時間戳重新導向，強制取得最新版；用 replace 避免
// 在瀏覽記錄裡堆一堆條目。
// ── 下拉重新整理 ───────────────────────────────────────────
// 加到主畫面之後（standalone）沒有瀏覽器自己的下拉重新整理，
// 而頁面被 CDN 快取，總得有個方法要最新版。
(function () {
  var ptr = document.getElementById('ptr');
  if (!ptr) return;
  var TRIGGER = 72;      // 拉超過這麼多 px 放開才會重新整理
  var MAX = 110;         // 指示器最多下移這麼多
  var y0 = 0, pulling = false, dist = 0, firing = false;

  function show(px, ready) {
    ptr.style.transform = 'translateY(' + px + 'px)';
    ptr.style.opacity = Math.min(1, px / 40);
    ptr.classList.toggle('ready', ready);
  }
  function reset() {
    ptr.classList.add('back');
    show(0, false);
    setTimeout(function () { ptr.classList.remove('back'); }, 200);
  }

  document.addEventListener('touchstart', function (e) {
    pulling = false;
    if (firing || e.touches.length !== 1) return;
    if (window.scrollY > 0) return;          // 只有在最上方才算
    var el = e.target;
    if (el.closest && el.closest('input, textarea, select, .chart')) return;
    y0 = e.touches[0].clientY;
    pulling = true;
    dist = 0;
  }, {passive: true});

  document.addEventListener('touchmove', function (e) {
    if (!pulling || e.touches.length !== 1) return;
    var dy = e.touches[0].clientY - y0;
    if (dy <= 0 || window.scrollY > 0) {     // 往上滑或已經捲走就交還給頁面
      if (dist) { dist = 0; reset(); }
      pulling = false;
      return;
    }
    // 阻止瀏覽器自己的橡皮筋／下拉重新整理，不然兩套會打架
    if (e.cancelable) e.preventDefault();
    dist = Math.min(MAX, dy * 0.5);          // 有阻尼，拉起來才有手感
    show(dist, dist >= TRIGGER);
  }, {passive: false});

  document.addEventListener('touchend', function () {
    if (!pulling) return;
    pulling = false;
    if (dist >= TRIGGER) {
      firing = true;
      ptr.classList.add('spin');
      show(TRIGGER, true);
      location.replace(location.pathname + '?r=' + Date.now());
      return;
    }
    if (dist) reset();
    dist = 0;
  }, {passive: true});
})();

// ── 主題 ───────────────────────────────────────────────────
try {
  var saved = localStorage.getItem('dram-theme');
  dark = saved ? saved === 'dark'
               : window.matchMedia('(prefers-color-scheme: dark)').matches;
} catch (e) { dark = false; }

document.querySelectorAll('.legend-bar').forEach(buildLegend);
applyTheme();
renderGroupBar();
selectGroup(curGroup, false);
var firstTab = firstTabOfGroup();
selectTab(firstTab ? firstTab.dataset.tab : 'settings', false);   // 只會畫出這一張圖
syncSticky();
Object.keys(CHARTS).forEach(function (k) {
  initTouch(document.getElementById('chart-' + k));
});

document.getElementById('toggle').addEventListener('click', function () {
  dark = !dark;
  renderAll();
  try { localStorage.setItem('dram-theme', dark ? 'dark' : 'light'); } catch (e) {}
});

// 轉螢幕方向 / 改變視窗寬度而跨越斷點時，重新套用對應 layout
if (MOBILE_Q.addEventListener) {
  MOBILE_Q.addEventListener('change', renderAll);
} else if (MOBILE_Q.addListener) {
  MOBILE_Q.addListener(renderAll);   // 舊版 Safari
}

// ── 每頁開頭的說明：收成「這是什麼」────────────────────────
// 第一次看到時展開一次（捲到畫面裡才算看過），之後預設收起，要看再點。
(function () {
  var KEY = 'dash-explain-seen';
  var seen = {};
  try { seen = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { seen = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(seen)); } catch (e) {} }
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      seen[en.target.dataset.explain] = 1;
      save();
      io.unobserve(en.target);
    });
  }) : null;
  Array.prototype.slice.call(document.querySelectorAll('.mo-explain')).forEach(function (p, i) {
    var host = p.closest('[data-sub]');
    var id = host ? host.dataset.sub : 'p' + i;
    p.dataset.explain = id;
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'explain-toggle';
    var mark = document.createElement('span');
    mark.className = 'explain-i';
    mark.textContent = 'i';
    b.appendChild(mark);
    b.appendChild(document.createTextNode('這是什麼'));
    p.parentNode.insertBefore(b, p);
    function set(open) {
      p.hidden = !open;
      b.setAttribute('aria-expanded', String(open));
    }
    set(!seen[id]);
    if (!seen[id] && io) io.observe(p);
    b.addEventListener('click', function () {
      set(p.hidden);
      seen[id] = 1;
      save();
      syncSticky();
    });
  });
})();
