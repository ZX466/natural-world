/** Camera gestures and world intentions share input, never selection semantics. */
import type { MovePoint } from '../../movement';
import type { VoxelRequestMessage } from '../../../net/protocol';

export interface WorldInputPorts {
  move(point: MovePoint): boolean;
  voxel(action: VoxelRequestMessage['action'], point: MovePoint): void;
  rotate(dx: number, dy: number): void;
  zoom(delta: number): void;
  pickEdit(x: number, y: number): MovePoint | null;
  pickGround(x: number, y: number): MovePoint | null;
  blocked(point: MovePoint): boolean;
  hero(): MovePoint | null;
  step(point: MovePoint): boolean;
  enabled(): boolean;
  typing(): boolean;
  epoch(): string;
  revision(): number;
  azimuth(): number;
  error(message: string): void;
}

export function movementDirection(keys: ReadonlySet<string>, azimuth: number): MovePoint {
  const forward =
    Number(keys.has('KeyW') || keys.has('ArrowUp')) -
    Number(keys.has('KeyS') || keys.has('ArrowDown'));
  const right =
    Number(keys.has('KeyD') || keys.has('ArrowRight')) -
    Number(keys.has('KeyA') || keys.has('ArrowLeft'));
  const yaw = (azimuth * Math.PI) / 180;
  const x = -forward * Math.sin(yaw) + right * Math.cos(yaw);
  const y = -forward * Math.cos(yaw) - right * Math.sin(yaw);
  const scale = Math.max(1, Math.abs(x), Math.abs(y));
  return { x: Math.round(x / scale) || 0, y: Math.round(y / scale) || 0 };
}

const moveKeys = new Set([
  'KeyW',
  'KeyA',
  'KeyS',
  'KeyD',
  'ArrowUp',
  'ArrowLeft',
  'ArrowDown',
  'ArrowRight',
]);

