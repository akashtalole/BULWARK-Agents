# Multi-user login with Firebase Auth: feasibility

Scoped as a writeup, not an implementation -- this is what it would
actually take, so the decision to build it (or not) is an informed one.

## What Firebase Auth actually gives you

Identity, not authorization. It answers "who is this person" (email/password,
Google/GitHub sign-in, magic links, etc.) and hands you a verified ID token.
It does **not** decide what that person is allowed to do -- that's still
this app's job. Anyone reaching for Firebase Auth expecting built-in
per-user permissions will be surprised: that layer has to be built
separately, on top.

`bulwark-agents`/this repo is already a Firebase-eligible project (Firebase
projects *are* GCP projects) -- no new project needed, just enabling
Firebase Auth on the existing one and turning on whichever sign-in
providers you want in the Firebase console.

## What it would take, end to end

**Frontend:**
- `firebase` npm package, initialized with the project's public web config
  (the `apiKey` etc. here are not secret -- safe to ship in the bundle,
  same as any OAuth client id).
- A real sign-in screen (Google popup sign-in is the least code; Firebase's
  prebuilt `FirebaseUI` covers email/password + several OAuth providers if
  you want more than one option).
- On sign-in, `user.getIdToken()` gives a short-lived JWT. Every API call
  needs to carry it (as a header, alongside or instead of `X-API-Key`).
- Token refresh, sign-out, and the "not signed in yet" loading state --
  `frontend/src/lib/theme.tsx` and `settings.tsx`'s context-provider pattern
  is a reasonable template for the equivalent `AuthProvider`.

**Backend:**
- `firebase-admin` (Python) added to `requirements.txt`.
- A new dependency, e.g. `verify_firebase_token(authorization_header)`,
  calling `firebase_admin.auth.verify_id_token(token)` -- this replaces or
  sits next to `platform/auth.py`'s `authenticate()` (the plain API-key
  check every route already runs through `_authorize()` in `api/routes.py`).
- A decision on an allow-list: does anyone with a Google account get in, or
  only specific judge/team emails? Firebase supports both (open sign-up, or
  checking the verified token's `email` claim against a server-side list --
  there's no built-in "invite-only" primitive, that check is on you).

## The part that actually matters: what changes for the user model

This app currently has **no per-user data model at all**. Every vendor,
finding, and questionnaire lives under one shared tenant (`acme-eu`,
`config.py`'s `default_tenant`), and `BULWARK_API_KEYS` is a single
all-or-nothing credential -- whoever has it can do everything the API
allows. That's a deliberate simplification for a hackathon build, not an
oversight, but it means "add Firebase Auth" branches into two very
different amounts of work depending on what you actually want:

**Option A -- attribution only (recommended scope, ~1-2 hours of work).**
Firebase Auth sits *alongside* the existing `BULWARK_UI_PASSWORD` gate,
not replacing it: a signed-in user's verified email gets attached to
actions they take (findings decisions, questionnaire edits) for the audit
trail, but *access* still works exactly as today -- the password gate
decides who gets in, Firebase Auth just answers "which judge is this."
Low risk: nothing about the existing `_authorize()`/rate-limiting/
BULWARK_API_KEYS model has to change, it's a strictly additive layer.

**Option B -- Firebase Auth replaces the password gate, with real
per-user permissions.** Every route's `_authorize()` needs to accept a
verified Firebase token as well as (or instead of) an API key; something
needs to decide what a given signed-in user can actually do (view-only
vs. can-decide-findings vs. admin, say) -- which means a real
authorization model and a Firestore-backed users/roles collection that
doesn't exist today; every test in `tests/test_api.py` that currently
authenticates via `X-API-Key: demo-key` needs an equivalent
token-verification path; and the frontend needs to gate UI elements
(the Findings "Record a decision" form, the new Questionnaire edit form,
the kill switch) by the signed-in user's role, not just whether they're
logged in at all. This is a genuine architecture change, not an add-on --
comparable in scope to the login-gate work already done, but with an
actual authorization model behind it instead of one shared password.

## Recommendation

Given the actual ask ("only judges will access it and me using same"),
`BULWARK_UI_PASSWORD` already solves the *access* problem. The realistic
incremental value of Firebase Auth here is knowing *which* judge did
something, not restricting what any of them can do -- so Option A is the
proportionate scope if this gets built. Option B is a legitimate thing to
want, but it's a different, larger project: a real multi-tenant
authorization model, not a login screen.
