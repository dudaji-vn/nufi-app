import type { ReactNode } from 'react';
import { Icon } from './icon';

// The recurring "sealed box" chrome around product screenshots: a window bar
// with three dots and a small lock/label tag, then the image.
export function BoxFrame({ tag, tagIcon, children }: { tag: string; tagIcon: string; children: ReactNode }) {
  return (
    <div className="boxframe">
      <div className="boxframe__bar">
        <span className="boxframe__dot" />
        <span className="boxframe__dot" />
        <span className="boxframe__dot" />
        <span className="boxframe__tag">
          <Icon name={tagIcon} /> {tag}
        </span>
      </div>
      {children}
    </div>
  );
}
