/** 试车台的检修面板（悬停识别 + 部件图鉴 + 分级拆解 + 三视图）。
 *
 * 为什么是裸 DOM 而不是 React：面板与 canvas 同属世界层（`CanvasHost` 只挂
 * canvas），而 React 树不碰世界内容（App 的分层约定）。这里只在 canvas 父容器
 * 里加一个绝对定位的浮层，销毁时整棵移除 —— 不引入 store 字段，也不让高频
 * 指针位置进 React。
 *
 * 样式在 `ui/ui.css` 的 `.od-lre-*` 段。所有状态（选中件、拆解度、视图模式）
 * 都由 vendored 模块持有，这里只发指令、不复制真相。
 */
import type {
  StandPartMeta,
  StandSystem,
} from '@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js';

export type StandViewMode = 'pbr' | 'holo' | 'flir';

export interface LandmarkPanelPorts {
  select(partId: number | null): void;
  hover(partId: number | null): void;
  setExplode(percent: number): void;
  setView(mode: StandViewMode): void;
  setFiring(on: boolean): void;
}

export interface LandmarkPanel {
  /** 悬停到某部件：更新画布角落的浮签（clientX/clientY 是视口坐标）。 */
  hover(partId: number | null, clientX: number, clientY: number): void;
  /** 外部改变选中件（例如画布点击命中部件）。 */
  select(partId: number | null): void;
  dispose(): void;
}

const VIEW_LABELS: Record<StandViewMode, string> = {
  pbr: '实感 PBR',
  holo: '全息 HOLO',
  flir: '热像 FLIR',
};

/** 拆解阶段文案：与 vendored `setExplodePercentage` 的四段 smoothstep 对齐。 */
export function explodeStageText(percent: number): string {
  if (percent <= 0) return '整机闭锁 · 24 件处于总装工位';
  if (percent <= 25) return '一阶 · 外层管路与阀件脱开';
  if (percent <= 50) return '二阶 · 喷管与燃烧室外壳分离';
  if (percent <= 75) return '三阶 · 涡轮泵与预燃室让位';
  return '四阶 · 喷注器与内衬全展';
}

function button(label: string, className: string): HTMLButtonElement {
  const element = document.createElement('button');
  element.type = 'button';
  element.className = className;
  element.textContent = label;
  return element;
}

