"""
DRAM 現貨報價 Dashboard（本地 Dash 版）

執行方式：
    python app.py
開啟瀏覽器：
    http://localhost:8051

資料來源為 data/dram_prices.csv；更新報價請執行 python update_data.py。
線上靜態版（GitHub Pages）由 build_static.py 產生，兩者共用 chart.build_figure()。
"""
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from chart import DARK_BG, LIGHT_BG, build_figure
from dram_data import latest_date, load_dram

app = dash.Dash(
    __name__,
    title="DRAM 現貨報價",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)
server = app.server


def _header() -> dbc.Row:
    df = load_dram()
    updated = latest_date(df)
    return dbc.Row(
        [
            dbc.Col(
                [
                    html.H4("DRAM 現貨報價趨勢", className="mb-1"),
                    html.Small(
                        f"資料來源：TrendForce　最後報價日：{updated or '無資料'}",
                        id="subtitle", className="text-muted",
                    ),
                ],
                md=8,
            ),
            dbc.Col(
                dbc.Switch(id="dark-toggle", label="深色模式", value=False,
                           className="mt-2 text-end"),
                md=4,
            ),
        ],
        className="align-items-center mb-3",
    )


app.layout = html.Div(
    id="page",
    children=dbc.Container(
        [
            _header(),
            dcc.Graph(id="dram-chart", style={"height": "600px"}),
        ],
        fluid=True,
        className="py-3",
    ),
)


@app.callback(
    Output("dram-chart", "figure"),
    Output("page", "style"),
    Input("dark-toggle", "value"),
)
def update_dram(dark):
    dark = bool(dark)
    page_style = {
        "backgroundColor": DARK_BG if dark else LIGHT_BG,
        "color": "#e8e8e8" if dark else "#212529",
        "minHeight": "100vh",
    }
    return build_figure(load_dram(), dark), page_style


if __name__ == "__main__":
    print("Dashboard 啟動中：http://localhost:8051")
    app.run(debug=True, port=8051)
