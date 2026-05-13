import React from 'react';

const SocialButton = ({ id, enabled, serverDomain, oauthPath, Icon, label }) => {
  if (!enabled) {
    return null;
  }

  return (
    <a
      aria-label={`${label}`}
      className="flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-card/40 px-4 py-2.5 text-sm font-medium text-foreground shadow-sm transition-all duration-200 hover:border-brand-purple/50 hover:bg-card/70"
      href={`${serverDomain}/oauth/${oauthPath}`}
      data-testid={id}
    >
      <span className="flex h-5 w-5 items-center justify-center">
        <Icon />
      </span>
      <span>{label}</span>
    </a>
  );
};

export default SocialButton;
