import { describe, it, expect } from 'vitest';
import { getControlType, getEnumOptions, getArrayItemType, splitUnionTypes } from './utils';
import { createField } from '@/test/fixtures';

describe('getControlType', () => {
  it('maps boolean to toggle', () => {
    expect(getControlType(createField({ key: 'enabled', type: 'boolean' }))).toBe('toggle');
  });

  it('maps enum(...) to select', () => {
    expect(getControlType(createField({ key: 'mode', type: 'enum(dark | light)' }))).toBe('select');
  });

  it('maps number to number', () => {
    expect(getControlType(createField({ key: 'port', type: 'number' }))).toBe('number');
  });

  it('maps string to text', () => {
    expect(getControlType(createField({ key: 'title', type: 'string' }))).toBe('text');
  });

  it('maps array<string> to array', () => {
    expect(getControlType(createField({ key: 'tags', type: 'array<string>' }))).toBe('array');
  });

  it('maps object to object', () => {
    expect(getControlType(createField({ key: 'settings', type: 'object', isObject: true }))).toBe(
      'object',
    );
  });

  it('prioritizes isObject flag over type string', () => {
    expect(getControlType(createField({ key: 'nested', type: 'ZodObject', isObject: true }))).toBe(
      'object',
    );
  });

  it('maps record to record', () => {
    expect(getControlType(createField({ key: 'headers', type: 'record' }))).toBe('record');
  });

  it('maps union containing string and number to text (string is more general)', () => {
    expect(getControlType(createField({ key: 'limit', type: 'union(number | string)' }))).toBe(
      'text',
    );
  });

  it('maps union containing only number (no string) to number', () => {
    expect(getControlType(createField({ key: 'limit', type: 'union(number | boolean)' }))).toBe(
      'number',
    );
  });

  it('maps union containing string (no number) to text', () => {
    expect(getControlType(createField({ key: 'val', type: 'union(string | boolean)' }))).toBe(
      'text',
    );
  });

  it('maps union containing only boolean to toggle', () => {
    expect(
      getControlType(createField({ key: 'flag', type: 'union(boolean | literal(null))' })),
    ).toBe('toggle');
  });

  it('falls back to record for unknown types', () => {
    expect(getControlType(createField({ key: 'data', type: 'ZodAny' }))).toBe('record');
  });

  it('maps wide union with primitives and complex types to record', () => {
    expect(
      getControlType(
        createField({
          key: 'doc',
          type: 'union(null | boolean | number | string | array<unknown> | record)',
        }),
      ),
    ).toBe('record');
  });

  it('maps union(boolean | object) with children to switch-object', () => {
    expect(
      getControlType(
        createField({
          key: 'prompts',
          type: 'union(boolean | object)',
          children: [createField({ key: 'use', type: 'boolean' })],
        }),
      ),
    ).toBe('switch-object');
  });

  it('maps union(boolean | object) without children to toggle', () => {
    expect(getControlType(createField({ key: 'x', type: 'union(boolean | object)' }))).toBe(
      'toggle',
    );
  });

  it('maps union(string | record) to text-record', () => {
    expect(getControlType(createField({ key: 'label', type: 'union(string | record)' }))).toBe(
      'text-record',
    );
  });

  it('maps union(string | array<string>) to text-record', () => {
    expect(
      getControlType(createField({ key: 'content', type: 'union(string | array<string>)' })),
    ).toBe('text-record');
  });

  it('maps union(array<string> | record) to list-record', () => {
    expect(
      getControlType(createField({ key: 'models', type: 'union(array<string> | record)' })),
    ).toBe('list-record');
  });

  it('maps union(enum(...) | number) to select', () => {
    expect(
      getControlType(
        createField({
          key: 'stderr',
          type: 'union(enum(pipe | ignore | inherit) | number)',
        }),
      ),
    ).toBe('select');
  });
});

describe('getEnumOptions', () => {
  it('parses standard enum options', () => {
    const options = getEnumOptions('enum(dark | light | system)');
    expect(options).toEqual([
      { label: 'Dark', value: 'dark' },
      { label: 'Light', value: 'light' },
      { label: 'System', value: 'system' },
    ]);
  });

  it('filters empty segments from leading/trailing delimiters', () => {
    const options = getEnumOptions('enum(| dark | light |)');
    expect(options).toEqual([
      { label: 'Dark', value: 'dark' },
      { label: 'Light', value: 'light' },
    ]);
  });

  it('handles single-value enum', () => {
    const options = getEnumOptions('enum(only)');
    expect(options).toEqual([{ label: 'Only', value: 'only' }]);
  });

  it('replaces underscores with spaces in labels', () => {
    const options = getEnumOptions('enum(my_custom_value)');
    expect(options).toEqual([{ label: 'My custom value', value: 'my_custom_value' }]);
  });

  it('returns empty array for non-enum type strings', () => {
    expect(getEnumOptions('string')).toEqual([]);
    expect(getEnumOptions('number')).toEqual([]);
  });

  it('extracts enum options from union(enum(...) | number) without leaking other branches', () => {
    const options = getEnumOptions('union(enum(pipe | ignore | inherit) | number)');
    expect(options).toEqual([
      { label: 'Pipe', value: 'pipe' },
      { label: 'Ignore', value: 'ignore' },
      { label: 'Inherit', value: 'inherit' },
    ]);
  });

  it('does not produce options with trailing parens from greedy regex', () => {
    const options = getEnumOptions('union(enum(a | b) | number)');
    for (const opt of options) {
      expect(opt.value).not.toContain(')');
      expect(opt.label).not.toContain(')');
    }
  });
});

describe('getArrayItemType', () => {
  it('extracts inner type from array<T>', () => {
    expect(getArrayItemType('array<string>')).toBe('string');
  });

  it('defaults to string when no angle brackets', () => {
    expect(getArrayItemType('array')).toBe('string');
  });
});

describe('splitUnionTypes', () => {
  it('splits simple union into parts', () => {
    expect(splitUnionTypes('union(string | number)')).toEqual(['string', 'number']);
  });

  it('respects depth tracking and does not split inside nested parens', () => {
    const result = splitUnionTypes('union(enum(a | b) | number)');
    expect(result).toEqual(['enum(a | b)', 'number']);
  });

  it('returns single type for union with one member', () => {
    expect(splitUnionTypes('union(string)')).toEqual(['string']);
  });

  it('returns empty array for non-union input', () => {
    expect(splitUnionTypes('string')).toEqual([]);
    expect(splitUnionTypes('')).toEqual([]);
  });

  it('handles nested parens without splitting inner content', () => {
    const result = splitUnionTypes('union(enum(a | b) | string)');
    expect(result).toEqual(['enum(a | b)', 'string']);
  });
});

describe('getControlType — union(literal(...)) as select', () => {
  it('returns select for union of literals', () => {
    const field = createField({
      key: 'method',
      type: 'union(literal("completion") | literal("structured"))',
    });
    expect(getControlType(field)).toBe('select');
  });
});

describe('getEnumOptions — union(literal(...)) parsing', () => {
  it('extracts options from union of literal types', () => {
    const options = getEnumOptions('union(literal("completion") | literal("structured"))');
    expect(options).toEqual([
      { label: 'Completion', value: 'completion' },
      { label: 'Structured', value: 'structured' },
    ]);
  });

  it('returns empty array for non-enum/non-literal-union input', () => {
    expect(getEnumOptions('string')).toEqual([]);
    expect(getEnumOptions('union(string | number)')).toEqual([]);
  });
});
