import json
import os
import re
from typing import Any, Dict, Optional, Tuple

import requests


HTTP_TIMEOUT = (10, 60)


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
