import { createFileRoute } from '@tanstack/react-router';
import { HelpPage } from '@/components/help/HelpPage';

export const Route = createFileRoute('/_app/help')({
  head: () => ({
    meta: [{ title: 'Help | NUFI Admin Panel' }],
  }),
  component: HelpPage,
});
