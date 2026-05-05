import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '~/lib/orpc';
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
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';

const BUDGET_DURATIONS = ['24h', '7d', '30d'] as const;
const KEY_DURATIONS = ['7d', '30d', '90d', '180d', '365d', 'never'] as const;

const DEFAULTS = {
  maxBudget: '10',
  budgetDuration: '30d' as const,
  tpmLimit: '10000',
  rpmLimit: '60',
  duration: '90d' as const,
};

export function KeyGenerateModal() {
  const open = useUi((s) => s.generateOpen);
  const setOpen = useUi((s) => s.setGenerateOpen);
  const showRevealedKey = useUi((s) => s.showRevealedKey);

  const [alias, setAlias] = useState('');
  const [maxBudget, setMaxBudget] = useState(DEFAULTS.maxBudget);
  const [budgetDuration, setBudgetDuration] = useState<typeof BUDGET_DURATIONS[number]>(DEFAULTS.budgetDuration);
  const [tpmLimit, setTpmLimit] = useState(DEFAULTS.tpmLimit);
  const [rpmLimit, setRpmLimit] = useState(DEFAULTS.rpmLimit);
  const [duration, setDuration] = useState<typeof KEY_DURATIONS[number]>(DEFAULTS.duration);

  const qc = useQueryClient();
  const create = useMutation(
    api.keys.create.mutationOptions({
      onSuccess: (res) => {
        showRevealedKey({ alias: res.view.alias ?? alias, key: res.key });
        qc.invalidateQueries({ queryKey: api.keys.list.queryKey() });
        toast.success(`Key "${res.view.alias ?? alias}" generated`);
        setAlias('');
        setMaxBudget(DEFAULTS.maxBudget);
        setBudgetDuration(DEFAULTS.budgetDuration);
        setTpmLimit(DEFAULTS.tpmLimit);
        setRpmLimit(DEFAULTS.rpmLimit);
        setDuration(DEFAULTS.duration);
      },
      onError: (err) => {
        toast.error(`Could not generate key: ${err.message}`);
      },
    }),
  );

  function submit(e: React.FormEvent) {
    e.preventDefault();
    create.mutate({
      alias: alias.trim(),
      maxBudget: Number(maxBudget),
      budgetDuration,
      tpmLimit: Number(tpmLimit),
      rpmLimit: Number(rpmLimit),
      duration,
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-[480px]">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Generate API key</DialogTitle>
            <DialogDescription>
              Use this key to call the LiteLLM proxy directly. The full value is shown once after creation.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="alias">Alias</Label>
            <Input
              id="alias"
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              placeholder="e.g. my-laptop"
              required
              maxLength={64}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="budget">Max budget (USD)</Label>
              <Input
                id="budget"
                type="number"
                min={0.01}
                step={0.01}
                value={maxBudget}
                onChange={(e) => setMaxBudget(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Budget period</Label>
              <Select value={budgetDuration} onValueChange={(v) => setBudgetDuration(v as typeof BUDGET_DURATIONS[number])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BUDGET_DURATIONS.map((d) => (
                    <SelectItem key={d} value={d}>{d}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="tpm">TPM limit</Label>
              <Input
                id="tpm"
                type="number"
                min={1}
                step={1}
                value={tpmLimit}
                onChange={(e) => setTpmLimit(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rpm">RPM limit</Label>
              <Input
                id="rpm"
                type="number"
                min={1}
                step={1}
                value={rpmLimit}
                onChange={(e) => setRpmLimit(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Expires</Label>
            <Select value={duration} onValueChange={(v) => setDuration(v as typeof KEY_DURATIONS[number])}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KEY_DURATIONS.map((d) => (
                  <SelectItem key={d} value={d}>{d === 'never' ? 'Never' : `in ${d}`}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || alias.trim().length === 0}>
              {create.isPending ? 'Generating…' : 'Generate'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
