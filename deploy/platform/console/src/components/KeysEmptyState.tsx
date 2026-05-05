import { KeyRound, Plus } from 'lucide-react';
import { Button } from './ui/button';

export function KeysEmptyState({ onGenerate }: { onGenerate: () => void }) {
  return (
    <div className="rounded-xl border bg-card p-10 text-center text-card-foreground">
      <div className="mx-auto inline-flex size-12 items-center justify-center rounded-full bg-muted">
        <KeyRound className="size-6 text-muted-foreground" />
      </div>
      <h3 className="mt-4 text-lg font-semibold">Create your first API key</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        API keys let you call the platform from your code. Each key has its own budget and rate limits.
      </p>

      <div className="mx-auto mt-6 max-w-md rounded-md border bg-muted/40 p-3 text-left">
        <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          What you’ll do with it
        </p>
        <pre className="overflow-x-auto text-xs font-mono leading-relaxed text-muted-foreground">
{`curl http://localhost:4000/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"qwen2.5-3b","messages":[
       {"role":"user","content":"hello"}]}'`}
        </pre>
      </div>

      <Button onClick={onGenerate} className="mt-6 gap-2">
        <Plus className="size-4" />
        Generate Key
      </Button>
    </div>
  );
}
