import { create } from 'zustand';
import './ui.css';

export type ToastTone = 'ok' | 'bad' | 'warn' | 'neutral';
type Toast = { id: number; msg: string; tone: ToastTone };

type State = {
  toasts: Toast[];
  push: (msg: string, tone?: ToastTone) => void;
  dismiss: (id: number) => void;
};

let nextId = 1;
const TTL_MS = 4000;

const useToastStore = create<State>((set, get) => ({
  toasts: [],
  push: (msg, tone = 'neutral') => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, msg, tone }] }));
    setTimeout(() => get().dismiss(id), TTL_MS);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function useToast() {
  const push = useToastStore((s) => s.push);
  return { push };
}

const TOAST_ICON: Record<ToastTone, string> = { ok: '✓', bad: '✕', warn: '!', neutral: 'i' };

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div className="ui-toaster" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} role="status" className={`ui-toast ui-toast--${t.tone}`}>
          <span className="ui-toast__ic" aria-hidden="true">{TOAST_ICON[t.tone]}</span>
          {t.msg}
        </div>
      ))}
    </div>
  );
}
