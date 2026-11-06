/** Lifecycle shared by the opt-in three world and the default Phaser world. */
export interface WorldGame {
  readonly isBooted: boolean;
  readonly scale: {
    readonly width: number;
    readonly height: number;
    setParentSize(width: number, height: number): unknown;
  };
  readonly events: {
    once(event: 'ready', listener: () => void): unknown;
    off(event: 'ready', listener: () => void): unknown;
  };
  destroy(removeCanvas: boolean): void;
}
