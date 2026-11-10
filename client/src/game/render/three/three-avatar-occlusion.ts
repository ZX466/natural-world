/** Hero silhouette against environment depth, without the avatar's own depth. */
import * as THREE from 'three';
import type { ActorView } from './three-actors';

type OcclusionActor = Pick<ActorView, 'sprite' | 'shadow' | 'silhouette'> & {
  readonly avatar: Pick<NonNullable<ActorView['avatar']>, 'root' | 'mesh'> | null;
};

function materialsOf(object: THREE.Object3D): readonly THREE.Material[] {
  if (!('material' in object)) return [];
  const material = object.material as THREE.Material | THREE.Material[];
  return Array.isArray(material) ? material : [material];
}

export function createAvatarOcclusion() {
  const depth = new THREE.MeshDepthMaterial({ colorWrite: false });
  const silhouette = new THREE.MeshBasicMaterial({
    color: 0xffd776,
    transparent: true,
    opacity: 0.45,
    depthFunc: THREE.GreaterDepth,
    depthWrite: false,
    fog: false,
    toneMapped: false,
  });

  return {
    /** Call after the normal world render and before screen-space overlays. */
    render(
      renderer: THREE.WebGLRenderer,
      scene: THREE.Scene,
      camera: THREE.PerspectiveCamera,
      actors: ReadonlyMap<string, OcclusionActor>,
      protagonist: string | null,
    ): void {
      const avatar = protagonist ? actors.get(protagonist)?.avatar : null;
      if (!avatar) return;
      for (let node: THREE.Object3D | null = avatar.mesh; node; node = node.parent) {
        if (!node.visible) return;
      }
      const background = scene.background;
      const override = scene.overrideMaterial;
      const autoClear = renderer.autoClear;
      const hidden: THREE.Object3D[] = [];
      const hide = (object: THREE.Object3D) => {
        if (object.visible) {
          hidden.push(object);
          object.visible = false;
        }
      };
      const restore = () => {
        for (const object of hidden) object.visible = true;
        hidden.length = 0;
      };
      try {
        // Keep the already composed world colour. Background rendering can
        // force a clear even with autoClear off, so suppress it for both passes.
        renderer.autoClear = false;
        scene.background = null;
        for (const actor of actors.values()) {
          hide(actor.sprite);
          hide(actor.shadow);
          if (actor.avatar) hide(actor.avatar.root);
          if (actor.silhouette) hide(actor.silhouette);
        }
        scene.traverse((object) => {
          const materials = materialsOf(object);
          // Translucent effects and cutouts are not solid walls. Never let a
          // replacement depth material turn them into opaque occluders.
          if (
            materials.some((m) => !m.visible || !m.depthWrite || m.transparent || m.alphaTest > 0)
          )
            hide(object);
        });
        renderer.clearDepth();
        scene.overrideMaterial = depth;
        renderer.render(scene, camera);
        restore();

        scene.traverse((object) => {
          if (object !== avatar.mesh && materialsOf(object).length) hide(object);
        });
        scene.overrideMaterial = silhouette;
        renderer.render(scene, camera);
      } finally {
        restore();
        scene.background = background;
        scene.overrideMaterial = override;
        renderer.autoClear = autoClear;
      }
    },
    dispose(): void {
      depth.dispose();
      silhouette.dispose();
    },
  };
}
