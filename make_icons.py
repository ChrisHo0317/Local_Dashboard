"""
產生網站圖示（favicon / iOS 加入主畫面用）

    python make_icons.py

輸出到 docs/：icon-180.png（iOS apple-touch-icon）、icon-192.png、
icon-512.png（Android / manifest）、favicon-32.png。

只在需要重做圖示時執行；平常不會用到。需要 Pillow：
    pip install pillow

圖示內容：K 線（漲跌燭身）＋上升折線，底色與 dashboard 深色主題一致。
這個 app 涵蓋 DRAM、美債、黃金、財經行事曆，所以用通用的財金意象，
不再用特定商品（原本是 DRAM 記憶體模組）。

iOS 會自行套用圓角遮罩，因此畫面必須是「不透明的整個正方形」，
且內容要留在中央安全區內，避免被切掉。
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent / "docs"

BG   = (22, 26, 43)       # #161a2b 深藍底（與 chart 深色主題同調）
UP   = (61, 220, 151)     # 上漲燭身（薄荷綠）
DOWN = (255, 107, 94)     # 下跌燭身（珊瑚紅）
LINE = (232, 236, 244)    # 趨勢線（近白）
AXIS = (60, 68, 96)       # 基準線

S = 1024  # 先畫大張再縮小，得到平滑邊緣

# 每根 K 棒：(低, 高, 開, 收) 皆為 0~1 的相對高度，1 = 最上緣
# 整體呈上升趨勢，中間夾一根下跌棒，一眼就看得出是行情圖
CANDLES = [
    (0.12, 0.42, 0.18, 0.36),
    (0.28, 0.62, 0.34, 0.56),
    (0.44, 0.70, 0.66, 0.50),   # 下跌
    (0.52, 0.90, 0.58, 0.84),
]


def draw_icon() -> Image.Image:
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    left, right = 0.13 * S, 0.87 * S
    bottom, top = 0.775 * S, 0.13 * S
    span = bottom - top

    def y(v: float) -> float:
        return bottom - v * span

    # 底部基準線
    d.rounded_rectangle([left - 0.03 * S, bottom, right + 0.03 * S, bottom + 0.018 * S],
                        radius=0.009 * S, fill=AXIS)

    n = len(CANDLES)
    slot = (right - left) / n
    body_w = slot * 0.52
    wick_w = max(2.0, slot * 0.10)

    centers = []
    for i, (lo, hi, op, cl) in enumerate(CANDLES):
        cx = left + slot * (i + 0.5)
        centers.append((cx, y(cl)))
        color = UP if cl >= op else DOWN

        # 影線
        d.rounded_rectangle([cx - wick_w / 2, y(hi), cx + wick_w / 2, y(lo)],
                            radius=wick_w / 2, fill=color)
        # 燭身
        b0, b1 = sorted((y(op), y(cl)))
        if b1 - b0 < 0.03 * S:            # 開收太接近時給個最小厚度
            mid = (b0 + b1) / 2
            b0, b1 = mid - 0.015 * S, mid + 0.015 * S
        d.rounded_rectangle([cx - body_w / 2, b0, cx + body_w / 2, b1],
                            radius=0.016 * S, fill=color)

    # 貫穿的上升趨勢線（沿各棒收盤價）
    d.line(centers, fill=LINE, width=int(0.024 * S), joint="curve")
    r = 0.026 * S
    hx, hy = centers[-1]
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=LINE)

    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    for size, name in [
        (180, "icon-180.png"),   # iOS apple-touch-icon
        (192, "icon-192.png"),   # Android
        (512, "icon-512.png"),   # manifest / 高解析
        (32,  "favicon-32.png"), # 瀏覽器分頁
    ]:
        icon.resize((size, size), Image.LANCZOS).save(OUT_DIR / name, optimize=True)
        print(f"[完成] {OUT_DIR / name}")


if __name__ == "__main__":
    main()
