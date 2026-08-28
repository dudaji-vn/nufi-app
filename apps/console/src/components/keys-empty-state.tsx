import { useQuery } from '@tanstack/react-query';
import { Activity, KeyRound, Plus, Wallet } from 'lucide-react';
import { api } from '@/lib/orpc';
import { Button } from './ui/button';

const LITELLM_URL = import.meta.env.VITE_LITELLM_URL ?? 'http://localhost:4000';
const FALLBACK_MODEL = 'qwen2.5-3b';

export function KeysEmptyState({ onGenerate }: { onGenerate: () => void }) {
  const { data: models } = useQuery({
    ...api.models.list.queryOptions(),
    staleTime: 5 * 60_000,
  });
  const model = models?.[0]?.id ?? FALLBACK_MODEL;
  return (
    <div className="rounded-xl border bg-card p-6 text-card-foreground sm:p-10">
      <div className="mx-auto max-w-xl text-center">
        <div className="mx-auto inline-flex size-12 items-center justify-center rounded-full bg-muted">
          <KeyRound className="size-6 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-xl font-semibold tracking-tight">
          Welcome — let’s create your first key
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          API keys let your code call the platform directly. Each key has its own budget and limits,
          so you can hand one to a script or service without worrying about runaway cost.
        </p>
      </div>

      <ol className="mx-auto mt-8 grid max-w-2xl gap-4 sm:grid-cols-3">
        <Step
          n={1}
          icon={<KeyRound className="size-4" />}
          title="Generate"
          body="Pick an alias, set a budget and rate limits, hit Generate. The full key shows once — copy it."
        />
        <Step
          n={2}
          icon={<Activity className="size-4" />}
          title="Use it"
          body="Send it as Authorization: Bearer to the NUFI gateway. Same shape as the OpenAI API."
        />
        <Step
          n={3}
          icon={<Wallet className="size-4" />}
          title="Track usage"
          body="Watch your spend per key here. The bar turns amber and red as you approach the cap."
        />
      </ol>

      <div className="mx-auto mt-8 max-w-2xl rounded-md border bg-muted/40 p-3 text-left">
        <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          What a call looks like
        </p>
        <pre className="overflow-x-auto text-[11px] font-mono leading-relaxed text-muted-foreground sm:text-xs">
          {`curl ${LITELLM_URL}/v1/chat/completions \\
  -H "Authorization: Bearer sk-..." \\
  -H "Content-Type: application/json" \\
  -d '{"model":"${model}","messages":[
       {"role":"user","content":"hello"}]}'`}
        </pre>
      </div>

      <div className="mt-6 text-center">
        <Button onClick={onGenerate} className="gap-2" size="lg">
          <Plus className="size-4" />
          Generate your first key
        </Button>
      </div>
    </div>
  );
}

function Step({
  n,
  icon,
  title,
  body,
}: {
  n: number;
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <li className="relative rounded-lg border bg-background p-4">
      <div className="flex items-center gap-2">
        <span className="inline-flex size-6 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
          {n}
        </span>
        <span className="flex items-center gap-1.5 text-sm font-medium">
          {icon}
          {title}
        </span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{body}</p>
    </li>
  );
}
