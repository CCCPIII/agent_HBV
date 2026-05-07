import os

from services.yfinance_env import yfinance_network_env


def test_yfinance_env_temporarily_clears_proxy_env(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    with yfinance_network_env():
        assert "HTTP_PROXY" not in os.environ
        assert "HTTPS_PROXY" not in os.environ

    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:9"
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"
