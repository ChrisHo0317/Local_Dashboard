"""
產生網站圖示（favicon / iOS 加入主畫面用 / Bark 通知圖示）

    python make_icons.py

輸出到 web/：icon-180.png（iOS apple-touch-icon，Bark 通知也用這張）、icon-192.png、
icon-512.png（Android / manifest）、favicon-32.png。

只在需要重做圖示時執行；平常不會用到。需要 Pillow、numpy：
    pip install pillow numpy

圖示內容（2026-10-07 使用者選的「熱力矩陣」）：深藍到深紫的斜向漸層底，
4×4 的圓角方格從左下（冷，天藍）到右上（熱，紅）斜向漸變，右上最強的一格加白框，
呼應網站的市場熱度與族群強度熱圖；不放文字（主畫面下方本來就有名稱）。

iOS 會自行套用圓角遮罩，因此畫面必須是「不透明的整個正方形」，
且內容要留在中央安全區內，避免被切掉。
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent / "web"   # 建置時原樣複製到 site/

BG_FROM = (15, 23, 42)     # #0f172a 左下
BG_TO   = (59, 7, 100)     # #3b0764 右上
FRAME   = (255, 255, 255)  # 最強那格的白框

# 冷 → 熱：方格顏色依「欄 + (3 - 列)」取，左下 0、右上 6
RAMP = ["#38bdf8", "#60a5fa", "#818cf8", "#a78bfa", "#f472b6", "#fb7185", "#ef4444"]

S = 2048  # 先畫大張再縮小，得到平滑邊緣（座標以 100 為一邊來寫，乘上 U）
U = S / 100


def hex_rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def background() -> Image.Image:
    # 左下到右上的斜向漸層：t ＝ (x + (1 − y)) / 2
    xs = np.linspace(0, 1, S)
    t = (xs[None, :] + (1 - xs[:, None])) / 2
    a, b = np.array(BG_FROM, float), np.array(BG_TO, float)
    rgb = a + (b - a) * t[..., None]
    return Image.fromarray(rgb.round().astype(np.uint8), "RGB")


def draw_icon() -> Image.Image:
    img = background()
    d = ImageDraw.Draw(img)
    for c in range(4):
        for r in range(4):
            x, y = 19.5 + 16 * c, 19.5 + 16 * r
            d.rounded_rectangle([x * U, y * U, (x + 13) * U, (y + 13) * U], radius=3 * U,
                                fill=hex_rgb(RAMP[c + (3 - r)]))
    # 右上最強的一格：外面一圈白框（框寬 2、和方格留 1 的空隙）
    d.rounded_rectangle([65 * U, 17 * U, 83 * U, 35 * U], radius=4.6 * U, outline=FRAME, width=round(2 * U))
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    for size, name in [
        (180, "icon-180.png"),   # iOS apple-touch-icon、Bark 通知圖示
        (192, "icon-192.png"),   # Android
        (512, "icon-512.png"),   # manifest / 高解析
        (32,  "favicon-32.png"), # 瀏覽器分頁
    ]:
        icon.resize((size, size), Image.LANCZOS).save(OUT_DIR / name, optimize=True)
        print(f"[完成] {OUT_DIR / name}")


if __name__ == "__main__":
    main()
