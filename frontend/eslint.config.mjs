/**
 * Debugging:
 *   https://eslint.org/docs/latest/use/configure/debug
 *  ----------------------------------------------------
 *
 *   Print a file's calculated configuration
 *
 *     npx eslint --print-config path/to/file.js
 *
 *   Inspecting the config
 *
 *     npx eslint --inspect-config
 *
 */
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import globals from 'globals';
import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';

import ts from 'typescript-eslint';

import ember from 'eslint-plugin-ember/recommended';

import eslintConfigPrettier from 'eslint-config-prettier';
import qunit from 'eslint-plugin-qunit';
import n from 'eslint-plugin-n';

import babelParser from '@babel/eslint-parser/experimental-worker';

const parserOptions = {
  esm: {
    js: {
      ecmaFeatures: { modules: true },
      ecmaVersion: 'latest',
    },
    ts: {
      projectService: true,
      tsconfigRootDir: dirname(fileURLToPath(import.meta.url)),
    },
  },
};

const THE_WIRE = {
  regex: '(^frontend|\\.)/data/(http|stream)$',
  message:
    'Only the store talks to the server: ask StoreService to read or write, and read what it holds.',
};

const THE_SUMMARIES = {
  regex: '(^frontend|\\.)/data/summaries$',
  message:
    'A summary is computed once, in the store: read it through StoreService.',
};

const THE_LOADER = {
  regex: '(^frontend|\\.)/services/poll$',
  message:
    'Components and helpers read the store; only routes and services drive the loader that polls the server.',
};

export default defineConfig([
  globalIgnores(['dist/', 'dist-tests/', 'coverage/', '!**/.*']),
  js.configs.recommended,
  ember.configs.base,
  ember.configs.gjs,
  ember.configs.gts,
  eslintConfigPrettier,
  /**
   * https://eslint.org/docs/latest/use/configure/configuration-files#configuring-linter-options
   */
  {
    linterOptions: {
      reportUnusedDisableDirectives: 'error',
    },
  },
  {
    files: ['**/*.js'],
    languageOptions: {
      parser: babelParser,
    },
  },
  {
    files: ['**/*.{js,gjs}'],
    languageOptions: {
      parserOptions: parserOptions.esm.js,
      globals: {
        ...globals.browser,
      },
    },
  },
  {
    files: ['**/*.{ts,gts}'],
    languageOptions: {
      parser: ember.parser,
      parserOptions: parserOptions.esm.ts,
      globals: {
        ...globals.browser,
      },
    },
    extends: [
      ...ts.configs.recommendedTypeChecked,
      // https://github.com/ember-cli/ember-addon-blueprint/issues/119
      {
        ...ts.configs.eslintRecommended,
        files: undefined,
      },
      ember.configs.gts,
    ],
  },
  {
    ...qunit.configs.recommended,
    files: ['tests/**/*-test.{js,gjs,ts,gts}'],
    plugins: {
      qunit,
    },
  },
  {
    files: ['app/**/*.{ts,gts}'],
    ignores: ['app/services/store.ts'],
    rules: {
      '@typescript-eslint/no-restricted-imports': [
        'error',
        { patterns: [THE_WIRE, THE_SUMMARIES] },
      ],
    },
  },
  {
    files: [
      'app/components/**/*.{ts,gts}',
      'app/controllers/**/*.{ts,gts}',
      'app/data/**/*.{ts,gts}',
      'app/helpers/**/*.{ts,gts}',
      'app/modifiers/**/*.{ts,gts}',
      'app/templates/**/*.{ts,gts}',
    ],
    rules: {
      '@typescript-eslint/no-restricted-imports': [
        'error',
        { patterns: [THE_WIRE, THE_SUMMARIES, THE_LOADER] },
      ],
    },
  },
  {
    files: ['tests/**/*.{ts,gts}'],
    rules: {
      '@typescript-eslint/no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: '^frontend/(?!tests/|config/environment$|app$|data/api$)',
              message:
                'A test reaches the board web app through its URL, its DOM and FakeBoard, never its insides.',
            },
            {
              regex: '^frontend/data/api$',
              allowTypeImports: true,
              message:
                'frontend/data/api is the Board API contract: import its types, nothing else.',
            },
            {
              regex: '^\\.\\.?/.*\\bapp/',
              message:
                'A test reaches the board web app through its URL, its DOM and FakeBoard, never its insides.',
            },
          ],
        },
      ],
      'no-restricted-syntax': [
        'error',
        {
          selector: "MemberExpression[property.name='owner']",
          message:
            'A test reaches the board web app through its URL, its DOM and FakeBoard, never its services.',
        },
        {
          selector:
            "ImportDeclaration[source.value='@ember/test-helpers'] ImportSpecifier[imported.name='render']",
          message:
            'A test renders the whole board by visiting a URL, not one component.',
        },
      ],
    },
  },
  /**
   * CJS node files
   */
  {
    ...n.configs['flat/recommended-script'],
    files: ['**/*.cjs', 'config/**/*.js'],
    plugins: {
      n,
    },

    languageOptions: {
      sourceType: 'script',
      ecmaVersion: 'latest',
      globals: {
        ...globals.node,
      },
    },
  },
  /**
   * ESM node files
   */
  {
    ...n.configs['flat/recommended-module'],
    files: ['**/*.mjs'],
    plugins: {
      n,
    },

    languageOptions: {
      sourceType: 'module',
      ecmaVersion: 'latest',
      parserOptions: parserOptions.esm.js,
      globals: {
        ...globals.node,
      },
    },
  },
]);
