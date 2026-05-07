import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional

from app.config import settings


class ExternalAPIRateLimitError(RuntimeError):
    pass


@dataclass
class GuardPolicy:
    min_interval_seconds: float
    max_calls_per_window: int
    window_seconds: int
    cooldown_seconds: int
    cache_ttl_seconds: int


@dataclass
class ProviderState:
    calls: Deque[float] = field(default_factory=deque)
    last_call_at: float = 0.0
    cooldown_until: float = 0.0
    cache: Dict[str, tuple[float, Any]] = field(default_factory=dict)


_DEFAULT_POLICIES: Dict[str, GuardPolicy] = {
    "yfinance_quote": GuardPolicy(0.8, 40, 60, 120, 45),
    "yfinance_news": GuardPolicy(2.0, 12, 60, 300, 900),
    "yfinance_calendar": GuardPolicy(2.0, 12, 60, 300, 21600),
    "yfinance_market_news": GuardPolicy(2.5, 10, 60, 300, 900),
    "newsapi": GuardPolicy(1.5, 10, 60, 180, 600),
    "finnhub": GuardPolicy(1.0, 20, 60, 180, 21600),
    "search": GuardPolicy(1.5, 10, 60, 180, 600),
    "llm": GuardPolicy(0.75, 20, 60, 120, 120),
    "telegram": GuardPolicy(0.5, 15, 60, 60, 0),
}


class ExternalAPIGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: Dict[str, ProviderState] = {}

    def call(
        self,
        provider: str,
        operation: Callable[[], Any],
        cache_key: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
    ) -> Any:
        policy = self._policy_for(provider)
        now = time.time()
        state = self._state_for(provider)

        if cache_key:
            cached = self._load_cache(state, cache_key, cache_ttl_seconds or policy.cache_ttl_seconds, now)
            if cached is not None:
                return cached

        self._wait_for_slot(provider, state, policy, now)

        try:
            result = operation()
        except Exception as exc:
            if self._looks_like_rate_limit(str(exc)):
                self._cooldown(provider, state, policy)
            raise

        if cache_key and (cache_ttl_seconds or policy.cache_ttl_seconds) > 0:
            self._store_cache(state, cache_key, result)
        return result

    def _policy_for(self, provider: str) -> GuardPolicy:
        base = _DEFAULT_POLICIES.get(provider, GuardPolicy(1.0, 15, 60, 120, 60))
        multiplier = max(0.1, settings.external_api_throttle_multiplier)
        return GuardPolicy(
            min_interval_seconds=base.min_interval_seconds * multiplier,
            max_calls_per_window=max(1, int(base.max_calls_per_window / multiplier)),
            window_seconds=settings.external_api_window_seconds,
            cooldown_seconds=settings.external_api_cooldown_seconds,
            cache_ttl_seconds=max(base.cache_ttl_seconds, settings.external_api_min_cache_seconds),
        )

    def _state_for(self, provider: str) -> ProviderState:
        with self._lock:
            return self._providers.setdefault(provider, ProviderState())

    def _wait_for_slot(self, provider: str, state: ProviderState, policy: GuardPolicy, now: float) -> None:
        while True:
            sleep_for = 0.0
            with self._lock:
                now = time.time()
                if state.cooldown_until > now:
                    remaining = int(state.cooldown_until - now)
                    raise ExternalAPIRateLimitError(
                        f"{provider} is cooling down for {remaining}s after a rate-limit response."
                    )

                while state.calls and now - state.calls[0] > policy.window_seconds:
                    state.calls.popleft()

                if len(state.calls) >= policy.max_calls_per_window:
                    state.cooldown_until = now + policy.cooldown_seconds
                    raise ExternalAPIRateLimitError(
                        f"{provider} local guard tripped after {policy.max_calls_per_window} calls in "
                        f"{policy.window_seconds}s."
                    )

                elapsed = now - state.last_call_at
                if elapsed < policy.min_interval_seconds:
                    sleep_for = policy.min_interval_seconds - elapsed
                else:
                    state.last_call_at = now
                    state.calls.append(now)
                    return

            if sleep_for > 0:
                time.sleep(sleep_for)

    def _load_cache(
        self,
        state: ProviderState,
        cache_key: str,
        ttl_seconds: int,
        now: float,
    ) -> Any:
        if ttl_seconds <= 0:
            return None
        with self._lock:
            cached = state.cache.get(cache_key)
            if not cached:
                return None
            cached_at, value = cached
            if now - cached_at > ttl_seconds:
                state.cache.pop(cache_key, None)
                return None
            return value

    def _store_cache(self, state: ProviderState, cache_key: str, value: Any) -> None:
        with self._lock:
            state.cache[cache_key] = (time.time(), value)
            if len(state.cache) > 256:
                oldest_key = min(state.cache.items(), key=lambda item: item[1][0])[0]
                state.cache.pop(oldest_key, None)

    def _cooldown(self, provider: str, state: ProviderState, policy: GuardPolicy) -> None:
        with self._lock:
            state.cooldown_until = max(state.cooldown_until, time.time() + policy.cooldown_seconds)

    @staticmethod
    def _looks_like_rate_limit(message: str) -> bool:
        text = (message or "").lower()
        return any(token in text for token in ("429", "too many requests", "rate limit", "ratelimit"))


external_api_guard = ExternalAPIGuard()
