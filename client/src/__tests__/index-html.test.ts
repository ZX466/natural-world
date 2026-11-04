/**
 * client/src/__tests__/index-html.test.ts — 静态入口自检（主树 D6-①）。
 *
 * 缺陷：`index.html` 没有 `<link rel="icon">`，`client/public/` 下也没有任何图标文件，
 * 浏览器每开一次页面就发一个 `GET /favicon.ico` → 404（Vite 控制台与后端日志都有）。
 * 这里钉两件事：**声明存在**、**声明的文件真的存在**（只钉声明会造出指向空气的链接）。
 */
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const CLIENT_ROOT = fileURLToPath(new URL('../../', import.meta.url));

describe('index.html 图标声明', () => {
  const html = readFileSync(`${CLIENT_ROOT}index.html`, 'utf8');

  it('声明 <link rel="icon">（否则浏览器必然请求 /favicon.ico 并 404）', () => {
    const icon = html.match(/<link[^>]*rel="icon"[^>]*>/)?.[0] ?? '';
    expect(icon).not.toBe('');
    expect(icon).toContain('href=');
  });

  it('声明的图标文件在 public/ 下真实存在', () => {
    const icon = html.match(/<link[^>]*rel="icon"[^>]*>/)?.[0] ?? '';
    const href = icon.match(/href="([^"]+)"/)?.[1] ?? '';
    expect(href).toMatch(/^\/[^/]/); // 必须是 public 根下的站内路径，不能是 CDN/相对路径
    expect(existsSync(`${CLIENT_ROOT}public${href}`)).toBe(true);
  });
});
