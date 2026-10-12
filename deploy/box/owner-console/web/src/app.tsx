import './app.css';
import { Files } from './tabs/files';
import { General } from './tabs/general';
import { Users } from './tabs/users';
import { useUi, type TabId } from './store';
import { NufiLogo } from './ui/logo';
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
      <header className="app-header">
        <span className="app-logo" aria-hidden="true"><NufiLogo height={26} /></span>
        <h1 className="app-title">Administrator Dashboard</h1>
      </header>
      <main className="app-body">
        <Tabs tabs={TABS} active={tab} onChange={(id) => setTab(id as TabId)} />
        {tab === 'general' && <General />}
        {tab === 'users' && <Users />}
        {tab === 'files' && <Files />}
      </main>
      <Toaster />
    </>
  );
}
