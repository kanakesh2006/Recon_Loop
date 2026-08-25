"""Settlement Q&A Copilot — conversational agent over reconciliation data.

LangGraph ReAct agent with MemorySaver chat history, the same Groq dual-model
setup and tools as the explainer. Degrades gracefully without an API key.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver

from backend.agents.llm import (
    DEFAULT_MIN_INTERVAL_SECONDS,
    RateLimiter,
    build_llm,
    invoke_with_retry,
)

logger = logging.getLogger(__name__)

COPILOT_UNAVAILABLE_MESSAGE = "Copilot unavailable: GROQ_API_KEY is not configured."

SYSTEM_PROMPT = (
    "You are ReconLoop's Settlement Q&A Copilot for finance-ops users. "
    "Answer questions about transactions, matches, exceptions, fees, and "
    "reconciliation policies. Ground every answer with the tools: "
    "get_transaction for transaction evidence, search_policy_docs for policy, "
    "get_fee_schedule for fee math. Cite what you relied on. If the tools do "
    "not give you enough information, say so plainly rather than guessing."
)


class CopilotSession:
    def __init__(
        self,
        transactions=None,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    ):
        self.rate_limiter = RateLimiter(min_interval_seconds)
        self.thread_id = "reconloop-copilot"
        self.agent = self._build_agent(transactions)

    def _build_agent(self, transactions=None):
        if transactions is not None:
            from backend.agents.tools import set_transaction_index

            set_transaction_index(transactions)
        llm = build_llm()
        if llm is None:
            return None
        try:
            from langgraph.prebuilt import create_react_agent

            from backend.agents.tools import AGENT_TOOLS

            return create_react_agent(
                llm,
                AGENT_TOOLS,
                checkpointer=MemorySaver(),
                prompt=SYSTEM_PROMPT,
            )
        except Exception as exc:
            logger.warning("Copilot agent initialization failed: %s", exc)
            return None

    @property
    def available(self) -> bool:
        return self.agent is not None

    def ask(self, question: str) -> str:
        if not self.agent:
            return COPILOT_UNAVAILABLE_MESSAGE
        if not question.strip():
            return "Please ask a question."
        try:
            self.rate_limiter.wait()
            result = invoke_with_retry(
                self.agent,
                {"messages": [("user", question.strip())]},
                config={"configurable": {"thread_id": self.thread_id}},
            )
            messages = result.get("messages", [])
            if not messages:
                return COPILOT_UNAVAILABLE_MESSAGE
            content = messages[-1].content
            text = content if isinstance(content, str) else str(content)
            return text.strip() or COPILOT_UNAVAILABLE_MESSAGE
        except Exception as exc:
            logger.warning("copilot.ask failed: %s", exc)
            return f"Copilot error: {exc}"
