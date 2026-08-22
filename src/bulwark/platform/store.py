"""Document-store abstraction: Firestore-backed when GOOGLE_CLOUD_PROJECT
is set, an in-process dict otherwise. Every collection in the data model
(platform/models.py) is a DocumentStore keyed by its own id, with
tenant_id/vendor_id carried as fields -- a flattening of the spec's true
nested subcollection paths (/tenants/{t}/vendors/{v}/artifacts/{a}) that
keeps queries simple in both backends. Composite indexes for the
production Firestore layout are listed in docs/architecture.md.
"""

from __future__ import annotations

import copy
import threading
from typing import Any, Callable

from bulwark.config import settings


class DocumentStore:
    def __init__(self, collection: str) -> None:
        self.collection_name = collection
        self._client = None
        if settings.use_firestore:
            from google.cloud import firestore  # optional dep, imported lazily

            self._client = firestore.Client(
                project=settings.gcp_project, database=settings.firestore_database
            )
        else:
            self._memory: dict[str, dict[str, Any]] = {}
            self._lock = threading.Lock()

    @property
    def is_firestore(self) -> bool:
        return self._client is not None

    def set(self, doc_id: str, data: dict[str, Any]) -> None:
        if self.is_firestore:
            self._client.collection(self.collection_name).document(doc_id).set(data)
            return
        with self._lock:
            self._memory[doc_id] = copy.deepcopy(data)

    def update(self, doc_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        if self.is_firestore:
            doc_ref = self._client.collection(self.collection_name).document(doc_id)
            doc_ref.set(patch, merge=True)
            snapshot = doc_ref.get()
            return snapshot.to_dict() or {}
        with self._lock:
            current = self._memory.setdefault(doc_id, {})
            current.update(copy.deepcopy(patch))
            return copy.deepcopy(current)

    def get(self, doc_id: str) -> dict[str, Any] | None:
        if self.is_firestore:
            snapshot = self._client.collection(self.collection_name).document(doc_id).get()
            return snapshot.to_dict() if snapshot.exists else None
        with self._lock:
            doc = self._memory.get(doc_id)
            return copy.deepcopy(doc) if doc is not None else None

    def list(self, where: Callable[[dict[str, Any]], bool] | None = None) -> list[dict[str, Any]]:
        if self.is_firestore:
            docs = [doc.to_dict() for doc in self._client.collection(self.collection_name).stream()]
        else:
            with self._lock:
                docs = [copy.deepcopy(doc) for doc in self._memory.values()]
        return [d for d in docs if where(d)] if where else docs

    def delete(self, doc_id: str) -> None:
        if self.is_firestore:
            self._client.collection(self.collection_name).document(doc_id).delete()
            return
        with self._lock:
            self._memory.pop(doc_id, None)

    def append_to_list_field(self, doc_id: str, field: str, item: dict[str, Any]) -> dict[str, Any]:
        if self.is_firestore:
            from google.cloud import firestore

            doc_ref = self._client.collection(self.collection_name).document(doc_id)
            if not doc_ref.get().exists:
                doc_ref.set({field: []})
            doc_ref.update({field: firestore.ArrayUnion([item])})
            return doc_ref.get().to_dict() or {}
        with self._lock:
            current = self._memory.setdefault(doc_id, {})
            current.setdefault(field, [])
            current[field].append(copy.deepcopy(item))
            return copy.deepcopy(current)
