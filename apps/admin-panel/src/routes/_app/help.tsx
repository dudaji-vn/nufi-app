import { createFileRoute } from '@tanstack/react-router';
import { HelpPage } from '@/components/help/HelpPage';

export const Route = createFileRoute('/_app/help')({
  head: () => ({
    meta: [{ title: 'Help | NuFi Admin Panel' }],
  }),
  component: HelpPage,
});
