"""Tests DocumentStore's two firestore.Client() call shapes: no
`database` kwarg for the special "(default)" database (discouraged, see
platform/store.py's module docstring -- this does NOT itself fix the
production crash that motivated it, since the client resolves an
omitted kwarg and an explicit "(default)" identically; config.py's
named-database default is the actual fix), and an explicit `database`
kwarg for a genuinely named one, which is the recommended, working
path. Can't be exercised against a real Firestore backend in this test
environment, so this checks exactly what firestore.Client() gets
called with in each case instead."""

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


def test_list_with_ids_pairs_each_doc_with_its_key():
    store = store_module.DocumentStore("list_with_ids_test")
    store.set("doc_a", {"n": 1})
    store.set("doc_b", {"n": 2})

    pairs = dict(store.list_with_ids())

    assert pairs == {"doc_a": {"n": 1}, "doc_b": {"n": 2}}


def test_list_with_ids_applies_where_filter():
    store = store_module.DocumentStore("list_with_ids_filter_test")
    store.set("keep", {"n": 1})
    store.set("drop", {"n": 2})

    pairs = dict(store.list_with_ids(where=lambda d: d["n"] == 1))

    assert pairs == {"keep": {"n": 1}}
