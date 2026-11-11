"""Creates that a client may retry: one sent again with the same
``idempotency_key`` (its answer was lost, it was queued offline) gives back
what the first one made and makes nothing more."""

from django.db import IntegrityError

from rest_framework import status
from rest_framework.response import Response

from .services.idempotency import existing_event


class IdempotentCreateMixin:
    """For a viewset whose create makes one event, ``idempotent_model``, and
    whose serializer takes an ``idempotency_key``: the first create with a
    key answers 201, every later one 200 with what the first one made."""

    idempotent_model = None

    def made_with(self, key):
        """What a create with ``key`` made, as this viewset gives it back."""
        return existing_event(self.idempotent_model, self.request.user, key)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data.get("idempotency_key")

        existing = self.made_with(key)
        if existing is None:
            try:
                self.perform_create(serializer)
            except IntegrityError:
                # The same key, sent twice at once: the other one made it.
                existing = self.made_with(key)
                if existing is None:
                    raise
        if existing is not None:
            return Response(self.get_serializer(existing).data)

        return Response(serializer.data, status=status.HTTP_201_CREATED)
