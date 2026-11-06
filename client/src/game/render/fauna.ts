import type Phaser from 'phaser';
import { FAUNA_SHAPES } from './fauna-shapes';

/** 观察投影的三种动物，使用本地像素剪影；无需外部素材或额外协议字段。 */
export function createFaunaTextures(scene: Phaser.Scene): void {
  for (const [key, shape] of Object.entries(FAUNA_SHAPES)) {
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
