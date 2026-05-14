import { Lock } from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { Button } from '@/components/ui';
import { useLocalize } from '@/hooks';

export function AccessDenied() {
  const localize = useLocalize();

  return (
    <div role="alert" className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Lock className="h-5 w-5" aria-hidden="true" />
      </div>
      <h2 className="text-xl font-semibold text-foreground">
        {localize('com_access_denied_title')}
      </h2>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        {localize('com_access_denied_description')}
      </p>
      <Button asChild variant="outline" size="sm" className="mt-2">
        <Link to="/configuration">{localize('com_nav_go_home')}</Link>
      </Button>
    </div>
  );
}
