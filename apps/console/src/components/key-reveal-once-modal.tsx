import { useQuery } from '@tanstack/react-query';
import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { api } from '@/lib/orpc';
import { useUi } from '@/stores/ui';
import { Button } from './ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';

const LITELLM_URL = import.meta.env.VITE_LITELLM_URL ?? 'http://localhost:4000';
const FALLBACK_MODEL = 'qwen2.5-3b';

const snippets = (key: string, model: string) => ({
  curl: `curl ${LITELLM_URL}/v1/chat/completions \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "hello"}]
  }'`,
  python: `from openai import OpenAI

client = OpenAI(
    api_key="${key}",
    base_url="${LITELLM_URL}/v1",
)

resp = client.chat.completions.create(
    model="${model}",
    messages=[{"role": "user", "content": "hello"}],
)
print(resp.choices[0].message.content)`,
  javascript: `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "${key}",
  baseURL: "${LITELLM_URL}/v1",
});

const resp = await client.chat.completions.create({
  model: "${model}",
  messages: [{ role: "user", content: "hello" }],
});
console.log(resp.choices[0].message.content);`,
});

export function KeyRevealOnceModal() {
  const revealed = useUi((s) => s.revealedKey);
  const clear = useUi((s) => s.clearRevealedKey);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);

  const { data: models } = useQuery({
    ...api.models.list.queryOptions(),
    enabled: !!revealed,
    staleTime: 5 * 60_000,
  });

  if (!revealed) return null;

  const model = models?.[0]?.id ?? FALLBACK_MODEL;
  const code = snippets(revealed.key, model);

  async function copy(text: string, kind: 'key' | string) {
    try {
      await navigator.clipboard.writeText(text);
      if (kind === 'key') {
        setCopiedKey(true);
        toast.success('Key copied to clipboard');
        setTimeout(() => setCopiedKey(false), 2000);
      } else {
        setCopiedSnippet(kind);
        toast.success('Snippet copied');
        setTimeout(() => setCopiedSnippet((c) => (c === kind ? null : c)), 2000);
      }
    } catch {
      toast.error('Clipboard write failed — copy manually');
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && clear()}>
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>Save your new key</DialogTitle>
          <DialogDescription>
            Copy it now — you won’t see the full value again. Treat it like a password.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {revealed.alias}
            </p>
            <div className="flex items-center gap-2 rounded-md border bg-muted p-3">
              <code className="flex-1 truncate font-mono text-sm">{revealed.key}</code>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => copy(revealed.key, 'key')}
                className="gap-1.5"
              >
                {copiedKey ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copiedKey ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>

          <div className="space-y-2 pt-2">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              How to use it
            </p>
            <Tabs defaultValue="curl">
              <TabsList>
                <TabsTrigger value="curl">curl</TabsTrigger>
                <TabsTrigger value="python">Python</TabsTrigger>
                <TabsTrigger value="javascript">JavaScript</TabsTrigger>
              </TabsList>
              {(['curl', 'python', 'javascript'] as const).map((kind) => (
                <TabsContent key={kind} value={kind}>
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-md border bg-muted p-3 font-mono text-xs leading-relaxed">
                      {code[kind]}
                    </pre>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copy(code[kind], kind)}
                      className="absolute top-2 right-2 gap-1.5"
                    >
                      {copiedSnippet === kind ? (
                        <Check className="size-3.5" />
                      ) : (
                        <Copy className="size-3.5" />
                      )}
                      {copiedSnippet === kind ? 'Copied' : 'Copy'}
                    </Button>
                  </div>
                </TabsContent>
              ))}
            </Tabs>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={clear}>I’ve saved it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
