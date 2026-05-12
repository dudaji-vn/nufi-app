import AddedConvo from './AddedConvo';
import type { TConversation } from 'librechat-data-provider';
import type { SetterOrUpdater } from 'recoil';

export default function TextareaHeader({
  addedConvo,
  setAddedConvo,
}: {
  addedConvo: TConversation | null;
  setAddedConvo: SetterOrUpdater<TConversation | null>;
}) {
  if (!addedConvo) {
    return null;
  }
  return (
    <div className="flex flex-col divide-y divide-border bg-transparent">
      <AddedConvo addedConvo={addedConvo} setAddedConvo={setAddedConvo} />
    </div>
  );
}
