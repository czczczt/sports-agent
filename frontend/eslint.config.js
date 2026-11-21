import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import boundaries from 'eslint-plugin-boundaries';
import a11y from 'eslint-plugin-jsx-a11y';
import hooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  {
    ignores: [
      '*.timestamp-*.mjs',
      'dist/**',
      'node_modules/**',
      'src/shared/api/schema.d.ts',
      'playwright-report/**',
      'test-results/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { boundaries, 'jsx-a11y': a11y, 'react-hooks': hooks },
    settings: {
      'import/resolver': { typescript: { project: './tsconfig.json' } },
      'boundaries/elements': [
        { type: 'app', pattern: 'src/app' },
        ...['pages', 'features', 'shared'].map((type) => ({ type, pattern: 'src/' + type + '/*' })),
      ],
      'boundaries/ignore': ['**/*.css'],
    },
    rules: {
      ...a11y.configs.recommended.rules,
      ...hooks.configs.recommended.rules,
      'react-hooks/exhaustive-deps': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      'boundaries/element-types': [
        'error',
        {
          default: 'disallow',
          rules: [
            { from: 'app', allow: ['pages', 'features', 'shared'] },
            { from: 'pages', allow: ['features', 'shared'] },
            { from: 'features', allow: ['shared'] },
            { from: 'shared', allow: ['shared'] },
          ],
        },
      ],
      'boundaries/entry-point': [
        'error',
        {
          default: 'disallow',
          rules: [{ target: ['pages', 'features', 'shared'], allow: ['index.ts', 'index.tsx'] }],
        },
      ],
    },
  },
);
