/**
 * 《临河镇》3D 分节体素角色核心模块 (2.8 头身 · 总高 1.80 世界单位/格 · 16 骨骼层级)
 * 零外部静态资产依赖，原生支持 Three.js (r128+)
 */
import * as THREE from 'three';

export const Facing = Object.freeze({
  SOUTH: 'south',
  SOUTH_EAST: 'south_east',
  EAST: 'east',
  NORTH_EAST: 'north_east',
  NORTH: 'north',
  NORTH_WEST: 'north_west',
  WEST: 'west',
  SOUTH_WEST: 'south_west'
});

export const FACING_TO_RAD = Object.freeze({
  [Facing.SOUTH]: 0,
  [Facing.SOUTH_EAST]: Math.PI * 0.25,
  [Facing.EAST]: Math.PI * 0.5,
  [Facing.NORTH_EAST]: Math.PI * 0.75,
  [Facing.NORTH]: Math.PI,
  [Facing.NORTH_WEST]: -Math.PI * 0.75,
  [Facing.WEST]: -Math.PI * 0.5,
  [Facing.SOUTH_WEST]: -Math.PI * 0.25
});

/**
 * 兼容旧版 2D 图集行号到显式 Facing 枚举的无损转换（彻底修复主角/古风NPC行序颠倒Bug）
 */
export function legacyRowToFacing(row, isAncientNpc = false) {
  if (isAncientNpc) {
    // 旧版 god_villager_* 行序：0=下(south), 1=上(north), 2=右(east), 3=左(west)
    return [Facing.SOUTH, Facing.NORTH, Facing.EAST, Facing.WEST][row & 3] || Facing.SOUTH;
  }
  // 旧版主角 chenmo / villager 行序：0=下(south), 1=右(east), 2=上(north), 3=左(west)
  return [Facing.SOUTH, Facing.EAST, Facing.NORTH, Facing.WEST][row & 3] || Facing.SOUTH;
}

/**
 * 同格多人站立子槽位偏移（防止 3D 模型同格穿模与脚底 Z-fighting）
 */
export function getSubTileSlotOffset(slotIndex, totalInTile = 1) {
  if (totalInTile <= 1) return { dx: 0, dy: 0, dz: 0 };
  const offsets = [
    [-0.22, -0.22],
    [ 0.22,  0.22],
    [-0.22,  0.22],
    [ 0.22, -0.22]
  ];
  const pair = offsets[slotIndex % 4];
  return {
    dx: pair[0],
    dy: (slotIndex % 4) * 0.002,
    dz: pair[1]
  };
}

