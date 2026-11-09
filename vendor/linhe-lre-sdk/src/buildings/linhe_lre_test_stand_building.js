/**
 * 《临河镇》LRE-DT100 液体火箭发动机 3D 数字孪生试车台 · 地标建筑独立模块
 * 支持任意体素坐标 (tileX, groundY, tileZ) 放置、24 子部件射线拾取、四阶爆炸拆解、PBR/HOLO/FLIR 三视图及 12 章导览
 */
import * as THREE from 'three';

// ============================================================================
// 1. 24-COMPONENT ENGINEERING CATALOG & METADATA
// ============================================================================
const SYSTEMS_CATALOG = [
  {
    sysId: 1,
    sysName: "System 1: 推力矢量与进流系统",
    parts: [
      { id: 1, name: "顶部倒三角承力桁架与压电测力计", en: "Load Cell Blocks & Thrust Truss", mat: "18Ni(300) 马氏体时效钢 / 石英压电阵列", env: "295 K / 承受1500 kN轴向冲击", stage: 0, explodeVec: [0, 0, 0], desc: "刚性倒三角空间桁架锁死在试车台主横梁上，万向节上方布置4只圆盘形高刚度石英压电测力传感器垫（Load Cell Blocks），实现发动机推力载荷向试车台地基的闭环传递与千赫兹级动态测力。" },
      { id: 2, name: "双向万向十字铰链球轴承", en: "Universal Gimbal Joint", mat: "Ti-6Al-4V ELI 钛合金 / 自润滑PTFE衬层", env: "280 K / 1350 kN 轴向承载", stage: 1, explodeVec: [0, 0.85, 0], desc: "十字轴万向节连接顶部测力传感器底座与发动机传力锥，支持俯仰（Pitch）与偏航（Yaw）双自由度±8°大负载摆动。" },
      { id: 3, name: "双通道电液伺服作动筒", en: "TVC Pitch/Yaw Hydraulic Actuators", mat: "300M 超高强度钢镀硬铬活塞杆", env: "340 K / 28 MPa 高压红油", stage: 1, explodeVec: [1.4, 0.4, 1.4], desc: "正交布置的俯仰与偏航双余度电液伺服作动器，内置MOOG双级伺服阀与LVDT位移传感器，待机时每8秒执行一次±1.5°微动力学自检摆动。" },
      { id: 4, name: "碳纤维缠绕高压氦气气瓶组", en: "COPV Helium Tanks", mat: "T1000碳纤维/环氧树脂 + 6061铝内胆", env: "220 K / 42.0 MPa 超高压氦气", stage: 1, explodeVec: [-2.2, 0.25, 0.6], desc: "4只T1000级碳纤维全缠绕复合材料气瓶（COPV），为气动主液氧截止阀及吹除密封系统提供42 MPa超高压氦气气源。" },
      { id: 5, name: "快速脱落推进剂加注接头", en: "Umbilical Disconnect Couplings", mat: "Inconel 718 镍基高温合金卡爪法兰", env: "90 K (LOX) / 293 K (RP-1) / 6.5 MPa", stage: 1, explodeVec: [2.4, 0.2, 0], desc: "与试车台两侧黄黑警示液压加注摆臂刚性锁紧的零泄漏卡爪法兰，内置自密封锥阀与紧急气动解锁机构。" }
    ]
  },
  {
    sysId: 2,
    sysName: "System 2: 燃烧室与喷注系统",
    parts: [
      { id: 6, name: "富氧预燃室/燃气发生器总成", en: "Oxygen-Rich Preburner Assembly", mat: "GH4169 高温镍基合金 + 抗氧化涂层", env: "820 K / 38.5 MPa 富氧燃气", stage: 3, explodeVec: [-1.5, 0.9, -1.1], desc: "高压补燃循环核心组件，绝大部分液氧与少量煤油在此富氧燃烧，生成820K、38.5MPa高压富氧燃气驱动主涡轮泵。" },
      { id: 7, name: "91孔同轴涡流喷注器内腔面板", en: "91-Element Coaxial Injector Faceplate", mat: "Inconel 718 激光选区熔化 (SLM)", env: "650 K / 21.0 MPa 喷注压降", stage: 4, explodeVec: [0, 2.35, 0], desc: "蜂窝状排布91只同轴离心涡流喷嘴，中心喷射富氧燃气、外环切向旋流喷入再生冷却升温后的煤油，雾化粒径低于35微米。" },
      { id: 8, name: "六边形抗高频燃烧振荡隔板", en: "Hexagonal Acoustic Baffles", mat: "CuCrZr 镀镍金高导热阻尼叶片", env: "2850 K / 18.5 MPa 高频声腔", stage: 4, explodeVec: [0, 1.85, 0], desc: "从喷注面板向下延伸的六边形辐射状隔板，将燃烧室头部声学模态分割为独立扇区，彻底抑制一阶切向高频不稳定燃烧（Screeching）。" },
      { id: 9, name: "铣槽铬锆铜再生冷却内衬", en: "CuCrZr Milled Cooling Liner (360 Channels)", mat: "CuCr0.8Zr 铬锆铜合金 (360道微槽)", env: "942 K 壁温 / 3600 K 燃气核心", stage: 2, explodeVec: [0, 0, 0], desc: "燃烧室与喉部核心热防护件，外表面精密数控铣削360条高深宽比再生冷却通道，煤油逆流冲刷将铜壁温度严格控制在950K安全红线内。" },
      { id: 10, name: "燃烧室高强承力外夹套", en: "High-Strength Structural Jacket (12 Ribs)", mat: "Inconel 718 电铸/精密机加 (12加强肋)", env: "520 K / 18.5 MPa 环向拉应力", stage: 2, explodeVec: [0, 0.15, 2.2], desc: "左右两半剖分式高强镍基合金外夹套，外壁带12道轴向抗弯加强肋、腰部法兰与高压测压孔，封闭360道铜内衬冷却铣槽。" },
      { id: 11, name: "周向高频压力传感器与热电偶线束", en: "Sensor Bosses & Braided Wiring Harness", mat: "PTFE镀银屏蔽线束 + K/C型钨铼热电偶", env: "450 K / 50 kHz 高频采样", stage: 1, explodeVec: [0, 0.1, -2.1], desc: "环绕燃烧室与喷管布置的多级测压凸台与橙色耐高温聚酰亚胺编织线束，实时采集室压脉动与壁面热流分布。" }
    ]
  },
  {
    sysId: 3,
    sysName: "System 3: 双回路涡轮泵动力系统",
    parts: [
      { id: 12, name: "低温液氧螺旋防气蚀诱导轮", en: "Cryogenic LOX Anti-Cavitation Inducer", mat: "Ti-5Al-2.5Sn ELI 超低温钛合金", env: "90 K (-183℃) / 4.2 MPa", stage: 3, explodeVec: [1.5, 0.65, 1.3], desc: "大前掠角三叶片变螺距螺旋诱导轮，在极低净正吸入压头（NPSH）下抑制液氧低温沸腾气蚀，为离心主叶轮提供预增压。" },
      { id: 13, name: "双吸闭式离心高压叶轮与蜗壳", en: "Centrifugal Impeller & Spiral Volute", mat: "Inconel 718 五轴整体铣削叶轮", env: "95 K / 44.0 MPa 泵出口高压", stage: 3, explodeVec: [2.1, 0.2, 1.6], desc: "高比转速双吸闭式离心叶轮配合阿基米德螺旋增压蜗壳，将液氧一次性增压至44 MPa以上，剖切态下可见高速自转叶片。" },
      { id: 14, name: "两级高温燃气轴流透平转子盘", en: "Two-Stage Supersonic Blisk Turbine", mat: "Rene 41 / 单晶镍基高温合金整体叶盘", env: "820 K / 34,850 RPM / 52 MW", stage: 3, explodeVec: [-2.1, 0.1, -1.6], desc: "两级整体叶盘（Blisk）包含84枚超音速冲动式涡轮叶片，在富氧预燃燃气驱动下输出52兆瓦轴功率。" },
      { id: 15, name: "动压石墨碳环与迷宫式密封座", en: "Hydrodynamic Carbon & Labyrinth Seal", mat: "浸渍锑高强石墨 + 蒙乃尔K-500迷宫齿", env: "380 K / 氦气隔离吹除腔", stage: 3, explodeVec: [1.5, -0.1, -1.4], desc: "位于低温液氧泵与高温富氧燃气透平之间的关键安全屏障，引入高压氦气形成正压气幕隔离，严防油氧互串。" },
      { id: 16, name: "煤油燃料主泵与行星减速箱", en: "RP-1 Fuel Turbopump & Planetary Gearbox", mat: "A356-T6 高强铸造外壳 + 渗碳齿轮钢", env: "305 K / 39.5 MPa 燃料出口压", stage: 3, explodeVec: [-2.2, 0.35, 1.3], desc: "双级离心式RP-1煤油主泵，将煤油加压至39.5 MPa后分为两路：主路直达喷管底部再生冷却环，副路进入预燃室。" },
      { id: 17, name: "涡轮排气环形集气总管与排放管", en: "Turbine Exhaust Manifold & Duct", mat: "GH3030 钛合金热氧化彩虹退火管路", env: "760 K / 19.5 MPa 二次喷注回路", stage: 1, explodeVec: [-1.8, -0.35, -1.5], desc: "收集透平做功后的富氧燃气并汇入燃烧室头部穹顶，管壁呈现典型的高温钛合金金黄→紫红→钴蓝氧化退火彩虹色（Heat-Tint）。" }
    ]
  },
  {
    sysId: 4,
    sysName: "System 4: 喷管与超音速膨胀控制系统",
    parts: [
      { id: 18, name: "超音速喉部收敛-扩散法兰段", en: "Supersonic Throat De Laval Flange", mat: "Inconel 718 锻造法兰 + 碳化铪热障层", env: "3600 K 燃气中心 / Ma = 1.0 声速截面", stage: 2, explodeVec: [0, -0.1, -1.8], desc: "拉瓦尔喷管喉部最小截面积处（Ma=1.0），承受全机最高热流密度（>85 MW/m²），外部由重型螺栓法兰强化。" },
      { id: 19, name: "180根螺旋薄壁冷却钢管钎焊喷管", en: "180-Tube Brazed Regenerative Nozzle", mat: "180根 347不锈钢变截面螺旋钎焊薄壁管", env: "780 K 壁温 / Ma = 3.8 超音速膨胀", stage: 0, explodeVec: [0, 0, 0], desc: "由180根精密成型的薄壁椭圆截面不锈钢冷却管沿抛物线钟形母线螺旋铺设并真空金镍钎焊而成，将燃气膨胀加速至3280 m/s。" },
      { id: 20, name: "主液氧气动截止阀组", en: "Main LOX Pneumatic Shutoff Valve", mat: "316L 超低温不锈钢球阀 + 气动执行器", env: "90 K / 42 MPa 响应时间 < 35ms", stage: 1, explodeVec: [2.0, -0.2, 0.9], desc: "由高压氦气驱动的超低温大口径主液氧球阀，具备毫秒级紧急关断能力与位置回读电感传感器。" },
      { id: 21, name: "主煤油节流调节蝶阀", en: "RP-1 Throttle Control Butterfly Valve", mat: "17-4PH 沉淀硬化不锈钢 + 谐波驱动器", env: "298 K / 38 MPa 50%~115%深度节流", stage: 1, explodeVec: [-2.0, -0.25, 0.9], desc: "高精度电动节流蝶阀，实时调节进入再生冷却回路与燃烧室的RP-1煤油流量，支持发动机50%~115%变推力节流运行。" },
      { id: 22, name: "多层不锈钢高压编织金属网波纹节", en: "Braided Metal Bellows Gimbal Joints", mat: "321不锈钢三层液压成形波纹管+编织网套", env: "90 K ~ 750 K / ±6° 角位移补偿", stage: 1, explodeVec: [1.65, -0.5, -0.9], desc: "串联在高压输送主管路上的多层不锈钢金属波纹膨胀节，外覆高强钢丝编织网套，吸收发动机矢量摆动与热胀冷缩变形。" },
      { id: 23, name: "再生冷却环形分配集液主管", en: "Toroidal Fuel Inlet Collector Ring", mat: "Inconel 625 环形焊接分流总管", env: "300 K / 36.5 MPa 冷却剂入口总管", stage: 1, explodeVec: [0, -0.85, 0], desc: "环绕在钟形喷管下缘的环形大口径集液总管，接收来自燃料泵的高压煤油并均匀分配至360道逆流再生冷却通道。" },
      { id: 24, name: "喷管外部环向防振加强套箍 (5道)", en: "5-Tier Nozzle Stiffener Hat-Section Rings", mat: "Ti-6Al-4V 钛合金工字截面加强环 (5道)", env: "520 K / 抑制喷管侧向流动分离椭圆模态振动", stage: 1, explodeVec: [0, -1.25, 0], desc: "沿扩散喷管外壁等距焊接的5道梯级高刚度环向防振加强套箍，防止地面试车高背压下喷管发生激波诱导流固耦合抖振。" }
    ]
  }
];

