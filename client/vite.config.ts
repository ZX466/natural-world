import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Phaser 只画 canvas 内的世界，React 只画 canvas 外的 UI（DESIGN.md §4 硬约束）。
// 两者唯一交接点是 CanvasHost 的 <div ref>（M0 客户端设计 §1，已归档）。

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 绑 127.0.0.1 而非 localhost：Windows 上 localhost 会解析到 IPv6 ::1，
    // 而 sim 的 Origin 白名单与常用访问地址都是 127.0.0.1，双栈不一致时
    // 浏览器连 ::1、白名单比对的是字符串 Origin，仍可能对不上。锁死 IPv4。
    host: '127.0.0.1',
    // 必须锁端口：sim 的 WS Origin 白名单写死 5173，Vite 若静默换到 5174
    // （5173 被占时），WS 握手会 403 → 前端无限重连、世界永远空，
    // 且无任何提示（2026-10-20 实测踩到）。宁可起不来，也不要静默换端口。
    strictPort: true,
    // 开发代理：前端 HTTP 走同源 /api → sim（http://127.0.0.1:8000），避免 CORS；
    // WS 仍由 runtime.ts 直连 ws://127.0.0.1:8000/ws（WS 不受 CORS 限制）。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
