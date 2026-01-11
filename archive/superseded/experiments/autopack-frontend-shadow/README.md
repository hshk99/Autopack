## Legacy: `src/autopack/frontend/*` "shadow frontend"

This folder preserves a historical/experimental duplicate frontend configuration that previously lived under:

- `src/autopack/frontend/package.json`
- `src/autopack/frontend/vite.config.ts`
- `src/autopack/frontend/tsconfig.json`
- `src/autopack/frontend/tsconfig.node.json`

**Canonical frontend (active)** is the **repo root** Vite app:

- `package.json`
- `vite.config.ts`
- `tsconfig.json`
- `tsconfig.node.json`
- `src/frontend/*`

Reason for archival:
- Avoid “two truths” drift where multiple `package.json` / `vite.config.ts` surfaces compete.
- CI now enforces canonical build-surface uniqueness via `scripts/ci/check_canonical_build_surfaces.py`.

