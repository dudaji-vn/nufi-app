import { useRecoilState } from 'recoil';
import store from '~/store';

export type UIMode = 'basic' | 'advanced';

export default function useUIMode() {
  const [mode, setMode] = useRecoilState<UIMode>(store.uiMode);
  return {
    mode,
    isBasic: mode === 'basic',
    isAdvanced: mode === 'advanced',
    setMode,
  };
}
