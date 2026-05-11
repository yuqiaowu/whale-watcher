import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests


HTTP_TIMEOUT = (10, 60)


def _deepseek_attempt_count() -> int:
    try:
        return max(1, min(5, int(os.getenv("DEEPSEEK_RETRY_ATTEMPTS", "2"))))
    except (TypeError, ValueError):
        return 2


def _deepseek_retry_delay_seconds() -> float:
    try:
        return max(0.0, min(5.0, float(os.getenv("DEEPSEEK_RETRY_DELAY_SECONDS", "0.5"))))
    except (TypeError, ValueError):
        return 0.5


def _preview_text(text: str, limit: int = 1200) -> str:
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _chat_completion_text(payload: Dict[str, Any]) -> Tuple[str, str]:
    try:
        message = payload["choices"][0]["message"]
    except Exception:
        return "", ""
    content = message.get("content") or ""
    reasoning_content = message.get("reasoning_content") or ""
    return str(content).strip(), str(reasoning_content).strip()


def _deepseek_base_audit(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    mode: str,
) -> Dict[str, Any]:
    return {
        "enabled": True,
        "provider": "deepseek",
        "model": model,
        "mode": mode,
        "status": "not_attempted",
        "system_prompt_preview": _preview_text(system_prompt),
        "user_prompt_preview": _preview_text(prompt),
        "raw_response_preview": "",
        "reasoning_available": False,
        "parsed_response": None,
        "error": None,
        "attempt_count": 0,
        "attempts": [],
    }


def call_deepseek_text_with_audit(
    prompt: str,
    *,
    system_prompt: str,
    temperature: float = 0.0,
    enable_env_flag: Optional[str] = None,
    model_env: str = "MODEL_DECISION_REASONER_MODEL",
    default_model: str = "deepseek-reasoner",
) -> Tuple[Optional[str], Dict[str, Any]]:
    if enable_env_flag:
        enabled = os.getenv(enable_env_flag, "0").lower() in {"1", "true", "yes"}
        if not enabled:
            audit = _deepseek_base_audit(
                model=os.getenv(model_env, default_model),
                system_prompt=system_prompt,
                prompt=prompt,
                mode="text",
            )
            audit["enabled"] = False
            audit["status"] = "disabled"
            return None, audit

    api_key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv(model_env, default_model)
    audit = _deepseek_base_audit(model=model, system_prompt=system_prompt, prompt=prompt, mode="text")
    if not api_key:
        audit["status"] = "no_provider_configured"
        audit["error"] = "missing_DEEPSEEK_API_KEY"
        return None, audit

    attempts = _deepseek_attempt_count()
    delay = _deepseek_retry_delay_seconds()
    for attempt in range(1, attempts + 1):
        audit["attempt_count"] = attempt
        try:
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "temperature": temperature,
                },
                timeout=HTTP_TIMEOUT,
            )
            if res.status_code != 200:
                error = f"status_{res.status_code}: {_preview_text(res.text, limit=500)}"
                audit["attempts"].append({"attempt": attempt, "status": "http_error", "error": error})
                audit["status"] = "http_error"
                audit["error"] = error
            else:
                content, reasoning_content = _chat_completion_text(res.json())
                audit["raw_response_preview"] = _preview_text(content)
                audit["reasoning_available"] = bool(reasoning_content)
                audit["status"] = "parsed" if content else "empty"
                audit["error"] = None if content else "empty_response"
                audit["attempts"].append({"attempt": attempt, "status": audit["status"], "error": audit["error"]})
                if content:
                    return content, audit
        except Exception as exc:
            audit["status"] = "exception"
            audit["error"] = str(exc)
            audit["attempts"].append({"attempt": attempt, "status": "exception", "error": str(exc)})
        if attempt < attempts and delay > 0:
            time.sleep(delay)
    return None, audit


def call_deepseek_json_with_audit(
    prompt: str,
    *,
    system_prompt: str,
    temperature: float = 0.0,
    enable_env_flag: Optional[str] = None,
    model_env: str = "MODEL_DECISION_FORMATTER_MODEL",
    default_model: str = "deepseek-chat",
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    if enable_env_flag:
        enabled = os.getenv(enable_env_flag, "0").lower() in {"1", "true", "yes"}
        if not enabled:
            audit = _deepseek_base_audit(
                model=os.getenv(model_env, default_model),
                system_prompt=system_prompt,
                prompt=prompt,
                mode="json_object",
            )
            audit["enabled"] = False
            audit["status"] = "disabled"
            return None, audit

    api_key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv(model_env, default_model)
    audit = _deepseek_base_audit(model=model, system_prompt=system_prompt, prompt=prompt, mode="json_object")
    if not api_key:
        audit["status"] = "no_provider_configured"
        audit["error"] = "missing_DEEPSEEK_API_KEY"
        return None, audit

    attempts = _deepseek_attempt_count()
    delay = _deepseek_retry_delay_seconds()
    for attempt in range(1, attempts + 1):
        audit["attempt_count"] = attempt
        try:
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
                timeout=HTTP_TIMEOUT,
            )
            if res.status_code != 200:
                error = f"status_{res.status_code}: {_preview_text(res.text, limit=500)}"
                audit["status"] = "http_error"
                audit["error"] = error
                audit["attempts"].append({"attempt": attempt, "status": "http_error", "error": error})
            else:
                text, reasoning_content = _chat_completion_text(res.json())
                parsed = _extract_json_object(text)
                audit["raw_response_preview"] = _preview_text(text)
                audit["reasoning_available"] = bool(reasoning_content)
                audit["parsed_response"] = parsed
                audit["status"] = "parsed" if isinstance(parsed, dict) else "unparsed"
                audit["error"] = None if isinstance(parsed, dict) else "response_not_valid_json_object"
                audit["attempts"].append({"attempt": attempt, "status": audit["status"], "error": audit["error"]})
                if isinstance(parsed, dict):
                    return parsed, audit
        except Exception as exc:
            audit["status"] = "exception"
            audit["error"] = str(exc)
            audit["attempts"].append({"attempt": attempt, "status": "exception", "error": str(exc)})
        if attempt < attempts and delay > 0:
            time.sleep(delay)
    return None, audit


