import type { ComponentType } from 'react';
import { HrBody } from './hr';
import { SealedNetworkBody } from './sealed-network';
import { SealedBoxArt } from '../components/post-art';

// One entry per blog post. Order is display order (newest first). A post's card
// thumbnail is either an image (`thumbSrc`) or a drawn component (`Thumb`).
export type PostMeta = {
  slug: string;
  kicker: string;
  title: string;
  summary: string;
  cta: string;
  Body: ComponentType;
  thumbSrc?: string;
  thumbAlt?: string;
  Thumb?: ComponentType;
};

export const POSTS: PostMeta[] = [
  {
    slug: 'no-road-to-the-internet',
    kicker: 'How it works',
    title: 'The box has no road to the internet',
    summary:
      '"Private AI" has become a checkbox. Here\'s the version we can show you, not just promise: on a sealed box, your documents have no route out to take.',
    cta: 'How it works',
    Body: SealedNetworkBody,
    Thumb: SealedBoxArt,
  },
  {
    slug: 'hr-private-document-qa',
    kicker: 'Field notes · HR',
    title: 'We put our HR handbook on a box and let the team interrogate it',
    summary:
      'One handbook, one box on the office network, an afternoon of the questions people actually email HR. Every answer quoted the document, and nothing left the building.',
    cta: 'Read the field notes',
    Body: HrBody,
    thumbSrc: '/blog/security.png',
    thumbAlt: 'A cited answer about the company security policy',
  },
];

export const postBySlug = (slug: string): PostMeta | undefined => POSTS.find((p) => p.slug === slug);
