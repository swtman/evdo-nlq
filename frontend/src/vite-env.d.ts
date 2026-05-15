/**
 * Vite environment variable type declarations.
 *
 * Vite replaces `import.meta.env.VITE_*` with literal values at build time.
 * Declaring them here tells TypeScript what variables exist so you get
 * autocomplete and type-checking when you write `import.meta.env.VITE_*`.
 *
 * How to add a new env var:
 *   1. Add `readonly VITE_MY_VAR?: string` to ImportMetaEnv below.
 *   2. Set it in your shell before running `pnpm dev`:
 *        $env:VITE_MY_VAR='value'; pnpm dev   (PowerShell)
 *   3. Use it in code: import.meta.env.VITE_MY_VAR
 *
 * Note: only variables prefixed with VITE_ are exposed to the browser.
 * Never put secrets in VITE_ variables — they are visible in the browser bundle.
 */

/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * When set to '1', api/client.ts delegates to api/mock.ts instead of making
   * real network requests. Useful for UI development without a backend.
   * Example: $env:VITE_USE_MOCK_API='1'; pnpm dev
   */
  readonly VITE_USE_MOCK_API?: string

  /**
   * Short git SHA injected at build time to show in the UI version chip.
   * Set via vite.config.ts define block or your CI pipeline.
   */
  readonly VITE_GIT_SHA?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
