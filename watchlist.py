"""
自選清單（repo 根目錄的 watchlist.csv）

    代號,備註,推播
    2330,範例，可刪除,否

在 GitHub 網頁或 App 上直接編輯就好：
    新增   加一列
    移除   刪掉那一列（或刪掉整個檔案）
    不推播 「推播」改成否，網頁上仍然顯示

檔案不存在、是空的、或格式有錯的列，都當成「沒有這一檔」處理，不會讓排程失敗。
"""
import csv
import io
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WATCHLIST = BASE_DIR / "watchlist.csv"
EDIT_URL = "https://github.com/ChrisHo0317/Local_Dashboard/edit/main/watchlist.csv"

YES = {"是", "y", "yes", "true", "1", "要", "推", "on"}


def parse(text: str) -> list[dict]:
    reader = csv.reader(io.StringIO(text))
    out, seen = [], set()
    for i, row in enumerate(reader):
        if not row or not row[0].strip() or row[0].strip().startswith("#"):
            continue
        code = row[0].strip().upper()
        if i == 0 and not re.fullmatch(r"\d{4,6}[A-Z]?", code):
            continue                                  # 標題列
        if not re.fullmatch(r"\d{4,6}[A-Z]?", code) or code in seen:
            continue
        seen.add(code)
        note = row[1].strip() if len(row) > 1 else ""
        push = (row[2].strip().lower() in YES) if len(row) > 2 and row[2].strip() else True
        out.append({"code": code, "note": note, "push": push})
    return out


def load_watchlist(path: Path = WATCHLIST) -> list[dict]:
    if not path.exists():
        return []
    try:
        return parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return []
