# End-to-end tests

Playwright tests that drive the real PWA, Keycloak login, gateway and APIs.

```bash
make up-core                      # or make up
cd tests/e2e
npm ci && npx playwright install chromium
DEMO_USER_PASSWORD=$(grep ^DEMO_USER_PASSWORD ../../.env | cut -d= -f2) \
WEB_URL=http://localhost:3000 npx playwright test
```

| Spec | Covers |
|---|---|
| `platform.spec.ts` | Viewer dashboard and role-based navigation; analyst reproduces the OLAP acceptance figures; manifest and service worker (installability) |
| `offline-sync.spec.ts` | Go offline → enter a record → it is queued in IndexedDB → reconnect → sync → accepted; resending the same batch returns the stored result instead of a duplicate |

The acceptance figures assume the warehouse still holds exactly the 7,043 sample customers. Run them against a fresh stack.
