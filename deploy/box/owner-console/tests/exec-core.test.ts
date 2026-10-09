import { describe, expect, test } from 'bun:test';
import {
  BadRequest,
  applyConfigToYaml,
  auditLine,
  buildControlArgv,
  buildReadArgv,
  buildReconfigureArgv,
  buildRemoteWorkArgv,
  buildRemoteWorkStatusArgv,
  configViewFromYaml,
  validateConfigPatch,
} from '../src/exec-core';

const C = ['docker', 'compose', '-p', 'nufi-box'];

describe('exec-core allowlist', () => {
  test('control argv exact', () => {
    expect(buildControlArgv('restart', 'caddy')).toEqual([...C, 'restart', 'caddy']);
  });
  test('invalid action/service rejected', () => {
    expect(() => buildControlArgv('rm', 'caddy')).toThrow(BadRequest);
    expect(() => buildControlArgv('restart', 'nope')).toThrow(BadRequest);
  });
  test('shell metachars rejected', () => {
    expect(() => buildControlArgv('restart', 'caddy; rm')).toThrow(BadRequest);
    expect(() => buildControlArgv('restart&&x', 'caddy')).toThrow(BadRequest);
  });
  test('remote-work argv start/stops the tailscale container by name', () => {
    expect(buildRemoteWorkArgv(true)).toEqual(['docker', 'start', 'nufi-box-tailscale-1']);
    expect(buildRemoteWorkArgv(false)).toEqual(['docker', 'stop', 'nufi-box-tailscale-1']);
    expect(() => buildRemoteWorkArgv('yes' as unknown as boolean)).toThrow(BadRequest);
    expect(buildRemoteWorkStatusArgv()).toEqual(['docker', 'inspect', '-f', '{{.State.Running}}', 'nufi-box-tailscale-1']);
  });
  test('read argv exact', () => {
    expect(buildReadArgv('status')).toEqual([...C, 'ps']);
    expect(buildReadArgv('logs librechat')).toEqual([...C, 'logs', '--no-color', '--tail=200', 'librechat']);
    expect(buildReadArgv('logs')).toEqual([...C, 'logs', '--no-color', '--tail=200']);
    expect(buildReadArgv('logs ollama')).toEqual([...C, 'logs', '--no-color', '--tail=200', 'ollama']);
    expect(buildReadArgv('logs postgres')).toEqual([...C, 'logs', '--no-color', '--tail=200', 'postgres']);
    expect(buildReadArgv('doctor')).toBeNull();
    expect(buildReadArgv('support')).toBeNull();
  });
  test('off-list read rejected', () => {
    expect(() => buildReadArgv('logs librechat; id')).toThrow(BadRequest);
    expect(() => buildReadArgv('ls')).toThrow(BadRequest);
    for (const c of ['logs badsvc', 'down', 'restore', 'logs; rm', 'status && x', 'logs  ollama', 'logs ollama '])
      expect(() => buildReadArgv(c)).toThrow(BadRequest);
  });
  test('auditLine format', () => {
    const d = new Date('2026-01-01T00:00:00Z');
    expect(auditLine(d, 'restart', 'caddy')).toBe('2026-01-01T00:00:00.000Z · restart · caddy');
    expect(auditLine(d, 'status')).toBe('2026-01-01T00:00:00.000Z · status');
  });
});

import { buildBoxArgv } from '../src/exec-core';
describe('buildBoxArgv', () => {
  test('whole-box argv has no service', () => {
    expect(buildBoxArgv('restart')).toEqual([...C, 'restart']);
  });
  test('invalid action -> BadRequest', () => {
    expect(() => buildBoxArgv('down')).toThrow(BadRequest);
  });
});

describe('config (Config modal)', () => {
  const YAML =
    'model_list:\n  - model_name: qwen2.5-7b\n    litellm_params:\n' +
    '      model: openai/qwen2.5:7b\n      api_base: http://host.docker.internal:11434/v1\n' +
    '      api_key: os.environ/INFERENCE_API_KEY\n';

  test('validateConfigPatch accepts a good patch, rejects bad url/model', () => {
    expect(validateConfigPatch({ aiBaseUrl: 'http://10.0.0.9:8000/v1', aiModel: 'llama-3-70b' })).toEqual({
      aiBaseUrl: 'http://10.0.0.9:8000/v1',
      aiModel: 'llama-3-70b',
    });
    expect(() => validateConfigPatch({ aiBaseUrl: 'notaurl', aiModel: 'm' })).toThrow(BadRequest);
    expect(() => validateConfigPatch({ aiBaseUrl: 'http://x/v1', aiModel: 'bad model!' })).toThrow(BadRequest);
  });

  test('configViewFromYaml reads model + base; os.environ base shows blank', () => {
    expect(configViewFromYaml(YAML)).toEqual({ aiModel: 'qwen2.5:7b', aiBaseUrl: 'http://host.docker.internal:11434/v1' });
    const envBased = YAML.replace('http://host.docker.internal:11434/v1', 'os.environ/INFERENCE_BASE_URL');
    expect(configViewFromYaml(envBased).aiBaseUrl).toBe('');
  });

  test('applyConfigToYaml rewrites only model + api_base', () => {
    const out = applyConfigToYaml(YAML, { aiBaseUrl: 'http://10.0.0.9:8000/v1', aiModel: 'llama-3-70b-instruct' });
    expect(out).toContain('model: openai/llama-3-70b-instruct');
    expect(out).toContain('api_base: http://10.0.0.9:8000/v1');
    expect(out).toContain('api_key: os.environ/INFERENCE_API_KEY');
    expect(out).toContain('model_name: qwen2.5-7b');
  });

  test('applyConfigToYaml throws on an unrecognised config (no model line)', () => {
    expect(() => applyConfigToYaml('general_settings: {}\n', { aiBaseUrl: 'http://x/v1', aiModel: 'm' })).toThrow(BadRequest);
  });

  test('buildReconfigureArgv re-creates only litellm-proxy', () => {
    expect(buildReconfigureArgv()).toEqual(['docker', 'compose', '-p', 'nufi-box', 'restart', 'litellm-proxy']);
  });
});
