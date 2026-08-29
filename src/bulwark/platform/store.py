"""Document-store abstraction: Firestore-backed when GOOGLE_CLOUD_PROJECT
is set, an in-process dict otherwise. Every collection in the data model
(platform/models.py) is a DocumentStore keyed by its own id, with
tenant_id/vendor_id carried as fields -- a flattening of the spec's true
nested subcollection paths (/tenants/{t}/vendors/{v}/artifacts/{a}) that
keeps queries simple in both backends. Composite indexes for the
production Firestore layout are listed in docs/architecture.md.

On the special "(default)" Firestore database (as opposed to a named
one): confirmed on a real Cloud Run deploy that this app crashes on
every startup with google.api_core.exceptions.InvalidArgument: 400
Invalid database id %28default%29 -- "(default)" percent-encoded --
whenever the client actually talks to Firestore, e.g. `set()` below.
Root-caused by reading the installed client's own source
(google.cloud.firestore_v1.base_client): `database = database or
DEFAULT_DATABASE` means passing `database="(default)"` explicitly and
omitting the kwarg both resolve to the exact same literal string, so
there is no code-level way to route around this from the caller's side
-- an earlier fix here that tried exactly that (omit the kwarg for the
default case) made no actual difference. The client then sends that
literal string, parentheses included, unencoded in a gRPC metadata
header; something downstream -- the transport layer or Cloud Run's own
networking, not anything this app's code touches -- percent-encodes it,
and Firestore rejects the mangled result. The actual fix is upstream of
this file: config.py's `firestore_database` defaults to a named
database ("bulwark", created by deploy/setup_gcp.sh) that has no
parentheses for anything in that chain to mangle. This file still
special-cases the literal "(default)" string below for anyone who sets
FIRESTORE_DATABASE to it anyway, but doing so is not recommended.
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

            if settings.firestore_database == "(default)":
                # See this module's docstring: omitting the kwarg here is
                # NOT a fix for the "(default)" database's percent-encoding
                # crash (the client resolves both forms identically) --
                # config.py's default of a named database is the actual
                # fix. This branch only exists so a caller who explicitly
                # opts into "(default)" still gets the semantically correct
                # call rather than a confusing one.
                self._client = firestore.Client(project=settings.gcp_project)
            else:
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

    def list_with_ids(
        self, where: Callable[[dict[str, Any]], bool] | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        """Same as `list`, but pairs each document with its id -- for
        collections (like the audit log) keyed by an id that isn't also
        carried as a field on the document itself."""
        if self.is_firestore:
            pairs = [(doc.id, doc.to_dict()) for doc in self._client.collection(self.collection_name).stream()]
        else:
            with self._lock:
                pairs = [(doc_id, copy.deepcopy(doc)) for doc_id, doc in self._memory.items()]
        return [(i, d) for i, d in pairs if where(d)] if where else pairs

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
