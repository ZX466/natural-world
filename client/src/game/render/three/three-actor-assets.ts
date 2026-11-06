import * as THREE from 'three';
import { GOD_SPRITE_KEYS } from '../actors';
import { FAUNA_SHAPES } from '../fauna-shapes';
import { loadImage } from './three-assets';
import type { ActorAssets, TextImage } from './three-actors';

function textImage(value: string, bubble: boolean): TextImage {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d')!;
  const font = '12px "Microsoft YaHei", sans-serif';
  context.font = font;
  const lines: string[] = [];
  let line = '';
  const display = value.length > 180 ? `${value.slice(0, 179)}…` : value;
  for (const char of display) {
    if (char === '\n' || (bubble && context.measureText(line + char).width > 150)) {
      lines.push(line);
      line = char === '\n' ? '' : char;
    } else line += char;
  }
  lines.push(line);
  const width =
    Math.ceil(Math.max(1, ...lines.map((text) => context.measureText(text).width))) + 12;
  const height = lines.length * 17 + 6;
  canvas.width = width * 2;
  canvas.height = height * 2;
  context.scale(2, 2);
  context.font = font;
  context.textBaseline = 'top';
  if (bubble) {
    context.fillStyle = '#171d1be6';
    context.fillRect(0, 0, width, height);
  }
  context.lineWidth = 3;
  context.strokeStyle = '#182019';
  context.fillStyle = '#fff3d5';
  lines.forEach((text, index) => {
    context.strokeText(text, 6, 3 + index * 17);
    context.fillText(text, 6, 3 + index * 17);
  });
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  return { texture, width, height };
}

export async function loadActorAssets(
  signal: AbortSignal,
): Promise<ActorAssets & { dispose(): void }> {
  const textures = new Map<string, THREE.Texture>();
  try {
    await Promise.all(
      ['protagonist', 'villager', ...GOD_SPRITE_KEYS].map(async (key) => {
        const url =
          key === 'protagonist'
            ? '/assets/actors/chenmo.png'
            : key === 'villager'
              ? '/assets/actors/villager.png'
              : `/assets/sprites/${key}.png`;
        const image = await loadImage(url, signal);
        if (signal.aborted) return;
        const texture = new THREE.Texture(image);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.magFilter = texture.minFilter = THREE.NearestFilter;
        texture.needsUpdate = true;
        textures.set(key, texture);
      }),
    );
    for (const [key, shape] of Object.entries(FAUNA_SHAPES)) {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 16;
      const context = canvas.getContext('2d')!;
      context.fillStyle = `#${shape.color.toString(16).padStart(6, '0')}`;
      shape.rows.forEach((row, y) =>
        [...row].forEach((pixel, x) => {
          if (pixel === 'x') context.fillRect(x * 2, y * 2, 2, 2);
        }),
      );
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.magFilter = texture.minFilter = THREE.NearestFilter;
      textures.set(key, texture);
    }
    return {
      texture: (key) => textures.get(key),
      text: textImage,
      dispose() {
        for (const texture of textures.values()) texture.dispose();
        textures.clear();
      },
    };
  } catch (error) {
    for (const texture of textures.values()) texture.dispose();
    throw error;
  }
}
