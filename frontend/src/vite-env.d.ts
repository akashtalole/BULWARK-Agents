/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Baked in at build time by deploy/deploy_frontend.sh from the deployed
   * Cloud Run URL, so a judge opening the dashboard doesn't need to type
   * a Base URL in before logging in. Falls back to localhost for local dev. */
  readonly VITE_DEFAULT_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
