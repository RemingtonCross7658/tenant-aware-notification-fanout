from typing import Any

from fanout_service import FanoutRequest, fan_out


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, object], str]] = []

    def publish(self, payload: dict[str, object], *, idempotency_key: str) -> dict[str, Any]:
        self.calls.append((payload, idempotency_key))
        return {"accepted": True}


def test_fanout_queues_only_onboarded_active_accounts() -> None:
    request = FanoutRequest.model_validate(
        {
            "event_id": "evt-42",
            "notification_type": "account_policy_changed",
            "attributes": {"policy_version": "7"},
            "subscribers": [
                {
                    "subscriber_id": "ready-admin",
                    "tenant_id": "ready-tenant",
                    "destination": "ready@example.com",
                    "tenant_onboarding": "completed",
                    "tenant_status": "active",
                    "account_status": "active",
                },
                {
                    "subscriber_id": "pending-admin",
                    "tenant_id": "pending-tenant",
                    "destination": "pending@example.com",
                    "tenant_onboarding": "pending",
                    "tenant_status": "active",
                    "account_status": "active",
                },
                {
                    "subscriber_id": "paused-admin",
                    "tenant_id": "ready-tenant",
                    "destination": "paused@example.com",
                    "tenant_onboarding": "completed",
                    "tenant_status": "active",
                    "account_status": "paused",
                },
            ],
        }
    )
    publisher = RecordingPublisher()

    result = fan_out(request, publisher)

    assert result.queued == 1
    assert result.skipped == 2
    assert publisher.calls[0][0]["subscriber_id"] == "ready-admin"
    assert publisher.calls[0][1] == result.delivery_keys[0]
