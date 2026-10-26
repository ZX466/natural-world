/** Deterministic pixel-center rasterizer for the terrain's filled polygons and rectangular clips. */
export function rasterContext(size: () => { width: number; height: number }) {
  type Rect = { left: number; top: number; right: number; bottom: number };
  let pixels = new Uint32Array();
  let points: [number, number][] = [];
  let rectangle: Rect | null = null;
  let clipping: Rect | null = null;
  const stack: { clipping: Rect | null; color: string }[] = [];
  const buffer = () => {
    const { width, height } = size();
    if (pixels.length !== width * height) pixels = new Uint32Array(width * height);
    return pixels;
  };
  const eachPixel = (rect: Rect, visit: (x: number, y: number) => void) => {
    const { width, height } = size();
    const left = Math.max(0, Math.floor(rect.left), clipping?.left ?? 0);
    const top = Math.max(0, Math.floor(rect.top), clipping?.top ?? 0);
    const right = Math.min(width, Math.ceil(rect.right), clipping?.right ?? width);
    const bottom = Math.min(height, Math.ceil(rect.bottom), clipping?.bottom ?? height);
    for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) visit(x, y);
  };
  const ctx = {
    fillStyle: '',
    beginPath() {
      points = [];
      rectangle = null;
    },
    moveTo(x: number, y: number) {
      points = [[x, y]];
    },
    lineTo(x: number, y: number) {
      points.push([x, y]);
    },
    closePath() {},
    rect(x: number, y: number, width: number, height: number) {
      rectangle = { left: x, top: y, right: x + width, bottom: y + height };
    },
    clip() {
      if (rectangle) clipping = rectangle;
    },
    save() {
      stack.push({ clipping, color: ctx.fillStyle });
    },
    restore() {
      const saved = stack.pop();
      if (saved) {
        clipping = saved.clipping;
        ctx.fillStyle = saved.color;
      }
    },
    clearRect(x: number, y: number, width: number, height: number) {
      const data = buffer();
      eachPixel({ left: x, top: y, right: x + width, bottom: y + height }, (px, py) => {
        data[py * size().width + px] = 0;
      });
    },
    fill() {
      if (points.length < 3) return;
      const data = buffer();
      const [r = 0, g = 0, b = 0] = (ctx.fillStyle.match(/\d+/g) ?? []).map(Number);
      const color = (0xff000000 | (r << 16) | (g << 8) | b) >>> 0;
      eachPixel(
        {
          left: Math.min(...points.map(([x]) => x)),
          top: Math.min(...points.map(([, y]) => y)),
          right: Math.max(...points.map(([x]) => x)),
          bottom: Math.max(...points.map(([, y]) => y)),
        },
        (x, y) => {
          let inside = false;
          const px = x + 0.5,
            py = y + 0.5;
          for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
            const [xi, yi] = points[i]!,
              [xj, yj] = points[j]!;
            if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi)
              inside = !inside;
          }
          if (inside) data[y * size().width + x] = color;
        },
      );
    },
    pixels: () => buffer().slice(),
  };
  return ctx;
}
