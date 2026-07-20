import { Button } from '@/components/ui';
import { useLocalize } from '@/hooks';

export function PermissionsUnavailable() {
  const localize = useLocalize();
  return (
    <div role="alert" className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
      <h2 className="text-xl font-semibold text-foreground">
        {localize('com_perm_unavailable_title')}
      </h2>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        {localize('com_perm_unavailable_desc')}
      </p>
      <Button variant="outline" size="sm" onClick={() => window.location.reload()} className="mt-2">
        {localize('com_ui_reload')}
      </Button>
    </div>
  );
}
