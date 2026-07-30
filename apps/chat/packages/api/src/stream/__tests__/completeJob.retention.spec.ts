import type { ServerSentEvent } from '~/types';
import { InMemoryEventTransport } from '~/stream/implementations/InMemoryEventTransport';
import { InMemoryJobStore } from '~/stream/implementations/InMemoryJobStore';
import { GenerationJobManagerClass } from '~/stream/GenerationJobManager';

/** Suppress winston Console transport output */
jest.spyOn(console, 'log').mockImplementation();

/**
 * A run can finish before the client that started it has connected to the SSE
 * stream — the POST that mints the streamId must return before the browser can
 * subscribe, so any run shorter than that round trip loses the race. Requests
 * refused upstream (security policy blocks, content filters) finish in a few
 * hundred milliseconds and lose it regularly.
 *
 * When that happened, the completed job had already been deleted, the subscribe
 * 404'd, and for a NEW conversation the client had no conversationId to refetch
 * by — so the assistant's reply was persisted but invisible until reload.
 */
describe('completeJob retention for late subscribers', () => {
  function createManager(): GenerationJobManagerClass {
    const manager = new GenerationJobManagerClass();
    manager.configure({
      jobStore: new InMemoryJobStore({ ttlAfterComplete: 60000 }),
      eventTransport: new InMemoryEventTransport(),
      isRedis: false,
    });
    manager.initialize();
    return manager;
  }

  let manager: GenerationJobManagerClass;

  beforeEach(() => {
    manager = createManager();
  });

  afterEach(async () => {
    await manager.destroy();
  });

  test('keeps a successfully completed job when no client has subscribed yet', async () => {
    const streamId = `no-subscriber-${Date.now()}`;
    await manager.createJob(streamId, 'user-1');

    await manager.completeJob(streamId);

    expect(await manager.getJob(streamId)).toBeDefined();
    expect(await manager.getJobStatus(streamId)).toBe('complete');
  });

  test('a late subscriber replays buffered content and receives the final event', async () => {
    const streamId = `late-subscriber-${Date.now()}`;
    await manager.createJob(streamId, 'user-1');

    const errorPart = {
      type: 'error',
      error:
        'This request was blocked by a security policy. (reference: grd_oata7syzkvv33vnxr7jaxhjume)',
    };
    await manager.emitChunk(streamId, errorPart as unknown as ServerSentEvent);
    await manager.emitDone(streamId, {
      final: true,
      responseMessage: { content: [errorPart] },
    } as unknown as ServerSentEvent);
    await manager.completeJob(streamId);

    const chunks: ServerSentEvent[] = [];
    const done: ServerSentEvent[] = [];

    const subscription = await manager.subscribe(
      streamId,
      (chunk) => chunks.push(chunk),
      (event) => done.push(event),
    );

    expect(subscription).not.toBeNull();
    await new Promise((resolve) => setImmediate(resolve));

    expect(chunks).toContainEqual(expect.objectContaining({ type: 'error' }));
    expect(done).toHaveLength(1);
    expect(JSON.stringify(done[0])).toContain('grd_oata7syzkvv33vnxr7jaxhjume');

    subscription?.unsubscribe();
  });

  test('still cleans up immediately once a subscriber has attached', async () => {
    const streamId = `with-subscriber-${Date.now()}`;
    await manager.createJob(streamId, 'user-1');

    const subscription = await manager.subscribe(
      streamId,
      () => undefined,
      () => undefined,
    );
    expect(subscription).not.toBeNull();

    await manager.completeJob(streamId);

    expect(await manager.getJob(streamId)).toBeUndefined();

    subscription?.unsubscribe();
  });

  test('error jobs are still retained, unchanged', async () => {
    const streamId = `error-job-${Date.now()}`;
    await manager.createJob(streamId, 'user-1');

    await manager.completeJob(streamId, 'boom');

    expect(await manager.getJobStatus(streamId)).toBe('error');
  });
});
