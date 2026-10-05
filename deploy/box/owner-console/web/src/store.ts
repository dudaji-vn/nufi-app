import { create } from 'zustand';

export type TabId = 'general' | 'users' | 'files';

type UiState = {
  tab: TabId;
  setTab: (tab: TabId) => void;
  filePath: string;
  setFilePath: (p: string) => void;
  modal: string | null;
  setModal: (modal: string | null) => void;
};

export const useUi = create<UiState>((set) => ({
  tab: 'general',
  setTab: (tab) => set({ tab }),
  filePath: '',
  setFilePath: (filePath) => set({ filePath }),
  modal: null,
  setModal: (modal) => set({ modal }),
}));
