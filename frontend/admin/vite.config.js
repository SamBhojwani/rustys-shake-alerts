import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // amazon-cognito-identity-js references a Node-style `global`. Vite
  // does not provide one out of the box, so it must be aliased to
  // `window` at build time or the library throws at runtime.
  define: {
    global: 'window',
  },
})
