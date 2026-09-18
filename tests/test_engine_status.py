from app import llm


def test_status_distinguishes_idle_loading_failure_and_recovery(monkeypatch):
    monkeypatch.setattr(llm, '_proc', None)
    monkeypatch.setattr(llm, '_engine_state', 'idle', raising=False)
    monkeypatch.setattr(llm, '_engine_error', None, raising=False)
    monkeypatch.setattr(llm, 'is_up', lambda: False)
    assert llm.status()['state'] == 'idle'
    monkeypatch.setattr(llm, '_engine_state', 'loading')
    assert llm.status()['state'] == 'loading'
    def fail(timeout):
        raise MemoryError('private raw engine log')
    monkeypatch.setattr(llm, '_ensure_server', fail)
    import pytest
    with pytest.raises(MemoryError):
        llm.ensure_server()
    result = llm.status()
    assert result['state'] == 'error'
    assert result['error']['code'] == 'memory'
    assert 'private' not in str(result)
    monkeypatch.setattr(llm, 'is_up', lambda: True)
    assert llm.status()['state'] == 'ready'
    monkeypatch.setattr(llm, 'is_up', lambda: False)
    assert llm.status()['error']['code'] == 'engine_connection'


def test_exited_process_is_not_normal_idle(monkeypatch):
    monkeypatch.setattr(llm, 'is_up', lambda: False)
    monkeypatch.setattr(llm, '_engine_state', 'idle', raising=False)
    monkeypatch.setattr(llm, '_engine_error', None, raising=False)
    monkeypatch.setattr(llm, '_proc', type('Exited', (), {'poll':lambda self: 1})())
    assert llm.status()['state'] == 'error'