export function createWorldInput(
  canvas: HTMLCanvasElement,
  ports: WorldInputPorts,
  keyboard: EventTarget = window,
) {
  const abort = new AbortController();
  const keys = new Set<string>();
  let epoch = ports.epoch();
  let timer: ReturnType<typeof setTimeout> | null = null;
  let goal: MovePoint | null = null;
  let pointer: { x: number; y: number } | null = null;
  let lastMove = '';
  let pendingDrag: MovePoint | null = null;
  let lastDragAt = -Infinity;
  let keyIntent = '';
  let press: {
    id: number;
    button: number;
    x: number;
    y: number;
    startX: number;
    startY: number;
    edit: MovePoint | null;
    digging: boolean;
    moving: boolean;
    orbiting: boolean;
  } | null = null;

  const clearTimer = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  const stop = () => {
    if (goal && ports.enabled()) {
      const actor = ports.hero();
      if (actor) ports.move(actor);
    }
    goal = null;
    keyIntent = '';
  };
  const move = (point: MovePoint | null) => {
    if (point && ports.enabled() && ports.move(point)) goal = point;
  };
  const flushDrag = (force = false) => {
    if (!pendingDrag || (!force && Date.now() - lastDragAt < 100)) return;
    const key = `${pendingDrag.x},${pendingDrag.y}`;
    if (key !== lastMove) {
      move(pendingDrag);
      lastMove = key;
      lastDragAt = Date.now();
    }
    pendingDrag = null;
  };
  const release = (send: boolean) => {
    clearTimer();
    if (send && ports.enabled() && press?.digging && press.edit)
      ports.voxel('dig_cancel', press.edit);
    press = null;
    lastMove = '';
    pendingDrag = null;
  };
  const cancel = (send = true) => {
    release(send);
    keys.clear();
    pointer = null;
    if (send) stop();
    else {
      goal = null;
      keyIntent = '';
    }
  };
  const drive = () => {
    const actor = ports.hero();
    const direction = movementDirection(keys, ports.azimuth());
    if (!actor || (!direction.x && !direction.y)) return;
    const intent = `${actor.x},${actor.y},${direction.x},${direction.y},${ports.revision()}`;
    if (intent === keyIntent) return;
    keyIntent = intent;
    const target = { x: actor.x + direction.x, y: actor.y + direction.y };
    if (ports.step(target)) move(target);
    else {
      stop();
      keyIntent = intent;
      ports.error('那处挡着路。');
    }
  };
  canvas.addEventListener('contextmenu', (event) => event.preventDefault(), {
    signal: abort.signal,
  });
  canvas.addEventListener(
    'pointerdown',
    (event) => {
      if (!ports.enabled() || ports.typing() || ![0, 1, 2].includes(event.button)) return;
      release(true);
      pointer = { x: event.clientX, y: event.clientY };
      const edit = ports.pickEdit(pointer.x, pointer.y);
      const ground = ports.pickGround(pointer.x, pointer.y);
      const canDig = edit !== null && ports.blocked(edit);
      const current = {
        id: event.pointerId,
        button: event.button,
        x: event.clientX,
        y: event.clientY,
        startX: event.clientX,
        startY: event.clientY,
        edit,
        digging: false,
        moving: event.button === 0 && !canDig,
        orbiting: false,
      };
      press = current;
      canvas.setPointerCapture(event.pointerId);
      if (event.button !== 0) {
        event.preventDefault();
        return;
      }
      if (!canDig) {
        pendingDrag = ground;
        flushDrag(true);
        return;
      }
      timer = setTimeout(() => {
        timer = null;
        if (
          press !== current ||
          !ports.enabled() ||
          ports.typing() ||
          epoch !== ports.epoch() ||
          !edit
        )
          return;
        stop();
        current.digging = true;
        ports.voxel('dig_start', edit);
      }, 150);
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'pointermove',
    (event) => {
      pointer = { x: event.clientX, y: event.clientY };
      if (!press || press.id !== event.pointerId) return;
      if (press.button === 1 || press.button === 2) {
        if (Math.hypot(event.clientX - press.startX, event.clientY - press.startY) >= 5)
          press.orbiting = true;
        if (press.orbiting) ports.rotate(event.clientX - press.x, event.clientY - press.y);
      } else if (Math.hypot(event.clientX - press.startX, event.clientY - press.startY) >= 5) {
        clearTimer();
        if (press.digging && press.edit) ports.voxel('dig_cancel', press.edit);
        press.digging = false;
        press.moving = true;
        const target = ports.pickGround(event.clientX, event.clientY);
        pendingDrag = target;
        flushDrag();
      }
      press.x = event.clientX;
      press.y = event.clientY;
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'pointerup',
    (event) => {
      if (!press || press.id !== event.pointerId) return;
      const current = press;
      if (epoch !== ports.epoch() || !ports.enabled()) {
        cancel(false);
        return;
      }
      if (ports.typing()) {
        cancel();
        return;
      }
      if (current.button === 2 && !current.orbiting) {
        const edit = ports.pickEdit(event.clientX, event.clientY);
        if (edit && !ports.blocked(edit)) {
          stop();
          ports.voxel('place', edit);
        }
      } else if (current.button === 0 && !current.digging) {
        if (current.moving) {
          pendingDrag = ports.pickGround(event.clientX, event.clientY);
          flushDrag(true);
        } else move(ports.pickGround(event.clientX, event.clientY));
      }
      release(true);
    },
    { signal: abort.signal },
  );
  canvas.addEventListener('pointercancel', () => cancel(), { signal: abort.signal });
  canvas.addEventListener(
    'pointerleave',
    () => {
      if (press) cancel();
      else pointer = null;
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'wheel',
    (event) => {
      event.preventDefault();
      ports.zoom(event.deltaY);
    },
    { signal: abort.signal, passive: false },
  );
  keyboard.addEventListener(
    'keydown',
    (raw) => {
      const event = raw as KeyboardEvent;
      if (
        ports.typing() ||
        !ports.enabled() ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        event.isComposing
      )
        return;
      if (event.code === 'Escape') {
        cancel();
        return;
      }
      if (!moveKeys.has(event.code)) return;
      event.preventDefault();
      if (event.repeat || keys.has(event.code)) return;
      release(true);
      keys.add(event.code);
      drive();
    },
    { signal: abort.signal },
  );
  keyboard.addEventListener(
    'keyup',
    (raw) => {
      const event = raw as KeyboardEvent;
      if (!keys.delete(event.code)) return;
      if (!keys.size) stop();
      else drive();
    },
    { signal: abort.signal },
  );
  keyboard.addEventListener('blur', () => cancel(), { signal: abort.signal });
  return {
    get goal() {
      return goal;
    },
    get pointer() {
      return pointer;
    },
    get orbiting() {
      return press?.orbiting ?? false;
    },
    cancel,
    tick() {
      if (epoch !== ports.epoch() || !ports.enabled()) {
        cancel(false);
        epoch = ports.epoch();
        return;
      }
      if (ports.typing()) {
        cancel();
        return;
      }
      const actor = ports.hero();
      if (goal && actor?.x === goal.x && actor.y === goal.y) goal = null;
      if (keys.size) drive();
      else if (press?.moving) flushDrag();
    },
    dispose() {
      cancel(false);
      abort.abort();
    },
  };
}
export type WorldInput = ReturnType<typeof createWorldInput>;
