import { useEffect, useRef } from 'react';
import { useRecoilState } from 'recoil';
import { useLocalize, useUIMode } from '~/hooks';
import store from '~/store';

export default function UIModeIntroBanner({
  onHeightChange,
}: {
  onHeightChange?: (height: number) => void;
}) {
  const localize = useLocalize();
  const { isBasic } = useUIMode();
  const [seen, setSeen] = useRecoilState(store.uiModeIntroSeen);
  const bannerRef = useRef<HTMLDivElement>(null);

  // The intro speaks only to Basic mode ("Basic interface enabled …"), so it
  // must disappear the moment the user is on Advanced — not linger with a now-
  // false message (and its reserved height) until it happens to be dismissed.
  const show = !seen && isBasic;

  useEffect(() => {
    onHeightChange?.(show && bannerRef.current ? bannerRef.current.offsetHeight : 0);
  }, [show, onHeightChange]);

  if (!show) {
    return null;
  }

  const handleDismiss = () => {
    setSeen(true);
    onHeightChange?.(0);
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
