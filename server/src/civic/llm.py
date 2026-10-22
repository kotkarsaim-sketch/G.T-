"""Provider-agnostic LLM gateway (ADR-003).

Every provider speaks chat completions from the caller's perspective; wire
differences are contained here. Streaming yields text deltas only.
"""

import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from civic.settings import get_settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


@dataclass
class Message:
    role: str  # system | user | assistant
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


def _is_azure(provider: str, base_url: str) -> bool:
    return provider == "azure" or "openai.azure.com" in base_url


async def stream_chat(messages: list[Message]) -> AsyncIterator[str]:
    settings = get_settings()
    provider = settings.llm_provider
    base = settings.llm_base_url.rstrip("/")
    try:
        if provider == "anthropic":
            async for tok in _stream_anthropic(messages, base):
                yield tok
        else:
            async for tok in _stream_openai_compatible(messages, base, _is_azure(provider, base)):
                yield tok
    except httpx.HTTPError as exc:
        log.error("llm stream failed: %s", exc)
        raise LLMError("generation upstream unavailable") from exc


async def complete(messages: list[Message]) -> str:
    """Non-streaming convenience used by enrichment tooling."""
    chunks: list[str] = []
    async for tok in stream_chat(messages):
        chunks.append(tok)
    return "".join(chunks)


# --------------------------------------------------------------------------
# OpenAI-compatible (also Azure OpenAI with deployment-style URL)
# --------------------------------------------------------------------------

async def _stream_openai_compatible(
    messages: list[Message], base_url: str, azure: bool
) -> AsyncIterator[str]:
    s = get_settings()
    headers = {"Content-Type": "application/json"}
    if azure:
        url = f"{base_url}/openai/deployments/{s.llm_model}/chat/completions?api-version=2024-06-01"
        headers["api-key"] = s.llm_api_key
    else:
        url = f"{base_url}/chat/completions"
        if s.llm_api_key:
            headers["Authorization"] = f"Bearer {s.llm_api_key}"

    body = {
        "model": s.llm_model,
        "messages": [m.as_dict() for m in messages],
        "stream": True,
        "temperature": 0.2,
        # Small local models are prone to degenerate loops; mild penalties plus
        # a hard token ceiling bound the damage. Hosted models tolerate these.
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
        "max_tokens": 700,
    }
    async with httpx.AsyncClient(timeout=s.llm_timeout_s) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode(errors="replace")[:300]
                raise LLMError(f"provider {resp.status_code}: {detail}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: ") :].strip()
                if payload == "[DONE]":
                    return
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta


# --------------------------------------------------------------------------
# Anthropic native messages API
# --------------------------------------------------------------------------

async def _stream_anthropic(messages: list[Message], base_url: str) -> AsyncIterator[str]:
    s = get_settings()
    url = f"{base_url}/v1/messages"
    system_parts = [m.content for m in messages if m.role == "system"]
    turns = [m.as_dict() for m in messages if m.role != "system"]
    headers = {
        "Content-Type": "application/json",
        "x-api-key": s.llm_api_key,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": s.llm_model,
        "system": "\n\n".join(system_parts),
        "messages": turns,
        "max_tokens": 1024,
        "temperature": 0.2,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=s.llm_timeout_s) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode(errors="replace")[:300]
                raise LLMError(f"provider {resp.status_code}: {detail}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[len("data: ") :])
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "content_block_delta":
                    text = event.get("delta", {}).get("text")
                    if text:
                        yield text
