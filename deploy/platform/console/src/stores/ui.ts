import { create } from 'zustand';

type RevealedKey = {
  alias: string;
  key: string;
};

type UiState = {
  generateOpen: boolean;
  setGenerateOpen: (v: boolean) => void;

  revealedKey: RevealedKey | null;
  showRevealedKey: (k: RevealedKey) => void;
  clearRevealedKey: () => void;
};

export const useUi = create<UiState>((set) => ({
  generateOpen: false,
  setGenerateOpen: (generateOpen) => set({ generateOpen }),

  revealedKey: null,
  showRevealedKey: (revealedKey) => set({ revealedKey, generateOpen: false }),
  clearRevealedKey: () => set({ revealedKey: null }),
}));
