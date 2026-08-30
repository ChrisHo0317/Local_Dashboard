"""
DRAM 報價走勢圖

本地 Dash 版（app.py）與靜態版（build_static.py）都呼叫 build_figure()，
確保兩邊圖表永遠一致。

圖表設定沿用原 Database_dashboard/app.py 的 update_dram() callback。
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DARK_BG = "#1e2130"
LIGHT_BG = "white"


def theme_colors(dark: bool) -> tuple[str, str]:
    """回傳 (plotly template 名稱, 背景色)。"""
    return ("plotly_dark", DARK_BG) if dark else ("plotly", LIGHT_BG)


def build_figure(df: pd.DataFrame, dark: bool = False) -> go.Figure:
    """依 DRAM 報價 DataFrame 產生折線圖。df 空白時回傳提示用的空圖。"""
    tmpl, bg = theme_colors(dark)

    if df is None or df.empty:
        return go.Figure().update_layout(
            title="尚無 DRAM 報價資料",
            template=tmpl, paper_bgcolor=bg, plot_bgcolor=bg,
        )

    fig = px.line(
        df, x="price_date", y="avg_price", color="item",
        title="DRAM 現貨報價 — 盤平均（USD）",
        labels={"price_date": "日期", "avg_price": "盤平均 (USD)", "item": "型號"},
        markers=True,
        template=tmpl,
    )
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        margin=dict(l=60, r=30, t=90, b=50),
    )
    return fig
