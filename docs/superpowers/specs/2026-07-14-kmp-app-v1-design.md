# Hitchwiki Maps — Kotlin Multiplatform App (v1) — Design

**Date:** 2026-07-14
**Status:** Approved design, ready for implementation planning (P0–P1 first)

## Goal

Convert the Hitchwiki Maps experience into **native Android + iOS apps** built with
**Kotlin Multiplatform (KMP) + Compose Multiplatform (CMP)**. The motivation is native
mobile apps (app-store presence, native GPS/maps, push, offline field use) — the existing
web PWA is not sufficient on mobile.

The Python backend (`hitch/`) and its generated `dist/` JSON stay the source of truth.
The mobile app is a **client** of that backend, not a replacement for it.

## Non-goals (v1)

- Desktop or web Kotlin targets (possible later; not now).
- Routing / directions (the repeatable-routes planner) — deferred to a later phase.
- Replacing the web frontend (`map.js` / `routing.js`) — the web app is untouched.
- Per-user Nostr keypairs / on-device Nostr signing (see "Write path" for why).

## Key decisions

| Decision | Choice |
|---|---|
| Kotlin target | Kotlin Multiplatform — Android + iOS (v1) |
| Primary driver | Native mobile apps (stores, GPS, push, offline) |
| UI | Compose Multiplatform (shared UI across Android + iOS) |
| Map | MapLibre native + offline OSM vector-tile packs (PMTiles) |
| v1 features | Map + spot browsing, offline map packs, ride submission + login |
| Deferred | Routing/directions, desktop/web target |
| Write path | App submits through the Python backend (single server `NSEC` stays server-side) |
| Repo | Fork this repo; add the KMP app under a top-level `mobile/` dir |
| Build order | Layer by layer (core → data → ui), with an early MapLibre spike to de-risk |

## Repo & module layout

Fork of `Hitchwiki/maps.hitchwiki.org`. The KMP app lives under a new top-level `mobile/`
directory; the Python backend and `dist/` stay where they are and evolve alongside.

```
maps.hitchwiki.org/                (fork)
├── hitch/ …                        Python backend — untouched except additive /api/*
├── dist/ …                         existing generated JSON = the READ API
└── mobile/                         NEW — KMP app (Gradle Kotlin DSL)
    ├── composeApp/                 shared UI + logic
    │   ├── commonMain / androidMain / iosMain
    │   ├── :core                   models, DTOs, kotlinx.serialization
    │   ├── :data                   Ktor client, repositories, SQLDelight cache, outbox
    │   └── :ui                     Compose Multiplatform screens + viewmodels
    ├── iosApp/                     Xcode host project (thin)
    └── androidApp/                 Android host (thin)
```

Clean layered boundaries (matching the chosen build order): **core → data → ui**, each
independently testable. Each layer depends only on the one below it.

## Tech stack

- **KMP + Compose Multiplatform** (JetBrains), Gradle Kotlin DSL.
- **Ktor client** + **kotlinx.serialization** — read `dist/` JSON, write `POST /ride`.
- **SQLDelight** — multiplatform local cache of spots/rides + the offline **outbox**.
- **MapLibre native** via `expect/actual`: `AndroidView` on Android, `UIKitView` on iOS.
  Offline via **PMTiles** vector-tile packs (single-file, local or ranged HTTP).
- **Secure token storage** — Keychain (iOS) / EncryptedSharedPreferences (Android).

## Architecture & data flow

### Read (map + spot browsing)

`dist/` is already a clean, static, CDN-friendly read API. The app consumes it directly:

- `GET /spots.json` — slim marker set (lat/lon/rating/review_count + presence flags).
- `GET /rides_index.json` — lightweight ride index for filters/search/recent list.
- `GET /rides/by-spot/<spot_id>.json` — per-spot detail, lazy-loaded on marker tap.

Spot id is derived client-side as `lat.toFixed(5)_lon.toFixed(5)` (matches
`generate_spot_id` / the per-spot filename). Responses are cached in SQLDelight; offline
reads serve the last cache plus the offline map pack.

### Write (ride submission)

**Critical constraint:** rides are signed by a **single server-side Nostr key** (`NSEC`),
not per-user keys. Ownership is tracked via Hitchwiki OAuth login + username + app-local DB.
Therefore the app **must** submit through the Python backend — it cannot (and must not) ship
the shared secret key or sign Nostr events itself. This is why "publish to Nostr directly"
is a non-goal for v1.

Flow: ride form → `POST /ride` (JSON body, `Authorization: Bearer <token>`, a
client-generated `d_tag`) → backend builds the standardized `HitchhikingRecord`, signs with
the server `NSEC`, publishes to Nostr, returns JSON. Offline submissions are persisted in a
local **outbox** and retried on reconnect.

