import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: './',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/*.png', 'icons/*.svg'],
      manifest: {
        name: 'TheHand — Local Transcription',
        short_name: 'TheHand',
        description: 'Transcribe TikTok, Instagram, YouTube and audio files privately on your device using Whisper AI.',
        theme_color: '#1A1A1A',
        background_color: '#F5F0E8',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        shortcuts: [
          {
            name: 'Transcribe URL',
            short_name: 'Transcribe',
            description: 'Open TheHand and transcribe a URL',
            url: '/?action=transcribe',
            icons: [{ src: 'icons/icon-192.png', sizes: '192x192' }],
          },
        ],
        categories: ['utilities', 'productivity'],
      },
      workbox: {
        // Cache all app shell assets
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Cache Google Fonts too
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-cache',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'gfonts-webfonts-cache',
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          // Cache API health check so the UI loads even offline
          {
            urlPattern: /\/api\/health$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-health-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 1, maxAgeSeconds: 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      devOptions: {
        enabled: true,
      },
    }),
  ],
  server: {
    port: 3000,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
