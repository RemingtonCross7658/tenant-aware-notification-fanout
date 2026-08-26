"""Tenant-aware notification fan-out service."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from notification_queue import InfraiError, InfraiQueue


class Subscriber(BaseModel):
    subscriber_id: str
    tenant_id: str
    destination: str
    tenant_onboarding: Literal["pending", "completed"]
    tenant_status: Literal["active", "suspended", "closed"]
    account_status: Literal["active", "paused", "closed"]


class FanoutRequest(BaseModel):
    event_id: str = Field(min_length=1)
    notification_type: str = Field(min_length=1)
    attributes: dict[str, str] = Field(default_factory=dict)
    subscribers: list[Subscriber]


class FanoutResult(BaseModel):
    event_id: str
    queued: int
    skipped: int
    delivery_keys: list[str]


class Publisher(Protocol):
    def publish(self, payload: dict[str, object], *, idempotency_key: str) -> dict[str, object]:
        return {}


def is_deliverable(subscriber: Subscriber) -> bool:
    return (
        subscriber.tenant_onboarding == "completed"
        and subscriber.tenant_status == "active"
        and subscriber.account_status == "active"
    )


def delivery_key(event_id: str, subscriber_id: str) -> str:
    source = f"{event_id}:{subscriber_id}".encode()
    return sha256(source).hexdigest()


def fan_out(request: FanoutRequest, publisher: Publisher) -> FanoutResult:
    eligible = [subscriber for subscriber in request.subscribers if is_deliverable(subscriber)]
    keys: list[str] = []

    for subscriber in eligible:
        key = delivery_key(request.event_id, subscriber.subscriber_id)
        publisher.publish(
            {
                "event_id": request.event_id,
                "notification_type": request.notification_type,
                "attributes": request.attributes,
                "subscriber_id": subscriber.subscriber_id,
                "tenant_id": subscriber.tenant_id,
                "destination": subscriber.destination,
            },
            idempotency_key=key,
        )
        keys.append(key)

    return FanoutResult(
        event_id=request.event_id,
        queued=len(eligible),
        skipped=len(request.subscribers) - len(eligible),
        delivery_keys=keys,
    )


app = FastAPI(title="Tenant notification fan-out")


@app.post("/notifications/fanout", response_model=FanoutResult)
def publish_notification(request: FanoutRequest) -> FanoutResult:
    try:
        return fan_out(request, InfraiQueue())
    except InfraiError as exc:
        caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=caller_status, detail=dict(exc.detail)) from exc
