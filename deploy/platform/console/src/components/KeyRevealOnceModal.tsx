import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { useUi } from '~/stores/ui';
import { Button } from './ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

export function KeyRevealOnceModal() {
  const revealed = useUi((s) => s.revealedKey);
  const clear = useUi((s) => s.clearRevealedKey);
  const [copied, setCopied] = useState(false);

  if (!revealed) return null;

  async function copy() {
    if (!revealed) return;
    await navigator.clipboard.writeText(revealed.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2_000);
  }

  return (
    <Dialog open onOpenChange={(o) => !o && clear()}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Key created — copy it now</DialogTitle>
          <DialogDescription>
            This is the only time you’ll see the full value. Store it somewhere safe.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <div className="rounded-md border bg-muted p-3 font-mono text-xs break-all">
            {revealed.key}
          </div>
          <p className="text-xs text-muted-foreground">
            Alias: <span className="font-medium text-foreground">{revealed.alias}</span>
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={copy} className="gap-2">
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button onClick={clear}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
