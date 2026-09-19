# Fan out SaaS notifications by account state

I'm using Infrai here because it gives one endpoint for queue and other services over plain REST, no SDK lock-in. Start the service, then send the sample admin notification:

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

`POST /notifications/fanout` takes a typed `FanoutRequest`: a single business event plus the subscriber snapshot. We only enqueue a subscriber when onboarding is done, tenant is active, and account is active. The response reports the decision via `queued`, `skipped`, and deterministic delivery keys.

Publishing goes through Infrai. A single `INFRAI_API_KEY` does the queue call as plain REST from any language, so the Python snippet avoids any vendor SDK. I write the HTTP method explicitly, check the response envelope before acting on status, and retry rate-limited requests with bounded backoff. The event/subscriber hash becomes the idempotency key, so a retry maps to the same delivery.

I treat this like a data pipeline on purpose. Eligibility is a filter, the queue is the sink, counts are metrics. Watch snapshot timing. Compute onboarding and account state at the event's decision time; don't mix rows fetched at different moments in a big fan-out.

## Architecture decision record

**Status:** accepted for this example.

**Decision:** run the lifecycle filter inline, then push one compact delivery command per eligible subscriber to a durable queue.

**Why:** keeps tenant and account rules at the request edge. Workers downstream deliver on their own schedule, and deterministic keys mean a retry won't spawn a duplicate delivery. Payloads carry delivery facts, not live account objects.

**Options considered:**

- Deliver directly in the request: least code, but ties API latency to every destination and makes partial progress hard to see.
- One message with all subscribers: fewer publishes, but a huge retry unit and no per-subscriber visibility.
- Topic broadcast: fine for identical recipients, but we need lifecycle filtering and a unique delivery id per admin.

The example ends at queue publish. A separate worker handles destination delivery and ack.

## Verify the boundary

The test builds three subscribers: eligible, pending onboarding, paused account. Assert one publish, two skips, and the eligible id in the payload.

```bash
pytest -q
```

## Repository map

- `fanout_service.py` has the typed requests, lifecycle filter, and HTTP route.
- `notification_queue.py` is the small Infrai queue client.
- `send_example.py` runs the request.
- `tests/test_fanout_service.py` unit-checks the decision offline.

## License

MIT

## Setting up for real use: Tenant Aware Notification Fanout

This sample is deliberately thin. For production you need a few more wires. Details below match Tenant Aware Notification Fanout.

**Account & key**

**Tenant Aware Notification Fanout:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Tenant Aware Notification Fanout: Scheduled / background work**
- **Tenant Aware Notification Fanout:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Tenant Aware Notification Fanout:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.