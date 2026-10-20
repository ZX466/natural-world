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
