import * as THREE from 'three';
import type { WorldMirror } from '../../world-mirror';

export function createWeatherLayer(overlay: THREE.Scene, mirror: WorldMirror) {
  const night = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({
      color: 0x0a1030,
      transparent: true,
      opacity: 0,
      depthTest: false,
      depthWrite: false,
    }),
  );
  night.renderOrder = 1000;
  const geometry = new THREE.BufferGeometry();
  const points = new Float32Array(80 * 2 * 3);
  geometry.setAttribute('position', new THREE.BufferAttribute(points, 3));
  const rain = new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color: 0x9fb8d8,
      transparent: true,
      opacity: 0.45,
      depthTest: false,
      depthWrite: false,
    }),
  );
  rain.frustumCulled = false;
  rain.renderOrder = 100;
  overlay.add(night, rain);
  return {
    night,
    rain,
    update(width: number, height: number, time: number, phase: 'day' | 'dawn' | 'dusk' | 'night') {
      const darkness = { day: 0, dawn: 0.12, dusk: 0.2, night: 0.38 }[phase];
      night.material.opacity = Math.min(
        1,
        darkness + ({ clear: 0, overcast: 0.08, rain: 0.16 }[mirror.weather.visual] ?? 0),
      );
      night.visible = night.material.opacity > 0;
      night.scale.set(width, height, 1);
      night.position.set(width / 2, height / 2, 0);
      rain.visible = mirror.weather.visual === 'rain';
      if (rain.visible) {
        for (let i = 0; i < 80; i++) {
          const x = (i * 173.141) % Math.max(1, width);
          const y = height - ((i * 97 + time * 0.35) % Math.max(1, height));
          points.set([x, y, 0, x - 2, y - 9, 0], i * 6);
        }
        geometry.getAttribute('position').needsUpdate = true;
      }
    },
    dispose() {
      overlay.remove(night, rain);
      night.geometry.dispose();
      night.material.dispose();
      geometry.dispose();
      rain.material.dispose();
    },
  };
}
