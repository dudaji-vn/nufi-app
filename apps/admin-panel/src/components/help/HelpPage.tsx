import { Icon } from '@clickhouse/click-ui';
import { useLocalize } from '@/hooks';

const RESOURCES = [
  {
    titleKey: 'com_help_docs_title',
    descKey: 'com_help_docs_desc',
    icon: 'document',
    href: 'https://www.librechat.ai/docs',
  },
  {
    titleKey: 'com_help_api_title',
    descKey: 'com_help_api_desc',
    icon: 'code',
    href: 'https://www.librechat.ai/docs/configuration',
  },
  {
    titleKey: 'com_help_community_title',
    descKey: 'com_help_community_desc',
    icon: 'users',
    href: 'https://github.com/danny-avila/LibreChat',
  },
  {
    titleKey: 'com_help_discord_title',
    descKey: 'com_help_discord_desc',
    icon: 'chat',
    href: 'https://discord.librechat.ai',
  },
] as const;

export function HelpPage() {
  const localize = useLocalize();

  return (
    <div
      role="region"
      aria-label={localize('com_nav_help')}
      className="flex flex-1 flex-col gap-6 overflow-auto p-6"
    >
      <section aria-label={localize('com_help_resources')}>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">
          {localize('com_help_resources')}
        </h3>
        <div className="flex flex-col gap-3">
          {RESOURCES.map((resource) => (
            <a
              key={resource.titleKey}
              href={resource.href}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-3 rounded-lg border border-border bg-card p-4 no-underline transition-colors hover:bg-accent"
            >
              <span aria-hidden="true" className="mt-0.5 text-muted-foreground">
                <Icon name={resource.icon} size="sm" />
              </span>
              <div className="flex flex-col gap-0.5">
                <span className="text-sm font-medium text-foreground">
                  {localize(resource.titleKey)}
                  <span
                    aria-hidden="true"
                    className="ml-1.5 inline-block text-muted-foreground"
                  >
                    ↗
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  {localize(resource.descKey)}
                </span>
              </div>
            </a>
          ))}
        </div>
      </section>

      <section aria-label={localize('com_help_support')}>
        <div className="rounded-lg border border-border bg-muted px-4 py-3">
          <span className="text-sm text-muted-foreground">
            <span aria-hidden="true" className="mr-1.5 inline-block align-middle">
              <Icon name="question" size="xs" />
            </span>
            {localize('com_help_support_text')}
          </span>
        </div>
      </section>
    </div>
  );
}
