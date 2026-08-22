from bulwark.platform.event_bus import EventBus, Envelope, make_idempotency_key


async def test_publish_dispatches_to_subscribers():
    bus = EventBus()
    received = []
    bus.subscribe("topic.a", lambda topic, env: received.append((topic, env.payload)))
    await bus.publish("topic.a", Envelope(payload={"x": 1}, idempotency_key=make_idempotency_key("a")))
    assert received == [("topic.a", {"x": 1})]


async def test_publish_supports_async_handlers():
    bus = EventBus()
    received = []

    async def handler(topic, env):
        received.append(topic)

    bus.subscribe("topic.b", handler)
    await bus.publish("topic.b", Envelope(payload={}, idempotency_key=make_idempotency_key("b")))
    assert received == ["topic.b"]


async def test_publish_with_no_subscribers_is_a_noop():
    bus = EventBus()
    await bus.publish("nobody.listens", Envelope(payload={}, idempotency_key=make_idempotency_key("c")))  # must not raise


async def test_duplicate_idempotency_key_is_skipped():
    bus = EventBus()
    received = []
    bus.subscribe("topic.d", lambda topic, env: received.append(env.event_id))
    key = make_idempotency_key("dup")
    await bus.publish("topic.d", Envelope(payload={}, idempotency_key=key))
    await bus.publish("topic.d", Envelope(payload={}, idempotency_key=key))
    assert len(received) == 1


async def test_failing_handler_routes_to_dlq_without_crashing_publisher():
    bus = EventBus()
    calls = []

    def good(topic, env):
        calls.append("good")

    def bad(topic, env):
        raise ValueError("boom")

    bus.subscribe("topic.e", good)
    bus.subscribe("topic.e", bad)
    await bus.publish("topic.e", Envelope(payload={}, idempotency_key=make_idempotency_key("e")))

    assert calls == ["good"]
    dlq = bus.dlq_entries("topic.e")
    assert len(dlq) == 1
    assert "boom" in dlq[0]["failure_chain"]


async def test_dlq_entries_can_be_filtered_by_topic():
    bus = EventBus()

    def bad(topic, env):
        raise RuntimeError("x")

    bus.subscribe("topic.f", bad)
    bus.subscribe("topic.g", bad)
    await bus.publish("topic.f", Envelope(payload={}, idempotency_key=make_idempotency_key("f")))
    await bus.publish("topic.g", Envelope(payload={}, idempotency_key=make_idempotency_key("g")))

    assert len(bus.dlq_entries("topic.f")) == 1
    assert len(bus.dlq_entries()) == 2
