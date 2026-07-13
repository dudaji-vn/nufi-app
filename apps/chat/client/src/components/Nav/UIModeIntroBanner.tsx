import { useRecoilState } from 'recoil';
import { useLocalize } from '~/hooks';
import store from '~/store';

export default function UIModeIntroBanner() {
  const localize = useLocalize();
  const [seen, setSeen] = useRecoilState(store.uiModeIntroSeen);

  if (seen) {
    return null;
  }

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 border-b border-border-light bg-surface-secondary px-4 py-2 text-sm text-text-primary"
    >
      <span>{localize('com_ui_mode_intro_banner')}</span>
      <button
        type="button"
        data-testid="ui-mode-intro-dismiss"
        className="rounded-md px-2 py-1 font-medium text-text-secondary hover:text-text-primary"
        onClick={() => setSeen(true)}
      >
        {localize('com_ui_mode_intro_dismiss')}
      </button>
    </div>
  );
}
