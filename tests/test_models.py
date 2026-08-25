from app import models


def test_catalog_integrity():
    ids = [e["id"] for e in models.CATALOG]
    assert len(ids) == len(set(ids))
    for e in models.CATALOG:
        for key in ("label", "repo", "model", "mmproj", "bytes", "min_ram_gb", "desc"):
            assert e.get(key), (e["id"], key)
    # min_ram 오름차순 (recommended_id가 '들어가는 것 중 마지막'을 고르므로)
    rams = [e["min_ram_gb"] for e in models.CATALOG]
    assert rams == sorted(rams)


def test_recommended_by_ram():
    assert models.recommended_id(4) == "qwen3vl-2b"
    assert models.recommended_id(8) == "qwen3vl-4b"
    assert models.recommended_id(16) == "qwen3vl-8b"
    assert models.recommended_id(64) == "qwen3vl-30b"
    assert models.recommended_id(2) == "qwen3vl-2b"  # 미달이어도 최소 모델


def test_current_defaults_to_recommended(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(models, "total_ram_gb", lambda: 16)
    monkeypatch.setattr(models, "installed", lambda e: False)
    assert models.current()["id"] == "qwen3vl-8b"  # 미설치 → 첫 실행 다운로드 대상


def test_current_falls_back_to_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(models, "total_ram_gb", lambda: 64)   # 추천은 30b지만
    monkeypatch.setattr(models, "installed", lambda e: e["id"] == "qwen3vl-8b")
    assert models.current()["id"] == "qwen3vl-8b"  # 설치된 8b 사용


def test_select_requires_installed(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(models, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(models, "installed", lambda e: False)
    with pytest.raises(ValueError):
        models.select("qwen3vl-2b")
    with pytest.raises(ValueError):
        models.select("없는모델")
