import { describe, expect, it } from 'vitest';
import { WorldMirror } from '../../game/world-mirror';

describe('structures projection (E7)', () => {
  it('applies structure delta into mirror (upsert by rtoken)', () => {
    const mirror = new WorldMirror();
    mirror.applyStructures([
      { op: 'add', rtoken: 'st-s1', x: 3, y: 3, phase: 'built' },
      { op: 'add', rtoken: 'st-s1', x: 4, y: 3, phase: 'built' },
    ]);
    expect(mirror.structures.get('st-s1')?.tiles).toEqual([
      [3, 3],
      [4, 3],
    ]);
    expect(mirror.structures.get('st-s1')?.phase).toBe('built');
  });

  it('phase change updates existing entry without duplicating tiles', () => {
    const mirror = new WorldMirror();
    mirror.applyStructures([{ op: 'add', rtoken: 'st-s1', x: 3, y: 3, phase: 'built' }]);
    mirror.applyStructures([{ op: 'add', rtoken: 'st-s1', x: 3, y: 3, phase: 'collapsing' }]);
    expect(mirror.structures.get('st-s1')?.tiles).toEqual([[3, 3]]);
    expect(mirror.structures.get('st-s1')?.phase).toBe('collapsing');
  });

  it('remove op deletes entry', () => {
    const mirror = new WorldMirror();
    mirror.applyStructures([{ op: 'add', rtoken: 'st-s1', x: 3, y: 3, phase: 'built' }]);
    mirror.applyStructures([{ op: 'remove', rtoken: 'st-s1', x: 3, y: 3, phase: 'rubble' }]);
    expect(mirror.structures.has('st-s1')).toBe(false);
  });

  it('reset clears structures', () => {
    const mirror = new WorldMirror();
    mirror.applyStructures([{ op: 'add', rtoken: 'st-s1', x: 3, y: 3, phase: 'built' }]);
    mirror.reset();
    expect(mirror.structures.size).toBe(0);
  });
});
