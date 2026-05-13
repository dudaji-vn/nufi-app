import { useLocalize } from '~/hooks';
import { Button, OGDialog, OGDialogTrigger } from '~/components/ui';
import OGDialogTemplate from '~/components/ui/OGDialogTemplate';

import ShareLinkTable from './SharedLinkTable';

export default function SharedLinks() {
  const localize = useLocalize();

  return (
    <div className="flex items-center justify-between">
      <div>{localize('com_nav_shared_links')}</div>

      <OGDialog>
        <OGDialogTrigger asChild>
          <Button variant="outline" size="sm">
            {localize('com_nav_shared_links_manage')}
          </Button>
        </OGDialogTrigger>
        <OGDialogTemplate
          title={localize('com_nav_shared_links')}
          className="max-w-[1000px]"
          showCancelButton={false}
          main={<ShareLinkTable />}
        />
      </OGDialog>
    </div>
  );
}
