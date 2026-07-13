import { useEffect, useRef } from 'react';
import { useRecoilState } from 'recoil';
import { useLocalize } from '~/hooks';
import store from '~/store';

export default function UIModeIntroBanner({
  onHeightChange,
}: {
  onHeightChange?: (height: number) => void;
}) {
  const localize = useLocalize();
  const [seen, setSeen] = useRecoilState(store.uiModeIntroSeen);
  const bannerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (onHeightChange && bannerRef.current) {
      onHeightChange(bannerRef.current.offsetHeight);
    }
  }, [seen, onHeightChange]);

  if (seen) {
    return null;
  }

  const handleDismiss = () => {
    setSeen(true);

    if (onHeightChange) {
      onHeightChange(0);
    }
  };

  return (
    <div
      ref={bannerRef}
      role="status"
      className="flex items-center justify-between gap-3 border-b border-border-light bg-surface-secondary px-4 py-2 text-sm text-text-primary"
    >
      <span>{localize('com_ui_mode_intro_banner')}</span>
      <button
        type="button"
        data-testid="ui-mode-intro-dismiss"
        className="rounded-md px-2 py-1 font-medium text-text-secondary hover:text-text-primary"
        onClick={handleDismiss}
      >
        {localize('com_ui_mode_intro_dismiss')}
      </button>
    </div>
  );
}
