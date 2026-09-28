import { describe, expect, test } from 'bun:test';
import { boxInfo } from '../src/boxinfo';

describe('boxInfo', () => {
  test('reads identity and departments from env', () => {
    const info = boxInfo({ BOX_NAME: 'nufi', BOX_HOST: 'nufi.local', BOX_IP: '192.168.1.10', DEPARTMENTS: 'legal, hr ,' });
    expect(info.name).toBe('nufi');
    expect(info.host).toBe('nufi.local');
    expect(info.ip).toBe('192.168.1.10');
    expect(info.departments).toEqual(['legal', 'hr']); // trimmed, empties dropped
  });

  test('a box with a mesh address reads as joined', () => {
    const info = boxInfo({
      MESH_SERVER_URL: 'https://coordinator.internal',
      NUFI_SELF_HOST_COORD: '1',
      BOX_MESH_IP: '100.64.0.1',
      BOX_MESH_HOST: 'nufi.box.internal',
    });
    expect(info.mesh.joined).toBe(true);
    expect(info.mesh.ip).toBe('100.64.0.1');
    expect(info.mesh.host).toBe('nufi.box.internal');
    expect(info.mesh.selfHost).toBe(true);
    expect(info.mesh.serverUrl).toBe('https://coordinator.internal');
  });

  test('a box with no mesh address reads as LAN-only (not joined)', () => {
    const info = boxInfo({ BOX_HOST: 'nufi.local' });
    expect(info.mesh.joined).toBe(false);
    expect(info.mesh.selfHost).toBe(false);
    expect(info.mesh.ip).toBe('');
  });

  test('empty env yields empty-but-shaped values, never throws', () => {
    const info = boxInfo({});
    expect(info.name).toBe('');
    expect(info.departments).toEqual([]);
    expect(info.mesh.joined).toBe(false);
  });
});
