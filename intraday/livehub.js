// 盤中即時轉播站（Cloudflare Durable Object，全帳號只有一個：idFromName('live')）
//
// 雲端小主機上的行情程式（feeder/feeder.py，永豐金 Shioaji）每 5 秒送一次全市場的價量變動進來，
// 這裡記住最新一份，轉發給所有開著盤中頁的裝置。只轉發、不存檔（每分鐘的快照仍由 worker.js 向證交所收）。
//
//   /feed    行情程式連進來（WebSocket，標頭 Authorization: Bearer {FEED_TOKEN}）
//   /stream  網站連進來（WebSocket；連上後第一則訊息送 {"auth": 存取碼}，對了才開始收資料）
//   /status  轉播站狀態（給 worker.js 的 /health 用，不含任何價格）
//
// 訊息（JSON）：
//   行情程式 → 這裡   {type:'full'|'delta', date:'20261007', t:'11:36:05', ts:毫秒, q:{代號:[價,累計量(張),買價,賣價,成交金額(億),內外盤,開,高,低]}}
//                     （行情程式大約每分鐘送一次 full；這裡休眠或重開後靠它補回）
//                     {type:'hb', date, t, ts}  沒有變動時的心跳
//   這裡 → 網站       full（剛連上時給一次全部）、delta、hb 原樣轉發；{type:'idle'} 目前沒有即時資料
//
// 用 WebSocket Hibernation API：沒有訊息時物件會休眠、不計運算時間；盤中每 5 秒有資料，會一直醒著
// （約 4.5 小時 × 128 MB ≈ 2,100 GB-s，免費額度每天 13,000）。進來的訊息每 20 則算 1 次請求，送出去的不算。

export class LiveHub {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.latest = null;         // {date, t, ts, q}
    if (typeof WebSocketRequestResponsePair !== 'undefined' && state.setWebSocketAutoResponse) {
      // 網站每 30 秒送 'ping' 保持連線：直接回 'pong'，不用叫醒物件
      state.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
    }
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === '/status') return Response.json(this.status());
    if (request.headers.get('Upgrade') !== 'websocket') return new Response('要用 WebSocket 連線', {status: 426});
    const role = url.pathname === '/feed' ? 'feed' : 'view';
    if (role === 'feed') {
      if (!this.env.FEED_TOKEN || request.headers.get('Authorization') !== 'Bearer ' + this.env.FEED_TOKEN) {
        return new Response('FEED_TOKEN 不對', {status: 401});
      }
      // 同時只留一個行情程式（重連時舊的那條關掉）
      this.state.getWebSockets('feed').forEach(ws => { try { ws.close(4000, '新的行情程式連上了'); } catch (e) { /* 已經斷了 */ } });
    }
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.state.acceptWebSocket(server, [role]);
    server.serializeAttachment({role, ok: role === 'feed'});
    return new Response(null, {status: 101, webSocket: client});
  }

  async webSocketMessage(ws, message) {
    const a = ws.deserializeAttachment() || {};
    let m;
    try { m = JSON.parse(typeof message === 'string' ? message : new TextDecoder().decode(message)); } catch (e) { return; }
    if (a.role === 'feed') return this.onFeed(m);
    if (!a.ok) {
      if (m && this.env.ACCESS_CODE && m.auth === this.env.ACCESS_CODE) {
        ws.serializeAttachment({role: 'view', ok: true});
        this.sendFull(ws);
      } else {
        ws.close(4001, '存取碼不對');
      }
    }
  }

  async webSocketClose(ws) {
    // compatibility_date 2026-04-07 以前不會自動回覆關閉，要自己回，對方才不會卡在 CLOSING
    try { ws.close(1000, 'bye'); } catch (e) { /* 已經關了 */ }
    const a = ws.deserializeAttachment() || {};
    // 最後一個行情程式也斷了才通知網站（重連時新的已經連上、部署時的登入測試關掉，都不算）
    if (a.role === 'feed' && !this.state.getWebSockets('feed').some(s => s !== ws)) {
      this.broadcast(JSON.stringify({type: 'idle', reason: 'feed-closed'}));
    }
  }

  async webSocketError(ws) {
    try { ws.close(1011, 'error'); } catch (e) { /* 已經斷了 */ }
  }

  onFeed(m) {
    if (!m || !m.type) return;
    if (m.type === 'full' || (m.type === 'delta' && (!this.latest || this.latest.date !== m.date))) {
      // 換日或剛醒來：delta 不完整，先記著，等下一份 full 補齊
      this.latest = {date: m.date, t: m.t, ts: m.ts, q: Object.assign({}, m.q || {}), partial: m.type !== 'full'};
    } else if (m.type === 'delta') {
      Object.assign(this.latest.q, m.q || {});
      this.latest.t = m.t;
      this.latest.ts = m.ts;
    } else if (m.type === 'hb' && this.latest && this.latest.date === m.date) {
      this.latest.t = m.t;
      this.latest.ts = m.ts;
    }
    this.broadcast(JSON.stringify(m));
  }

  sendFull(ws) {
    const L = this.latest;
    if (!L) {
      ws.send(JSON.stringify({type: 'idle', reason: 'no-data'}));
      return;
    }
    ws.send(JSON.stringify({type: 'full', date: L.date, t: L.t, ts: L.ts, q: L.q, partial: !!L.partial}));
  }

  broadcast(text) {
    for (const ws of this.state.getWebSockets('view')) {
      const a = ws.deserializeAttachment() || {};
      if (!a.ok) continue;
      try { ws.send(text); } catch (e) { /* 斷線的下次就不在清單裡了 */ }
    }
  }

  status() {
    const L = this.latest;
    const views = this.state.getWebSockets('view').filter(ws => (ws.deserializeAttachment() || {}).ok).length;
    return {feed_connected: this.state.getWebSockets('feed').length > 0, viewers: views,
            date: L ? L.date : null, time: L ? L.t : null, ts: L ? L.ts : null, codes: L ? Object.keys(L.q).length : 0};
  }
}
