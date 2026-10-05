import { Files } from './tabs/files';
import { General } from './tabs/general';
import { Users } from './tabs/users';
import { useUi, type TabId } from './store';
import { Tabs } from './ui/tabs';
import { Toaster } from './ui/toast';

const TABS = [
  { id: 'general', label: 'General' },
  { id: 'users', label: 'Users' },
  { id: 'files', label: 'File Sharing' },
];

export function App() {
  const { tab, setTab } = useUi();
  return (
    <>
    <main>
      <Tabs tabs={TABS} active={tab} onChange={(id) => setTab(id as TabId)} />
      {tab === 'general' && <General />}
      {tab === 'users' && <Users />}
      {tab === 'files' && <Files />}
    </main>
    <Toaster />
    </>
  );
}
