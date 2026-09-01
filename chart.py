"""
走勢圖

兩張圖共用同一套版面設定，本地 Dash 版（app.py）與靜態版（build_static.py）
也都呼叫這裡，確保各處外觀一致：

    build_figure()       DRAM 現貨報價（USD）
    build_bond_figure()  美國公債殖利率（%）
    build_gold_figure()  國際金價（USD / 盎司）

圖表本身不設 title —— 標題由外層的 HTML 標頭負責。

x 軸帶 rangeslider（圖表下方的時間軸縮圖，可拖曳兩端縮放）與 rangeselector
（快速切換 1／3／6 個月與全部區間）。

showlegend=False 時不畫 Plotly 內建圖例，改由外層自行實作 —— 靜態版
（build_static.py）用可收合的色點按鈕取代，避免多個項目在手機上佔掉大半畫面。
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DARK_BG = "#1e2130"
LIGHT_BG = "white"

# rangeselector 的顏色必須逐項指定：Plotly 對它有一組硬編碼預設值
# （bgcolor '#eee' 配深色文字），plotly_dark 樣板並不會覆寫，
# 因此深色模式下若不指定就會是淺灰底配淺色字，幾乎看不見。
_SELECTOR_STYLE = {
    False: dict(bgcolor="#f1f3f5", activecolor="#ced4da",
                bordercolor="#ced4da", font=dict(color="#212529", size=11)),
    True:  dict(bgcolor="#2a2f45", activecolor="#454d70",
                bordercolor="#4a5170", font=dict(color="#e8e8e8", size=11)),
}

_SLIDER_BORDER = {False: "#ced4da", True: "#4a5170"}
_SPIKE_COLOR = {False: "#868e96", True: "#7a8296"}

# 超過這個日期數就改成純線條，不畫標記點
MARKER_LIMIT = 300

# 預設只看最近幾個月；時間軸縮圖仍顯示完整區間，可自行拉開
DEFAULT_MONTHS = 3


def theme_colors(dark: bool) -> tuple[str, str]:
    """回傳 (plotly template 名稱, 背景色)。"""
    return ("plotly_dark", DARK_BG) if dark else ("plotly", LIGHT_BG)


def series_colors(fig: go.Figure) -> list[dict]:
    """取出各條線的名稱與顏色，供外層自製圖例使用。"""
    return [
        {"name": t.name, "color": (t.line.color if t.line else None) or "#888888"}
        for t in fig.data
    ]


def _line_figure(df: pd.DataFrame, value_col: str, y_label: str,
                 value_format: str, dark: bool, showlegend: bool) -> go.Figure:
    """
    共用的折線圖組裝。df 需有 item / price_date / <value_col> 三欄。

    value_format 是 hovertemplate 中數值的格式，例如 "%{y:.3f}" 或 "%{y:.2f}%"。
    """
    tmpl, bg = theme_colors(dark)

    if df is None or df.empty:
        return go.Figure().update_layout(
            title="尚無資料", template=tmpl, paper_bgcolor=bg, plot_bgcolor=bg,
        )

    # 補齊成「所有日期 × 所有項目」，缺的填 NaN，讓各項目共用同一組 x 座標，
    # 指標標籤才會依同一個日期對齊。搭配 connectgaps=True，線本身仍然連續，
    # 不會因為某項目偶爾缺一天就斷開。
    # 注意：補 NaN 並不會讓停更的項目從指標標籤消失 —— hoverdistance=-1 之下
    # Plotly 仍會往回找到它最後一個有值的點，所以標籤才需要逐列標日期。
    wide = df.pivot_table(index="price_date", columns="item",
                          values=value_col, aggfunc="last").sort_index()
    # pivot 會把項目重排成字母序，px 依序指派顏色，等於整組換色。
    # 還原成原始資料的出現順序，配色才不會因為這次補齊而變動。
    wide = wide.reindex(columns=df["item"].drop_duplicates().tolist())
    grid = wide.reset_index().melt(id_vars="price_date",
                                   var_name="item", value_name=value_col)

    # 點一多就不畫標記：手機上繪圖區僅約 295px 寬，900 多個日期等於每 0.3px
    # 一個點，size 4 的標記會糊成一片噪點，反而看不出線。
    dense = len(wide.index) > MARKER_LIMIT

    fig = px.line(
        grid, x="price_date", y=value_col, color="item",
        labels={"price_date": "", value_col: y_label, "item": "項目"},
        markers=not dense,
        template=tmpl,
        # 點數超過 px 的 1000 點門檻時預設會改用 WebGL 的 scattergl，
        # 那個 trace 型別不支援 cliponaxis、hover 行為也不同。固定用 SVG。
        render_mode="svg",
    )
    fig.update_traces(
        line=dict(width=1.6 if dense else 2),
        # cliponaxis=False：x 軸右端貼齊最後一筆資料後，最末端的點才不會被切一半
        cliponaxis=False,
        connectgaps=True,
        # 指標標籤每列格式：「項目 : 日期 值」。帶上該點自己的日期是必要的 ——
        # hoverdistance=-1 之下，早已停更的項目仍會被列出它最後一筆舊值。
        hovertemplate="%{x|%m/%d}　" + value_format + "<extra>%{fullData.name}</extra>",
    )

    first = df["price_date"].min()
    last = df["price_date"].max()
    # 預設顯示最近 DEFAULT_MONTHS 個月
    start = max(first, last - pd.DateOffset(months=DEFAULT_MONTHS))

    # y 軸配合預設視窗，第一眼就是縮放好的樣子；之後改變時間軸範圍時
    # 由前端重算（Plotly 不會因為 x 縮放而自動調整 y）。
    win = grid[(grid["price_date"] >= start) & (grid["price_date"] <= last)]
    vals = win[value_col].dropna()
    y_range = None
    if len(vals):
        lo, hi = float(vals.min()), float(vals.max())
        pad = (hi - lo) * 0.04 or abs(hi) * 0.02 or 1.0
        # 價格與殖利率都不會是負的，下緣不要因為留白而掉到 0 以下
        y_range = [max(0.0, lo - pad) if lo >= 0 else lo - pad, hi + pad]

    fig.update_xaxes(
        # 明確指定範圍，右端貼齊最後一筆資料。留給 autorange 的話右邊會多出一段
        # 留白，而 rangeselector 的「1月」是以目前範圍右端往回算，
        # 那段留白會讓最新資料無法對齊右邊界。
        range=[start, last],
        # 垂直指標線：手機上以單指點按移動，spikesnap="data" 讓它對齊實際資料點
        showspikes=True, spikemode="across", spikesnap="data",
        spikethickness=1, spikedash="dot", spikecolor=_SPIKE_COLOR[dark],
        # 月份一律用數字，不要 Jan/Feb。依縮放程度自動換格式：
        # 放到日的層級顯示 月/日，月的層級顯示 年/月，再拉遠只顯示年份。
        tickformatstops=[
            dict(dtickrange=[None, 604800000], value="%m/%d"),
            dict(dtickrange=[604800000, "M1"], value="%m/%d"),
            dict(dtickrange=["M1", "M12"], value="%Y/%m"),
            dict(dtickrange=["M12", None], value="%Y"),
        ],
        hoverformat="%Y/%m/%d",   # 指標標籤標頭的日期格式
        # 縮圖固定顯示完整區間（不跟著主圖的預設視窗縮），才看得出目前看的是哪一段
        rangeslider=dict(visible=True, thickness=0.10, autorange=True,
                         bgcolor=bg, bordercolor=_SLIDER_BORDER[dark], borderwidth=1),
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1月", step="month", stepmode="backward"),
                dict(count=3, label="3月", step="month", stepmode="backward"),
                dict(count=6, label="6月", step="month", stepmode="backward"),
                dict(step="all", label="全部"),
            ],
            x=0, xanchor="left", y=1.06, yanchor="bottom",
            **_SELECTOR_STYLE[dark],
        ),
    )

    fig.update_layout(
        hovermode="x unified",
        # hoverdistance 預設 20（px）會連垂直方向一起算，游標不夠靠近線就整組被濾掉，
        # 造成指標標籤完全不出現。-1 = 不限距離，手指點在任何高度都會列出該時間點的資料。
        # （改用有限值無法解決停更項目的問題：手機上整段 x 範圍才約 330px，
        #   停更點的距離比任何合理門檻都小，反而會因垂直距離誤刪正常的項目。）
        hoverdistance=-1,
        spikedistance=-1,
        showlegend=showlegend,
        # 圖例置於圖表下方：放在上方會與 Plotly 右上角工具列重疊，
        # 窄螢幕換行成多列後更會蓋到標題。
        legend=dict(orientation="h", yanchor="top", y=-0.30,
                    xanchor="left", x=0, title_text=""),
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        margin=dict(l=60, r=30, t=60, b=150 if showlegend else 40),
    )
    if y_range:
        fig.update_yaxes(range=y_range)
    return fig


def build_figure(df: pd.DataFrame, dark: bool = False,
                 showlegend: bool = True) -> go.Figure:
    """DRAM 現貨報價走勢圖（欄位 item / price_date / avg_price）。"""
    return _line_figure(df, "avg_price", "盤平均 (USD)", "%{y:.3f}", dark, showlegend)


def build_bond_figure(df: pd.DataFrame, dark: bool = False,
                      showlegend: bool = True) -> go.Figure:
    """美國公債殖利率走勢圖（欄位 item / price_date / yield_pct）。"""
    return _line_figure(df, "yield_pct", "殖利率 (%)", "%{y:.2f}%", dark, showlegend)


def build_gold_figure(df: pd.DataFrame, dark: bool = False,
                      showlegend: bool = True) -> go.Figure:
    """國際金價走勢圖（欄位 item / price_date / price_usd）。"""
    return _line_figure(df, "price_usd", "USD / 盎司", "%{y:,.1f}", dark, showlegend)


def build_points_figure(df: pd.DataFrame, dark: bool = False,
                        showlegend: bool = True) -> go.Figure:
    """
    F1 冠軍積分走勢（欄位 round / name / points，points 為累積值）。

    x 軸是「第幾站」而不是日期，所以不用 _line_figure 那一套
    （rangeslider、快速區間、日期格式在這裡都沒有意義）。
    """
    tmpl, bg = theme_colors(dark)

    if df is None or df.empty:
        return go.Figure().update_layout(
            title="尚無積分資料", template=tmpl, paper_bgcolor=bg, plot_bgcolor=bg,
        )

    # 依最終積分排序，圖例與配色才會照名次
    order = (df.sort_values("round").groupby("name")["points"].last()
               .sort_values(ascending=False).index.tolist())
    grid = df.pivot_table(index="round", columns="name",
                          values="points", aggfunc="last").sort_index()
    grid = grid.reindex(columns=order)
    long = grid.reset_index().melt(id_vars="round", var_name="name", value_name="points")

    fig = px.line(
        long, x="round", y="points", color="name",
        labels={"round": "站次", "points": "累積積分", "name": "項目"},
        markers=True, template=tmpl, render_mode="svg",
    )
    fig.update_traces(
        marker=dict(size=4), line=dict(width=2), cliponaxis=False, connectgaps=True,
        hovertemplate="%{y:.0f}<extra>%{fullData.name}</extra>",
    )
    fig.update_xaxes(
        dtick=1, tick0=1, title_text="站次",
        showspikes=True, spikemode="across", spikesnap="data",
        spikethickness=1, spikedash="dot", spikecolor=_SPIKE_COLOR[dark],
    )
    fig.update_layout(
        hovermode="x unified",
        hoverdistance=-1,
        spikedistance=-1,
        showlegend=showlegend,
        legend=dict(orientation="h", yanchor="top", y=-0.22,
                    xanchor="left", x=0, title_text=""),
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        margin=dict(l=54, r=20, t=20, b=150 if showlegend else 46),
    )
    return fig
