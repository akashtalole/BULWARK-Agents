# BULWARK Dashboard

A modern React dashboard for BULWARK's Agent Gateway — the fleet's
[38-route API surface](../docs/architecture.md#api-surface-section-9) as
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

`dist/` is a static site — serve it from any static host (Cloud Storage
+ a load balancer, Firebase Hosting, Vercel, a `nginx` sidecar container
on Cloud Run, etc.). It talks to whatever Base URL is configured in the
browser at runtime, so the same build works against local, staging, or
the deployed Cloud Run URL without a rebuild.

## CORS

`src/bulwark/config.py`'s `cors_allow_origins` (env var
`BULWARK_CORS_ALLOW_ORIGINS`, comma-separated) controls which origins
the Agent Gateway accepts cross-origin requests from. Add the
dashboard's deployed origin there before pointing a deployed dashboard
at a deployed backend:

```bash
export BULWARK_CORS_ALLOW_ORIGINS="http://localhost:5173,https://your-dashboard.example.com"
```

## What's deliberately not here

- **No questionnaire list endpoint.** `api/routes.py` has no `GET
  /questionnaires` by design (see its module docstring) — the
  dashboard remembers submitted questionnaire/trace ids in
  `localStorage` per browser (`src/lib/recent.ts`) rather than
  inventing a backend endpoint that doesn't exist. Paste an id
  directly if you have one from elsewhere.
- **No auth beyond the API key.** Same model as the rest of BULWARK —
  this is a hackathon build's Agent Gateway, not a multi-tenant SaaS
  product. The X-API-Key you configure here is exactly the header every
  other caller (`curl`, `demo_cli.py`) uses.
- **No offline/optimistic writes.** Every mutation round-trips to the
  Agent Gateway and re-fetches; there is no local state that could
  drift from what the fleet actually did.

## Project layout

```
src/
  lib/
    api.ts        Typed client (BulwarkClient) over every route in api/routes.py
    types.ts       TypeScript types mirroring platform/models.py's dataclasses exactly
    settings.tsx   Base URL / API key, localStorage-backed React context
    recent.ts       Per-browser "recently submitted" id memory (questionnaires, traces)
  components/
    ui.tsx         Card, Table, Badge, Button, etc. -- the whole design system
    Layout.tsx     Sidebar nav + connection/autonomy status bar
  pages/           One file per route (Dashboard, Vendors, Findings, ...)
```
