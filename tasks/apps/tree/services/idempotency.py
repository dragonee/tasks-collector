"""Exactly-once writes: a client that retries a request whose response was
lost (an offline outbox, a double tap) sends the same key again."""


def existing_event(model, user, idempotency_key):
    """The event ``user`` previously created with ``idempotency_key``, or None.

    Used for exactly-once writes: a retried request (whose first response was
    lost) re-uses the existing event instead of creating a duplicate.

    Raises ``ValueError`` for a key longer than ``Event.idempotency_key``
    allows: no event can carry it, and the insert that follows would fail.
    """
    if not idempotency_key:
        return None
    max_length = model._meta.get_field("idempotency_key").max_length
    if len(idempotency_key) > max_length:
        raise ValueError(f"idempotency_key must be at most {max_length} characters")
    return model.objects.filter(
        created_by=user, idempotency_key=idempotency_key
    ).first()