**Idempotency reuses an existing backend mechanism:** `build_ride_d_tag` already accepts a
client-supplied bare id and, because ride events are parameterized-replaceable (kind 36820),
a retry with the same `client_d_tag` *replaces* rather than duplicates. The mobile outbox
generates that id once per pending ride and reuses it across retries. No backend change is
needed for idempotency.

## Authentication (mobile OAuth)

Today the backend uses **session-cookie** auth (Flask-Security) after a Hitchwiki OAuth2
flow, with a popup variant for the web map. No bearer token is issued. Native apps handle
cookies poorly, so the app uses a system-browser OAuth flow that ends in a **bearer token**:

1. App opens the system browser (AppAuth pattern) to the backend's OAuth start.
2. Backend runs the existing Hitchwiki OAuth2 exchange, finds/creates the local user.
3. Backend issues a **bearer token** for that user and redirects to a custom scheme,
   `hitchwiki-app://oauth-callback?token=…`.
4. App captures the redirect, stores the token in secure storage, and sends it as
   `Authorization: Bearer` on `/ride`.

**Backend additions (the only new Python; all additive, all under `/api/`):**

- `/api/auth/*` — issue and validate a bearer token after the existing OAuth callback
  (token model + verification helper). The web session flow is unchanged.
- Let `/ride` accept bearer auth + a JSON body and always answer JSON for API clients
  (the in-ride JSON path already exists as a precedent).
- Optional: `/api/regions` — list available offline map packs (see below).

Keeping everything behind `/api/` means the existing web app is untouched.

## Offline strategy

- **Map tiles:** PMTiles regional packs. A "Download region" manager stores the pack file
  locally; MapLibre reads it directly. **Largest infra unknown:** producing offline OSM
  vector tiles needs a build/host pipeline (e.g. Planetiler → PMTiles). v1 can hand-build a
  few key regions and host them (backend or CDN), listed via `/api/regions`. This is a
  dependency to resolve during the offline phase, not a blocker for earlier phases.
- **Spot data:** cached in SQLDelight; offline reads serve the last cache.
- **Outbox:** pending ride submissions persisted locally and retried on connectivity, using
  the client `d_tag` for replace-not-duplicate semantics.

## Phased milestones (layer by layer)

Each phase gets its own spec → plan → implement cycle.

- **P0 — Scaffold.** KMP+CMP project under `mobile/`; builds and runs an empty app on both
  Android and iOS; CI green. Fork/repo setup happens here.
- **P1 — Data layer.** Ktor client + kotlinx.serialization models for `dist/` JSON +
  SQLDelight repositories; unit-tested against real JSON fixtures. Includes the **MapLibre
  spike** (a throwaway proof that MapLibre renders inside CMP on both platforms) to de-risk
  the biggest unknown before the map phase.
- **P2 — Map layer.** MapLibre `expect/actual`; base map + spot markers from the repository
  on both platforms; one offline PMTiles region proven end to end.
- **P3 — UI.** Compose screens: map, spot-detail sheet, filters/search, recent-rides list.
- **P4 — Auth.** Mobile OAuth + bearer token + secure storage; backend `/api/auth/*`.
- **P5 — Write.** Ride form + outbox + offline retry; backend bearer/JSON `/ride`.
- **P6 — Offline UX.** Region download manager, storage management, cache refresh policy.
- **P7 — Polish / store prep.** Icons, permissions, (optional) push, store assets.

## Testing

- `commonMain` unit tests (kotlin.test): JSON parsing, repositories, outbox/idempotency,
  filter logic.
- Backend: pytest for the new `/api/auth` endpoints and bearer/JSON `/ride`.
- Map/UI: verified on emulator/device by the user (headless browsers/emulators are not run
  in the agent environment). Optional Android screenshot tests (Paparazzi).

## Risks & external dependencies

- **MapLibre-in-CMP on iOS** — custom `expect/actual` interop (CocoaPods/Swift), community
  support varies. Mitigated by the P1 spike.
- **Offline tile pipeline** — Planetiler/PMTiles generation + hosting is real infra work;
  scope it during P6 (or earlier as a side track).
- **iOS build** — needs a Mac + Xcode (developer is on macOS ✓).
- **Store accounts** — Apple ($99/yr) and Google Play accounts are needed only to ship, not
  to build.

## Open questions for later phases (not blocking v1 P0–P1)

- Exact PMTiles region granularity and hosting location (backend vs CDN).
- Push-notification transport (deferred; likely a later phase).
- Whether the deferred routing feature reuses `repeatable_router.py` logic via a backend
  endpoint or a Kotlin port.
