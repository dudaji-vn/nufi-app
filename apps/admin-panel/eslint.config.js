import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';
import importPlugin from 'eslint-plugin-import-x';
import tailwindCanonicalClasses from 'eslint-plugin-tailwind-canonical-classes';
import clickUiPlugin from 'eslint-plugin-click-ui';

export default [
  {
    ignores: ['src/routeTree.gen.ts'],
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'import-x': importPlugin,
      'tailwind-canonical-classes': tailwindCanonicalClasses,
      'click-ui': clickUiPlugin,
    },
    rules: {
      '@typescript-eslint/ban-ts-comment': ['error', { 'ts-ignore': false }],
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@tanstack/start-server-core',
              message: 'Use @tanstack/react-start/server instead.',
            },
          ],
        },
      ],
      semi: ['error', 'always'],
      'no-nested-ternary': 'warn',
      'no-constant-binary-expression': 'warn',
      'import-x/no-duplicates': ['error', { 'prefer-inline': false }],
      'import-x/no-cycle': 'error',
      'import-x/no-self-import': 'error',
      'tailwind-canonical-classes/tailwind-canonical-classes': [
        'warn',
        { cssPath: './src/styles.css' },
      ],
      ...clickUiPlugin.configs.recommended.rules,
      'click-ui/require-provider': 'off',
      'click-ui/select-requires-options': 'off',
    },
  },
  {
    // shadcn primitives + shadcn-based shell/shared use their own Button, Dialog, Switch APIs.
    // The click-ui plugin doesn't know to skip them, so disable its rules in these directories.
    files: [
      'src/components/ui/**/*.{ts,tsx}',
      'src/components/shared/**/*.{ts,tsx}',
      'src/components/access/**/*.{ts,tsx}',
      'src/components/Sidebar.tsx',
      'src/components/Header.tsx',
      'src/components/CommandMenu.tsx',
      'src/components/SettingsDialog.tsx',
      'src/components/AuthCard.tsx',
      'src/components/PasswordInput.tsx',
      'src/components/ThemeSelector.tsx',
      'src/components/configuration/ImportYamlDialog.tsx',
      'src/components/configuration/ConfirmSaveDialog.tsx',
      'src/components/configuration/DeleteProfileValueModal.tsx',
      'src/components/configuration/ProfileValueModal.tsx',
      'src/components/configuration/ProfileIndicator.tsx',
      'src/components/configuration/ConfigTabBar.tsx',
      'src/components/configuration/InfoBanner.tsx',
      'src/components/configuration/fields/KeyValueField.tsx',
      'src/components/configuration/fields/SwitchObjectField.tsx',
      'src/components/configuration/fields/RecordObjectField.tsx',
      'src/components/configuration/ScopeSelector.tsx',
      'src/components/grants/EditCapabilitiesDialog.tsx',
      'src/routes/_app.tsx',
      'src/routes/__root.tsx',
    ],
    rules: Object.fromEntries(
      Object.keys(clickUiPlugin.rules ?? clickUiPlugin.configs.recommended.rules).map((name) => [
        name.startsWith('click-ui/') ? name : `click-ui/${name}`,
        'off',
      ]),
    ),
  },
];
