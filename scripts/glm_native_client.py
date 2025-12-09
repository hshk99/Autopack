#!/usr/bin/env python3
"""
Native client for Zhipu GLM chat completion API (BigModel V4).

Auth specifics:
- GLM_API_KEY format: "<api_id>.<api_secret>"
- JWT HS256 with header {"sign_type": "SIGN"}
- Claims MUST be milliseconds:
    api_key: api_id
    exp: now_ms + ttl_ms
    timestamp: now_ms

Endpoint: https://open.bigmodel.cn/api/paas/v4/chat/completions
Default model: glm-4.6

Dependencies: requests, pyjwt
"""

from __future__ import annotations

import os
import time
from typing import List, Dict, Any

import jwt
import requests


class NativeGLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "glm-4.6",
        timeout: int = 30,
    ):
        self.api_key = api_key or os.getenv("GLM_API_KEY")
        if not self.api_key or "." not in self.api_key:
            raise ValueError("GLM_API_KEY is required and must be in the form '<api_id>.<api_secret>'")
        self.api_id, self.api_secret = self.api_key.split(".", 1)
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.model = model
        self.timeout = timeout

    def _generate_token(self, ttl_seconds: int = 300) -> str:
        """
        Generate Zhipu-compatible JWT. Timestamps MUST be milliseconds.
        """
        now_ms = int(round(time.time() * 1000))
        payload = {
            "api_key": self.api_id,
            "exp": now_ms + (ttl_seconds * 1000),
            "timestamp": now_ms,
        }
        headers = {
            "alg": "HS256",
            "sign_type": "SIGN",
        }
        return jwt.encode(payload, self.api_secret.encode("utf-8"), algorithm="HS256", headers=headers)

    def chat(self, messages: List[Dict[str, Any]], model: str | None = None, temperature: float = 0.1) -> str:
        token = self._generate_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "do_sample": True if temperature > 0 else False,
            "stream": False,
        }
        resp = requests.post(self.base_url, json=payload, headers=headers, timeout=self.timeout)
        if not resp.ok:
            # emit raw text for debugging
            raise RuntimeError(f"GLM API error {resp.status_code}: {resp.text}")
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"Unexpected GLM response structure: {resp.text}") from exc


if __name__ == "__main__":
    print("Testing Native GLM-4.6 Client...")
    client = NativeGLMClient()
    try:
        reply = client.chat([{"role": "user", "content": "Hello, are you online?"}])
        print(f"\nSUCCESS: {reply}")
    except Exception as e:
        print(f"\nFAILED: {e}")

