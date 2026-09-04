/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Control-plane base URL. Set at build time; defaults to localhost:8001. */
  readonly VITE_CONTROL_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
