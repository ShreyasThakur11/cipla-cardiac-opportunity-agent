"""Language-model provider layer.

Anthropic's Claude is the primary provider. The abstraction exists for two
reasons that both matter in a live demonstration: a second provider can be
swapped in without touching the agent, and a :class:`NullClient` makes the whole
system run with no credentials at all.

The null path is not a stub. Every number, ranking, forecast and verdict is
produced by the deterministic analytics package; the model's only job is to
turn a finished evidence pack into prose. With no key configured the agent
renders that pack through templates instead. The answer is less fluent and
exactly as correct.

Anthropic API notes that this code depends on:

* Claude Opus 5 does not accept ``temperature``, ``top_p`` or ``top_k``.
  Sending any of them returns a 400. Output shape is steered by prompt and by
  ``output_config.effort`` instead.
* Thinking is adaptive; ``budget_tokens`` was removed and is rejected.
* A request may return ``stop_reason == "refusal"`` with a normal 200. Reading
  ``content[0]`` without checking would break, so the check comes first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import Settings, get_settings
from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ToolCall:
    """A tool the model wants executed."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """One turn from the model."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    raw_content: Any = None
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class LLMClient(Protocol):
    """What the agent needs from a language model."""

    available: bool
    model: str

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Produce one turn, possibly requesting tools."""
        ...


class NullClient:
    """Deterministic fallback used when no provider is configured.

    Returns no tool calls and no prose. The caller detects this and renders the
    evidence pack through templates, which is why the agent still answers
    correctly with no credentials present.
    """

    available = False
    model = "deterministic"

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(text="", stop_reason="no_model")


class AnthropicClient:
    """Claude via the official Anthropic SDK."""

    available = True

    def __init__(self, settings: Settings | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "The `anthropic` package is not installed. Run "
                "`pip install -r requirements.txt`, or set CARDIAC_LLM_PROVIDER=none "
                "to run the agent in deterministic mode."
            ) from exc

        self._settings = settings or get_settings()
        self._anthropic = anthropic
        # A bare constructor also picks up an `ant auth login` profile, so this
        # works without ANTHROPIC_API_KEY being exported.
        self._client = anthropic.Anthropic()
        self.model = self._settings.llm_model
        self.effort = self._settings.llm_effort
        self.default_max_tokens = self._settings.llm_max_tokens

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(max_tokens or self.default_max_tokens),
            # Cache the system prompt: it is large, byte-stable across turns,
            # and re-sent on every iteration of the tool loop.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"effort": self.effort},
            "thinking": {"type": "adaptive"},
        }
        if tools:
            request["tools"] = tools

        try:
            response = self._client.messages.create(**request)
        except self._anthropic.RateLimitError as exc:
            logger.warning("llm.rate_limited", error=str(exc))
            raise
        except self._anthropic.APIStatusError as exc:
            logger.error("llm.api_error", status=exc.status_code, error=str(exc))
            raise

        stop_reason = getattr(response, "stop_reason", "end_turn") or "end_turn"

        # Guard before touching content: a refusal returns HTTP 200 with an
        # empty or partial content array.
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            logger.warning(
                "llm.refusal",
                category=getattr(details, "category", None),
                explanation=getattr(details, "explanation", None),
            )
            return LLMResponse(
                text="",
                stop_reason="refusal",
                raw_content=getattr(response, "content", []),
                model=getattr(response, "model", self.model),
            )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "tool_use":
                arguments = block.input
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(arguments or {}))
                )

        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": int(getattr(usage_obj, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage_obj, "output_tokens", 0) or 0),
            "cache_read_input_tokens": int(getattr(usage_obj, "cache_read_input_tokens", 0) or 0),
        }

        logger.info(
            "llm.turn",
            model=getattr(response, "model", self.model),
            stop_reason=stop_reason,
            tool_calls=[call.name for call in tool_calls],
            **usage,
        )
        return LLMResponse(
            text="\n".join(part for part in text_parts if part).strip(),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw_content=response.content,
            usage=usage,
            model=getattr(response, "model", self.model),
        )


class OpenAIClient:
    """Optional OpenAI provider, kept deliberately thin.

    Present so the architecture is genuinely provider-agnostic rather than
    nominally so. Claude is the default because the agent leans on adaptive
    thinking and long-context tool loops.
    """

    available = True

    def __init__(self, settings: Settings | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "CARDIAC_LLM_PROVIDER=openai requires the `openai` package. "
                "Install it, or switch the provider back to anthropic."
            ) from exc
        self._settings = settings or get_settings()
        self._client = OpenAI()
        self.model = self._settings.llm_model
        self.default_max_tokens = self._settings.llm_max_tokens

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        converted_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            for tool in (tools or [])
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_completion_tokens": int(max_tokens or self.default_max_tokens),
        }
        if converted_tools:
            payload["tools"] = converted_tools

        completion = self._client.chat.completions.create(**payload)
        choice = completion.choices[0]
        calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in (choice.message.tool_calls or [])
        ]
        return LLMResponse(
            text=choice.message.content or "",
            tool_calls=calls,
            stop_reason="tool_use" if calls else "end_turn",
            model=self.model,
        )


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    """Instantiate the configured provider, degrading to deterministic mode.

    A missing key or an uninstalled SDK is not a fatal error - it downgrades to
    :class:`NullClient` with a warning, so a demonstration never dies because
    of a credential problem.
    """
    settings = settings or get_settings()

    if settings.llm_provider == "none":
        logger.info("llm.provider.disabled")
        return NullClient()

    if not settings.llm_available:
        logger.warning(
            "llm.provider.no_credentials",
            provider=settings.llm_provider,
            hint="Set the provider API key in .env, or CARDIAC_LLM_PROVIDER=none to silence this.",
        )
        return NullClient()

    try:
        if settings.llm_provider == "anthropic":
            return AnthropicClient(settings)
        if settings.llm_provider == "openai":
            return OpenAIClient(settings)
    except RuntimeError as exc:
        logger.warning("llm.provider.unavailable", provider=settings.llm_provider, error=str(exc))
        return NullClient()

    logger.warning("llm.provider.unknown", provider=settings.llm_provider)
    return NullClient()


__all__ = [
    "AnthropicClient",
    "LLMClient",
    "LLMResponse",
    "NullClient",
    "OpenAIClient",
    "ToolCall",
    "build_llm_client",
]
