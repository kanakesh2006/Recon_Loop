"""Exception Explainer agent — grounded, cited explanations for reconciliation breaks.

Uses a LangGraph ReAct agent over Groq (gpt-oss-120b primary, gpt-oss-20b
fallback) with the policy/transaction tools. Rate-limited for free tiers and
degrades to a fixed message when the LLM is unavailable.
"""

from __future__ import annotations

import logging

from backend.agents.llm import (
    RateLimiter,
    build_llm,
    invoke_with_retry,
)
from backend.matching.match_record import MatchRecord

logger = logging.getLogger(__name__)

DEGRADED_MESSAGE = "Automated explanation unavailable."

SYSTEM_PROMPT = (
    "You are a finance-operations reconciliation expert for ReconLoop. "
    "You explain why reconciliation exceptions occurred, grounded in evidence. "
    "Always use the search_policy_docs tool to retrieve the relevant policy and "
    "get_transaction for transaction evidence before answering. Explain: "
    "(1) why this break likely occurred, (2) a suggested resolution, and "
    "(3) cite the policy document or transaction records you relied on. "
    "If the evidence is insufficient, say so plainly instead of guessing. "
    "At the very end of your explanation, you MUST append your confidence score (0.0 to 1.0) "
    "in exactly this format: [CONFIDENCE: 0.95]. "
    "Be concise: 3-5 sentences."
)


class ExceptionExplainer:
    def __init__(self, min_interval_seconds: float = 2.5):
        self.rate_limiter = RateLimiter(min_interval_seconds)
        self.agent = self._build_agent()

    def _build_agent(self):
        llm = build_llm()
        if llm is None:
            return None
        try:
            from langgraph.prebuilt import create_react_agent

            from backend.agents.tools import AGENT_TOOLS

            return create_react_agent(llm, AGENT_TOOLS, prompt=SYSTEM_PROMPT)
        except Exception as exc:
            logger.warning("Explainer agent initialization failed: %s", exc)
            return None

    @property
    def available(self) -> bool:
        return self.agent is not None

    @staticmethod
    def _build_prompt(record: MatchRecord) -> str:
        details = record.details or {}
        detail_lines = "\n".join(f"- {key}: {value}" for key, value in details.items())
        if not detail_lines:
            detail_lines = "- (none recorded)"
        return (
            "Explain this reconciliation exception for a finance-ops user.\n\n"
            f"Rule fired: {record.rule_or_model}\n"
            f"Match stage: {record.match_stage}\n"
            f"Confidence: {record.confidence_score:.2f}\n"
            f"Involved transactions: {', '.join(record.txn_ids)}\n"
            f"Matcher details:\n{detail_lines}\n\n"
            "Retrieve policy and transaction evidence with the tools, then explain "
            "why this break occurred, suggest a resolution, and cite your sources."
        )

    def explain_exception(self, record: MatchRecord) -> tuple[str, float | None]:
        if not self.available:
            return DEGRADED_MESSAGE, None
        try:
            self.rate_limiter.wait()
            result = invoke_with_retry(
                self.agent, {"messages": [("user", self._build_prompt(record))]}
            )
            messages = result.get("messages", [])
            if not messages:
                return DEGRADED_MESSAGE, None
            content = messages[-1].content
            text = content if isinstance(content, str) else str(content)
            
            # Extract confidence score
            import re
            confidence = None
            match = re.search(r"\[CONFIDENCE:\s*([\d\.]+)\]", text, re.IGNORECASE)
            if match:
                try:
                    confidence = float(match.group(1))
                    text = text[:match.start()].strip()
                except ValueError:
                    pass
                    
            return text.strip() or DEGRADED_MESSAGE, confidence
        except Exception as exc:
            logger.warning("explain_exception failed: %s", exc)
            return DEGRADED_MESSAGE, None
