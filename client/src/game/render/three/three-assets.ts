import { createHeightLookup, type HeightLookup } from '../iso';
import { createColorSampler, FALLBACK_COLOR } from '../tile-color';

export function loadImage(url: string, signal: AbortSignal): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const abort = () => {
      image.src = '';
      reject(new DOMException('Aborted', 'AbortError'));
    };
    if (signal.aborted) {
      abort();
      return;
    }
    signal.addEventListener('abort', abort, { once: true });
    image.onload = () => {
      signal.removeEventListener('abort', abort);
      resolve(image);
    };
    image.onerror = () => {
      signal.removeEventListener('abort', abort);
      reject(new Error('World image unavailable'));
    };
    image.src = url;
  });
}

export async function loadTerrainAssets(signal: AbortSignal): Promise<{
  heightOf: HeightLookup;
  sampleColor: (gid: number) => number;
}> {
  const [heightData, image] = await Promise.all([
    fetch('/assets/tilesets/linhe-height.json', { signal }).then((response) => {
      if (!response.ok) throw new Error('World height unavailable');
      return response.json();
    }),
    loadImage('/assets/tilesets/god-town-16.png', signal),
  ]);
  const canvas = document.createElement('canvas');
  canvas.width = image.width;
  canvas.height = image.height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context)
    return { heightOf: createHeightLookup(heightData), sampleColor: () => FALLBACK_COLOR };
  context.drawImage(image, 0, 0);
  return {
    heightOf: createHeightLookup(heightData),
    sampleColor: createColorSampler(
      context.getImageData(0, 0, image.width, image.height).data,
      image.width,
      image.height,
    ),
  };
}
