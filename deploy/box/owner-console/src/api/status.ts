import type { BoxInfo } from '../boxinfo';
import type { Health } from '../health';

export type StatusResponse = { box: BoxInfo; services: Health[] };

export async function buildStatus(
  getBox: () => BoxInfo,
  checkHealth: () => Promise<Health[]>,
): Promise<StatusResponse> {
  return { box: getBox(), services: await checkHealth() };
}
