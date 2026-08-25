"""Shared LLM plumbing for ReconLoop agents: model fallback, rate limiting, retries.

Free-tier discipline: primary/fallback Groq models, a strict minimum interval
between LLM calls, and exponential backoff on failures. Never raises past the
agent boundary — callers degrade gracefully.
"""

from __future__ import annotations

import logging
import os
import time

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PRIMARY_LLM_MODEL = "openai/gpt-oss-120b"
FALLBACK_LLM_MODEL = "openai/gpt-oss-20b"
DEFAULT_MIN_INTERVAL_SECONDS = 2.5


class RateLimiter:
    """Enforces a minimum interval between successive LLM calls."""

    def __init__(self, min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS):
        self.min_interval = min_interval_seconds
        self._last_call = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()


def groq_api_key() -> str:
    load_dotenv()
    return (os.getenv("GROQ_API_KEY") or "").strip()


def build_llm():
    """ChatGroq with model fallback, or None when unavailable."""
    if not groq_api_key():
        logger.warning("GROQ_API_KEY not configured - LLM agents degraded")
        return None
    try:
        from langchain_groq import ChatGroq

        primary = ChatGroq(model=PRIMARY_LLM_MODEL, temperature=0, max_retries=0)
        fallback = ChatGroq(model=FALLBACK_LLM_MODEL, temperature=0, max_retries=0)
        return primary.with_fallbacks([fallback])
    except Exception as exc:
        logger.warning("LLM initialization failed (%s) - agents degraded", exc)
        return None


def invoke_with_retry(
    agent, payload: dict, config: dict | None = None, max_attempts: int = 4
):
    """Invoke a LangGraph agent with exponential backoff on transient failures."""
    attempt = 0
    delay = 2.0
    while True:
        try:
            if config is not None:
                return agent.invoke(payload, config=config)
            return agent.invoke(payload)
        except Exception as exc:
            attempt += 1
            if attempt >= max_attempts:
                raise
            sleep_seconds = min(delay * (2 ** (attempt - 1)), 30.0)
            logger.warning(
                "LLM call failed (%s); retry %d/%d in %.1fs",
                exc,
                attempt,
                max_attempts - 1,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
