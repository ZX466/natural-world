import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Phaser 只画 canvas 内的世界，React 只画 canvas 外的 UI（DESIGN.md §4 硬约束）。
// 两者唯一交接点是 CanvasHost 的 <div ref>（docs/arch/m0-client.md §1）。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
});
