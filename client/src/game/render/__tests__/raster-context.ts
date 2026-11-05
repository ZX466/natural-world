/** Deterministic pixel-center rasterizer for the terrain's filled polygons, rectangular clips
 * and affine image blits. */
export function rasterContext(size: () => { width: number; height: number }) {
  type Rect = { left: number; top: number; right: number; bottom: number };
  type Matrix = readonly [number, number, number, number, number, number];
  const IDENTITY: Matrix = [1, 0, 0, 1, 0, 0];
  let pixels = new Uint32Array();
  let points: [number, number][] = [];
  let rectangle: Rect | null = null;
  let clipping: Rect | null = null;
  let matrix: Matrix = IDENTITY;
  let smoothing = true;
  const stack: {
    clipping: Rect | null;
    color: string;
    matrix: Matrix;
    smoothing: boolean;
  }[] = [];
  /** Compose `next` after the current transform (standard 2×3 matrix product). */
  const compose = (base: Matrix, next: Matrix): Matrix => {
    const [a1, b1, c1, d1, e1, f1] = base;
    const [a2, b2, c2, d2, e2, f2] = next;
    return [
      a1 * a2 + c1 * b2,
      b1 * a2 + d1 * b2,
      a1 * c2 + c1 * d2,
      b1 * c2 + d1 * d2,
      a1 * e2 + c1 * f2 + e1,
      b1 * e2 + d1 * f2 + f1,
    ];
  };
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
      stack.push({ clipping, color: ctx.fillStyle, matrix, smoothing });
    },
    restore() {
      const saved = stack.pop();
      if (saved) {
        clipping = saved.clipping;
        ctx.fillStyle = saved.color;
        matrix = saved.matrix;
        smoothing = saved.smoothing;
      }
    },
    transform(a: number, b: number, c: number, d: number, e: number, f: number) {
      matrix = compose(matrix, [a, b, c, d, e, f]);
    },
    get imageSmoothingEnabled() {
      return smoothing;
    },
    set imageSmoothingEnabled(value: boolean) {
      smoothing = value;
    },
    /** Nearest-neighbour blit through the current affine.
     * `smoothing` is accepted but never interpolated: the terrain always asks for
     * nearest-neighbour, and a bilinear path here would only hide mismatches. */
    drawImage(
      source: { width: number; height: number; pixels: Uint32Array },
      sx: number,
      sy: number,
      sw: number,
      sh: number,
      dx: number,
      dy: number,
      dw: number,
      dh: number,
    ) {
      const data = buffer();
      const { width } = size();
      const [a, b, c, d, e, f] = matrix;
      const det = a * d - b * c;
      if (det === 0) return;
      // The destination rect is given in user space; iterate its image in device space.
      const corners: [number, number][] = [
        [dx, dy],
        [dx + dw, dy],
        [dx, dy + dh],
        [dx + dw, dy + dh],
      ].map(([x, y]) => [a * x + c * y + e, b * x + d * y + f]);
      eachPixel(
        {
          left: Math.min(...corners.map(([x]) => x)),
          top: Math.min(...corners.map(([, y]) => y)),
          right: Math.max(...corners.map(([x]) => x)),
          bottom: Math.max(...corners.map(([, y]) => y)),
        },
        (px, py) => {
          const tx = px + 0.5,
            ty = py + 0.5;
          // Inverse map: device point → user space.
          const ux = (d * (tx - e) - c * (ty - f)) / det;
          const uy = (-b * (tx - e) + a * (ty - f)) / det;
          if (ux < dx || uy < dy || ux >= dx + dw || uy >= dy + dh) return;
          const col = Math.floor(sx + (ux - dx) * (sw / dw));
          const row = Math.floor(sy + (uy - dy) * (sh / dh));
          if (col < 0 || row < 0 || col >= source.width || row >= source.height) return;
          data[py * width + px] = source.pixels[row * source.width + col]!;
        },
      );
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
