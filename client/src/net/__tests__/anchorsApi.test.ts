/**
 * client/src/net/__tests__/anchorsApi.test.ts — 批次 D4：存档/读档 API 客户端钉。
 * fetch mock；形状对齐 shared/protocol.ts（AnchorListItem/AnchorCreate）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { anchorsApi } from '../anchorsApi';

const sampleItem = {
  id: 'a1',
  name: '第一天夜里',
  story_label: '第 1 天 夜晚',
  protected: false,
  created_at: '2026-10-06T00:00:00Z',
};

describe('anchorsApi', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('list: GET /api/anchors', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([sampleItem]), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const items = await anchorsApi.list();
    expect(items).toEqual([sampleItem]);
    expect(fetchMock).toHaveBeenCalledWith('/api/anchors');
  });

  it('create: POST /api/anchors {name}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(sampleItem), { status: 201 }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const item = await anchorsApi.create({ name: '开镇第两天' });
    expect(item.id).toBe('a1');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/anchors');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ name: '开镇第两天' });
  });

  it('remove: DELETE /api/anchors/:id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    await anchorsApi.remove('a1');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/anchors/a1');
    expect(init.method).toBe('DELETE');
  });

  it('错误响应抛 SettingsApiError 同族（含 detail）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '这个档读不出来了。' }), { status: 500 }),
    );
    vi.stubGlobal('fetch', fetchMock);
    await expect(anchorsApi.list()).rejects.toThrow('这个档读不出来了。');
  });
});
