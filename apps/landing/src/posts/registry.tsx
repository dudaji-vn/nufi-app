import type { ComponentType } from 'react';
import { HrBody } from './hr';
import { SealedNetworkBody } from './sealed-network';
import { AirGapBody } from './air-gap';
import { AnsweringBody } from './answering';
import { SealedBoxArt, UnpluggedBoxArt, AnsweringArt } from '../components/post-art';

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
    slug: 'how-the-box-answers',
    kicker: 'How it works',
    title: 'How the box answers from your files',
    summary:
      "How does it know what's in your documents? It reads them on the box, finds the passages that match your question, and answers from those — with the source attached.",
    cta: 'Read the post',
    Body: AnsweringBody,
    Thumb: AnsweringArt,
  },
  {
    slug: 'air-gapped-ai-for-real',
    kicker: 'How it works',
    title: 'We unplugged the internet, and the box kept answering',
    summary:
      "Some sites can't have internet at all. We built the box so you can carry it in, load it, pull the cable, and still ask your documents questions.",
    cta: 'Read the post',
    Body: AirGapBody,
    Thumb: UnpluggedBoxArt,
  },
  {
    slug: 'no-road-to-the-internet',
    kicker: 'How it works',
    title: 'The box has no road to the internet',
    summary:
      '"Private AI" has become a checkbox. Here\'s the version we can show you, not just promise: on a sealed box, your documents have no route out to take.',
    cta: 'Read the post',
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
