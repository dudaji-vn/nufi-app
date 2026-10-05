import { General } from './tabs/general';
import { useUi, type TabId } from './store';
import { Tabs } from './ui/tabs';

const TABS = [
  { id: 'general', label: 'General' },
  { id: 'users', label: 'Users' },
  { id: 'files', label: 'File Sharing' },
];

export function App() {
  const { tab, setTab } = useUi();
  return (
    <main>
      <Tabs tabs={TABS} active={tab} onChange={(id) => setTab(id as TabId)} />
      {tab === 'general' && <General />}
      {tab === 'users' && <p>Users — coming soon</p>}
      {tab === 'files' && <p>File Sharing — coming soon</p>}
    </main>
  );
}
