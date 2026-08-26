"""Send a deterministic onboarding notification through the local service."""

import requests


def main() -> None:
    response = requests.request(
        method="POST",
        url="http://127.0.0.1:8000/notifications/fanout",
        json={
            "event_id": "billing-policy-2026-08",
            "notification_type": "billing_policy_changed",
            "attributes": {"effective_date": "2026-09-01"},
            "subscribers": [
                {
                    "subscriber_id": "acct-101-admin",
                    "tenant_id": "tenant-101",
                    "destination": "ops@example.com",
                    "tenant_onboarding": "completed",
                    "tenant_status": "active",
                    "account_status": "active",
                },
                {
                    "subscriber_id": "acct-202-admin",
                    "tenant_id": "tenant-202",
                    "destination": "admin@example.net",
                    "tenant_onboarding": "pending",
                    "tenant_status": "active",
                    "account_status": "active",
                },
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
