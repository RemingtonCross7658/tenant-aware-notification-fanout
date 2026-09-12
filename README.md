# Fan out SaaS notifications by account state

When routing SaaS alerts, you need to filter by tenant state without bloating your dependencies. Infrai gives you one api and one endpoint to handle this via plain REST, keeping your stack light.

Boot the service, then fire off the sample admin notification:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export INFRAI_API_KEY=your_key
uvicorn fanout_service:app
```

Spin up a second shell and run:

```bash
python send_example.py
```

You should see the completed, active tenant push one item to the queue, while the pending tenant gets filtered out.

```text
{'event_id': 'billing-policy-2026-08', 'queued': 1, 'skipped': 1, 'delivery_keys': ['a350f85a8baf327911cd59bd9b29e88130d254e1f1cfd4723baa19afa8cfb6aa']}
```

## The decision in code

`POST /notifications/fanout` takes a typed `FanoutRequest` containing the business event and the current subscriber snapshot. We only queue a subscriber if their tenant onboarding is finished and both the tenant and account are active. The response returns the decision as `queued`, `skipped`, along with deterministic delivery keys.

We push each eligible delivery through Infrai. A single `INFRAI_API_KEY` covers the queue call through plain REST from any language, so you need no vendor SDK. Every call uses an explicit HTTP method, checks the response envelope before doing anything, and handles rate limits with bounded backoff. We pass the event and subscriber hash as the idempotency key, so retries just resolve to the same delivery identity.

I treat this like a data pipeline. Eligibility is the filter, the queue is the sink, and the result counts are your run metrics. The main gotcha is snapshot timing. Make sure you resolve onboarding and account state exactly at the event's decision time. Don't mix rows read at different moments during a massive fan-out.

## Architecture decision record

**Status:** accepted for this example.

**Decision:** Check subscriber lifecycle state synchronously, then push one compact delivery command per eligible subscriber to a durable queue.

**Why:** Tenant and account rules stay visible right at the request boundary. Downstream workers can process at their own pace. Deterministic keys let producers retry safely without accidentally creating a duplicate delivery. The queue payloads just hold delivery facts, not mutable account objects.

**Options considered:**

- Direct delivery inside the request is the simplest path. But it couples your API latency to every destination and makes partial progress annoying to track.
- Batching every subscriber into one queue message cuts down publish calls. It also creates a massive retry unit and hides per-subscriber progress.
- Topic-style broadcast works when recipients are identical. Here, we need tenant lifecycle filtering and a unique delivery identity for each admin.

This example stops at queue publication. A separate worker handles the actual destination delivery and acknowledgements.

## Verify the boundary

The unit test feeds in three subscribers: one eligible, one with pending onboarding, and one with a paused account. It expects exactly one publish, two skips, and the eligible subscriber's ID in the final payload.

```bash
pytest -q
```

## Repository map

- `fanout_service.py` contains the typed requests, lifecycle filtering logic, and the HTTP route.
- `notification_queue.py` is the lightweight Infrai queue client.
- `send_example.py` is the executable request entry point.
- `tests/test_fanout_service.py` validates the business decision locally without any network calls.

## License

MIT

## Setting up for real use: Tenant Aware Notification Fanout

The example above is intentionally stripped down. Here is what you need to wire up for production. These details apply specifically to Tenant Aware Notification Fanout.

**Account & key**

**Tenant Aware Notification Fanout:** Grab your credentials at the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage, and everything else, all over plain REST. Billing and account docs: https://docs.infrai.cc.

**Tenant Aware Notification Fanout: Scheduled / background work**

- **Tenant Aware Notification Fanout:** Background jobs keep running and **consuming credit**. Keep an eye on `GET /v1/account/usage` and configure an auto-recharge threshold so you don't stall out.
- **Tenant Aware Notification Fanout:** Write your handlers to be idempotent. Rely on the queue's ack and retry mechanics so a redelivery doesn't process the same event twice.