// Flatten parts for quick lookup
const PARTS_BY_ID = {};
SYSTEMS_CATALOG.forEach(sys => {
  sys.parts.forEach(p => {
    p.sysName = sys.sysName;
    p.sysId = sys.sysId;
    PARTS_BY_ID[p.id] = p;
  });
});

// ============================================================================
// 2. PROCEDURAL CANVAS TEXTURES (ZERO EXTERNAL ASSETS)
// ============================================================================
function createProceduralTextures() {
  // 2.1 Brushed Aerospace Metal Bump/Roughness Map
  const metalCanvas = document.createElement('canvas');
  metalCanvas.width = 512; metalCanvas.height = 512;
  const mctx = metalCanvas.getContext('2d');
  mctx.fillStyle = '#888';
  mctx.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 4000; i++) {
    const y = Math.random() * 512;
    const lum = 110 + Math.floor(Math.random() * 60);
    mctx.fillStyle = `rgb(${lum},${lum},${lum})`;
    mctx.fillRect(Math.random() * 512, y, 40 + Math.random() * 120, 1.2);
  }
  const brushedTex = new THREE.CanvasTexture(metalCanvas);
  brushedTex.wrapS = brushedTex.wrapT = THREE.RepeatWrapping;

  // 2.2 Titanium Heat-Tint Anodization Gradient (Gold -> Magenta/Purple -> Cobalt Blue)
  const tintCanvas = document.createElement('canvas');
  tintCanvas.width = 512; tintCanvas.height = 256;
  const tctx = tintCanvas.getContext('2d');
  const grad = tctx.createLinearGradient(0, 0, 512, 256);
  grad.addColorStop(0.0, '#d8c29d');
  grad.addColorStop(0.28, '#e8a838');
  grad.addColorStop(0.55, '#a83279');
  grad.addColorStop(0.78, '#2b58b8');
  grad.addColorStop(1.0, '#7898b8');
  tctx.fillStyle = grad;
  tctx.fillRect(0, 0, 512, 256);
  const heatTintTex = new THREE.CanvasTexture(tintCanvas);

  // 2.3 Carbon Fiber Weave (COPV Helium Tanks)
  const cfCanvas = document.createElement('canvas');
  cfCanvas.width = 256; cfCanvas.height = 256;
  const cctx = cfCanvas.getContext('2d');
  cctx.fillStyle = '#14181f';
  cctx.fillRect(0, 0, 256, 256);
  for (let y = 0; y < 256; y += 8) {
    for (let x = 0; x < 256; x += 8) {
      const odd = ((x + y) / 8) % 2 === 0;
      cctx.fillStyle = odd ? '#262d38' : '#0f1318';
      cctx.fillRect(x, y, 7, 7);
      cctx.fillStyle = odd ? '#343e4d' : '#1b2129';
      cctx.fillRect(x + 1, y + 1, 5, 2);
    }
  }
  const carbonTex = new THREE.CanvasTexture(cfCanvas);
  carbonTex.wrapS = carbonTex.wrapT = THREE.RepeatWrapping;
  carbonTex.repeat.set(10, 10);

  // 2.4 CuCrZr 360 Milled Micro-Channels Liner Texture
  const linerCanvas = document.createElement('canvas');
  linerCanvas.width = 1024; linerCanvas.height = 512;
  const lctx = linerCanvas.getContext('2d');
  lctx.fillStyle = '#b86b35';
  lctx.fillRect(0, 0, 1024, 512);
  for (let i = 0; i < 360; i++) {
    const x = (i / 360) * 1024;
    lctx.fillStyle = (i % 2 === 0) ? '#e39254' : '#633214';
    lctx.fillRect(x, 0, 1.8, 512);
  }
  const milledCopperTex = new THREE.CanvasTexture(linerCanvas);
  milledCopperTex.wrapS = milledCopperTex.wrapT = THREE.RepeatWrapping;

  // 2.5 180 Spiral Brazed Nozzle Tubes Texture
  const nozCanvas = document.createElement('canvas');
  nozCanvas.width = 1024; nozCanvas.height = 512;
  const nctx = nozCanvas.getContext('2d');
  nctx.fillStyle = '#5c6672';
  nctx.fillRect(0, 0, 1024, 512);
  nctx.lineWidth = 2.6;
  for (let i = -90; i < 270; i++) {
    const x0 = (i / 180) * 1024;
    nctx.strokeStyle = (i % 2 === 0) ? '#9aa6b5' : '#2d333b';
    nctx.beginPath();
    nctx.moveTo(x0, 0);
    nctx.lineTo(x0 + 220, 512);
    nctx.stroke();
  }
  // Horizontal braze weld seams
  nctx.strokeStyle = 'rgba(215, 175, 105, 0.35)';
  nctx.lineWidth = 3;
  for (let y = 64; y < 512; y += 64) {
    nctx.beginPath(); nctx.moveTo(0, y); nctx.lineTo(1024, y); nctx.stroke();
  }
  const brazedNozzleTex = new THREE.CanvasTexture(nozCanvas);
  brazedNozzleTex.wrapS = brazedNozzleTex.wrapT = THREE.RepeatWrapping;

  // 2.6 Yellow/Black Hazard Stripes (Umbilical Swing Arms)
  const hazCanvas = document.createElement('canvas');
  hazCanvas.width = 256; hazCanvas.height = 256;
  const hctx = hazCanvas.getContext('2d');
  hctx.fillStyle = '#e5a900';
  hctx.fillRect(0, 0, 256, 256);
  hctx.fillStyle = '#15181c';
  for (let i = -256; i < 512; i += 48) {
    hctx.beginPath();
    hctx.moveTo(i, 0);
    hctx.lineTo(i + 24, 0);
    hctx.lineTo(i - 104, 256);
    hctx.lineTo(i - 128, 256);
    hctx.closePath();
    hctx.fill();
  }
  const hazardTex = new THREE.CanvasTexture(hazCanvas);
  hazardTex.wrapS = hazardTex.wrapT = THREE.RepeatWrapping;
  hazardTex.repeat.set(4, 1);

  return { brushedTex, heatTintTex, carbonTex, milledCopperTex, brazedNozzleTex, hazardTex };
}


const PART_CAMERA_PROFILES = {
  1:  { azim: 26,  elev: 16, dist: 5.2, focusWorld: [0, 3.85, 0], minExplode: 0 },
  2:  { azim: 28,  elev: 14, dist: 3.4, focusLocal: [0, -0.15, 0], minExplode: 0 },
  3:  { azim: 42,  elev: 18, dist: 3.6, focusLocal: [0.85, -0.42, 0.85], minExplode: 0 },
  4:  { azim: -48, elev: 16, dist: 3.5, focusLocal: [-1.12, -0.70, 0.52], minExplode: 0 },
  5:  { azim: 58,  elev: 14, dist: 3.2, focusLocal: [1.38, -1.30, 0.32], minExplode: 0 },
  6:  { azim: -55, elev: 20, dist: 3.1, focusLocal: [-0.98, -1.10, -0.48], minExplode: 0 },
  7:  { azim: 25,  elev: 28, dist: 2.9, focusLocal: [0, -1.73, 0], minExplode: 88 },
  8:  { azim: 32,  elev: 22, dist: 2.8, focusLocal: [0, -1.91, 0], minExplode: 88 },
  9:  { azim: -32, elev: 12, dist: 3.5, focusLocal: [0, -2.55, 0], minExplode: 48 },
  10: { azim: 28,  elev: 12, dist: 3.8, focusLocal: [0, -2.40, 0], minExplode: 0 },
  11: { azim: -38, elev: 14, dist: 3.6, focusLocal: [0, -2.35, -0.45], minExplode: 0 },
  12: { azim: 54,  elev: 20, dist: 2.7, focusLocal: [1.02, -1.53, 0.25], minExplode: 0 },
  13: { azim: 56,  elev: 15, dist: 2.9, focusLocal: [1.02, -1.93, 0.25], minExplode: 65 },
  14: { azim: -58, elev: 18, dist: 2.9, focusLocal: [-0.98, -1.83, -0.48], minExplode: 65 },
  15: { azim: 52,  elev: 12, dist: 2.7, focusLocal: [1.02, -2.23, 0.25], minExplode: 0 },
  16: { azim: -54, elev: 14, dist: 3.6, focusLocal: [-1.02, -2.15, 0.35], minExplode: 0 },
  17: { azim: -44, elev: 18, dist: 3.6, focusLocal: [-0.75, -1.75, -0.48], minExplode: 0 },
  18: { azim: -28, elev: 10, dist: 3.2, focusLocal: [0, -3.10, 0], minExplode: 0 },
  19: { azim: 26,  elev: 8,  dist: 4.8, focusLocal: [0, -4.60, 0], minExplode: 0 },
  20: { azim: 46,  elev: 20, dist: 3.1, focusLocal: [0.85, -1.47, -0.25], minExplode: 0 },
  21: { azim: -52, elev: 12, dist: 2.9, focusLocal: [-1.16, -2.70, 0.40], minExplode: 0 },
  22: { azim: 48,  elev: 16, dist: 3.0, focusLocal: [0.92, -1.70, -0.05], minExplode: 0 },
  23: { azim: 28,  elev: 12, dist: 4.2, focusLocal: [0, -5.33, 0], minExplode: 0 },
  24: { azim: 30,  elev: 8,  dist: 4.6, focusLocal: [0, -4.75, 0], minExplode: 0 }
};

// Build Left Panel 24-Part Tree DOM

const TOUR_TOTAL_DURATION = 180.0; // 180 seconds = 3 minutes full engineering documentary

