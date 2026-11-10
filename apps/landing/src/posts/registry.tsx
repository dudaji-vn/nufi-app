import type { ComponentType } from 'react';
import { HrBody } from './hr';
import { LlmSchedulingBody, LlmSchedulingFigure } from './llm-scheduling';
import { SealedNetworkBody } from './sealed-network';
import { AirGapBody } from './air-gap';
import { AnsweringBody } from './answering';
import { SealedBoxArt, UnpluggedBoxArt, AnsweringArt } from '../components/post-art';
import type { AreaId } from './taxonomy';

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
  // Library metadata (see taxonomy.ts)
  area: AreaId;
  series: string;
  date: string; // ISO yyyy-mm-dd
  readingMinutes: number;
  author: string;
  video?: { src: string; poster: string };
  // A real figure from inside the post, shown in the blog's "Latest" slot
  Figure?: ComponentType;
};

export const POSTS: PostMeta[] = [
  {
    slug: 'when-everyone-asks-the-llm-at-once',
    area: 'engineering',
    series: 'ai-native-platform',
    date: '2026-11-10',
    readingMinutes: 9,
    author: 'Dudaji AI team',
    kicker: 'Engineering · AI-native platform',
    title: 'When everyone asks the LLM at once',
    summary:
      'GPU time is the scarce resource of an AI-native platform. We flooded a model until an urgent agent couldn\'t get through, put a scheduler in front of it, and simulated what that means for a whole fab.',
    cta: 'Read the post',
    Body: LlmSchedulingBody,
    Figure: LlmSchedulingFigure,
  },
  {
    slug: 'how-the-box-answers',
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
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
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
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
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
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
    area: 'nufi-box',
    series: 'field-notes',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
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
