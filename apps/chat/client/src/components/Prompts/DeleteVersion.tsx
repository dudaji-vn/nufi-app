import { Button, OGDialog, OGDialogTrigger, Label } from '~/components/ui';
import OGDialogTemplate from '~/components/ui/OGDialogTemplate';
import { TrashIcon } from '~/components/svg';
import { useLocalize } from '~/hooks';

const DeleteVersion = ({
  name,
  disabled,
  selectHandler,
}: {
  name: string;
  disabled?: boolean;
  selectHandler: () => void;
}) => {
  const localize = useLocalize();

  return (
    <OGDialog>
      <OGDialogTrigger asChild>
        <Button
          size={'sm'}
          className="h-10 w-10 border border-transparent bg-destructive text-white transition-all duration-200 hover:bg-destructive/80"
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation();
          }}
        >
          <TrashIcon className="icon-lg cursor-pointer text-white dark:text-white" />
        </Button>
      </OGDialogTrigger>
      <OGDialogTemplate
        showCloseButton={false}
        title={localize('com_ui_delete_prompt')}
        className="max-w-[450px]"
        main={
          <>
            <div className="flex w-full flex-col items-center gap-2">
              <div className="grid w-full items-center gap-2">
                <Label
                  htmlFor="dialog-delete-confirm-prompt"
                  className="text-left text-sm font-medium"
                >
                  {localize('com_ui_delete_confirm_prompt_version_var', name)}
                </Label>
              </div>
            </div>
          </>
        }
        selection={{
          selectHandler,
          selectClasses:
            'bg-destructive text-white transition-all duration-200 hover:bg-destructive/80',
          selectText: localize('com_ui_delete'),
        }}
      />
    </OGDialog>
  );
};

export default DeleteVersion;
