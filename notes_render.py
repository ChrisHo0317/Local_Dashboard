"""
筆記分頁的靜態 HTML

這一頁沒有任何建置期資料 —— 筆記存在讀者自己的瀏覽器（localStorage），
不會上傳、也不會進到 repo 裡。所以這裡只產生空殼：清單容器、新增鍵、
編輯畫面，內容全部由頁面上的 JS 依 localStorage 繪出。
"""

META = "存在這台裝置的瀏覽器　·　不會上傳"


def stats(data: dict) -> dict:
    """設定分頁用的摘要。實際筆數由 JS 在讀到 localStorage 後補上。"""
    return {
        "rows": 0,
        "shown": 0,
        "latest": "—",
        "range": "只存在這台裝置",
        "local": True,
    }


def panel_html(data: dict) -> str:
    return (
        '  <div class="notes-list"></div>\n'
        '  <p class="notes-empty" hidden>還沒有任何筆記。按下面的按鈕新增一則。</p>\n'
        '  <button type="button" class="notes-new">＋ 新增筆記</button>\n'
        '  <div class="notes-edit" hidden>\n'
        '    <input class="notes-title" type="text" placeholder="標題"'
        ' aria-label="筆記標題" maxlength="120">\n'
        '    <textarea class="notes-body" rows="14" placeholder="內容…"'
        ' aria-label="筆記內容"></textarea>\n'
        '    <div class="notes-foot">\n'
        '      <span class="notes-saved"></span>\n'
        '      <button type="button" class="notes-del">刪除這則筆記</button>\n'
        '    </div>\n'
        '  </div>'
    )
