import prettier from 'eslint-config-prettier';
import prettierPlugin from 'eslint-plugin-prettier';

export default [
  {
    files: ['**/*.{js,mjs,cjs,ts}'],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        console: 'readonly',
        process: 'readonly',
        Buffer: 'readonly',
        __dirname: 'readonly',
        __filename: 'readonly',
      },
    },
    plugins: {
      prettier: prettierPlugin,
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': 'warn',
      'quotes': 'off',
      'prettier/prettier': 'off',
    },
  },
  prettier,
  {
    ignores: ['eslint.config.js', 'deploy/**', 'node_modules/**', 'ecosystem.config.cjs'],
  },
];