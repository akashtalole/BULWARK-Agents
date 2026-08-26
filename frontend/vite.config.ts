import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Relative asset paths, not root-absolute ones -- this app is deployed to
  // a Cloud Storage bucket path (deploy/deploy_frontend.sh), not domain
  // root, so "/assets/x.js" would resolve to the bucket host's root and
  // 404. "./assets/x.js" resolves relative to index.html wherever it's
  // served from.
  base: './',
  server: {
    port: 5173,
  },
})