const TOUR_CHAPTERS = [
  {
    id: 1,
    tStart: 0, tEnd: 15,
    title: "第一章 · 试车台全景与外部承力空间拓扑",
    narration: "【全景巡礼】LRE-DT100 采用高压补燃循环（Staged Combustion Cycle），海平面推力达 1,225 kN。整机悬挂于四柱重型钢结构试车台中央，消除悬浮感，建立从燃烧室轴心到地面承力地基的完整力学传递闭环。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explode: 0, partId: 19,
    camStart: { azim: -38, elev: 14, dist: 16.5, target: [0, 0.4, 0] },
    camEnd:   { azim:  38, elev: 10, dist: 14.2, target: [0, 0.5, 0] }
  },
  {
    id: 2,
    tStart: 15, tEnd: 30,
    title: "第二章 · 顶部倒三角推力主桁架与四阵元压电测力计",
    narration: "【推力载荷闭环】镜头推近试车台顶部：8根高强斜撑构成倒三角承力主梁（#01），万向节上方安装4只圆盘形石英压电测力传感器垫（Load Cell Blocks），配合十字轴万向节（#02）与电液伺服作动筒（#03），实时采集千赫兹级三轴推力载荷。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explode: 0, partId: 1,
    camStart: { azim: 22, elev: 20, dist: 6.2, target: [0, 3.55, 0] },
    camEnd:   { azim: -30, elev: 14, dist: 4.5, target: [0, 3.25, 0] },
    subEvents: [
      { t: 20, partId: 2 },
      { t: 25, partId: 3, triggerSweep: true }
    ]
  },
  {
    id: 3,
    tStart: 30, tEnd: 45,
    title: "第三章 · 液压加注摆臂与推进剂快速脱落法兰",
    narration: "【推进剂加注与气源】两侧柱体延伸出涂有黄黑防夹警示斜纹的摆动式加注脐带臂，通过 Inconel 718 快速脱落卡爪法兰（#05）分别锁死在右侧 -183℃ 液氧主入口与左侧 RP-1 煤油入口；上方搭载 T1000 碳纤维缠绕高压氦气瓶组（#04）。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explode: 0, partId: 5,
    camStart: { azim: 52, elev: 14, dist: 5.2, target: [1.1, 2.0, 0.3] },
    camEnd:   { azim: -48, elev: 16, dist: 5.0, target: [-0.9, 2.3, 0.2] },
    subEvents: [
      { t: 38, partId: 4 }
    ]
  },
  {
    id: 4,
    tStart: 45, tEnd: 60,
    title: "第四章 · 阶梯拆解工序 I (0%→25%)：外围管网与传感线束剥离",
    narration: "【一级爆炸拆解】启动第一阶段拆解（0%→25%）：周向高频压力传感器与橙色聚酰亚胺热电偶线束（#11）、主液氧截止阀（#20）、煤油节流蝶阀（#21）以及多层不锈钢金属网波纹膨胀节（#22）沿径向平稳剥离。",
    mode: "pbr", firing: true, flow: true, throttle: 95, explodeRange: [0, 25], partId: 11,
    camStart: { azim: -34, elev: 12, dist: 7.2, target: [0, 1.1, 0] },
    camEnd:   { azim:  36, elev: 15, dist: 6.4, target: [0, 1.2, 0] },
    subEvents: [
      { t: 50, partId: 20 },
      { t: 55, partId: 22 }
    ]
  },
  {
    id: 5,
    tStart: 60, tEnd: 75,
    title: "第五章 · 阶梯拆解工序 II (25%→50%)：承力外套滑脱与360槽铬锆铜内衬",
    narration: "【再生冷却核心】进入第二阶段拆解（25%→50%）：带12道轴向加强肋的 Inconel 718 高强承力外夹套（#10）向前滑脱，完整裸露出内部金铜色 CuCr0.8Zr 铣槽内衬（#09）——外壁精密铣削360道微冷却槽道，承受喉部（#18）3600K 极热。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explodeRange: [25, 50], partId: 9,
    camStart: { azim: 28, elev: 12, dist: 5.4, target: [0, 0.85, 0.3] },
    camEnd:   { azim: -32, elev: 10, dist: 4.1, target: [0, 0.65, 0.0] },
    subEvents: [
      { t: 63, partId: 10 },
      { t: 68, partId: 9 },
      { t: 72, partId: 18 }
    ]
  },
  {
    id: 6,
    tStart: 75, tEnd: 90,
    title: "第六章 · 阶梯拆解工序 III (50%→75%)：双回路涡轮泵与两级超音速叶盘",
    narration: "【52兆瓦动力心脏】第三阶段拆解（50%→75%）剖开涡轮泵壳体：右侧展示低温液氧防气蚀螺旋诱导轮（#12）、双吸离心叶轮（#13）与迷宫密封座（#15）；左侧展示富氧预燃室（#06）、34,850 RPM 两级轴流透平转子盘（#14）与煤油主泵（#16）。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explodeRange: [50, 75], partId: 13,
    camStart: { azim: 54, elev: 16, dist: 5.5, target: [0.8, 1.55, 0.3] },
    camEnd:   { azim: -54, elev: 18, dist: 5.5, target: [-0.8, 1.65, -0.2] },
    subEvents: [
      { t: 77, partId: 12 },
      { t: 81, partId: 13 },
      { t: 85, partId: 14 },
      { t: 88, partId: 6 }
    ]
  },
  {
    id: 7,
    tStart: 90, tEnd: 105,
    title: "第七章 · 阶梯拆解工序 IV (75%→100%)：91孔同轴涡流喷注器与防振隔板",
    narration: "【微米级雾化与声学阻尼】第四阶段拆解（75%→100%）将喷注器穹顶向上顶开：彻底展露蜂窝状排布的 91 孔同轴涡流喷注面板（#07）与六边形抗高频燃烧振荡隔板（#08），有效抑制一阶切向高频声学不稳定燃烧。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explodeRange: [75, 100], partId: 7,
    camStart: { azim: 26, elev: 26, dist: 4.8, target: [0, 2.7, 0] },
    camEnd:   { azim: -28, elev: 22, dist: 4.3, target: [0, 2.4, 0] },
    subEvents: [
      { t: 98, partId: 8 }
    ]
  },
  {
    id: 8,
    tStart: 105, tEnd: 120,
    title: "第八章 · 全息线框扫描模式 (HOLO-SCAN) 与整机精密合拢",
    narration: "【全息无损探伤】切换至电光青全息线框扫描视图（Holo-Scan Mode）：水平激光扫描面沿 Y 轴往复扫掠激发截面轮廓高亮，全部 24 个子部件从 100% 完全拆解态按序同步复位合拢至 0% 标准试车状态。",
    mode: "holo", firing: true, flow: true, throttle: 100, explodeRange: [100, 0], partId: 19,
    camStart: { azim: -42, elev: 18, dist: 11.5, target: [0, 0.9, 0] },
    camEnd:   { azim:  42, elev: 12, dist: 10.2, target: [0, 0.5, 0] }
  },
  {
    id: 9,
    tStart: 120, tEnd: 135,
    title: "第九章 · 三路热力循环流光追踪与逆流再生冷却机制",
    narration: "【热力学逆流再生冷却】追踪三条流光着色器轨迹：常温 RP-1 煤油经喷管底部环形集液总管（#23）分流后，化作琥珀金脉冲沿 180 根螺旋钎焊管（#19）与 360 道铜内衬微槽自下而上逆流盘旋，冷却管壁后注入喷头与深蓝液氧、赤红富氧燃气汇合。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explode: 0, partId: 23,
    camStart: { azim: 32, elev: -4, dist: 6.2, target: [0, -1.5, 0] },
    camEnd:   { azim: -28, elev: 16, dist: 5.8, target: [0, 1.35, 0] },
    subEvents: [
      { t: 125, partId: 19 },
      { t: 130, partId: 17 }
    ]
  },
  {
    id: 10,
    tStart: 135, tEnd: 150,
    title: "第十章 · FLIR 红外热成像测温场分布 (90K 极冷至 3600K 极热)",
    narration: "【红外热像色谱分析】切换至 FLIR 红外热成像模式：直观呈现从右侧液氧涡轮泵 90K（-183℃）深蓝极冷区，到预燃室与透平排气深红高温区，再到拉瓦尔喉部（Ma=1.0）3600K 亮白紫核心热流峰值区的陡峭温度梯度。",
    mode: "flir", firing: true, flow: false, throttle: 108, explode: 0, partId: 18,
    camStart: { azim: 45, elev: 12, dist: 8.2, target: [0, 0.5, 0] },
    camEnd:   { azim: -35, elev: 10, dist: 7.4, target: [0, 0.3, 0] }
  },
  {
    id: 11,
    tStart: 150, tEnd: 165,
    title: "第十一章 · 深度变推力节流 (50%→115%)、马赫激波环与45°导流消音水幕",
    narration: "【超音速尾焰与消音水系统】恢复物理实感视图并执行 50%→115% 极限变推力拉偏测试：观察 FBM 湍流蓝白核心射流中的周期性马赫激波环（Mach Diamonds），高速燃气撞击 45° 双曲面耐磨导流槽并在双排 4.8 t/s 高压消音喷水阵列下翻卷起壮观白雾。",
    mode: "pbr", firing: true, flow: true, throttleRange: [50, 115], explode: 0, partId: 24,
    camStart: { azim: 24, elev: -6, dist: 10.5, target: [0, -3.4, 0.5] },
    camEnd:   { azim: 48, elev:  8, dist: 12.2, target: [0, -3.1, 0.8] }
  },
  {
    id: 12,
    tStart: 165, tEnd: 180,
    title: "第十二章 · TVC 矢量摆动闭环考核与试车圆满收官",
    narration: "【全系统总结巡礼】导览进入尾声：电液伺服作动筒驱动发动机完成 ±1.5° 俯仰与偏航推力矢量摆动考核，全部 24 个精密子部件温压遥测均处于安全包线内。您可以随时点击任意部件或拖动滑块继续自由探索。",
    mode: "pbr", firing: true, flow: true, throttle: 100, explode: 0, partId: 9,
    camStart: { azim: 42, elev: 12, dist: 12.8, target: [0, -0.2, 0] },
    camEnd:   { azim: 40, elev: 15, dist: 17.7, target: [0,  0.8, 0] },
    subEvents: [
      { t: 167, partId: 3, triggerSweep: true },
      { t: 173, partId: 9 }
    ]
  }
];

export { SYSTEMS_CATALOG, PARTS_BY_ID, createProceduralTextures, PART_CAMERA_PROFILES, TOUR_TOTAL_DURATION, TOUR_CHAPTERS };

export class LRETestStandBuilding {
  /**
   * @param {Object} options
   * @param {number} [options.tileX=0] 建筑中心所在《临河镇》X 格坐标
   * @param {number} [options.tileZ=-3] 建筑中心所在《临河镇》Z 格坐标
   * @param {number} [options.groundY=1.0] 建筑底部贴合的地面高度（高 1 土块顶面为 1.0）
   * @param {number} [options.scale=1.0] 整体缩放比例（默认 1.0，占地 16×14 格）
   */
  constructor(options = {}) {
    this.tileX = options.tileX ?? 0;
    this.tileZ = options.tileZ ?? -3.0;
    this.groundY = options.groundY ?? 1.0;
    this.scale = options.scale ?? 1.0;

    // 内部地基最低点为 -6.05，向上偏移 +6.05 使建筑底面严格贴合 root (0,0,0)
    this.baseOffsetY = 6.05;

    this.root = new THREE.Group();
    this.root.position.set(this.tileX, this.groundY, this.tileZ);
    this.root.scale.setScalar(this.scale);

    this.worldRoot = new THREE.Group();
    this.worldRoot.position.set(0, this.baseOffsetY, 0);
    this.root.add(this.worldRoot);

    this.testStandGroup = new THREE.Group();
    this.worldRoot.add(this.testStandGroup);

    this.gimbalPivot = new THREE.Group();
    this.gimbalPivot.position.set(0, 3.35, 0);
    this.worldRoot.add(this.gimbalPivot);

    this.plumeLight = new THREE.PointLight(0xff9933, 4.5, 24, 1.6);
    this.plumeLight.position.set(0, -3.5, 0);
    this.worldRoot.add(this.plumeLight);

    this.trenchBounceLight = new THREE.PointLight(0x55aaff, 2.8, 18, 1.8);
    this.trenchBounceLight.position.set(0, -5.2, 1.2);
    this.worldRoot.add(this.trenchBounceLight);

    this.partGroups = {};
    this.interactiveMeshes = [];
    this.spinningRotors = [];

    this.currentViewMode = 'pbr';
    this.isFiring = true;
    this.isFluidFlowVisible = true;
    this.throttleValue = 1.0;
    this.explodeProgress = 0.0;
    this.selectedPartId = 9;
    this.hoveredPartId = null;
    this.manualSweepTriggerTime = -999;

    const worldCenter = this.getWorldCenter();
    this.globalShaderUniforms = {
      uTime: { value: 0.0 },
      uScanY: { value: 0.0 },
      uThrottle: { value: 1.0 },
      uWorldCenter: { value: worldCenter }
    };

    this._initMaterials();
    this._buildGeometry();
    this._buildFluidCircuits();
    this._buildPlumeAndParticles();
  }

