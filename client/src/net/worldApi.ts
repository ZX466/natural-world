/**
 * client/src/net/worldApi.ts — 世界静态资产 HTTP 客户端（codex 意见 5：
 * 碰撞/地面层走 HTTP 不走 WS）。走同源 /api（vite dev 代理 → sim:8000）。
 */
import type { WorldMapResponse } from './protocol';

const WORLD_MAP_URL = '/api/world/map';

export async function fetchWorldMap(): Promise<WorldMapResponse> {
  const res = await fetch(WORLD_MAP_URL);
  if (!res.ok) {
    throw new Error(`世界地图加载失败（HTTP ${res.status}）`);
  }
  return (await res.json()) as WorldMapResponse;
}

/** base64(每格 1 字节 0/1) → Uint8Array（chunk 内行主序）。 */
export function decodeCollisionB64(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

const CHUNK_SIZE = 16;

/** chunk 载荷 → 整图碰撞网格（w*h，行主序；chunk 外未覆盖格=0 不可通行）。 */
export function assembleCollision(
  w: number,
  h: number,
  chunks: readonly { cx: number; cy: number; collision_b64: string }[],
): Uint8Array {
  const grid = new Uint8Array(w * h);
  for (const c of chunks) {
    const bits = decodeCollisionB64(c.collision_b64);
    const baseX = c.cx * CHUNK_SIZE;
    const baseY = c.cy * CHUNK_SIZE;
    for (let ly = 0; ly < CHUNK_SIZE; ly += 1) {
      for (let lx = 0; lx < CHUNK_SIZE; lx += 1) {
        const bit = bits[ly * CHUNK_SIZE + lx] ?? 0;
        const gx = baseX + lx;
        const gy = baseY + ly;
        if (gx < w && gy < h) grid[gy * w + gx] = bit;
      }
    }
  }
  return grid;
}

/** base64(u16 小端、chunk 内行主序) → Uint16Array（每格 tile id）。
 *  与 sim map_static_payload / shared/protocol.ts MapChunk.ground_b64 同一定义。 */
export function decodeGroundB64(b64: string): Uint16Array {
  const bin = atob(b64);
  const view = new DataView(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i += 1) view.setUint8(i, bin.charCodeAt(i));
  const out = new Uint16Array(bin.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = view.getUint16(i * 2, true); // LE
  return out;
}

/** chunk 载荷 → 整图地面 id 网格（w*h 行主序；未覆盖格=0）。 */
export function assembleGround(
  w: number,
  h: number,
  chunks: readonly { cx: number; cy: number; ground_b64: string }[],
): Uint16Array {
  const grid = new Uint16Array(w * h);
  for (const c of chunks) {
    const ids = decodeGroundB64(c.ground_b64);
    const baseX = c.cx * CHUNK_SIZE;
    const baseY = c.cy * CHUNK_SIZE;
    for (let ly = 0; ly < CHUNK_SIZE; ly += 1) {
      for (let lx = 0; lx < CHUNK_SIZE; lx += 1) {
        const id = ids[ly * CHUNK_SIZE + lx] ?? 0;
        const gx = baseX + lx;
        const gy = baseY + ly;
        if (gx < w && gy < h) grid[gy * w + gx] = id;
      }
    }
  }
  return grid;
}
