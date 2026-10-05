import { describe, expect, test } from 'bun:test';
import { BadRequest, auditLine, buildControlArgv, buildReadArgv } from '../src/exec-core';

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
  test('read argv exact', () => {
    expect(buildReadArgv('status')).toEqual([...C, 'ps']);
    expect(buildReadArgv('logs librechat')).toEqual([...C, 'logs', '--no-color', '--tail=200', 'librechat']);
    expect(buildReadArgv('doctor')).toBeNull();
  });
  test('off-list read rejected', () => {
    expect(() => buildReadArgv('logs librechat; id')).toThrow(BadRequest);
    expect(() => buildReadArgv('ls')).toThrow(BadRequest);
  });
  test('auditLine format', () => {
    const d = new Date('2026-01-01T00:00:00Z');
    expect(auditLine(d, 'restart', 'caddy')).toBe('2026-01-01T00:00:00.000Z · restart · caddy');
    expect(auditLine(d, 'status')).toBe('2026-01-01T00:00:00.000Z · status');
  });
});
