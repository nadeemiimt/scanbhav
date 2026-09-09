"""Configurable GenAI providers for ScanBhav deep research.

Supported backends (env-driven, swap without code changes):
- ollama              → local Llama / any Ollama chat model
- cursor              → Cursor Agent SDK (composer-2.5, grok-4.5, …)
- openai              → OpenAI Chat Completions
- openai_compatible   → any OpenAI-compatible API (Claude via gateway, Groq, Azure, …)
- anthropic           → Anthropic Messages API (Claude)

Default research model is configurable via GENAI_PROVIDER + GENAI_MODEL.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests

from config import (
    BASE_DIR,
    LLM_MODEL,
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    setting,
)


GENAI_PROVIDER = setting("GENAI_PROVIDER", "ollama")  # ollama | cursor | openai | openai_compatible | anthropic
GENAI_MODEL = setting("GENAI_MODEL", LLM_MODEL)
OPENAI_API_KEY = setting("OPENAI_API_KEY", "") or setting("GENAI_API_KEY", "")
ANTHROPIC_API_KEY = setting("ANTHROPIC_API_KEY", "")
OPENAI_BASE_URL = setting("OPENAI_BASE_URL", "https://api.openai.com/v1")
ANTHROPIC_BASE_URL = setting("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
CURSOR_API_BASE = setting("CURSOR_API_BASE", "https://api.cursor.com")


def _reload_dotenv() -> None:
    """Pick up .env edits without requiring a full process restart."""
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env", override=True)
    except Exception:
        pass


def cursor_api_key() -> str:
    _reload_dotenv()
    return (setting("CURSOR_API_KEY", "") or "").strip()


def openai_api_key() -> str:
    _reload_dotenv()
    return (setting("OPENAI_API_KEY", "") or setting("GENAI_API_KEY", "") or "").strip()


def anthropic_api_key() -> str:
    _reload_dotenv()
    return (setting("ANTHROPIC_API_KEY", "") or "").strip()

# Friendly catalog shown in UI — actual availability depends on keys / Ollama.
PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "ollama",
        "label": "Ollama (local Llama)",
        "models": [
            {"id": "llama3.2:3b", "label": "Llama 3.2 3B"},
            {"id": "llama3.1:8b", "label": "Llama 3.1 8B"},
            {"id": "llama3.2:latest", "label": "Llama 3.2 latest"},
        ],
        "needs_key": False,
        "notes": "Uses local Ollama. Best for offline / private runs.",
    },
    {
        "id": "cursor",
        "label": "Cursor Agent SDK",
        "models": [
            {"id": "composer-2.5", "label": "Composer 2.5"},
            {"id": "cursor-grok-4.5-medium", "label": "Cursor Grok 4.5"},
            {"id": "auto", "label": "Auto → Composer 2.5"},
        ],
        "needs_key": True,
        "key_env": "CURSOR_API_KEY",
        "notes": "Uses CURSOR_API_KEY via Cursor Cloud Agents API (Composer / Grok). Models must include API variant params.",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "models": [
            {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
            {"id": "gpt-4o", "label": "GPT-4o"},
            {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
        ],
        "needs_key": True,
        "key_env": "OPENAI_API_KEY",
        "notes": "Standard OpenAI Chat Completions.",
    },
    {
        "id": "openai_compatible",
        "label": "OpenAI-compatible gateway",
        "models": [
            {"id": "gpt-4o-mini", "label": "Gateway default / GPT-style"},
            {"id": "claude-sonnet-4-20250514", "label": "Claude via compatible gateway"},
        ],
        "needs_key": True,
        "key_env": "OPENAI_API_KEY / GENAI_API_KEY",
        "notes": "Point OPENAI_BASE_URL at any compatible host (OpenRouter, Azure, Groq, Claude gateway, …).",
    },
    {
        "id": "anthropic",
        "label": "Anthropic Claude",
        "models": [
            {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
            {"id": "claude-3-5-haiku-latest", "label": "Claude 3.5 Haiku"},
        ],
        "needs_key": True,
        "key_env": "ANTHROPIC_API_KEY",
        "notes": "Native Anthropic Messages API.",
    },
]


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    raw: Optional[dict[str, Any]] = None


def list_providers() -> dict[str, Any]:
    return {
        "default_provider": GENAI_PROVIDER,
        "default_model": GENAI_MODEL,
        "providers": PROVIDER_CATALOG,
        "configured": {
            "cursor_api_key": bool(cursor_api_key()),
            "openai_api_key": bool(openai_api_key()),
            "anthropic_api_key": bool(anthropic_api_key()),
            "ollama_host": OLLAMA_HOST,
            "openai_base_url": OPENAI_BASE_URL,
            "cursor_http_api": True,
        },
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"narrative": text}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {"narrative": text}


def chat_completion(
    *,
    system: str,
    user: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> LLMResult:
    provider = (provider or GENAI_PROVIDER or "ollama").lower().strip()
    model = (model or GENAI_MODEL or LLM_MODEL).strip()

    if provider == "ollama":
        return _ollama_chat(system, user, model, temperature)
    if provider == "cursor":
        return _cursor_chat(system, user, model)
    if provider in ("openai", "openai_compatible"):
        return _openai_chat(system, user, model, temperature, compatible=(provider == "openai_compatible"))
    if provider == "anthropic":
        return _anthropic_chat(system, user, model, temperature)
    raise ValueError(f"Unknown GENAI_PROVIDER '{provider}'. Use ollama, cursor, openai, openai_compatible, or anthropic.")


def _ollama_chat(system: str, user: str, model: str, temperature: float) -> LLMResult:
    from rag import ollama_client

    response = ollama_client().chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        format="json",
        options={"temperature": temperature, "num_ctx": 8192},
        keep_alive=OLLAMA_KEEP_ALIVE,
    )
    text = response["message"]["content"]
    return LLMResult(text=text, provider="ollama", model=model, raw={"ollama": True})


def _cursor_chat(system: str, user: str, model: str) -> LLMResult:
    api_key = cursor_api_key()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY is not set. Add it to .env to use Cursor Grok / Composer.")

    # Preferred path: Cloud Agents HTTP API (works on Python 3.9; no-repo agent).
    try:
        return _cursor_http_chat(system, user, model, api_key)
    except Exception as http_exc:
        # Optional SDK path when Python >= 3.10 and cursor-sdk is installed.
        try:
            return _cursor_sdk_chat(system, user, model, api_key)
        except ImportError:
            raise RuntimeError(
                f"Cursor HTTP GenAI failed: {http_exc}. "
                "cursor-sdk also unavailable (needs Python >= 3.10). "
                "Check CURSOR_API_KEY and network access to api.cursor.com."
            ) from http_exc
        except Exception as sdk_exc:
            raise RuntimeError(
                f"Cursor GenAI failed via HTTP ({http_exc}) and SDK ({sdk_exc})."
            ) from sdk_exc


def _cursor_model_payload(model: str) -> dict[str, Any]:
    """Build Cloud Agents `model` object (id + required variant params).

    GET /v1/models returns variants that must be sent verbatim — bare ids like
    `grok-4.5` without params are rejected as invalid_model.
    """
    mid = (model or "").strip().lower()
    # Catalog-aligned defaults (see GET https://api.cursor.com/v1/models).
    catalog: dict[str, dict[str, Any]] = {
        "auto": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        "default": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        "composer-2.5": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        "composer": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        "composer-latest": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        "composer-2-5": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        # Fast variant not listed for this account yet — fall back to default composer.
        "composer-2.5-fast": {
            "id": "composer-2.5",
            "params": [{"id": "fast", "value": "false"}],
        },
        "grok-4.5": {
            "id": "grok-4.5",
            "params": [
                {"id": "effort", "value": "medium"},
                {"id": "fast", "value": "false"},
            ],
        },
        "cursor-grok-4.5-medium": {
            "id": "grok-4.5",
            "params": [
                {"id": "effort", "value": "medium"},
                {"id": "fast", "value": "false"},
            ],
        },
    }
    if mid in catalog:
        return catalog[mid]
    # Unknown id: send as-is without params (may still fail — UI should use catalog ids).
    return {"id": (model or "composer-2.5").strip()}


CURSOR_AGENT_NAME = "ScanBhav GenAI research"
CURSOR_AGENT_ID_PATH = BASE_DIR / "data" / "cursor_agent_id.txt"


def _cursor_req(
    method: str,
    url: str,
    api_key: str,
    *,
    json_body: Optional[dict[str, Any]] = None,
    timeout: float = 60,
) -> requests.Response:
    """Cloud Agents auth: Basic (key:) preferred, Bearer fallback on 401."""
    kwargs: dict[str, Any] = {"timeout": timeout}
    if json_body is not None:
        kwargs["json"] = json_body
        kwargs["headers"] = {"Content-Type": "application/json"}
    resp = requests.request(method, url, auth=(api_key, ""), **kwargs)
    if resp.status_code == 401:
        headers = {"Authorization": f"Bearer {api_key}"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
    return resp


def _save_cursor_agent_id(agent_id: str) -> None:
    try:
        CURSOR_AGENT_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
        CURSOR_AGENT_ID_PATH.write_text(agent_id.strip() + "\n", encoding="utf-8")
    except Exception:
        pass


def _load_cursor_agent_id() -> str:
    env_id = (setting("CURSOR_AGENT_ID", "") or "").strip()
    if env_id:
        return env_id
    try:
        if CURSOR_AGENT_ID_PATH.exists():
            return CURSOR_AGENT_ID_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _list_cursor_agents(api_key: str, base: str) -> list[dict[str, Any]]:
    resp = _cursor_req("GET", f"{base}/v1/agents", api_key, timeout=30)
    if resp.status_code >= 400:
        return []
    return list((resp.json() or {}).get("items") or [])


def _archive_cursor_agent(api_key: str, base: str, agent_id: str) -> None:
    _cursor_req("POST", f"{base}/v1/agents/{agent_id}/archive", api_key, timeout=30)


def _resolve_cursor_agent_id(api_key: str, base: str) -> str:
    """Reuse one durable no-repo agent to stay under Cloud Agents plan limits."""
    saved = _load_cursor_agent_id()
    agents = _list_cursor_agents(api_key, base)
    by_id = {a.get("id"): a for a in agents if a.get("id")}

    if saved and saved in by_id and (by_id[saved].get("status") or "").upper() == "ACTIVE":
        return saved

    named = [
        a for a in agents
        if (a.get("name") or "") == CURSOR_AGENT_NAME
        and (a.get("status") or "").upper() == "ACTIVE"
    ]
    if named:
        agent_id = named[0]["id"]
        _save_cursor_agent_id(agent_id)
        return agent_id

    # Prefer any active no-repo agent before creating a new one.
    norepo = [
        a for a in agents
        if (a.get("status") or "").upper() == "ACTIVE" and not (a.get("repos") or [])
    ]
    if norepo:
        agent_id = norepo[0]["id"]
        _save_cursor_agent_id(agent_id)
        return agent_id
    return ""


def _poll_cursor_run(api_key: str, base: str, agent_id: str, run_id: str, model: str) -> LLMResult:
    import time

    deadline = time.time() + 300
    last_status = None
    while time.time() < deadline:
        resp = _cursor_req("GET", f"{base}/v1/agents/{agent_id}/runs/{run_id}", api_key, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"Cursor run poll error {resp.status_code}: {resp.text[:400]}")
        payload = resp.json()
        last_status = payload.get("status")
        if last_status in {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}:
            result_text = payload.get("result") or ""
            if last_status != "FINISHED":
                raise RuntimeError(
                    f"Cursor run ended with status={last_status}: {result_text[:400] or payload}"
                )
            if not result_text:
                raise RuntimeError("Cursor run finished but returned an empty result.")
            return LLMResult(
                text=result_text,
                provider="cursor",
                model=model,
                raw={
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "status": last_status,
                    "transport": "http",
                },
            )
        time.sleep(2.5)
    raise RuntimeError(f"Cursor run timed out (last status={last_status}). agent={agent_id} run={run_id}")


def _cursor_http_chat(system: str, user: str, model: str, api_key: str) -> LLMResult:
    """Call Cursor Cloud Agents API without requiring cursor-sdk / Python 3.10.

    Reuses one durable agent + follow-up runs so Hobby/Free plan concurrency limits
    don't block every GenAI click.
    """
    base = CURSOR_API_BASE.rstrip("/")
    prompt_text = (
        f"{system}\n\n---\n\n{user}\n\n"
        "Return ONLY valid JSON. No markdown fences. Do not edit files; answer in the final reply only."
    )
    model_payload = _cursor_model_payload(model)
    agent_id = _resolve_cursor_agent_id(api_key, base)

    if agent_id:
        run_resp = _cursor_req(
            "POST",
            f"{base}/v1/agents/{agent_id}/runs",
            api_key,
            json_body={"prompt": {"text": prompt_text}},
            timeout=60,
        )
        if run_resp.status_code == 409:
            # Agent busy — wait briefly then poll latest run, or fall through to create.
            import time
            time.sleep(3)
            detail = _cursor_req("GET", f"{base}/v1/agents/{agent_id}", api_key, timeout=30)
            latest = (detail.json() or {}).get("latestRunId") if detail.ok else None
            if latest:
                return _poll_cursor_run(api_key, base, agent_id, latest, model)
        elif run_resp.status_code < 400:
            run = (run_resp.json() or {}).get("run") or run_resp.json() or {}
            run_id = run.get("id")
            if not run_id:
                raise RuntimeError(f"Cursor create-run missing run id: {run_resp.text[:400]}")
            return _poll_cursor_run(api_key, base, agent_id, run_id, model)
        # Stale agent id / archived — clear and create fresh below.
        try:
            if CURSOR_AGENT_ID_PATH.exists():
                CURSOR_AGENT_ID_PATH.unlink()
        except Exception:
            pass

    create_body: dict[str, Any] = {
        "prompt": {"text": prompt_text},
        "name": CURSOR_AGENT_NAME,
        "model": model_payload,
    }
    create = _cursor_req("POST", f"{base}/v1/agents", api_key, json_body=create_body, timeout=120)
    if create.status_code >= 400 and "limit" in (create.text or "").lower():
        # Free up concurrent slots: archive non-primary ScanBhav agents, then retry once.
        agents = _list_cursor_agents(api_key, base)
        keep = _resolve_cursor_agent_id(api_key, base)
        for a in agents:
            aid = a.get("id")
            if not aid or aid == keep:
                continue
            if (a.get("status") or "").upper() != "ACTIVE":
                continue
            _archive_cursor_agent(api_key, base, aid)
        if keep:
            run_resp = _cursor_req(
                "POST",
                f"{base}/v1/agents/{keep}/runs",
                api_key,
                json_body={"prompt": {"text": prompt_text}},
                timeout=60,
            )
            if run_resp.status_code < 400:
                run = (run_resp.json() or {}).get("run") or {}
                run_id = run.get("id")
                if run_id:
                    return _poll_cursor_run(api_key, base, keep, run_id, model)
        create = _cursor_req("POST", f"{base}/v1/agents", api_key, json_body=create_body, timeout=120)

    if create.status_code >= 400:
        raise RuntimeError(
            f"Cursor /v1/agents error {create.status_code}: {create.text[:500]}. "
            "If this is a plan limit, archive old Cloud Agents at cursor.com/agents "
            "or upgrade, then retry."
        )

    data = create.json()
    agent = data.get("agent") or {}
    run = data.get("run") or {}
    agent_id = agent.get("id")
    run_id = run.get("id") or agent.get("latestRunId")
    if not agent_id or not run_id:
        raise RuntimeError(f"Cursor create response missing agent/run ids: {data}")
    _save_cursor_agent_id(agent_id)
    return _poll_cursor_run(api_key, base, agent_id, run_id, model)


def _cursor_sdk_chat(system: str, user: str, model: str, api_key: str) -> LLMResult:
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

    prompt = (
        f"{system}\n\n---\n\n{user}\n\n"
        "Return ONLY valid JSON. No markdown fences."
    )
    result = Agent.prompt(
        prompt,
        AgentOptions(
            api_key=api_key,
            model=model,
            local=LocalAgentOptions(cwd=str(BASE_DIR)),
        ),
    )
    text = getattr(result, "result", None) or getattr(result, "text", None) or str(result)
    status = getattr(result, "status", None)
    if status == "error":
        raise RuntimeError(f"Cursor agent run failed (status=error). Check CURSOR_API_KEY and model '{model}'.")
    return LLMResult(text=str(text), provider="cursor", model=model, raw={"status": status, "transport": "sdk"})


def _openai_chat(system: str, user: str, model: str, temperature: float, *, compatible: bool) -> LLMResult:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY (or GENAI_API_KEY) is not set.")
    base = OPENAI_BASE_URL.rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    # Some gateways reject response_format — retry without it on 400.
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    if response.status_code == 400 and "response_format" in (response.text or ""):
        payload.pop("response_format", None)
        response = requests.post(url, headers=headers, json=payload, timeout=120)
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI-compatible error {response.status_code}: {response.text[:400]}")
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    label = "openai_compatible" if compatible else "openai"
    return LLMResult(text=text, provider=label, model=model, raw={"id": data.get("id")})


def _anthropic_chat(system: str, user: str, model: str, temperature: float) -> LLMResult:
    key = anthropic_api_key()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    url = f"{ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    if response.status_code >= 400:
        raise RuntimeError(f"Anthropic error {response.status_code}: {response.text[:400]}")
    data = response.json()
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return LLMResult(text=text, provider="anthropic", model=model, raw={"id": data.get("id")})


def parse_llm_json(result: LLMResult) -> dict[str, Any]:
    parsed = _extract_json(result.text)
    parsed["_meta"] = {"provider": result.provider, "model": result.model}
    return parsed
