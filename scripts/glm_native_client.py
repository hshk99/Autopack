#!/usr/bin/env python3
"""
Native client for Zhipu GLM chat completion API (BigModel V4).

Authentication: GLM_API_KEY in the format "<api_id>.<api_secret>".
We construct a JWT (HS256) with claims:
  - api_key: api_id
  - exp: now + 30 minutes
  - timestamp: now

Endpoint (default):
  https://open.bigmodel.cn/api/paas/v4/chat/completions

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
        base_url: str | None = None,
        model: str = "glm-4",
        timeout: int = 30,
    ):
        self.api_key = api_key or os.getenv("GLM_API_KEY")
        self.base_url = (base_url or os.getenv("GLM_API_BASE") or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.model = model
        self.timeout = timeout
        if not self.api_key or "." not in self.api_key:
            raise ValueError("GLM_API_KEY is required and must be in the form '<api_id>.<api_secret>'")
        self.api_id, self.api_secret = self.api_key.split(".", 1)
        self.endpoint = f"{self.base_url}/chat/completions"

    def _generate_token(self) -> str:
        now = int(time.time())
        payload = {
            "api_key": self.api_id,
            "exp": now + 1800,  # 30 minutes
            "timestamp": now,
        }
        return jwt.encode(payload, self.api_secret, algorithm="HS256")

    def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.1) -> str:
        token = self._generate_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "do_sample": True,
            "stream": False,
        }
        resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"GLM API error {resp.status_code}: {resp.text}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"Unexpected GLM response structure: {data}") from exc

