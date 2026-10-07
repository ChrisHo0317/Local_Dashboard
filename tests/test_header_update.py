"""頁首「資料更新」時間：讀 update.yml 寫的 data/last_update.json。"""
import build_static as bs


def test_data_updated(tmp_path, monkeypatch):
    f = tmp_path / "last_update.json"
    monkeypatch.setattr(bs, "LAST_UPDATE", f)
    assert bs._data_updated() == ""                         # 還沒有紀錄：不顯示
    f.write_text('{"time": "2026-10-07 02:41", "slot": "30 9 * * 1-5"}', encoding="utf-8")
    assert bs._data_updated() == "10/7（三）02:41"
    f.write_text("壞掉", encoding="utf-8")
    assert bs._data_updated() == ""
