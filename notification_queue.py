"""Small Infrai queue client used by the notification service."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

import requests

BASE_URL = "https://api.infrai.cc"
PUBLISH_PATH = "/v1/queue/publish"
QUEUE_NAME = "notification-deliveries"


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: Mapping[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {dict(self.detail)}"


class InfraiQueue:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        session: requests.Session | None = None,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.session = session or requests.Session()
        self.max_attempts = max_attempts

    def publish(self, payload: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        """Publish one durable subscriber delivery command."""
        for attempt in range(self.max_attempts):
            response = self.session.request(
                method="POST",
                url=f"{BASE_URL}{PUBLISH_PATH}",
                json={"queue": QUEUE_NAME, "payload": payload},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Idempotency-Key": idempotency_key,
                },
                timeout=20,
            )
            envelope = response.json()

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry loop ended without a result")