  /**
   * 获取 worldRoot 在《临河镇》世界坐标系中的中心点 (默认: (0, 7.05, -3.0))
   */
  getWorldCenter(target = new THREE.Vector3()) {
    return target.set(
      this.root.position.x,
      this.root.position.y + this.baseOffsetY * this.scale,
      this.root.position.z
    );
  }

  /**
   * 返回试车台地基占用的格子范围与高度，供《临河镇》地图寻路与碰撞层注册
   */
  getOccupiedTiles() {
    const tiles = [];
    for (let gx = Math.round(this.tileX - 8); gx <= Math.round(this.tileX + 8); gx++) {
      for (let gz = Math.round(this.tileZ - 7); gz <= Math.round(this.tileZ + 7); gz++) {
        tiles.push({ gx, gz, topY: this.groundY + 0.52 * this.scale });
      }
    }
    return tiles;
  }

  /**
   * 返回试车台二层维护平台的人物站立世界坐标点 (供主角或钦天监 NPC 站立巡检)
   */
  getPlatformStandPoint(side = 'left') {
    const x = side === 'left' ? -2.8 : 2.8;
    return new THREE.Vector3(
      this.tileX + x * this.scale,
      this.groundY + (this.baseOffsetY + 1.60) * this.scale,
      this.tileZ + 1.2 * this.scale
    );
  }

  _initMaterials() {
    const texLib = createProceduralTextures();
    this.holoMaterial = new THREE.ShaderMaterial({
      uniforms: this.globalShaderUniforms,
      vertexShader: `
        varying vec3 vWorldPos;
        varying vec3 vNormal;
        void main() {
          vec4 wp = modelMatrix * vec4(position, 1.0);
          vWorldPos = wp.xyz;
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * viewMatrix * wp;
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform float uScanY;
        uniform vec3 uWorldCenter;
        varying vec3 vWorldPos;
        varying vec3 vNormal;
        void main() {
          vec3 viewDir = normalize(cameraPosition - vWorldPos);
          float fresnel = pow(max(0.0001, 1.0 - abs(dot(viewDir, vNormal))), 2.2);
          float localY = vWorldPos.y - uWorldCenter.y;
          float scanDist = abs(localY - uScanY);
          float scanBeam = smoothstep(0.42, 0.0, scanDist);
          float scanCore = smoothstep(0.06, 0.0, scanDist);
          float gridY = step(0.92, fract(localY * 8.0));
          vec3 baseCol = vec3(0.0, 0.78, 1.0) * (0.22 + fresnel * 0.85 + gridY * 0.18);
          vec3 col = baseCol + vec3(0.25, 0.95, 1.0) * scanBeam * 0.9 + vec3(1.0) * scanCore;
          float alpha = clamp(0.28 + fresnel * 0.55 + scanBeam * 0.65, 0.2, 0.98);
          gl_FragColor = vec4(col, alpha);
        }
      `,
      transparent: true,
      wireframe: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    });

    this.flirMaterial = new THREE.ShaderMaterial({
      uniforms: this.globalShaderUniforms,
      vertexShader: `
        varying vec3 vWorldPos;
        varying vec3 vNormal;
        void main() {
          vec4 wp = modelMatrix * vec4(position, 1.0);
          vWorldPos = wp.xyz;
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * viewMatrix * wp;
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform float uThrottle;
        uniform vec3 uWorldCenter;
        varying vec3 vWorldPos;
        varying vec3 vNormal;
        vec3 flirPalette(float t) {
          t = clamp(t, 0.0, 1.0);
          vec3 c0 = vec3(0.04, 0.08, 0.45);
          vec3 c1 = vec3(0.45, 0.05, 0.65);
          vec3 c2 = vec3(0.92, 0.18, 0.08);
          vec3 c3 = vec3(1.00, 0.72, 0.05);
          vec3 c4 = vec3(0.98, 0.96, 1.00);
          if (t < 0.25) return mix(c0, c1, t / 0.25);
          if (t < 0.52) return mix(c1, c2, (t - 0.25) / 0.27);
          if (t < 0.80) return mix(c2, c3, (t - 0.52) / 0.28);
          return mix(c3, c4, (t - 0.80) / 0.20);
        }
        void main() {
          float y = vWorldPos.y - uWorldCenter.y;
          float lx = vWorldPos.x - uWorldCenter.x;
          float r = length(vWorldPos.xz - uWorldCenter.xz);
          float throatHeat = exp(-pow((y - 0.22) * 1.15, 2.0)) * exp(-max(0.0, r - 0.75) * 1.4);
          float nozzleHeat = smoothstep(-2.6, 0.2, y) * step(y, 0.25) * 0.68;
          float cryoZone = smoothstep(0.4, 1.3, lx) * smoothstep(0.6, 2.2, y) * 0.55;
          float preburnerHeat = smoothstep(-0.4, -1.3, lx) * smoothstep(0.7, 2.1, y) * 0.45;
          float tempNorm = (throatHeat * 0.95 + nozzleHeat * 0.45 + preburnerHeat - cryoZone + 0.22);
          tempNorm *= (0.35 + 0.65 * clamp(uThrottle, 0.0, 1.15));
          tempNorm += 0.025 * sin(y * 16.0 - uTime * 6.0);
          vec3 viewDir = normalize(cameraPosition - vWorldPos);
          float rim = pow(max(0.0001, 1.0 - abs(dot(viewDir, vNormal))), 1.8);
          vec3 col = flirPalette(tempNorm) + vec3(0.18, 0.12, 0.25) * rim;
          gl_FragColor = vec4(col, 1.0);
        }
      `
    });

    this.pbrMaterials = {
      steelBrushed: new THREE.MeshStandardMaterial({ color: 0xb8c4d0, metalness: 0.9, roughness: 0.22, bumpMap: texLib.brushedTex, bumpScale: 0.015 }),
      darkAlloy: new THREE.MeshStandardMaterial({ color: 0x3a434e, metalness: 0.86, roughness: 0.32, bumpMap: texLib.brushedTex, bumpScale: 0.02 }),
      inconelGold: new THREE.MeshStandardMaterial({ color: 0xc8aa78, metalness: 0.88, roughness: 0.26, bumpMap: texLib.brushedTex, bumpScale: 0.015 }),
      copperMilled: new THREE.MeshStandardMaterial({ map: texLib.milledCopperTex, bumpMap: texLib.milledCopperTex, bumpScale: 0.035, metalness: 0.92, roughness: 0.20 }),
      heatTint: new THREE.MeshStandardMaterial({ map: texLib.heatTintTex, metalness: 0.88, roughness: 0.24 }),
      carbonCOPV: new THREE.MeshStandardMaterial({ map: texLib.carbonTex, bumpMap: texLib.carbonTex, bumpScale: 0.025, metalness: 0.35, roughness: 0.42 }),
      brazedNozzle: new THREE.MeshStandardMaterial({ map: texLib.brazedNozzleTex, bumpMap: texLib.brazedNozzleTex, bumpScale: 0.03, metalness: 0.88, roughness: 0.28, side: THREE.DoubleSide }),
      cryoFrost: new THREE.MeshStandardMaterial({ color: 0xaadfff, metalness: 0.65, roughness: 0.35 }),
      sensorOrange: new THREE.MeshStandardMaterial({ color: 0xff6b1a, metalness: 0.45, roughness: 0.38 }),
      loadCellPiezoelectric: new THREE.MeshStandardMaterial({ color: 0x00d8ff, emissive: 0x003a4d, metalness: 0.8, roughness: 0.2 }),
      hazardArm: new THREE.MeshStandardMaterial({ map: texLib.hazardTex, metalness: 0.6, roughness: 0.4 }),
      trussSteel: new THREE.MeshStandardMaterial({ color: 0x2a333d, metalness: 0.78, roughness: 0.42 }),
      trenchAlloy: new THREE.MeshStandardMaterial({ color: 0x222830, metalness: 0.75, roughness: 0.48, side: THREE.DoubleSide })
    };
  }

