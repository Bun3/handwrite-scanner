from app import templates_store


def test_add_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(templates_store, "TEMPLATES_DIR", tmp_path)
    templates_store.save("t", [{"id": "name", "label": "성명",
                                "type": "candidates", "box": [0, 0, 10, 10],
                                "candidates": ["홍길동"]}])
    assert templates_store.add_candidate("t", "name", "김철수") is True
    assert templates_store.add_candidate("t", "name", "김철수") is False  # 중복
    assert templates_store.add_candidate("t", "없는필드", "x") is False
    assert templates_store.add_candidate("t", "name", " ") is False
    assert templates_store.get("t")["fields"][0]["candidates"] == ["홍길동", "김철수"]
