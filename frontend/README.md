# BULWARK Dashboard

A modern React dashboard for BULWARK's Agent Gateway — the fleet's
[40-route API surface](../docs/architecture.md#api-surface-section-9) as
a real UI instead of `curl`/`jq`. Fleet health and the kill switch,
per-vendor findings/contract-terms/subprocessors/assessment-history
(with a live risk-trend chart)/crosswalk/offboarding, the reasoning
chain behind every finding, questionnaires, concentration risks, the
executive digest, trace timelines, and the DLQ.

Everything here calls the same Agent Gateway the rest of the fleet uses
— this is a client, not a second backend. No data is duplicated or
cached beyond React Query's in-memory cache.

## Stack

Vite + React 19 + TypeScript, Tailwind CSS v4, React Router, TanStack
Query, Recharts, lucide-react. No component library beyond a small
hand-rolled set in `src/components/ui.tsx` — kept deliberately light so
the whole thing builds and ships without a design-system dependency.

## Running it

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The backend needs to allow this origin — see "CORS" below. By default
`BULWARK_CORS_ALLOW_ORIGINS` already includes
`http://localhost:5173`, so a local backend + local dashboard works with
zero configuration.

On first load, open **Connection** in the sidebar and confirm the
**Base URL** (`http://localhost:8080` by default) and **X-API-Key**
(`demo-key` by default) match your running BULWARK instance. Both are
stored in `localStorage`, per browser, never sent anywhere but the
Agent Gateway itself.

## Building for production

```bash
npm run build     # outputs to dist/
npm run preview   # serve the production build locally
```

`dist/` is a static site — serve it from any static host. It talks to
whatever Base URL is configured, so the same build works against local,
staging, or a deployed backend without a rebuild.

**Default: fullstack on Cloud Run, one URL.** `../Dockerfile` is a
multi-stage build: it runs this exact `npm run build` in its own stage,
then copies `dist/` into the same image as the backend. `main.py` mounts
it at `/`, so `../deploy/deploy_cloud_run.sh` alone deploys both the API
and this dashboard, same-origin, on the one Cloud Run URL -- no
`BULWARK_CORS_ALLOW_ORIGINS` configuration needed for the dashboard's
own calls, and no Base URL to set: it defaults to `""` (same-origin) in
this build, not `localhost:8080` (see `lib/settings.tsx`).

**Alternative: hosted separately.** `../deploy/deploy_frontend.sh`
builds and deploys this same code to a public Cloud Storage bucket
instead (`PROJECT_ID=my-project ./deploy/deploy_frontend.sh` from the
repo root) -- useful if you want the dashboard on its own URL/cadence,
decoupled from the backend's deploys. Since that IS cross-origin from
the backend, its output prints the exact `BULWARK_CORS_ALLOW_ORIGINS`
value the backend needs to allow it, and it bakes the backend's Cloud
Run URL in as the Base URL at build time (`VITE_DEFAULT_BASE_URL`).

## Login page

Optional. If the backend has `BULWARK_UI_PASSWORD` set, the dashboard
opens on a login page instead of the fleet view. Enter that one password
and `POST /auth/login` trades it for the real API key -- stored the same
way a manually-entered key would be (`localStorage`, this browser only),
so every request after that still goes through the same `X-API-Key`
check every other route enforces. This exists so a judge (or you) gets
one password to type in rather than the literal API key; it is not a
second, independent auth system -- `BULWARK_API_KEYS` server-side is
still the actual gate. If `BULWARK_UI_PASSWORD` is unset, `GET
/auth/config` reports `login_required: false` and the login page is
skipped entirely -- local dev needs no configuration, same as before
this existed.

`deploy/deploy_frontend.sh` bakes the deployed Cloud Run URL in as the
default Base URL at build time (`VITE_DEFAULT_BASE_URL`), so a judge
opening the login page doesn't need to configure Connection settings
first -- just the password.

## CORS

`src/bulwark/config.py`'s `cors_allow_origins` (env var
`BULWARK_CORS_ALLOW_ORIGINS`, comma-separated) controls which origins
the Agent Gateway accepts cross-origin requests from. Add the
dashboard's deployed origin there before pointing a deployed dashboard
at a deployed backend:

```bash
export BULWARK_CORS_ALLOW_ORIGINS="http://localhost:5173,https://your-dashboard.example.com"
```

## Theme, search/filter/sort, and questionnaire editing

**Light/dark theme** (the sun/moon toggle in the header) needs zero
per-component styling — every page already uses Tailwind's standard
`zinc`/`indigo`/`emerald`/`rose`/`amber`/`blue` classes, which Tailwind
v4 compiles to `var(--color-*)` references under the hood. `index.css`
overrides those same variables under `[data-theme="light"]` (a mirror of
the dark-mode zinc ramp, plus darkened accent-color text stops for
legibility on a light background) — see its comment for the reasoning.
`lib/theme.tsx` is the `ThemeProvider`/`useTheme()` pair that sets the
attribute and persists the choice; `index.html` has a small inline
script that applies it before React mounts, so there's no flash of the
wrong theme on load.

**Search/filter/sort** on the Vendors, Findings, and Questionnaires
tables is client-side over already-fetched data (`lib/sort.ts`'s
`useSort()` hook, reused across all three) — click a column header to
sort by it, click again to reverse.

**Editing a questionnaire** (rename the buyer, add/remove questions) is
on its detail page, via `PATCH /questionnaires/{id}`. It's a manual
edit, not a re-run of the Attest loop: a question whose text didn't
change keeps its existing answer untouched, a genuinely new question
gets a blank `needs_human` answer (nothing here calls the LLM), and a
dropped question's answer is deleted with it. The Questionnaires list
page itself now comes from a real `GET /questionnaires` (added
alongside this), not the localStorage-remembered-ids workaround the
next bullet used to describe.

## What's deliberately not here

- **No multi-user auth, just an optional single password.** Same model
  as the rest of BULWARK — this is a hackathon build's Agent Gateway,
  not a multi-tenant SaaS product. The X-API-Key every request carries
  is exactly the header every other caller (`curl`, `demo_cli.py`)
  uses; the login page (see above) is a friendlier way to obtain that
  one key, not a second user system. See
  [`docs/firebase_auth_feasibility.md`](../docs/firebase_auth_feasibility.md)
  for what real per-user login (Firebase Auth) would actually take.
- **No offline/optimistic writes.** Every mutation round-trips to the
  Agent Gateway and re-fetches; there is no local state that could
  drift from what the fleet actually did.

## Project layout

```
src/
  lib/
    api.ts        Typed client (BulwarkClient) over every route in api/routes.py
    types.ts       TypeScript types mirroring platform/models.py's dataclasses exactly
    settings.tsx   Base URL / API key / login state, localStorage-backed React context
    recent.ts       Per-browser "recently submitted" id memory (questionnaires, traces)
  components/
    ui.tsx         Card, Table, Badge, Button, etc. -- the whole design system
    Layout.tsx     Sidebar nav + connection/autonomy status bar + log out
    RequireAuth.tsx Route guard -- redirects to /login when BULWARK_UI_PASSWORD is set
  pages/           One file per route (Dashboard, Vendors, Findings, ..., Login)
```
