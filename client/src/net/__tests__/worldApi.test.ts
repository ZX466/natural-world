/**
 * client/src/net/__tests__/worldApi.test.ts — 碰撞层组装纯函数回归钉。
 *
 * 背景（M7 修复二）：真实模式地图从未装入镜像（ws.ts M0 占位注释、无 HTTP
 * 加载）→ WorldScene handlePointer 的 map=null 守卫吞掉一切点击。
 * assembleCollision 是本次新增的地图数据组装核心，此处锁死其行为。
 */
import { describe, expect, it } from 'vitest';
import { assembleCollision, decodeCollisionB64 } from '../worldApi';

describe('decodeCollisionB64', () => {
  it('解码 0/1 位序列', () => {
    // bytes [1,0,1,1] → base64 "AQABAQ=="
    expect(Array.from(decodeCollisionB64('AQABAQ=='))).toEqual([1, 0, 1, 1]);
  });
  it('空输入 → 空数组', () => {
    expect(decodeCollisionB64('').length).toBe(0);
  });
});

describe('assembleCollision', () => {
  it('单 chunk 全 1 → 16x16 全可通行，图内其余为 0', () => {
    const full = Array(256).fill(1);
    // 256 字节全 1 的 base64
    const b64 = btoa(String.fromCharCode(...full));
    const grid = assembleCollision(32, 32, [{ cx: 0, cy: 0, collision_b64: b64 }]);
    expect(grid[0]).toBe(1);
    expect(grid[15 * 32 + 15]).toBe(1);
    expect(grid[15 * 32 + 16]).toBe(0); // chunk 外
    expect(grid[16 * 32]).toBe(0);
  });

  it('多 chunk 各归其位（cx,cy 偏移正确）', () => {
    // chunk(0,0) 与 chunk(1,1) 各 256B 全 1
    const full = btoa(String.fromCharCode(...Array(256).fill(1)));
    const grid2 = assembleCollision(32, 32, [
      { cx: 0, cy: 0, collision_b64: full },
      { cx: 1, cy: 1, collision_b64: full },
    ]);
    expect(grid2[0]).toBe(1);
    expect(grid2[16 * 32 + 16]).toBe(1); // chunk(1,1) 首格
    expect(grid2[16 * 32 + 15]).toBe(0); // chunk(1,1) 左邻
  });

  it('越界 chunk 数据安全截断（w/h 非 16 倍数场景容错）', () => {
    const full = btoa(String.fromCharCode(...Array(256).fill(1)));
    // 18x18 图：chunk(1,0) 越界部分被裁
    const grid = assembleCollision(18, 18, [{ cx: 1, cy: 0, collision_b64: full }]);
    expect(grid[0 * 18 + 16]).toBe(1);
    expect(grid.length).toBe(18 * 18);
  });
});