  _buildGeometry() {
    const testStandGroup = this.testStandGroup;
    const gimbalPivot = this.gimbalPivot;
    const pbrMaterials = this.pbrMaterials;
    const partGroups = this.partGroups;
    const interactiveMeshes = this.interactiveMeshes;
    const spinningRotors = this.spinningRotors;

    function registerPartGroup(partId, parentGroup) {
      const grp = new THREE.Group();
      grp.userData = { partId: partId, meta: PARTS_BY_ID[partId], basePos: new THREE.Vector3(0, 0, 0) };
      parentGroup.add(grp);
      partGroups[partId] = grp;
      return grp;
    }

    function addPartMesh(partId, geometry, material, pos, rot, scale) {
      const grp = partGroups[partId];
      const mesh = new THREE.Mesh(geometry, material.clone());
      if (pos) mesh.position.set(pos[0], pos[1], pos[2]);
      if (rot) mesh.rotation.set(rot[0], rot[1], rot[2]);
      if (scale) mesh.scale.set(scale[0], scale[1], scale[2]);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData.partId = partId;
      mesh.userData.origMaterial = mesh.material;
      grp.add(mesh);
      interactiveMeshes.push(mesh);
      return mesh;
    }

    function makePipeGeo(pointsArray, radius, radialSegs = 12, tubularSegs = 36) {
      const vecs = pointsArray.map(p => new THREE.Vector3(p[0], p[1], p[2]));
      const curve = new THREE.CatmullRomCurve3(vecs);
      return new THREE.TubeGeometry(curve, tubularSegs, radius, radialSegs, false);
    }

    function buildExternalTestStand() {
  // 1. Heavy Ground Concrete/Steel Foundation Pad at Y = -5.55
  const padGeo = new THREE.BoxGeometry(16, 0.5, 14);
  const padMesh = new THREE.Mesh(padGeo, pbrMaterials.trussSteel);
  padMesh.position.set(0, -5.8, 0);
  padMesh.receiveShadow = true;
  testStandGroup.add(padMesh);

  // Subtle Reference Grid on Test Stand Floor
  const gridHelper = new THREE.GridHelper(16, 32, 0x00f0ff, 0x12304a);
  gridHelper.position.set(0, -5.54, 0);
  gridHelper.material.transparent = true;
  gridHelper.material.opacity = 0.35;
  testStandGroup.add(gridHelper);

  // 2. Four Heavy Vertical Test Stand Main Columns + Cross Bracing (Forming Load Closure)
  const colPositions = [
    [-3.6, -0.6, -2.8], [3.6, -0.6, -2.8],
    [-3.6, -0.6,  2.8], [3.6, -0.6,  2.8]
  ];
  const colGeo = new THREE.BoxGeometry(0.38, 10.2, 0.38);
  colPositions.forEach(p => {
    const col = new THREE.Mesh(colGeo, pbrMaterials.trussSteel);
    col.position.set(p[0], p[1], p[2]);
    col.castShadow = true;
    testStandGroup.add(col);
  });

  // Top Rectangular Ring Girder at Y = +4.45
  const beamXGeo = new THREE.BoxGeometry(7.6, 0.42, 0.42);
  const beamZGeo = new THREE.BoxGeometry(0.42, 0.42, 6.0);
  [-2.8, 2.8].forEach(z => {
    const bx = new THREE.Mesh(beamXGeo, pbrMaterials.trussSteel);
    bx.position.set(0, 4.45, z);
    testStandGroup.add(bx);
  });
  [-3.6, 3.6].forEach(x => {
    const bz = new THREE.Mesh(beamZGeo, pbrMaterials.trussSteel);
    bz.position.set(x, 4.45, 0);
    testStandGroup.add(bz);
  });

  // Diagonal K-Braces on Left & Right Sides
  for (let side of [-1, 1]) {
    const x = side * 3.6;
    for (let lvl = -4.0; lvl <= 2.0; lvl += 3.0) {
      const braceGeo = makePipeGeo([[x, lvl, -2.8], [x, lvl + 3.0, 2.8]], 0.09, 8, 8);
      const braceGeo2 = makePipeGeo([[x, lvl + 3.0, -2.8], [x, lvl, 2.8]], 0.09, 8, 8);
      testStandGroup.add(new THREE.Mesh(braceGeo, pbrMaterials.trussSteel));
      testStandGroup.add(new THREE.Mesh(braceGeo2, pbrMaterials.trussSteel));
    }
  }

  // Maintenance Platform Deck at Y = +1.6 (with central cutout)
  const deckLeft = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.1, 5.6), pbrMaterials.trussSteel);
  deckLeft.position.set(-2.8, 1.6, 0);
  const deckRight = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.1, 5.6), pbrMaterials.trussSteel);
  deckRight.position.set(2.8, 1.6, 0);
  testStandGroup.add(deckLeft, deckRight);

  // 3. Dynamic Propellant Umbilical Swing Arms (Left RP-1 & Right LOX with Yellow-Black Hazard Stripes)
  // Right Swing Arm -> LOX Disconnect Coupling
  const rightArmGroup = new THREE.Group();
  const rArmBeam = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.22, 0.26), pbrMaterials.hazardArm);
  rArmBeam.position.set(2.35, 2.05, 0.55);
  rArmBeam.rotation.y = 0.22;
  const rArmHinge = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.65, 16), pbrMaterials.darkAlloy);
  rArmHinge.position.set(3.5, 2.05, 0.8);
  const rFlexCryoHose = new THREE.Mesh(
    makePipeGeo([[3.45, 2.2, 0.8], [2.4, 2.35, 0.55], [1.42, 2.05, 0.32]], 0.11, 14, 28),
    pbrMaterials.cryoFrost
  );
  rightArmGroup.add(rArmBeam, rArmHinge, rFlexCryoHose);
  testStandGroup.add(rightArmGroup);

  // Left Swing Arm -> RP-1 Fuel Disconnect Coupling
  const leftArmGroup = new THREE.Group();
  const lArmBeam = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.22, 0.26), pbrMaterials.hazardArm);
  lArmBeam.position.set(-2.35, 1.85, 0.55);
  lArmBeam.rotation.y = -0.22;
  const lArmHinge = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.65, 16), pbrMaterials.darkAlloy);
  lArmHinge.position.set(-3.5, 1.85, 0.8);
  const lFlexFuelHose = new THREE.Mesh(
    makePipeGeo([[-3.45, 2.0, 0.8], [-2.4, 2.1, 0.55], [-1.42, 1.85, 0.32]], 0.10, 14, 28),
    pbrMaterials.inconelGold
  );
  leftArmGroup.add(lArmBeam, lArmHinge, lFlexFuelHose);
  testStandGroup.add(leftArmGroup);

  // 4. 45° Heavy Curved Abrasion-Resistant Flame Trench Deflector (Directly under Nozzle)
  // Nozzle Exit is at Y = -2.35, Diameter = 2.40m. Ground is at Y = -5.55 (Clearance = 3.20m = 1.33x Diameter).
  const trenchGroup = new THREE.Group();
  const chuteCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, -3.55, -1.85),
    new THREE.Vector3(0, -4.45, -0.95),
    new THREE.Vector3(0, -5.15,  0.25),
    new THREE.Vector3(0, -5.42,  2.20),
    new THREE.Vector3(0, -5.48,  4.80)
  ]);
  // Build thick double-curved deflector plate + side containment walls
  const chutePts = chuteCurve.getPoints(32);
  const chuteGeom = new THREE.BufferGeometry();
  const verts = [];
  const halfW = 2.15;
  for (let i = 0; i < chutePts.length - 1; i++) {
    const p0 = chutePts[i], p1 = chutePts[i + 1];
    verts.push(
      -halfW, p0.y, p0.z,  halfW, p0.y, p0.z,  halfW, p1.y, p1.z,
      -halfW, p0.y, p0.z,  halfW, p1.y, p1.z, -halfW, p1.y, p1.z
    );
  }
  chuteGeom.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  chuteGeom.computeVertexNormals();
  const chuteMesh = new THREE.Mesh(chuteGeom, pbrMaterials.trenchAlloy);
  chuteMesh.receiveShadow = true;
  trenchGroup.add(chuteMesh);

  // Side Containment Cheeks of the 45° Flame Deflector
  [-halfW, halfW].forEach(wx => {
    const wallBox = new THREE.Mesh(new THREE.BoxGeometry(0.28, 2.2, 6.6), pbrMaterials.trussSteel);
    wallBox.position.set(wx, -4.55, 1.3);
    wallBox.rotation.x = 0.25;
    trenchGroup.add(wallBox);
  });

  // 5. Two Rows of High-Pressure Sound Suppression Water Deluge Nozzles along Deflector Slopes
  for (let side of [-1, 1]) {
    const headerPipe = new THREE.Mesh(
      makePipeGeo([
        [side * 2.25, -3.4, -1.6],
        [side * 2.25, -4.3, -0.3],
        [side * 2.25, -5.0,  1.6],
        [side * 2.25, -5.2,  3.4]
      ], 0.12, 12, 24),
      pbrMaterials.loadCellPiezoelectric
    );
    trenchGroup.add(headerPipe);

    for (let k = 0; k < 6; k++) {
      const t = k / 5;
      const ny = -3.55 - t * 1.55;
      const nz = -1.4 + t * 4.4;
      const noz = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.34, 12), pbrMaterials.steelBrushed);
      noz.position.set(side * 2.02, ny, nz);
      noz.rotation.z = side * 1.15;
      noz.rotation.x = 0.35;
      trenchGroup.add(noz);
    }
  }

  testStandGroup.add(trenchGroup);
}

