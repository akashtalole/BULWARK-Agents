"""Regression test for a real Cloud Run deploy failure: DocumentStore
used to always pass `database=settings.firestore_database` to
`firestore.Client(...)`, including the default `"(default)"` value.
Passing that literal string explicitly triggers a known
google-cloud-firestore bug where the resource path ends up with it
percent-encoded, and the backend rejects it with "Invalid database id
%28default%29" -- observed directly in production logs, not
theoretical. This can't be exercised against a real Firestore backend
in this test environment, so it verifies the fix the only way possible
offline: that DocumentStore calls firestore.Client() *without* a
`database` kwarg for the default database, and *with* one only for a
genuinely non-default, named database."""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import bulwark.platform.store as store_module
from bulwark.config import settings


def _with_firestore_settings(monkeypatch, **overrides):
    monkeypatch.setattr(store_module, "settings", dataclasses.replace(settings, use_firestore=True, **overrides))


def test_default_database_omits_the_database_kwarg(monkeypatch):
    _with_firestore_settings(monkeypatch, gcp_project="test-project", firestore_database="(default)")
    fake_client_cls = MagicMock()
    monkeypatch.setattr("google.cloud.firestore.Client", fake_client_cls)

    store_module.DocumentStore("vendors")

    fake_client_cls.assert_called_once_with(project="test-project")


def test_named_database_still_passes_the_database_kwarg(monkeypatch):
    _with_firestore_settings(monkeypatch, gcp_project="test-project", firestore_database="bulwark-prod")
    fake_client_cls = MagicMock()
    monkeypatch.setattr("google.cloud.firestore.Client", fake_client_cls)

    store_module.DocumentStore("vendors")

    fake_client_cls.assert_called_once_with(project="test-project", database="bulwark-prod")
