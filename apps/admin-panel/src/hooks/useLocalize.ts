import { useTranslation } from 'react-i18next';
import type * as t from '@/types';

export function useLocalize(): (
  phraseKey: t.TranslationKeys,
  options?: Record<string, string | number>,
) => string {
  const { t: translate } = useTranslation();

  const localize = (phraseKey: t.TranslationKeys, options?: Record<string, string | number>) =>
    translate(phraseKey, options ?? {});

  return localize;
}