// ----------------------------------------------------------------------------
// SECTION B: 4 MECHANICAL SYSTEMS & 24 DETAILED SUB-COMPONENTS
// ----------------------------------------------------------------------------
function buildAll24EngineComponents() {
  // Register all 24 part groups:
  // Part #1 is anchored to testStandGroup (Top Inverted-Triangle Load Truss & 4 Load Cell Blocks)
  // Parts #2..#24 are mounted inside gimbalPivot (converted so world Y matches local Y + 3.35)
  registerPartGroup(1, testStandGroup);
  for (let id = 2; id <= 24; id++) {
    registerPartGroup(id, gimbalPivot);
  }

  // Helper to convert World Y to Gimbal-local Y (since gimbalPivot is at World Y = 3.35)
  const GY = (worldY) => worldY - 3.35;

  // ==========================================================================
  // [System 1: 推力矢量与进流系统] (Parts 1 - 5)
  // ==========================================================================

  // Part #1: 顶部倒三角承力桁架与4只压电测力计 (Load Cell Blocks & Inverted Triangle Truss)
  {
    // Central Thrust Bearing Plate at Y = 3.72
    addPartMesh(1, new THREE.CylinderGeometry(1.15, 0.95, 0.24, 24), pbrMaterials.darkAlloy, [0, 3.72, 0]);
    // Upper Main Load Ring at Y = 4.42
    addPartMesh(1, new THREE.CylinderGeometry(1.85, 1.85, 0.22, 8), pbrMaterials.trussSteel, [0, 4.42, 0]);
    // Inverted Triangle Struts (8 heavy diagonal struts from top frame corners & ring down to load plate)
    const corners = [
      [-3.5, 4.45, -2.7], [3.5, 4.45, -2.7],
      [-3.5, 4.45,  2.7], [3.5, 4.45,  2.7],
      [-1.75, 4.42, 0],   [1.75, 4.42, 0],
      [0, 4.42, -1.75],   [0, 4.42,  1.75]
    ];
    corners.forEach(c => {
      const strutGeo = makePipeGeo([c, [c[0] * 0.22, 3.75, c[2] * 0.22]], 0.085, 10, 8);
      addPartMesh(1, strutGeo, pbrMaterials.steelBrushed);
    });
    // 4 Disc-Shaped Piezoelectric Load Cell Sensor Blocks directly above the Universal Gimbal
    const loadCellAngles = [0, Math.PI / 2, Math.PI, Math.PI * 1.5];
    loadCellAngles.forEach(ang => {
      const lx = Math.cos(ang) * 0.58;
      const lz = Math.sin(ang) * 0.58;
      addPartMesh(1, new THREE.CylinderGeometry(0.24, 0.24, 0.18, 24), pbrMaterials.loadCellPiezoelectric, [lx, 3.54, lz]);
      addPartMesh(1, new THREE.TorusGeometry(0.24, 0.025, 10, 24), pbrMaterials.inconelGold, [lx, 3.54, lz], [Math.PI / 2, 0, 0]);
    });
  }

  // Part #2: 双向万向十字铰链球轴承 (Universal Gimbal Joint at World Y = 3.35 -> Local Y = 0)
  {
    addPartMesh(2, new THREE.SphereGeometry(0.36, 28, 28), pbrMaterials.steelBrushed, [0, 0, 0]);
    addPartMesh(2, new THREE.TorusGeometry(0.46, 0.075, 16, 32), pbrMaterials.inconelGold, [0, 0, 0], [Math.PI / 2, 0, 0]);
    // Cross trunnion pins
    addPartMesh(2, new THREE.CylinderGeometry(0.09, 0.09, 1.15, 16), pbrMaterials.darkAlloy, [0, 0, 0], [0, 0, Math.PI / 2]);
    addPartMesh(2, new THREE.CylinderGeometry(0.09, 0.09, 1.15, 16), pbrMaterials.darkAlloy, [0, 0, 0], [Math.PI / 2, 0, 0]);
    // Thrust Mount Cone connecting gimbal to injector dome
    addPartMesh(2, new THREE.CylinderGeometry(0.35, 0.78, 0.75, 24), pbrMaterials.darkAlloy, [0, GY(2.90), 0]);
  }

  // Part #3: 双通道电液伺服作动筒 (TVC Pitch/Yaw Hydraulic Actuators + Servo Valves)
  {
    const actConfigs = [
      { top: [1.35, GY(3.60), 0.0], bot: [0.82, GY(2.25), 0.0] },
      { top: [0.0, GY(3.60), 1.35], bot: [0.0, GY(2.25), 0.82] },
      { top: [-1.35, GY(3.60), 0.0], bot: [-0.82, GY(2.25), 0.0] },
      { top: [0.0, GY(3.60), -1.35], bot: [0.0, GY(2.25), -0.82] }
    ];
    actConfigs.forEach(cfg => {
      const mid = [
        (cfg.top[0] + cfg.bot[0]) * 0.5,
        (cfg.top[1] + cfg.bot[1]) * 0.5,
        (cfg.top[2] + cfg.bot[2]) * 0.5
      ];
      // Outer hydraulic cylinder barrel
      addPartMesh(3, makePipeGeo([cfg.top, mid], 0.095, 14, 10), pbrMaterials.inconelGold);
      // Chrome piston rod
      addPartMesh(3, makePipeGeo([mid, cfg.bot], 0.055, 14, 10), pbrMaterials.steelBrushed);
      // MOOG Servo Valve block mounted on cylinder
      addPartMesh(3, new THREE.BoxGeometry(0.18, 0.22, 0.18), pbrMaterials.sensorOrange, mid);
    });
  }

  // Part #4: 碳纤维缠绕高压氦气气瓶组 (4x COPV Helium Tanks)
  {
    const copvOffsets = [
      [-1.12, GY(2.65), -0.52], [-1.12, GY(2.65), 0.52],
      [ 1.12, GY(2.65), -0.52]
    ];
    copvOffsets.forEach(pos => {
      addPartMesh(4, new THREE.CylinderGeometry(0.24, 0.24, 0.72, 24), pbrMaterials.carbonCOPV, pos);
      addPartMesh(4, new THREE.SphereGeometry(0.24, 24, 16), pbrMaterials.carbonCOPV, [pos[0], pos[1] + 0.36, pos[2]]);
      addPartMesh(4, new THREE.SphereGeometry(0.24, 24, 16), pbrMaterials.carbonCOPV, [pos[0], pos[1] - 0.36, pos[2]]);
      addPartMesh(4, new THREE.CylinderGeometry(0.06, 0.08, 0.18, 12), pbrMaterials.inconelGold, [pos[0], pos[1] + 0.62, pos[2]]);
    });
  }

  // Part #5: 快速脱落推进剂加注接头 (Umbilical Disconnect Couplings - LOX Right & RP-1 Left)
  {
    // LOX Quick-Disconnect on Right (+X)
    addPartMesh(5, new THREE.CylinderGeometry(0.22, 0.22, 0.36, 20), pbrMaterials.cryoFrost, [1.38, GY(2.05), 0.32], [0, 0, Math.PI / 2]);
    addPartMesh(5, new THREE.TorusGeometry(0.24, 0.04, 12, 24), pbrMaterials.steelBrushed, [1.45, GY(2.05), 0.32], [0, Math.PI / 2, 0]);
    // RP-1 Quick-Disconnect on Left (-X)
    addPartMesh(5, new THREE.CylinderGeometry(0.20, 0.20, 0.36, 20), pbrMaterials.inconelGold, [-1.38, GY(1.85), 0.32], [0, 0, Math.PI / 2]);
    addPartMesh(5, new THREE.TorusGeometry(0.22, 0.04, 12, 24), pbrMaterials.steelBrushed, [-1.45, GY(1.85), 0.32], [0, Math.PI / 2, 0]);
  }

  // ==========================================================================
  // [System 2: 燃烧室与喷注系统] (Parts 6 - 11)
  // ==========================================================================

  // Part #6: 富氧预燃室/燃气发生器总成 (Oxygen-Rich Preburner Assembly)
  {
    const pbPos = [-0.98, GY(2.15), -0.48];
    addPartMesh(6, new THREE.SphereGeometry(0.32, 24, 20), pbrMaterials.heatTint, [pbPos[0], pbPos[1] + 0.28, pbPos[2]]);
    addPartMesh(6, new THREE.CylinderGeometry(0.30, 0.26, 0.56, 24), pbrMaterials.inconelGold, pbPos);
    addPartMesh(6, new THREE.TorusGeometry(0.32, 0.045, 12, 24), pbrMaterials.steelBrushed, [pbPos[0], pbPos[1] + 0.18, pbPos[2]], [Math.PI / 2, 0, 0]);
  }

  // Part #7: 91孔同轴涡流喷注器内腔面板 (Coaxial Injector Faceplate - 91 Micro-Elements)
  {
    const injY = GY(1.62);
    addPartMesh(7, new THREE.CylinderGeometry(0.68, 0.68, 0.14, 36), pbrMaterials.inconelGold, [0, injY, 0]);
    addPartMesh(7, new THREE.SphereGeometry(0.68, 32, 18, 0, Math.PI * 2, 0, Math.PI * 0.5), pbrMaterials.steelBrushed, [0, injY + 0.07, 0]);
    // Build concentric rings of coaxial swirl injector nozzles (1 + 6 + 12 + 18 + 24 + 30 = 91 elements!)
    const ringCounts = [1, 6, 12, 18, 24, 30];
    const nozElemGeo = new THREE.CylinderGeometry(0.022, 0.018, 0.09, 8);
    ringCounts.forEach((cnt, rIdx) => {
      const rad = rIdx * 0.105;
      for (let k = 0; k < cnt; k++) {
        const a = (k / cnt) * Math.PI * 2;
        const nx = (rIdx === 0) ? 0 : Math.cos(a) * rad;
        const nz = (rIdx === 0) ? 0 : Math.sin(a) * rad;
        addPartMesh(7, nozElemGeo, pbrMaterials.copperMilled, [nx, injY - 0.09, nz]);
      }
    });
  }

  // Part #8: 六边形抗高频燃烧振荡隔板 (Hexagonal Acoustic Baffles)
  {
    const bafY = GY(1.44);
    // Central Hexagonal Ring + 6 Radial Acoustic Damping Blades
    addPartMesh(8, new THREE.CylinderGeometry(0.28, 0.28, 0.18, 6, 1, true), pbrMaterials.copperMilled, [0, bafY, 0]);
    for (let i = 0; i < 6; i++) {
      const ang = (i / 6) * Math.PI * 2;
      const bx = Math.cos(ang) * 0.44;
      const bz = Math.sin(ang) * 0.44;
      addPartMesh(8, new THREE.BoxGeometry(0.34, 0.17, 0.028), pbrMaterials.copperMilled, [bx, bafY, bz], [0, -ang, 0]);
    }
  }

  // Part #9: 铣槽铬锆铜内衬 (360道高深宽比再生冷却微槽道，CuCrZr Milled Liner)
  {
    // Lathe profile from Injector (Y=1.55) down through Combustor cylinder and Throat (Y=0.25) to upper Nozzle (Y=-0.15)
    const linerPts = [
      new THREE.Vector2(0.66, GY(-0.15)),
      new THREE.Vector2(0.46, GY(0.25)), // Throat Ma=1
      new THREE.Vector2(0.55, GY(0.52)),
      new THREE.Vector2(0.68, GY(0.82)),
      new THREE.Vector2(0.68, GY(1.55))
    ];
    const linerGeo = new THREE.LatheGeometry(linerPts, 48);
    addPartMesh(9, linerGeo, pbrMaterials.copperMilled);
  }

  // Part #10: 燃烧室高强承力外夹套 (含12道轴向加强肋与高压测压孔)
  {
    const jacketPts = [
      new THREE.Vector2(0.70, GY(-0.12)),
      new THREE.Vector2(0.52, GY(0.25)),
      new THREE.Vector2(0.73, GY(0.80)),
      new THREE.Vector2(0.73, GY(1.56))
    ];
    // Split into Front & Back Clamshell halves for dramatic explosion
    const halfJacketGeo = new THREE.LatheGeometry(jacketPts, 36);
    addPartMesh(10, halfJacketGeo, pbrMaterials.steelBrushed);

    // 12 Axial Strengthening Ribs around the Combustor Jacket
    for (let i = 0; i < 12; i++) {
      const ang = (i / 12) * Math.PI * 2;
      const rx = Math.cos(ang) * 0.74;
      const rz = Math.sin(ang) * 0.74;
      addPartMesh(10, new THREE.BoxGeometry(0.045, 0.78, 0.08), pbrMaterials.darkAlloy, [rx, GY(1.16), rz], [0, -ang, 0]);
    }
    // Upper & Lower Structural Bolted Flanges
    addPartMesh(10, new THREE.TorusGeometry(0.75, 0.055, 12, 36), pbrMaterials.inconelGold, [0, GY(1.54), 0], [Math.PI / 2, 0, 0]);
    addPartMesh(10, new THREE.TorusGeometry(0.75, 0.05, 12, 36), pbrMaterials.inconelGold, [0, GY(0.82), 0], [Math.PI / 2, 0, 0]);
  }

  // Part #11: 周向高频压力传感器与热电偶线束阵列 (Sensor Bosses & Wiring Harness)
  {
    for (let i = 0; i < 8; i++) {
      const ang = (i / 8) * Math.PI * 2 + 0.26;
      const sx = Math.cos(ang) * 0.78;
      const sz = Math.sin(ang) * 0.78;
      addPartMesh(11, new THREE.CylinderGeometry(0.035, 0.035, 0.14, 12), pbrMaterials.sensorOrange, [sx, GY(1.18), sz], [0, 0, Math.PI / 2], [1, 1, 1]);
    }
    // Circumferential Orange Polyimide Braided Harness Rings + Vertical Trunk
    addPartMesh(11, new THREE.TorusGeometry(0.79, 0.022, 10, 36), pbrMaterials.sensorOrange, [0, GY(1.30), 0], [Math.PI / 2, 0, 0]);
    addPartMesh(11, new THREE.TorusGeometry(0.79, 0.022, 10, 36), pbrMaterials.sensorOrange, [0, GY(1.02), 0], [Math.PI / 2, 0, 0]);
    const harnessTrunk = makePipeGeo([
      [0.0, GY(1.52), -0.80],
      [0.0, GY(1.00), -0.82],
      [0.0, GY(0.25), -0.62],
      [0.0, GY(-0.65), -0.88]
    ], 0.028, 10, 24);
    addPartMesh(11, harnessTrunk, pbrMaterials.sensorOrange);
  }

  // ==========================================================================
  // [System 3: 双回路涡轮泵动力系统] (Parts 12 - 17)
  // ==========================================================================

  // Part #12: 低温液氧螺旋防气蚀诱导轮 (Cryogenic LOX Anti-Cavitation Inducer - Right +X Side)
  {
    const indPos = [1.02, GY(1.82), 0.25];
    const hub = addPartMesh(12, new THREE.CylinderGeometry(0.08, 0.11, 0.34, 16), pbrMaterials.cryoFrost, indPos);
    spinningRotors.push(hub);
    for (let b = 0; b < 4; b++) {
      const blade = addPartMesh(12, new THREE.TorusGeometry(0.18, 0.022, 8, 20, Math.PI * 0.85), pbrMaterials.steelBrushed,
        [indPos[0], indPos[1] - 0.08 + b * 0.05, indPos[2]], [Math.PI * 0.38, b * Math.PI * 0.5, 0]);
      spinningRotors.push(blade);
    }
  }

  // Part #13: 双吸闭式离心高压叶轮与蜗壳 (Centrifugal Impeller & Spiral Volute)
  {
    const pumpPos = [1.02, GY(1.42), 0.25];
    // Impeller disc & vanes (exposed when turbopump casing explodes at 50-75%)
    const impDisc = addPartMesh(13, new THREE.CylinderGeometry(0.28, 0.28, 0.14, 24), pbrMaterials.inconelGold, pumpPos);
    spinningRotors.push(impDisc);
    for (let v = 0; v < 8; v++) {
      const a = (v / 8) * Math.PI * 2;
      const vane = addPartMesh(13, new THREE.BoxGeometry(0.24, 0.16, 0.025), pbrMaterials.steelBrushed,
        [pumpPos[0] + Math.cos(a) * 0.12, pumpPos[1], pumpPos[2] + Math.sin(a) * 0.12], [0, a + 0.5, 0]);
      spinningRotors.push(vane);
    }
    // Outer Spiral Volute Scroll Casing
    addPartMesh(13, new THREE.TorusGeometry(0.32, 0.13, 18, 32), pbrMaterials.cryoFrost, pumpPos, [Math.PI / 2, 0, 0]);
  }

  // Part #14: 两级高温燃气轴流透平转子盘 (Two-Stage Supersonic Blisk Turbine - Left -X Side)
  {
    const turbPos = [-0.98, GY(1.52), -0.48];
    for (let stage = 0; stage < 2; stage++) {
      const sy = turbPos[1] + (stage === 0 ? 0.12 : -0.12);
      const disk = addPartMesh(14, new THREE.CylinderGeometry(0.26, 0.26, 0.07, 24), pbrMaterials.inconelGold, [turbPos[0], sy, turbPos[2]]);
      spinningRotors.push(disk);
      for (let b = 0; b < 18; b++) {
        const ang = (b / 18) * Math.PI * 2;
        const bx = turbPos[0] + Math.cos(ang) * 0.30;
        const bz = turbPos[2] + Math.sin(ang) * 0.30;
        const blade = addPartMesh(14, new THREE.BoxGeometry(0.09, 0.08, 0.018), pbrMaterials.heatTint, [bx, sy, bz], [0.35, -ang, 0]);
        spinningRotors.push(blade);
      }
    }
  }

  // Part #15: 动压石墨碳环与迷宫式密封座 (Shaft Seal Housing)
  {
    const sealPos = [1.02, GY(1.12), 0.25];
    addPartMesh(15, new THREE.CylinderGeometry(0.22, 0.25, 0.26, 24), pbrMaterials.darkAlloy, sealPos);
    for (let r = 0; r < 3; r++) {
      addPartMesh(15, new THREE.TorusGeometry(0.24, 0.02, 10, 24), pbrMaterials.inconelGold, [sealPos[0], sealPos[1] - 0.07 + r * 0.07, sealPos[2]], [Math.PI / 2, 0, 0]);
    }
  }

  // Part #16: 煤油燃料主泵与行星减速箱 (RP-1 Fuel Turbopump & Planetary Gearbox)
  {
    const rpPos = [-1.02, GY(1.38), 0.35];
    addPartMesh(16, new THREE.CylinderGeometry(0.32, 0.34, 0.48, 24), pbrMaterials.darkAlloy, rpPos);
    addPartMesh(16, new THREE.TorusGeometry(0.34, 0.10, 16, 28), pbrMaterials.inconelGold, [rpPos[0], rpPos[1] - 0.12, rpPos[2]], [Math.PI / 2, 0, 0]);
    // High-pressure RP-1 Downcomer Line from Fuel Pump down to Nozzle Bottom Collector Ring
    const rpDownPipe = makePipeGeo([
      [-1.02, GY(1.12), 0.35],
      [-1.18, GY(0.45), 0.42],
      [-1.15, GY(-0.75), 0.38],
      [-1.22, GY(-1.95), 0.15]
    ], 0.068, 12, 28);
    addPartMesh(16, rpDownPipe, pbrMaterials.inconelGold);
  }

  // Part #17: 涡轮排气环形集气总管与侧向排放喷管 (Turbine Exhaust Manifold & Heat-Tint Duct)
  {
    // Hot gas duct from Turbine (-0.98, 1.35, -0.48) sweeping up into Combustor Injector Dome (0, 1.85, 0)
    const hotGasDuct = makePipeGeo([
      [-0.98, GY(1.22), -0.48],
      [-0.85, GY(1.68), -0.62],
      [-0.45, GY(2.02), -0.35],
      [ 0.0,  GY(1.92),  0.0]
    ], 0.135, 16, 32);
    addPartMesh(17, hotGasDuct, pbrMaterials.heatTint);
    // Auxiliary Heat-Exchanger Exhaust Stub
    const auxExhaust = makePipeGeo([
      [-0.98, GY(1.18), -0.55],
      [-1.25, GY(0.45), -0.78],
      [-1.32, GY(-0.85), -0.82]
    ], 0.075, 12, 24);
    addPartMesh(17, auxExhaust, pbrMaterials.heatTint);
  }

  // ==========================================================================
  // [System 4: 喷管与超音速膨胀控制系统] (Parts 18 - 24)
  // ==========================================================================

  // Part #18: 超音速喉部收敛-扩散法兰段 (Supersonic Throat Assembly at Y = +0.25)
  {
    const throatPts = [
      new THREE.Vector2(0.67, GY(-0.14)),
      new THREE.Vector2(0.51, GY(0.25)),
      new THREE.Vector2(0.66, GY(0.65))
    ];
    addPartMesh(18, new THREE.LatheGeometry(throatPts, 36), pbrMaterials.darkAlloy);
    addPartMesh(18, new THREE.TorusGeometry(0.54, 0.055, 14, 36), pbrMaterials.inconelGold, [0, GY(0.25), 0], [Math.PI / 2, 0, 0]);
  }

  // Part #19: 180根螺旋薄壁冷却钢管精密钎焊扩散喷管 (Brazed Tube Bell Nozzle: Y = -0.12 down to Y = -2.35, Exit Radius = 1.20m -> Diameter = 2.40m)
  {
    const bellPts = [];
    const steps = 28;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps; // 0 at top (-0.12), 1 at exit (-2.35)
      const wy = -0.12 - t * 2.23;
      // Rao Parabolic Bell Contour from r=0.64m to r=1.20m
      const r = 0.64 + 0.56 * (1.0 - Math.pow(1.0 - t, 1.55));
      bellPts.push(new THREE.Vector2(r, GY(wy)));
    }
    const bellGeo = new THREE.LatheGeometry(bellPts, 64);
    addPartMesh(19, bellGeo, pbrMaterials.brazedNozzle);
  }

  // Part #20: 主液氧气动截止阀组 (Main LOX Pneumatic Shutoff Valve)
  {
    const loxValvePos = [0.85, GY(1.88), -0.35];
    addPartMesh(20, new THREE.SphereGeometry(0.21, 20, 20), pbrMaterials.cryoFrost, loxValvePos);
    addPartMesh(20, new THREE.CylinderGeometry(0.14, 0.14, 0.32, 16), pbrMaterials.inconelGold, [loxValvePos[0] + 0.18, loxValvePos[1] + 0.15, loxValvePos[2]], [0, 0, -0.7]);
    // Main LOX Feedline connecting Pump to Injector Dome & Preburner
    const loxMainPipe = makePipeGeo([
      [1.02, GY(1.42), 0.25],
      [0.85, GY(1.88), -0.35],
      [0.32, GY(2.05), -0.12],
      [0.0,  GY(1.82),  0.0]
    ], 0.105, 14, 28);
    addPartMesh(20, loxMainPipe, pbrMaterials.cryoFrost);
  }

  // Part #21: 主煤油节流调节蝶阀 (RP-1 Throttle Control Butterfly Valve)
  {
    const thrPos = [-1.16, GY(0.65), 0.40];
    addPartMesh(21, new THREE.CylinderGeometry(0.16, 0.16, 0.24, 20), pbrMaterials.inconelGold, thrPos);
    addPartMesh(21, new THREE.BoxGeometry(0.26, 0.18, 0.22), pbrMaterials.sensorOrange, [thrPos[0] - 0.18, thrPos[1], thrPos[2]]);
  }

  // Part #22: 多层不锈钢高压编织金属网波纹膨胀节 (Braided Metal Bellows)
  {
    const bellowLocations = [
      [0.92, GY(1.65), -0.05],
      [-0.90, GY(1.65), -0.58],
      [-1.16, GY(-0.20), 0.39]
    ];
    bellowLocations.forEach(bpos => {
      addPartMesh(22, new THREE.CylinderGeometry(0.13, 0.13, 0.30, 20), pbrMaterials.steelBrushed, bpos);
      for (let k = -2; k <= 2; k++) {
        addPartMesh(22, new THREE.TorusGeometry(0.135, 0.022, 10, 24), pbrMaterials.inconelGold, [bpos[0], bpos[1] + k * 0.055, bpos[2]], [Math.PI / 2, 0, 0]);
      }
    });
  }

  // Part #23: 再生冷却环形分配集液主管 (Toroidal Fuel Inlet Ring at Y = -1.98)
  {
    addPartMesh(23, new THREE.TorusGeometry(1.16, 0.085, 18, 48), pbrMaterials.inconelGold, [0, GY(-1.98), 0], [Math.PI / 2, 0, 0]);
    // Upper Return Collector Manifold Ring at Combustor Head (Y = +1.48)
    addPartMesh(23, new THREE.TorusGeometry(0.76, 0.065, 16, 40), pbrMaterials.copperMilled, [0, GY(1.48), 0], [Math.PI / 2, 0, 0]);
  }

  // Part #24: 喷管外部环向防振加强套箍 (Nozzle Stiffener Rings - 5 Stepped Hat-Section Rings)
  {
    const ringWorldYs = [-0.45, -0.88, -1.32, -1.72, -2.28];
    ringWorldYs.forEach((wy) => {
      const t = (-0.12 - wy) / 2.23;
      const r = 0.64 + 0.56 * (1.0 - Math.pow(1.0 - t, 1.55)) + 0.03;
      addPartMesh(24, new THREE.TorusGeometry(r, 0.042, 12, 48), pbrMaterials.darkAlloy, [0, GY(wy), 0], [Math.PI / 2, 0, 0]);
    });
  }
}

    buildExternalTestStand();
    buildAll24EngineComponents();
  }

  _buildFluidCircuits() {
    const fluidFlowGroup = new THREE.Group();
    this.fluidFlowGroup = fluidFlowGroup;
    this.gimbalPivot.add(fluidFlowGroup);

    const fluidShaderUniforms = {
      uTime: { value: 0.0 },
      uSpeed: { value: 1.0 }
    };
    this.fluidShaderUniforms = fluidShaderUniforms;

function createFluidTrailTube(pointsWorld, colorHex, speedSign = 1.0, radius = 0.032) {
  const GY = (wy) => wy - 3.35;
  const pts = pointsWorld.map(p => new THREE.Vector3(p[0], GY(p[1]), p[2]));
  const curve = new THREE.CatmullRomCurve3(pts);
  const geo = new THREE.TubeGeometry(curve, 64, radius, 8, false);
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uTime: fluidShaderUniforms.uTime,
      uSpeed: fluidShaderUniforms.uSpeed,
      uColor: { value: new THREE.Color(colorHex) },
      uDir: { value: speedSign }
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float uTime;
      uniform float uSpeed;
      uniform vec3 uColor;
      uniform float uDir;
      varying vec2 vUv;
      void main() {
        float phase = fract(vUv.x * 6.0 - uTime * 1.8 * uSpeed * uDir);
        float pulse = pow(max(0.0001, sin(phase * 3.14159265)), 3.2);
        float core = smoothstep(0.2, 0.95, pulse);
        vec3 col = uColor * (0.45 + 1.85 * core);
        float alpha = 0.25 + 0.72 * core;
        gl_FragColor = vec4(col, alpha);
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  });
  const mesh = new THREE.Mesh(geo, mat);
  fluidFlowGroup.add(mesh);
  return mesh;
}

