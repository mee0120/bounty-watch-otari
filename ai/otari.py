"""Thin client for the hosted Otari gateway (https://otari.ai).

Every model call in this project goes through Otari, so routing, fallbacks,
tool execution (web fetch / web search / code execution / MCP), budgets and
usage tracking all happen in the gateway, not in this code.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import requests

BASE_URL = os.getenv("OTARI_BASE_URL", "https://otari.ai/api/v1")


class BudgetExceeded(RuntimeError):
    """Otari refused the call because a budget (workspace or per-user key) is spent."""


@dataclass
class Result:
    content: str
    cost_usd: float = 0.0
    model: str = ""            # model that actually answered (Otari-Model)
    fallback: bool = False     # True when a backup in the routing policy served
    attempts: int = 1
    request_id: str = ""
    guardrails: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)


def _tools(names: list[str]) -> list[dict]:
    return [{"type": n} for n in names]


def chat(key: str, model: str, messages: list[dict], *, tools: list[str] | None = None,
         mcp_servers: list[dict] | None = None, guardrails: list[dict] | None = None,
         user: str | None = None, max_tokens: int = 1200, temperature: float = 0.2,
         max_tool_iterations: int | None = None, tags: list[str] | None = None,
         timeout: int = 300, stream: bool = False, on_tool=None) -> Result:
    if not key:
        raise RuntimeError("Otari API key is not set")
    body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens,
                  "temperature": temperature}
    if tools:
        body["tools"] = _tools(tools)
    if mcp_servers:
        body["mcp_servers"] = mcp_servers
    if guardrails:
        body["guardrails"] = guardrails
    if user:
        body["user"] = user
    if max_tool_iterations:
        body["max_tool_iterations"] = max_tool_iterations
    headers = {"Otari-Key": key, "Content-Type": "application/json"}
    if tags:
        headers["Otari-Tags"] = ",".join(tags)
    if tools and "otari_web_fetch" in tools:
        headers["Otari-Web-Fetch"] = "otari"
    if tools and "otari_web_search" in tools:
        headers["Otari-Web-Search"] = "otari"

    if stream:
        # A tool loop can outlast an HTTP proxy's idle timeout; streaming keeps
        # bytes flowing (Otari sends a chunk as each web tool starts and ends).
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    r = requests.post(f"{BASE_URL}/chat/completions", headers=headers,
                      data=json.dumps(body), timeout=timeout, stream=stream)
    if r.status_code >= 400:
        text = r.text
        if "budget_exceeded" in text or (r.status_code in (402, 429) and "budget" in text.lower()):
            raise BudgetExceeded(text[:300])
        raise RuntimeError(f"Otari {r.status_code}: {text[:400]}")
    if stream:
        data = _read_stream(r, on_tool)
    else:
        data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    try:
        g = json.loads(r.headers.get("Otari-Guardrails", "[]"))
    except ValueError:
        g = []
    return Result(
        content=msg.get("content") or "",
        cost_usd=float(usage.get("cost_usd") or 0),
        model=r.headers.get("Otari-Model", data.get("model", "")),
        fallback=r.headers.get("Otari-Fallback", "false").lower() == "true",
        attempts=int(r.headers.get("Otari-Attempt-Count", "1") or 1),
        request_id=r.headers.get("Otari-Request-ID", ""),
        guardrails=g,
        tool_calls=data.get("otari_tool_calls") or msg.get("tool_calls") or [],
    )


def _read_stream(r, on_tool=None) -> dict:
    """Fold a Chat Completions SSE stream into one non-streamed response shape."""
    content, usage, model, tools_seen = [], {}, "", {}
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if payload == "[DONE]":
            break
        chunk = json.loads(payload)
        if "error" in chunk:
            raise RuntimeError(f"Otari stream error: {str(chunk['error'])[:300]}")
        model = chunk.get("model") or model
        for t in chunk.get("otari_tool_calls") or []:
            first = t.get("id") not in tools_seen
            tools_seen[t.get("id")] = t
            if on_tool and (first or t.get("status") != "in_progress"):
                on_tool(t)
        for ch in chunk.get("choices") or []:
            piece = (ch.get("delta") or {}).get("content")
            if piece:
                content.append(piece)
        if chunk.get("usage"):
            usage = chunk["usage"]
    return {"model": model, "usage": usage,
            "choices": [{"message": {"content": "".join(content)}}],
            "otari_tool_calls": list(tools_seen.values())}


def extract_json(text: str) -> dict:
    """Return the last {...} object in a model answer (models sometimes wrap it)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    end = text.rfind("}")
    depth = 0
    for i in range(end, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            depth -= 1
            if depth == 0:
                return json.loads(text[i:end + 1])
    raise ValueError("no JSON object in answer")
