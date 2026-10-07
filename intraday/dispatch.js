// 準時觸發 GitHub Actions 的排程
//
// GitHub 自己的排程常晚好幾個小時（17:30 那次常常凌晨才跑），偶爾整次被丟掉；
// Cloudflare 的 cron 是準時的，所以由 Worker 在對的時間呼叫 GitHub 的 workflow_dispatch：
//   NEWS_CRON（每 10 分鐘，3、13、23…分）  news.yml：新聞
//   SLOT_CRON 裡的 SLOTS 四個時段           update.yml，inputs.slot 帶 update.yml 原本的 cron 字串，
//                                          它就照那個時段的清單跑；GitHub 自己的排程晚到時，看到這個時段跑過就略過
// 需要 Worker 密鑰 GH_TOKEN（fine-grained token：只限這個 repo、Actions 讀寫）與變數 GH_REPO；
// 沒設定就什麼都不做（GitHub 自己的排程照舊）。
// 結果記在 KV 的 g:last（/status 看得到）；token 失效時，有 BARK_KEY 就一天推播一次。

// 這兩個字串要和 wrangler.toml 的 crons 一字不差（scheduled 靠它分辨是哪一個 cron）
export const NEWS_CRON = '3,13,23,33,43,53 * * * *';
export const SLOT_CRON = '0,10,30,40 0,1,9,13 * * *';
// 盤中推播檢查（worker.js 的 pushCheck）：每 5 分鐘的第 2 分，讀上一分鐘（1、6、11…分）的快照
export const PUSH_CRON = '2,7,12,17,22,27,32,37,42,47,52,57 1-5 * * mon-fri';

// UTC 時:分 → [update.yml 的時段（它的 cron 字串）, 只在週一～五]
export const SLOTS = {
  '00:10': ['10 0 * * 1-5', true],      // 台北 08:10 盤前
  '01:00': ['0 1 * * *', false],        // 09:00
  '09:30': ['30 9 * * 1-5', true],      // 17:30 盤後
  '13:40': ['40 13 * * 1-5', true],     // 21:40
};

const TTL = 86400 * 5;
const pad = n => String(n).padStart(2, '0');

// 這一次要觸發哪些 workflow：[[檔名, inputs], …]（時間用 UTC，和 GitHub 的 cron 一樣）
export function plan(cron, ts) {
  if (cron === NEWS_CRON) return [['news.yml', null]];
  if (cron !== SLOT_CRON) return [];
  const d = new Date(ts);
  const s = SLOTS[pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes())];
  if (!s || (s[1] && (d.getUTCDay() === 0 || d.getUTCDay() === 6))) return [];
  return [['update.yml', {slot: s[0]}]];
}

export async function dispatch(env, cron, ts = Date.now()) {
  const jobs = plan(cron, ts);
  if (!jobs.length) return 'none';
  if (!env.GH_TOKEN || !env.GH_REPO) return 'no-token';
  const out = [];
  for (const [file, inputs] of jobs) {
    let status = 0;
    try {
      const r = await fetch('https://api.github.com/repos/' + env.GH_REPO + '/actions/workflows/' + file + '/dispatches', {
        method: 'POST',
        headers: {Authorization: 'Bearer ' + env.GH_TOKEN, Accept: 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'local-dash-intraday',
                  'Content-Type': 'application/json'},
        body: JSON.stringify(inputs ? {ref: 'main', inputs} : {ref: 'main'}),
      });
      status = r.status;
    } catch (e) {
      status = -1;                                 // 連不上 GitHub
    }
    const ok = status >= 200 && status < 300;
    out.push(file + ':' + status);
    // 新聞每 10 分鐘一次，成功就不記（KV 免費方案一天只能寫 1000 次）
    if (!ok || inputs) {
      await env.KV.put('g:last', JSON.stringify({at: new Date(ts).toISOString(), file, slot: inputs ? inputs.slot : '',
                                                 status}), {expirationTtl: TTL});
    }
    if (status === 401 || status === 403 || status === 404) await warn(env, ts, status);
  }
  return out.join(',');
}

// token 過期或權限不對：一天推播一次（GitHub 自己的排程仍會跑，只是會晚）
async function warn(env, ts, status) {
  if (!env.BARK_KEY) return;
  const key = 'g:warn:' + new Date(ts + 8 * 3600 * 1000).toISOString().slice(0, 10);
  if (await env.KV.get(key)) return;
  await env.KV.put(key, '1', {expirationTtl: 86400 * 2});
  const title = '排程觸發失敗';
  const body = 'GitHub 回應 ' + status + '：DISPATCH_TOKEN 可能過期或權限不足，資料更新會改靠 GitHub 自己的排程（會晚幾個小時）';
  try {
    await fetch('https://api.day.app/' + encodeURIComponent(env.BARK_KEY) + '/' + encodeURIComponent(title) + '/' +
                encodeURIComponent(body) + '?group=' + encodeURIComponent('排程'));
  } catch (e) { /* 推播失敗就算了 */ }
}