function buildPropellantFluidCircuits() {
  // 1. Deep Blue Electric Flow (-183℃ LOX Circuit): Umbilical -> LOX Inducer/Pump -> Main LOX Valve -> Injector Dome & Preburner
  createFluidTrailTube([
    [1.42, 2.05, 0.32],
    [1.02, 1.82, 0.25],
    [1.02, 1.42, 0.25],
    [0.85, 1.88, -0.35],
    [0.32, 2.05, -0.12],
    [0.0,  1.72,  0.0]
  ], 0x00e5ff, 1.0, 0.042);

  // Branch of LOX to Preburner
  createFluidTrailTube([
    [0.85, 1.88, -0.35],
    [0.0,  2.22, -0.45],
    [-0.98, 2.38, -0.48]
  ], 0x00e5ff, 1.0, 0.032);

  // 2. Amber-Gold Pulsing Flow (RP-1 Kerosene Circuit):
  // Left Umbilical -> Fuel Pump -> Downcomer Pipe -> Toroidal Bottom Collector Ring (Y=-1.98)
  createFluidTrailTube([
    [-1.42, 1.85, 0.32],
    [-1.02, 1.38, 0.35],
    [-1.18, 0.45, 0.42],
    [-1.15, -0.75, 0.38],
    [-1.16, -1.98, 0.12]
  ], 0xffaa00, 1.0, 0.038);

  // Counter-Flow Regenerative Cooling Spiral Paths! (Bottom Collector Ring Y=-1.98 spiraling UPWARD along nozzle & 360 liner channels to Injector Head Y=+1.55)
  const spiralCount = 12; // 12 luminous representative bundles illustrating the 360 micro-channels
  for (let s = 0; s < spiralCount; s++) {
    const baseAngle = (s / spiralCount) * Math.PI * 2;
    const spiralPts = [];
    const segs = 22;
    for (let i = 0; i <= segs; i++) {
      const u = i / segs; // 0 at bottom ring (-1.98), 1 at injector head (+1.52)
      const wy = -1.98 + u * 3.50;
      let r = 0.69;
      if (wy < -0.12) {
        const tn = (-0.12 - wy) / 2.23;
        r = 0.65 + 0.56 * (1.0 - Math.pow(1.0 - tn, 1.55));
      } else if (wy < 0.25) {
        r = 0.48 + Math.abs(wy - 0.25) * 0.42;
      } else if (wy < 0.82) {
        r = 0.48 + ((wy - 0.25) / 0.57) * 0.21;
      } else {
        r = 0.70;
      }
      const ang = baseAngle + u * Math.PI * 1.65;
      spiralPts.push([Math.cos(ang) * r, wy, Math.sin(ang) * r]);
    }
    createFluidTrailTube(spiralPts, 0xffaa00, 1.0, 0.016);
  }

  // 3. Crimson-Gold Glowing Pulse (Oxygen-Rich Hot Gas Circuit): Preburner -> Two-Stage Blisk Turbine -> Exhaust Manifold -> Injector Dome
  createFluidTrailTube([
    [-0.98, 2.35, -0.48],
    [-0.98, 1.52, -0.48],
    [-0.98, 1.22, -0.48],
    [-0.85, 1.68, -0.62],
    [-0.45, 2.02, -0.35],
    [0.0,   1.85,  0.0]
  ], 0xff3344, 1.25, 0.046);
}


    buildPropellantFluidCircuits();
  }

  _buildPlumeAndParticles() {
    this.plumeGroup = new THREE.Group();
    this.plumeGroup.position.set(0, -2.35 - 3.35, 0);
    this.gimbalPivot.add(this.plumeGroup);

    this.plumeUniforms = {
      uTime: { value: 0.0 },
      uThrottle: { value: 1.0 }
    };

    const corePlumeGeo = new THREE.CylinderGeometry(1.12, 0.42, 4.2, 48, 64, true);
    corePlumeGeo.translate(0, -2.1, 0);
    const corePlumeMat = new THREE.ShaderMaterial({
      uniforms: this.plumeUniforms,
      vertexShader: `
        uniform float uTime;
        uniform float uThrottle;
        varying vec2 vUv;
        void main() {
          vUv = uv;
          float depth = 1.0 - uv.y;
          float shockWave = sin(depth * 24.0 - uTime * 22.0) * 0.055 * depth;
          float flutter = sin(depth * 15.0 - uTime * 35.0 + position.x * 4.0) * 0.03 * depth;
          vec3 p = position;
          p.xz *= (1.0 + shockWave + flutter) * mix(0.45, 1.05, clamp(uThrottle, 0.0, 1.15));
          p.y *= mix(0.35, 1.08, clamp(uThrottle, 0.0, 1.15));
          gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform float uThrottle;
        varying vec2 vUv;
        float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
        float noise(vec2 p) {
          vec2 i = floor(p); vec2 f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
          return mix(mix(hash(i + vec2(0.0,0.0)), hash(i + vec2(1.0,0.0)), u.x),
                     mix(hash(i + vec2(0.0,1.0)), hash(i + vec2(1.0,1.0)), u.x), u.y);
        }
        float fbm(vec2 p) {
          float v = 0.0; float a = 0.5;
          for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.05; a *= 0.5; }
          return v;
        }
        void main() {
          if (uThrottle <= 0.01) discard;
          float depth = 1.0 - vUv.y;
          float turb = fbm(vec2(vUv.x * 10.0, depth * 8.0 - uTime * 9.5));
          float machWave = abs(sin(depth * 3.14159265 * 5.5));
          float machNode = pow(max(0.0001, 1.0 - machWave), 3.2);
          float axialFade = smoothstep(1.0, 0.05, depth);
          vec3 col = mix(vec3(1.0, 0.55, 0.12), vec3(0.35, 0.78, 1.0), axialFade * 0.85 + turb * 0.25);
          col = mix(col, vec3(0.95, 0.98, 1.0) * 1.9, machNode * axialFade * 0.92);
          float alpha = axialFade * (0.48 + machNode * 0.48 + turb * 0.22) * clamp(uThrottle, 0.0, 1.15);
          gl_FragColor = vec4(col, clamp(alpha, 0.0, 0.96));
        }
      `,
      transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
    });
    this.plumeGroup.add(new THREE.Mesh(corePlumeGeo, corePlumeMat));

    const PARTICLE_COUNT = 520;
    this.pGeo = new THREE.BufferGeometry();
    const pPositions = new Float32Array(PARTICLE_COUNT * 3);
    const pColors = new Float32Array(PARTICLE_COUNT * 3);
    this.pVelocities = [];
    this.pTypes = [];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const isSteam = i >= 220;
      this.pTypes.push(isSteam ? 1 : 0);
      this.pVelocities.push({ vx: 0, vy: -9.0, vz: 0, life: Math.random() });
      pColors[i * 3] = isSteam ? 0.78 : 1.0;
      pColors[i * 3 + 1] = isSteam ? 0.92 : 0.78;
      pColors[i * 3 + 2] = isSteam ? 1.0 : 0.35;
    }
    this.pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions, 3));
    this.pGeo.setAttribute('color', new THREE.BufferAttribute(pColors, 3));

    const pMat = new THREE.PointsMaterial({
      size: 0.24, vertexColors: true, transparent: true, opacity: 0.72,
      depthWrite: false, blending: THREE.AdditiveBlending
    });
    this.dualParticleSystem = new THREE.Points(this.pGeo, pMat);
    this.worldRoot.add(this.dualParticleSystem);
  }

  setViewMode(mode) {
    this.currentViewMode = mode;
    this.interactiveMeshes.forEach(mesh => {
      if (mode === 'pbr') mesh.material = mesh.userData.origMaterial;
      else if (mode === 'holo') mesh.material = this.holoMaterial;
      else if (mode === 'flir') mesh.material = this.flirMaterial;
    });
    this.applyHighlightStates();
  }

  setExplodePercentage(pct) {
    this.explodeProgress = pct / 100.0;
    const smooth = (val, minP, maxP) => {
      const t = Math.max(0.0, Math.min(1.0, (val - minP) / (maxP - minP)));
      return t * t * (3.0 - 2.0 * t);
    };
    const s1 = smooth(this.explodeProgress, 0.00, 0.25);
    const s2 = smooth(this.explodeProgress, 0.25, 0.50);
    const s3 = smooth(this.explodeProgress, 0.50, 0.75);
    const s4 = smooth(this.explodeProgress, 0.75, 1.00);

    Object.keys(this.partGroups).forEach(idStr => {
      const grp = this.partGroups[idStr];
      const meta = grp.userData.meta;
      const factor = [0, s1, s2, s3, s4][meta.stage] || 0.0;
      const ev = meta.explodeVec;
      grp.position.set(ev[0] * factor, ev[1] * factor, ev[2] * factor);
    });
  }

  applyHighlightStates() {
    if (this.currentViewMode !== 'pbr') return;
    this.interactiveMeshes.forEach(mesh => {
      const pid = mesh.userData.partId;
      const mat = mesh.material;
      if (!mat || !mat.emissive) return;
      if (pid === this.hoveredPartId) {
        mat.emissive.setHex(0x006688);
        mat.emissiveIntensity = 0.9;
      } else if (pid === this.selectedPartId) {
        mat.emissive.setHex(0x00334d);
        mat.emissiveIntensity = 0.65;
      } else {
        mat.emissive.setHex(pid === 1 ? 0x002230 : 0x000000);
        mat.emissiveIntensity = 1.0;
      }
    });
  }

  update(dt, elapsedSec) {
    this.getWorldCenter(this.globalShaderUniforms.uWorldCenter.value);
    const effThrottle = this.isFiring ? this.throttleValue : 0.0;

    this.globalShaderUniforms.uTime.value = elapsedSec;
    this.globalShaderUniforms.uScanY.value = -0.35 + Math.sin(elapsedSec * 1.45) * 4.65;
    this.globalShaderUniforms.uThrottle.value = effThrottle;

    this.plumeUniforms.uTime.value = elapsedSec;
    this.plumeUniforms.uThrottle.value = effThrottle;

    this.fluidShaderUniforms.uTime.value = elapsedSec;
    this.fluidShaderUniforms.uSpeed.value = this.isFiring ? (0.4 + 0.9 * effThrottle) : 0.25;

    const spinRate = this.isFiring ? (18.0 * effThrottle) : 1.8;
    this.spinningRotors.forEach(r => { r.rotation.y += spinRate * dt; });

    const cyclePos = elapsedSec % 8.0;
    const timeSinceManual = elapsedSec - this.manualSweepTriggerTime;
    let pitchDeg = 0.0, yawDeg = 0.0;
    if (timeSinceManual >= 0 && timeSinceManual < 2.6) {
      const phase = (timeSinceManual / 2.6) * Math.PI * 2;
      pitchDeg = Math.sin(phase) * 1.5;
      yawDeg = Math.cos(phase) * 1.5 * Math.sin(phase * 0.5);
    } else if (cyclePos < 2.4) {
      const phase = (cyclePos / 2.4) * Math.PI * 2;
      pitchDeg = Math.sin(phase) * 1.5;
      yawDeg = Math.sin(phase * 2.0) * 1.5;
    }

    const vibAmp = effThrottle * 0.008;
    const vibX = (Math.sin(elapsedSec * 95.0) + Math.cos(elapsedSec * 143.0)) * vibAmp;
    const vibY = Math.sin(elapsedSec * 120.0) * vibAmp * 0.8;
    const vibZ = (Math.cos(elapsedSec * 88.0) + Math.sin(elapsedSec * 131.0)) * vibAmp;

    this.gimbalPivot.rotation.x = THREE.MathUtils.degToRad(pitchDeg) + vibX * 0.25;
    this.gimbalPivot.rotation.z = THREE.MathUtils.degToRad(yawDeg) + vibZ * 0.25;
    this.gimbalPivot.position.set(vibX, 3.35 + vibY, vibZ);

    this.dualParticleSystem.visible = effThrottle > 0.02;
    if (this.dualParticleSystem.visible) {
      const posAttr = this.pGeo.attributes.position;
      const arr = posAttr.array;
      const speedScale = 0.4 + 0.9 * effThrottle;
      for (let i = 0; i < this.pVelocities.length; i++) {
        const st = this.pVelocities[i];
        st.life += dt * (this.pTypes[i] === 0 ? 1.8 : 0.85) * speedScale;
        if (st.life >= 1.0) {
          st.life = 0.0;
          if (this.pTypes[i] === 0) {
            const ang = Math.random() * Math.PI * 2, rad = Math.random() * 0.95;
            arr[i * 3] = Math.cos(ang) * rad;
            arr[i * 3 + 1] = -2.35;
            arr[i * 3 + 2] = Math.sin(ang) * rad;
            st.vx = (Math.random() - 0.5) * 1.2;
            st.vy = -(9.5 + Math.random() * 5.0) * speedScale;
            st.vz = (Math.random() - 0.5) * 1.2;
          } else {
            const side = Math.random() < 0.5 ? -1 : 1;
            arr[i * 3] = side * (1.2 + Math.random() * 0.8);
            arr[i * 3 + 1] = -4.2 - Math.random() * 1.0;
            arr[i * 3 + 2] = -0.8 + Math.random() * 2.2;
            st.vx = -side * (1.8 + Math.random() * 1.5);
            st.vy = 0.8 + Math.random() * 2.2;
            st.vz = 4.5 + Math.random() * 4.5;
          }
        } else {
          arr[i * 3] += st.vx * dt;
          arr[i * 3 + 1] += st.vy * dt;
          arr[i * 3 + 2] += st.vz * dt;
          if (arr[i * 3 + 1] < -4.65) {
            arr[i * 3 + 1] = -4.65 + Math.random() * 0.25;
            st.vy = Math.abs(st.vy) * 0.28 + 0.9;
            st.vz = Math.max(st.vz, 6.5 * speedScale);
          }
        }
      }
      posAttr.needsUpdate = true;
    }

    return { pitchDeg, yawDeg, effThrottle };
  }
}
