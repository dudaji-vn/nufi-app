import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/unauthorized')({
  component: UnauthorizedPage,
});

const CHAT_URL = import.meta.env.VITE_LIBRECHAT_URL ?? 'http://localhost:3080';

function UnauthorizedPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in required</h1>
      <p className="text-muted-foreground">
        The console reuses your chat session. Sign in there first, then come back to this tab.
      </p>
      <a
        href={CHAT_URL}
        className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Open chat
      </a>
    </section>
  );
}
