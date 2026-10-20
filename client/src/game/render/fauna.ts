import type Phaser from 'phaser';

/** 观察投影的三种动物，使用本地像素剪影；无需外部素材或额外协议字段。 */
export function createFaunaTextures(scene: Phaser.Scene): void {
  const shapes: Record<string, { color: number; rows: string[] }> = {
    fauna_wolf: {
      color: 0x949b9b,
      rows: [
        '....x.x.',
        '....xxx.',
        '..xxxxx.',
        'xxxxxxx.',
        '..xxxxx.',
        '..x..x..',
        '..x..x..',
        '........',
      ],
    },
    fauna_deer: {
      color: 0xb98a53,
      rows: [
        '...x.x..',
        '....x...',
        '....xx..',
        '.xxxxxx.',
        '.xxxxxx.',
        '..x..x..',
        '..x..x..',
        '........',
      ],
    },
    fauna_bird: {
      color: 0x496d88,
      rows: [
        '........',
        '....xx..',
        '...xxxx.',
        '..xxxxx.',
        '.xxxxxx.',
        '....xx..',
        '...x.x..',
        '........',
      ],
    },
    // 创世三只（GENESIS_ENTITIES 的 cat_grey / dog_black / raven）。
    // 2026-10-20 修：此前后端把这三只分到 GOD 村民池 → 猫狗鸦画成人形村民；
    // 现后端 ANIMAL_SPRITES 直接给这三个 key，前端必须有同名贴图。
    fauna_cat: {
      color: 0x8b8b7e,
      rows: [
        '........',
        '..x..x..',
        '.xxxxxx.',
        '.xxxxxx.',
        '.xxxxxx.',
        '.x.xx.x.',
        '........',
        '........',
      ],
    },
    fauna_dog: {
      color: 0x4a4038,
      rows: [
        '........',
        '.x....x.',
        '.xxxxxx.',
        '.xxxxxx.',
        '.xxxxxx.',
        '..x..x..',
        '..x..x..',
        '........',
      ],
    },
    fauna_raven: {
      color: 0x2f3440,
      rows: [
        '........',
        '...xx...',
        '..xxxx..',
        '.xxxxxx.',
        '..xxxx..',
        '...xx...',
        '..x..x..',
        '........',
      ],
    },
  };
  for (const [key, shape] of Object.entries(shapes)) {
    if (scene.textures.exists(key)) continue;
    const graphics = scene.add.graphics();
    graphics.fillStyle(shape.color);
    shape.rows.forEach((row, y) =>
      [...row].forEach((pixel, x) => {
        if (pixel === 'x') graphics.fillRect(x * 2, y * 2, 2, 2);
      }),
    );
    graphics.generateTexture(key, 16, 16);
    graphics.destroy();
  }
}
