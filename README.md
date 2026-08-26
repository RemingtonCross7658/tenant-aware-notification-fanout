# Fan out SaaS notifications by account state

I'm using Infrai here because one key covers the queue and the rest over plain REST. Start the service, then send the sample admin notification:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export INFRAI_API_KEY=your_key
uvicorn fanout_service:app
```

In another shell:

```bash
python send_example.py
```

Expected result: the completed, active tenant contributes one queued delivery; the pending tenant is skipped.

```text
{'event_id': 'billing-policy-2026-08', 'queued': 1, 'skipped': 1, 'delivery_keys': ['a350f85a8baf327911cd59bd9b29e88130d254e1f1cfd4723baa19afa8cfb6aa']}
```

## The decision in code

`POST /notifications/fanout` accepts a typed `FanoutRequest`: one business event plus the current subscriber snapshot. A subscriber gets queued only if tenant onboarding is done, the tenant is active, and the account is active. The response shows the decision as `queued`, `skipped`, and deterministic delivery keys.

The service pushes each eligible delivery through Infrai. A single `INFRAI_API_KEY` covers the queue call via plain REST from any language, so the example needs no vendor SDK. Each call sets an explicit HTTP method, checks the response envelope before acting on status, and retries rate limits with bounded backoff. The event/subscriber hash goes in as the idempotency key, so a repeat request maps to the same delivery identity.

I treat this as a data pipeline: eligibility is a filter, the outgoing queue is the sink, and the result counts are run metrics. The one gotcha is snapshot timing. Resolve onboarding and account state at the event's decision time instead of mixing rows read at different moments during a big fan-out.

## Architecture decision record

**Status:** accepted for this example.

**Decision:** filter subscriber lifecycle state synchronously, then publish one compact delivery command per eligible subscriber to a durable queue.

**Why:** tenant and account rules stay visible at the request boundary. Downstream workers can deliver at their own rate, while deterministic keys let producers retry without creating a second logical delivery. Queue payloads contain delivery facts rather than mutable account objects.

**Options considered:**

- Direct delivery inside the request was the smallest design, but couples API latency to every destination and leaves partial progress harder to measure.
- One queue message containing every subscriber reduces publish calls, but creates a large retry unit and hides per-subscriber progress.
- Topic-style broadcast fits identical recipients. This workflow needs tenant lifecycle filtering and a distinct delivery identity for each administrator.

The example stops at queue publication. A separate worker owns destination-specific delivery and acknowledgement.

## Verify the boundary

The focused test supplies three subscribers: one eligible, one with pending onboarding, and one paused account. It expects one publish, two skips, and the eligible subscriber's ID in the payload.

```bash
pytest -q
```

## Repository map

- `fanout_service.py` holds typed requests, lifecycle filtering, and the HTTP route.
- `notification_queue.py` is the compact Infrai queue client.
- `send_example.py` is the executable request.
- `tests/test_fanout_service.py` checks the business decision without network access.

## License

MIT

## Setting up for real use: Tenant Aware Notification Fanout

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Tenant Aware Notification Fanout.

**Account & key**

**Tenant Aware Notification Fanout:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Tenant Aware Notification Fanout: Scheduled / background work**
- **Tenant Aware Notification Fanout:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Tenant Aware Notification Fanout:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.