"""
產生網站圖示（favicon / iOS 加入主畫面用）

    python make_icons.py

輸出到 docs/：icon-180.png（iOS apple-touch-icon）、icon-192.png、
icon-512.png（Android / manifest）、favicon-32.png。

只在需要重做圖示時執行；平常不會用到。需要 Pillow：
    pip install pillow

圖示內容：DRAM 記憶體模組 + 上升折線，底色與 dashboard 深色主題一致。
iOS 會自行套用圓角遮罩，因此畫面必須是「不透明的整個正方形」，
且內容要留在中央安全區內，避免被切掉。
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent / "docs"

BG      = (22, 26, 43)      # #161a2b 深藍底（與 chart 深色主題同調）
PCB     = (32, 122, 92)     # 模組基板綠
PCB_EDGE= (24, 92, 70)
CHIP    = (232, 236, 244)   # 模組上的顆粒
PIN     = (229, 181, 103)   # 金手指
LINE    = (77, 212, 172)    # 上升折線（薄荷綠）
DOT     = (255, 255, 255)

S = 1024  # 先畫大張再縮小，得到平滑邊緣


def draw_icon() -> Image.Image:
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    # ── 上半部：上升折線 ────────────────────────────────
    pts = [
        (0.16, 0.46), (0.32, 0.36), (0.46, 0.40),
        (0.62, 0.26), (0.84, 0.17),
    ]
    xy = [(x * S, y * S) for x, y in pts]
    d.line(xy, fill=LINE, width=int(0.062 * S), joint="curve")
    for x, y in xy:
        r = 0.036 * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=LINE)
    # 最高點加白色圓點強調
    hx, hy = xy[-1]
    r = 0.026 * S
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=DOT)

    # ── 下半部：DRAM 模組 ──────────────────────────────
    left, right = 0.11 * S, 0.89 * S
    top, bottom = 0.585 * S, 0.79 * S
    d.rounded_rectangle([left, top, right, bottom], radius=0.022 * S,
                        fill=PCB, outline=PCB_EDGE, width=int(0.008 * S))

    # 模組上的 4 顆記憶體顆粒
    n = 4
    pad = 0.035 * S
    gap = 0.022 * S
    cw = (right - left - 2 * pad - (n - 1) * gap) / n
    ch = (bottom - top) * 0.52
    cy = top + (bottom - top - ch) / 2
    for i in range(n):
        cx = left + pad + i * (cw + gap)
        d.rounded_rectangle([cx, cy, cx + cw, cy + ch],
                            radius=0.008 * S, fill=CHIP)

    # 金手指（底部接腳）
    py0, py1 = bottom, bottom + 0.065 * S
    pin_w = 0.030 * S
    pin_gap = 0.024 * S
    x = left + 0.03 * S
    while x + pin_w <= right - 0.03 * S:
        d.rounded_rectangle([x, py0, x + pin_w, py1],
                            radius=0.004 * S, fill=PIN)
        x += pin_w + pin_gap

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