export function createLandmarkPanel(
  host: HTMLElement,
  systems: readonly StandSystem[],
  parts: Readonly<Record<number, StandPartMeta>>,
  ports: LandmarkPanelPorts,
): LandmarkPanel {
  // 默认收起：这是游戏画面，常驻 20rem 的检修面板会把半个镇子挡住。
  // 点画布上的试车台会自动展开（用户想看的就是那个部件）。
  const root = document.createElement('div');
  root.className = 'od-lre-panel';
  root.hidden = true;

  const titleRow = document.createElement('div');
  titleRow.className = 'od-lre-panel__title-row';
  const title = document.createElement('div');
  title.className = 'od-lre-panel__title';
  title.textContent = 'LRE-DT100 试车台 · 检修图鉴';
  const collapse = button('收起', 'od-lre-btn od-lre-btn--collapse');
  titleRow.append(title, collapse);
  root.append(titleRow);

  const toggle = button('试车台', 'od-lre-toggle');
  toggle.setAttribute('aria-expanded', 'false');
  const setOpen = (open: boolean): void => {
    root.hidden = !open;
    toggle.hidden = open;
    toggle.setAttribute('aria-expanded', String(open));
    if (!open) tooltip.hidden = true;
  };
  collapse.addEventListener('click', () => setOpen(false));
  toggle.addEventListener('click', () => setOpen(true));
  host.append(toggle);

  // --- 视图模式 ---------------------------------------------------------------
  const modes = document.createElement('div');
  modes.className = 'od-lre-row';
  const modeButtons = new Map<StandViewMode, HTMLButtonElement>();
  for (const mode of ['pbr', 'holo', 'flir'] as const) {
    const element = button(VIEW_LABELS[mode], 'od-lre-btn');
    element.setAttribute('aria-pressed', String(mode === 'pbr'));
    element.addEventListener('click', () => {
      for (const [other, entry] of modeButtons)
        entry.setAttribute('aria-pressed', String(other === mode));
      ports.setView(mode);
    });
    modeButtons.set(mode, element);
    modes.append(element);
  }
  root.append(modes);

  // --- 点火开关 ---------------------------------------------------------------
  const fire = button('点火试车：开', 'od-lre-btn od-lre-btn--fire');
  fire.setAttribute('aria-pressed', 'true');
  let firing = true;
  fire.addEventListener('click', () => {
    firing = !firing;
    fire.textContent = `点火试车：${firing ? '开' : '关'}`;
    fire.setAttribute('aria-pressed', String(firing));
    ports.setFiring(firing);
  });
  root.append(fire);

  // --- 分级拆解 ---------------------------------------------------------------
  const sliderLabel = document.createElement('label');
  sliderLabel.className = 'od-lre-slider';
  const sliderHead = document.createElement('span');
  sliderHead.className = 'od-lre-slider__head';
  const sliderText = document.createElement('span');
  sliderText.textContent = '分级拆解';
  const sliderValue = document.createElement('span');
  sliderValue.className = 'od-lre-slider__value';
  sliderValue.textContent = '0%';
  sliderHead.append(sliderText, sliderValue);
  const slider = document.createElement('input');
  slider.type = 'range';
  slider.min = '0';
  slider.max = '100';
  slider.step = '1';
  slider.value = '0';
  slider.setAttribute('aria-label', '分级拆解进度');
  const stage = document.createElement('span');
  stage.className = 'od-lre-slider__stage';
  stage.textContent = explodeStageText(0);
  slider.addEventListener('input', () => {
    const percent = Number(slider.value);
    sliderValue.textContent = `${percent}%`;
    stage.textContent = explodeStageText(percent);
    ports.setExplode(percent);
  });
  sliderLabel.append(sliderHead, slider, stage);
  root.append(sliderLabel);

  // --- 4 系统 / 24 部件 -------------------------------------------------------
  const tree = document.createElement('div');
  tree.className = 'od-lre-tree';
  const partButtons = new Map<number, HTMLButtonElement>();
  for (const system of systems) {
    const heading = document.createElement('div');
    heading.className = 'od-lre-tree__system';
    heading.textContent = system.sysName;
    tree.append(heading);
    for (const part of system.parts) {
      const element = button(`#${String(part.id).padStart(2, '0')} ${part.name}`, 'od-lre-part');
      element.addEventListener('mouseenter', () => ports.hover(part.id));
      element.addEventListener('mouseleave', () => ports.hover(null));
      element.addEventListener('focus', () => ports.hover(part.id));
      element.addEventListener('blur', () => ports.hover(null));
      element.addEventListener('click', () => {
        ports.select(part.id);
        select(part.id);
      });
      partButtons.set(part.id, element);
      tree.append(element);
    }
  }
  root.append(tree);

  // --- 选中件详情 -------------------------------------------------------------
  const inspector = document.createElement('div');
  inspector.className = 'od-lre-inspector';
  root.append(inspector);

  const select = (partId: number | null): void => {
    for (const [id, element] of partButtons)
      element.setAttribute('aria-pressed', String(id === partId));
    inspector.replaceChildren();
    const meta = partId === null ? undefined : parts[partId];
    if (!meta) {
      const empty = document.createElement('p');
      empty.className = 'od-lre-inspector__empty';
      empty.textContent = '点选左侧部件，或把鼠标移到台体上。';
      inspector.append(empty);
      return;
    }
    const name = document.createElement('div');
    name.className = 'od-lre-inspector__name';
    name.textContent = `#${String(meta.id).padStart(2, '0')} ${meta.name}`;
    const en = document.createElement('div');
    en.className = 'od-lre-inspector__en';
    en.textContent = meta.en;
    const mat = document.createElement('div');
    mat.className = 'od-lre-inspector__meta';
    mat.textContent = `材质：${meta.mat}`;
    const env = document.createElement('div');
    env.className = 'od-lre-inspector__meta';
    env.textContent = `工况：${meta.env}`;
    const desc = document.createElement('p');
    desc.className = 'od-lre-inspector__desc';
    desc.textContent = meta.desc;
    inspector.append(name, en, mat, env, desc);
  };
  select(null);

  // --- 悬停浮签（跟随指针，相对 host 定位） -----------------------------------
  const tooltip = document.createElement('div');
  tooltip.className = 'od-lre-tooltip';
  tooltip.hidden = true;
  const tooltipSystem = document.createElement('span');
  tooltipSystem.className = 'od-lre-tooltip__system';
  const tooltipName = document.createElement('span');
  tooltipName.className = 'od-lre-tooltip__name';
  tooltip.append(tooltipSystem, tooltipName);

  host.append(root, tooltip);

  return {
    hover(partId, clientX, clientY) {
      const meta = partId === null ? undefined : parts[partId];
      if (!meta) {
        tooltip.hidden = true;
        return;
      }
      tooltipSystem.textContent = `SYSTEM ${meta.sysId}`;
      tooltipName.textContent = `#${String(meta.id).padStart(2, '0')} ${meta.name}`;
      tooltip.hidden = false;
      // 浮签夹在 host 内，避免贴边时跑出画布。
      const rect = host.getBoundingClientRect();
      const left = Math.min(Math.max(8, clientX - rect.left + 14), rect.width - 240);
      const top = Math.min(Math.max(8, clientY - rect.top + 14), rect.height - 64);
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    },
    select(partId) {
      select(partId);
      // 画布上点中部件 = 想看它：把抽屉打开，否则选中了却看不到详情。
      if (partId !== null) setOpen(true);
    },
    dispose() {
      root.remove();
      toggle.remove();
      tooltip.remove();
    },
  };
}
