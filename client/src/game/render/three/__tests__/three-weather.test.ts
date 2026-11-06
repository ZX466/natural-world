import * as THREE from 'three';
import { expect, it } from 'vitest';
import { WorldMirror } from '../../../world-mirror';
import { createWeatherLayer } from '../three-weather';

it('preserves night/weather dimming and confines rain to the world canvas', () => {
  const overlay = new THREE.Scene();
  const mirror = new WorldMirror();
  const weather = createWeatherLayer(overlay, mirror);
  weather.update(800, 600, 0, 'day');
  expect(weather.night.visible).toBe(false);
  weather.update(800, 600, 100, 'night');
  expect(weather.night.material.opacity).toBeCloseTo(0.38);
  mirror.setWeather({ visual: 'rain', ambientLight: 0.4 });
  weather.update(800, 600, 200, 'night');
  expect(weather.night.material.opacity).toBeCloseTo(0.54);
  expect(weather.rain.visible).toBe(true);
  expect(weather.rain.geometry.getAttribute('position').count).toBe(160);
  weather.dispose();
  expect(overlay.children).toHaveLength(0);
});
