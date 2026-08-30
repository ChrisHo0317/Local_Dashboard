"""
DRAM 報價走勢圖

本地 Dash 版（app.py）與靜態版（build_static.py）都呼叫 build_figure()，
確保兩邊圖表永遠一致。

圖表本身不設 title —— 標題由外層的 HTML 標頭負責。

x 軸帶 rangeslider（圖表下方的時間軸縮圖，可拖曳兩端縮放）與 rangeselector
（快速切換 1／3／6 個月與全部區間）。

showlegend=False 時不畫 Plotly 內建圖例，改由外層自行實作 —— 靜態版
（build_static.py）用可收合的色點按鈕取代，避免 9 個型號在手機上佔掉大半畫面。
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DARK_BG = "#1e2130"
LIGHT_BG = "white"


def theme_colors(dark: bool) -> tuple[str, str]:
    """回傳 (plotly template 名稱, 背景色)。"""
    return ("plotly_dark", DARK_BG) if dark else ("plotly", LIGHT_BG)


def series_colors(fig: go.Figure) -> list[dict]:
    """取出各條線的名稱與顏色，供外層自製圖例使用。"""
    return [
        {"name": t.name, "color": (t.line.color if t.line else None) or "#888888"}
        for t in fig.data
    ]


def build_figure(df: pd.DataFrame, dark: bool = False,
                 showlegend: bool = True) -> go.Figure:
    """依 DRAM 報價 DataFrame 產生折線圖。df 空白時回傳提示用的空圖。"""
    tmpl, bg = theme_colors(dark)

    if df is None or df.empty:
        return go.Figure().update_layout(
            title="尚無 DRAM 報價資料",
            template=tmpl, paper_bgcolor=bg, plot_bgcolor=bg,
        )

    fig = px.line(
        df, x="price_date", y="avg_price", color="item",
        labels={"price_date": "", "avg_price": "盤平均 (USD)", "item": "型號"},
        markers=True,
        template=tmpl,
    )
    fig.update_traces(marker=dict(size=4), line=dict(width=2))

    # 圖表下方的時間軸縮圖：拖曳兩端可縮放，上方主圖同步顯示選取區間
    fig.update_xaxes(
        rangeslider=dict(visible=True, thickness=0.10),
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1月", step="month", stepmode="backward"),
                dict(count=3, label="3月", step="month", stepmode="backward"),
                dict(count=6, label="6月", step="month", stepmode="backward"),
                dict(step="all", label="全部"),
            ],
            font=dict(size=11),
            x=0, xanchor="left", y=1.06, yanchor="bottom",
        ),
    )

    fig.update_layout(
        hovermode="x unified",
        showlegend=showlegend,
        # 圖例置於圖表下方：放在上方會與 Plotly 右上角工具列重疊，
        # 窄螢幕換行成多列後更會蓋到標題。
        legend=dict(orientation="h", yanchor="top", y=-0.30,
                    xanchor="left", x=0, title_text=""),
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        margin=dict(l=60, r=30, t=60, b=150 if showlegend else 40),
    )
    return fig
