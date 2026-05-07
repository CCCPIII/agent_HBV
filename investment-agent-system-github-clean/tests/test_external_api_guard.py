from services.external_api_guard import ExternalAPIGuard, ExternalAPIRateLimitError


def test_guard_returns_cached_result_without_second_call(monkeypatch):
    guard = ExternalAPIGuard()
    monkeypatch.setattr("services.external_api_guard.settings.external_api_throttle_multiplier", 1.0)
    monkeypatch.setattr("services.external_api_guard.settings.external_api_window_seconds", 60)
    monkeypatch.setattr("services.external_api_guard.settings.external_api_cooldown_seconds", 60)
    monkeypatch.setattr("services.external_api_guard.settings.external_api_min_cache_seconds", 60)

    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        return {"ok": True}

    first = guard.call("search", operation, cache_key="same", cache_ttl_seconds=60)
    second = guard.call("search", operation, cache_key="same", cache_ttl_seconds=60)

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert calls["count"] == 1


def test_guard_enters_cooldown_on_local_burst(monkeypatch):
    guard = ExternalAPIGuard()
    monkeypatch.setattr("services.external_api_guard.settings.external_api_throttle_multiplier", 100.0)
    monkeypatch.setattr("services.external_api_guard.settings.external_api_window_seconds", 60)
    monkeypatch.setattr("services.external_api_guard.settings.external_api_cooldown_seconds", 30)
    monkeypatch.setattr("services.external_api_guard.settings.external_api_min_cache_seconds", 0)

    result = guard.call("search", lambda: "ok", cache_ttl_seconds=0)
    assert result == "ok"

    try:
        guard.call("search", lambda: "boom", cache_ttl_seconds=0)
    except ExternalAPIRateLimitError as exc:
        assert "local guard tripped" in str(exc)
    else:
        raise AssertionError("Expected local rate-limit error")
