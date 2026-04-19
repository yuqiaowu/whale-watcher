import json
import os
import re
from typing import Any, Dict, Optional

import requests


HTTP_TIMEOUT = (10, 60)


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
