// ESLint 9 flat config（前端骨架 — cline TASK-001）
// 规则分层：eslint 官方推荐 → typescript-eslint 推荐 → 关闭与 Prettier 冲突的格式规则。
import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // 世界与 UI 跑在浏览器里（Phaser canvas / React DOM）
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // DESIGN §19：协议类型只从 OpenAPI 生成，不手写（import 一律走 @shared/protocol）
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/shared/protocol', '../shared/*', '../../shared/*'],
              message: '协议类型请用 @shared/protocol（自动生成物），不要手写或相对路径引入',
            },
          ],
        },
      ],
    },
  },
  {
    // 外部产出的 vendored ES Module（`landmarks/lre-test-stand.js`）。它是
    // 原样引入的第三方源码，不是本仓风格：只给浏览器 globals，不套 TS 规则，
    // 也不做 import 限制（它从 'three' 直接取 THREE）。
    files: ['src/**/*.js'],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-unused-vars': 'off',
      'no-restricted-imports': 'off',
    },
  },
  {
    // 构建脚本跑在 Node 里
    files: ['*.config.ts', '*.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
  prettier,
);