export const CHARACTER_PRESETS = [
  {
    "id": "chenmo",
    "name": "陈默 (药铺学徒·主角)",
    "role": "protagonist",
    "atlasSlot": [
      0,
      0
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#bfa787",
      "trim": "#65659b",
      "belt": "#c43c3c",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": true,
      "strawHat": false,
      "herbBasket": true,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "villager",
    "name": "普通村民",
    "role": "villager",
    "atlasSlot": [
      1,
      0
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#bfa787",
      "trim": "#6a4834",
      "belt": "#432e27",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": false
    }
  },
  {
    "id": "god_villager_01",
    "name": "墨衡 · 钦天监司匠",
    "role": "ancient_npc",
    "atlasSlot": [
      2,
      0
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#171717",
      "robe": "#65659b",
      "trim": "#d4c38c",
      "belt": "#b89052",
      "pants": "#2f3842"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_02",
    "name": "林采薇 · 采药女",
    "role": "ancient_npc",
    "atlasSlot": [
      3,
      0
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#171717",
      "robe": "#96b37b",
      "trim": "#f6e8dc",
      "belt": "#ffbd7f",
      "pants": "#5a6b49"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": true,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_03",
    "name": "赵掌柜 · 济世堂",
    "role": "ancient_npc",
    "atlasSlot": [
      4,
      0
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#432e27",
      "robe": "#6d4a2f",
      "trim": "#b89052",
      "belt": "#882e2e",
      "pants": "#2f3842"
    },
    "accessories": {
      "bun": false,
      "cap": true,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_04",
    "name": "沈书生 · 临河书院",
    "role": "ancient_npc",
    "atlasSlot": [
      5,
      0
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#171717",
      "robe": "#d4c38c",
      "trim": "#65659b",
      "belt": "#6a4834",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_05",
    "name": "周老汉 · 渡口渔夫",
    "role": "ancient_npc",
    "atlasSlot": [
      6,
      0
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#432e27",
      "robe": "#5a6b49",
      "trim": "#bfa787",
      "belt": "#6d4a2f",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": false,
      "strawHat": true,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_06",
    "name": "孙货郎 · 走街行商",
    "role": "ancient_npc",
    "atlasSlot": [
      7,
      0
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#b89052",
      "trim": "#ffbd7f",
      "belt": "#882e2e",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": true,
      "strawHat": false,
      "herbBasket": false,
      "sack": true,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_07",
    "name": "苏绣娘 · 锦绣坊",
    "role": "ancient_npc",
    "atlasSlot": [
      0,
      1
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#171717",
      "robe": "#ffbd7f",
      "trim": "#c43c3c",
      "belt": "#882e2e",
      "pants": "#6d4a2f"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_08",
    "name": "铁匠雷大叔",
    "role": "ancient_npc",
    "atlasSlot": [
      1,
      1
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#432e27",
      "trim": "#6a4834",
      "belt": "#c43c3c",
      "pants": "#171717"
    },
    "accessories": {
      "bun": false,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_09",
    "name": "柳先生 · 账房",
    "role": "ancient_npc",
    "atlasSlot": [
      2,
      1
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#432e27",
      "robe": "#6a4834",
      "trim": "#d4c38c",
      "belt": "#432e27",
      "pants": "#2f3842"
    },
    "accessories": {
      "bun": false,
      "cap": true,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_10",
    "name": "阿竹 · 茶寮小二",
    "role": "ancient_npc",
    "atlasSlot": [
      3,
      1
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#96b37b",
      "trim": "#bfa787",
      "belt": "#6d4a2f",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": true,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_11",
    "name": "白发医仙 · 鹤翁",
    "role": "ancient_npc",
    "atlasSlot": [
      4,
      1
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#e8dccb",
      "robe": "#d4c38c",
      "trim": "#96b37b",
      "belt": "#b89052",
      "pants": "#5a6b49"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": true,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_12",
    "name": "吴樵夫 · 北山",
    "role": "ancient_npc",
    "atlasSlot": [
      5,
      1
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#6d4a2f",
      "trim": "#5a6b49",
      "belt": "#432e27",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": false,
      "strawHat": true,
      "herbBasket": false,
      "sack": true,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_13",
    "name": "春桃 · 药铺侍女",
    "role": "ancient_npc",
    "atlasSlot": [
      6,
      1
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#171717",
      "robe": "#ffbd7f",
      "trim": "#96b37b",
      "belt": "#c43c3c",
      "pants": "#6a4834"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_14",
    "name": "陆捕头 · 巡街",
    "role": "ancient_npc",
    "atlasSlot": [
      7,
      1
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#2f3842",
      "trim": "#c43c3c",
      "belt": "#882e2e",
      "pants": "#171717"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_15",
    "name": "顾娘子 · 豆腐坊",
    "role": "ancient_npc",
    "atlasSlot": [
      0,
      2
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#432e27",
      "robe": "#bfa787",
      "trim": "#ffbd7f",
      "belt": "#6a4834",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_16",
    "name": "徐道长 · 云游",
    "role": "ancient_npc",
    "atlasSlot": [
      1,
      2
    ],
    "palette": {
      "skin": "#f6e8dc",
      "hair": "#171717",
      "robe": "#65659b",
      "trim": "#e8dccb",
      "belt": "#b89052",
      "pants": "#2f3842"
    },
    "accessories": {
      "bun": true,
      "cap": false,
      "strawHat": false,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  },
  {
    "id": "god_villager_17",
    "name": "小豆子 · 牧童",
    "role": "ancient_npc",
    "atlasSlot": [
      2,
      2
    ],
    "palette": {
      "skin": "#e8d4b2",
      "hair": "#171717",
      "robe": "#96b37b",
      "trim": "#d4c38c",
      "belt": "#ffbd7f",
      "pants": "#432e27"
    },
    "accessories": {
      "bun": false,
      "cap": false,
      "strawHat": true,
      "herbBasket": false,
      "sack": false,
      "robeFlaps": true
    }
  }
];

export const PRESETS_BY_ID = Object.fromEntries(CHARACTER_PRESETS.map(p => [p.id, p]));

function makeFaceTexture(skinHex, hairHex, eyeHex = '#171717') {
  const c = document.createElement('canvas');
  c.width = 16;
  c.height = 16;
  const ctx = c.getContext('2d');
  ctx.fillStyle = skinHex;
  ctx.fillRect(0, 0, 16, 16);
  ctx.fillStyle = hairHex;
  ctx.fillRect(0, 0, 16, 4);
  ctx.fillRect(0, 4, 2, 4);
  ctx.fillRect(14, 4, 2, 4);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(3, 7, 3, 3);
  ctx.fillRect(10, 7, 3, 3);
  ctx.fillStyle = eyeHex;
  ctx.fillRect(4, 7, 2, 3);
  ctx.fillRect(10, 7, 2, 3);
  ctx.fillStyle = '#a86454';
  ctx.fillRect(6, 12, 4, 1);
  const t = new THREE.CanvasTexture(c);
  t.magFilter = THREE.NearestFilter;
  t.minFilter = THREE.NearestFilter;
  t.generateMipmaps = false;
  return t;
}

export class VoxelAvatar3D {
  constructor(options = {}) {
    const presetId = options.presetId || 'chenmo';
    const preset = PRESETS_BY_ID[presetId] || PRESETS_BY_ID.chenmo;
    const pal = { ...preset.palette, ...(options.palette || {}) };
    const acc = { ...preset.accessories, ...(options.accessories || {}) };

    this.presetId = presetId;
    this.root = new THREE.Group();
    this.root.position.set(options.x || 0, options.y || 1.0, options.z || 0);

    // 固定包围球半径 1.2 格，防止相机拉近到 3 格时被视锥剔除
    this.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.9, 0), 1.2);

    const skinMat = new THREE.MeshLambertMaterial({ color: pal.skin });
    const hairMat = new THREE.MeshLambertMaterial({ color: pal.hair });
    const robeMat = new THREE.MeshLambertMaterial({ color: pal.robe });
    const trimMat = new THREE.MeshLambertMaterial({ color: pal.trim });
    const beltMat = new THREE.MeshLambertMaterial({ color: pal.belt });
    const pantsMat = new THREE.MeshLambertMaterial({ color: pal.pants });
    const faceMat = new THREE.MeshLambertMaterial({
      map: makeFaceTexture(pal.skin, pal.hair)
    });

    // 1. hips (Y = 0.58)
    this.hips = new THREE.Group();
    this.hips.position.set(0, 0.58, 0);
    this.root.add(this.hips);

    const hipsMesh = new THREE.Mesh(new THREE.BoxGeometry(0.50, 0.19, 0.26), beltMat);
    hipsMesh.castShadow = true;
    this.hips.add(hipsMesh);

    // 2. spine (Y = 0.71 -> local +0.13)
    this.spine = new THREE.Group();
    this.spine.position.set(0, 0.13, 0);
    this.hips.add(this.spine);

    const torsoMesh = new THREE.Mesh(new THREE.BoxGeometry(0.50, 0.39, 0.26), robeMat);
    torsoMesh.position.set(0, 0.195, 0);
    torsoMesh.castShadow = true;
    this.spine.add(torsoMesh);

    const collarMesh = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.10, 0.28), trimMat);
    collarMesh.position.set(0, 0.34, 0);
    this.spine.add(collarMesh);

    // 3. head (Y = 1.16 -> local +0.45, head height 0.64 -> total height = 1.80 blocks)
    this.head = new THREE.Group();
    this.head.position.set(0, 0.45, 0);
    this.spine.add(this.head);

    const headMats = [hairMat, hairMat, hairMat, skinMat, faceMat, hairMat];
    const headMesh = new THREE.Mesh(new THREE.BoxGeometry(0.64, 0.64, 0.64), headMats);
    headMesh.position.set(0, 0.32, 0);
    headMesh.castShadow = true;
    this.head.add(headMesh);

    // 4. hair_acc (发髻 / 方巾 / 竹斗笠)
    this.hairAcc = new THREE.Group();
    this.hairAcc.position.set(0, 0.64, 0);
    this.head.add(this.hairAcc);

    if (acc.strawHat) {
      const brim = new THREE.Mesh(new THREE.BoxGeometry(0.88, 0.06, 0.88), new THREE.MeshLambertMaterial({ color: 0xc8a862 }));
      const crown = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.16, 0.46), new THREE.MeshLambertMaterial({ color: 0xb89052 }));
      crown.position.y = 0.10;
      this.hairAcc.add(brim, crown);
    } else if (acc.bun || acc.cap) {
      const bunMesh = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.16, 0.32), acc.cap ? trimMat : hairMat);
      bunMesh.position.set(0, 0.04, -0.04);
      this.hairAcc.add(bunMesh);
    }

    // 5. back_prop (药篓 / 行商背囊)
    this.backProp = new THREE.Group();
    this.backProp.position.set(0, 0.24, -0.24);
    this.spine.add(this.backProp);

    if (acc.herbBasket) {
      const basketBody = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.44, 0.24), new THREE.MeshLambertMaterial({ color: 0x9c7a44 }));
      basketBody.castShadow = true;
      const herbLeaf = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.14, 0.18), new THREE.MeshLambertMaterial({ color: 0x588141 }));
      herbLeaf.position.set(0, 0.26, 0);
      const gourd = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.18, 0.12), beltMat);
      gourd.position.set(0.16, 0.22, -0.05);
      this.backProp.add(basketBody, herbLeaf, gourd);
    } else if (acc.sack) {
      const sackMesh = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.42, 0.26), new THREE.MeshLambertMaterial({ color: 0xd4c38c }));
      sackMesh.castShadow = true;
      this.backProp.add(sackMesh);
    }

    // 6. robe_front & robe_back
    this.robeFront = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.30, 0.04), robeMat);
    this.robeFront.position.set(0, -0.12, 0.14);
    this.robeFront.visible = Boolean(acc.robeFlaps);
    this.hips.add(this.robeFront);

    this.robeBack = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.30, 0.04), robeMat);
    this.robeBack.position.set(0, -0.12, -0.14);
    this.robeBack.visible = Boolean(acc.robeFlaps);
    this.hips.add(this.robeBack);

    // 7. 分节手臂 (arm_upper + arm_lower)
    const buildArm = (sideSign) => {
      const armUpper = new THREE.Group();
      armUpper.position.set(sideSign * 0.35, 0.39, 0);
      const uMesh = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.29, 0.20), robeMat);
      uMesh.position.set(0, -0.145, 0);
      uMesh.castShadow = true;
      armUpper.add(uMesh);

      const armLower = new THREE.Group();
      armLower.position.set(0, -0.29, 0);
      const lMesh = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.29, 0.18), skinMat);
      lMesh.position.set(0, -0.145, 0);
      lMesh.castShadow = true;
      const cuff = new THREE.Mesh(new THREE.BoxGeometry(0.205, 0.09, 0.205), trimMat);
      cuff.position.set(0, -0.05, 0);
      armLower.add(lMesh, cuff);
      armUpper.add(armLower);
      this.spine.add(armUpper);
      return { armUpper, armLower };
    };

    this.armL = buildArm(1);
    this.armR = buildArm(-1);

    // 8. 分节双腿 (leg_upper + leg_lower, 脚底严格落在 Y = 0.00)
    const buildLeg = (sideSign) => {
      const legUpper = new THREE.Group();
      legUpper.position.set(sideSign * 0.13, 0, 0);
      const uMesh = new THREE.Mesh(new THREE.BoxGeometry(0.23, 0.29, 0.23), pantsMat);
      uMesh.position.set(0, -0.145, 0);
      uMesh.castShadow = true;
      legUpper.add(uMesh);

      const legLower = new THREE.Group();
      legLower.position.set(0, -0.29, 0);
      const lMesh = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.29, 0.22), pantsMat);
      lMesh.position.set(0, -0.145, 0);
      lMesh.castShadow = true;
      legLower.add(lMesh);
      legUpper.add(legLower);
      this.hips.add(legUpper);
      return { legUpper, legLower };
    };

    this.legL = buildLeg(1);
    this.legR = buildLeg(-1);

    this.animState = options.animState || 'idle';
    this.animTime = 0;
    this.facingRad = FACING_TO_RAD[options.facing || Facing.SOUTH] ?? 0;
    this.targetFacingRad = this.facingRad;
    this.root.rotation.y = this.facingRad;
  }

  setPosition(x, y, z) {
    this.root.position.set(x, y, z);
  }

  setFacing(facingEnumOrRad) {
    if (typeof facingEnumOrRad === 'number') {
      this.targetFacingRad = facingEnumOrRad;
    } else if (FACING_TO_RAD[facingEnumOrRad] !== undefined) {
      this.targetFacingRad = FACING_TO_RAD[facingEnumOrRad];
    }
  }

  playAnim(animName) {
    if (this.animState !== animName) {
      this.animState = animName;
    }
  }

  /**
   * 返回名字标签/血条/对话气泡的世界坐标挂点 (Y + 1.95 格，随跳跃重心同步起伏)
   */
  getTopAnchor(targetVec = new THREE.Vector3()) {
    const jumpDelta = this.hips.position.y - 0.58;
    return targetVec.set(
      this.root.position.x,
      this.root.position.y + 1.95 + jumpDelta,
      this.root.position.z
    );
  }

  update(dt) {
    this.animTime += dt;
    let diff = this.targetFacingRad - this.facingRad;
    while (diff > Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    this.facingRad += diff * Math.min(1.0, 15.0 * dt);
    this.root.rotation.y = this.facingRad;

    const t = this.animTime;
    if (this.animState === 'jump') {
      this.hips.position.y = 0.58;
      this.spine.rotation.set(0.18, 0, 0);
      this.armL.armUpper.rotation.x = -1.05;
      this.armR.armUpper.rotation.x = -1.05;
      this.armL.armLower.rotation.x = -0.6;
      this.armR.armLower.rotation.x = -0.6;
      this.legL.legUpper.rotation.x = -0.78;
      this.legL.legLower.rotation.x = 1.10;
      this.legR.legUpper.rotation.x = 0.35;
      this.legR.legLower.rotation.x = 0.45;
      this.robeFront.rotation.x = -0.65;
      this.robeBack.rotation.x = 0.65;
    } else if (this.animState === 'run') {
      const w = t * (Math.PI * 2 / 0.40);
      const s = Math.sin(w);
      this.hips.position.y = 0.54 + Math.abs(Math.cos(w)) * 0.08;
      this.spine.rotation.set(THREE.MathUtils.degToRad(18), s * THREE.MathUtils.degToRad(12), 0);
      this.armL.armUpper.rotation.x = s * THREE.MathUtils.degToRad(62);
      this.armR.armUpper.rotation.x = -s * THREE.MathUtils.degToRad(62);
      this.armL.armLower.rotation.x = -THREE.MathUtils.degToRad(75);
      this.armR.armLower.rotation.x = -THREE.MathUtils.degToRad(75);
      this.legL.legUpper.rotation.x = -s * THREE.MathUtils.degToRad(52);
      this.legR.legUpper.rotation.x = s * THREE.MathUtils.degToRad(52);
      this.legL.legLower.rotation.x = Math.max(0, s) * THREE.MathUtils.degToRad(75);
      this.legR.legLower.rotation.x = Math.max(0, -s) * THREE.MathUtils.degToRad(75);
      this.robeFront.rotation.x = -Math.max(0, Math.abs(s)) * 0.45;
      this.robeBack.rotation.x = 0.55;
    } else if (this.animState === 'walk') {
      const w = t * (Math.PI * 2 / 0.60);
      const s = Math.sin(w);
      this.hips.position.y = 0.58 + Math.abs(Math.cos(w)) * 0.03;
      this.spine.rotation.set(THREE.MathUtils.degToRad(3), s * THREE.MathUtils.degToRad(4), 0);
      this.armL.armUpper.rotation.x = s * THREE.MathUtils.degToRad(25);
      this.armR.armUpper.rotation.x = -s * THREE.MathUtils.degToRad(25);
      this.armL.armLower.rotation.x = -THREE.MathUtils.degToRad(15);
      this.armR.armLower.rotation.x = -THREE.MathUtils.degToRad(15);
      this.legL.legUpper.rotation.x = -s * THREE.MathUtils.degToRad(28);
      this.legR.legUpper.rotation.x = s * THREE.MathUtils.degToRad(28);
      this.legL.legLower.rotation.x = Math.max(0, s) * THREE.MathUtils.degToRad(25);
      this.legR.legLower.rotation.x = Math.max(0, -s) * THREE.MathUtils.degToRad(25);
      this.robeFront.rotation.x = -0.15;
      this.robeBack.rotation.x = 0.15;
    } else {
      const b = Math.sin(t * (Math.PI * 2 / 1.60));
      this.hips.position.y = 0.58 + b * 0.015;
      this.spine.rotation.set(0, Math.sin(t * 0.9) * 0.06, 0);
      this.armL.armUpper.rotation.x = b * 0.04;
      this.armR.armUpper.rotation.x = -b * 0.04;
      this.armL.armLower.rotation.x = -0.12;
      this.armR.armLower.rotation.x = -0.12;
      this.legL.legUpper.rotation.x = 0;
      this.legR.legUpper.rotation.x = 0;
      this.legL.legLower.rotation.x = 0;
      this.legR.legLower.rotation.x = 0;
      this.robeFront.rotation.x = 0;
      this.robeBack.rotation.x = 0;
    }
  }
}