def call_llm_json(
    prompt: str,
    *,
    system_prompt: str,
    temperature: float = 0.0,
    enable_env_flag: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if enable_env_flag:
        enabled = os.getenv(enable_env_flag, "0").lower() in {"1", "true", "yes"}
        if not enabled:
            return None

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        try:
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {deepseek_key}",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
                timeout=HTTP_TIMEOUT,
            )
            if res.status_code == 200:
                text = res.json()["choices"][0]["message"]["content"].strip()
                return _extract_json_object(text)
        except Exception:
            pass

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            res = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": f"SYSTEM: {system_prompt}\n\nUSER: {prompt}"
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": temperature,
                        "response_mime_type": "application/json",
                    },
                },
                timeout=HTTP_TIMEOUT,
            )
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return _extract_json_object(text)
        except Exception:
            pass

    return None


def call_llm_json_with_audit(
    prompt: str,
    *,
    system_prompt: str,
    temperature: float = 0.0,
    enable_env_flag: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    enabled = True
    if enable_env_flag:
        enabled = os.getenv(enable_env_flag, "0").lower() in {"1", "true", "yes"}
        if not enabled:
            return None, {
                "enabled": False,
                "provider": None,
                "model": None,
                "status": "disabled",
                "system_prompt_preview": _preview_text(system_prompt),
                "user_prompt_preview": _preview_text(prompt),
                "raw_response_preview": "",
                "parsed_response": None,
                "error": None,
            }

    providers = [
        {
            "name": "deepseek",
            "key": os.getenv("DEEPSEEK_API_KEY"),
            "model": "deepseek-chat",
        },
        {
            "name": "gemini",
            "key": os.getenv("GEMINI_API_KEY"),
            "model": "gemini-2.5-pro",
        },
    ]
    base_audit = {
        "enabled": True,
        "provider": None,
        "model": None,
        "status": "not_attempted",
        "system_prompt_preview": _preview_text(system_prompt),
        "user_prompt_preview": _preview_text(prompt),
        "raw_response_preview": "",
        "parsed_response": None,
        "error": None,
    }

    for provider in providers:
        if not provider["key"]:
            continue
        audit = dict(base_audit)
        audit["provider"] = provider["name"]
        audit["model"] = provider["model"]
        audit["status"] = "attempted"
        try:
            if provider["name"] == "deepseek":
                res = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {provider['key']}",
                    },
                    json={
                        "model": provider["model"],
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=HTTP_TIMEOUT,
                )
                if res.status_code == 200:
                    text = res.json()["choices"][0]["message"]["content"].strip()
                    parsed = _extract_json_object(text)
                    audit["raw_response_preview"] = _preview_text(text)
                    audit["parsed_response"] = parsed
                    audit["status"] = "parsed" if isinstance(parsed, dict) else "unparsed"
                    if isinstance(parsed, dict):
                        return parsed, audit
                    audit["error"] = "response_not_valid_json_object"
                else:
                    audit["status"] = "http_error"
                    audit["error"] = f"status_{res.status_code}"
            else:
                res = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{provider['model']}:generateContent?key={provider['key']}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [
                            {
                                "parts": [
                                    {
                                        "text": f"SYSTEM: {system_prompt}\n\nUSER: {prompt}"
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {
                            "temperature": temperature,
                            "response_mime_type": "application/json",
                        },
                    },
                    timeout=HTTP_TIMEOUT,
                )
                if res.status_code == 200:
                    text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = _extract_json_object(text)
                    audit["raw_response_preview"] = _preview_text(text)
                    audit["parsed_response"] = parsed
                    audit["status"] = "parsed" if isinstance(parsed, dict) else "unparsed"
                    if isinstance(parsed, dict):
                        return parsed, audit
                    audit["error"] = "response_not_valid_json_object"
                else:
                    audit["status"] = "http_error"
                    audit["error"] = f"status_{res.status_code}"
        except Exception as exc:
            audit["status"] = "exception"
            audit["error"] = str(exc)
        base_audit = audit

    if not enabled:
        base_audit["status"] = "disabled"
    elif base_audit["provider"] is None:
        base_audit["status"] = "no_provider_configured"
    return None, base_audit
