import type { ComponentType } from 'react';
import { HrBody } from './hr';
import { LlmSchedulingBody, LlmSchedulingFigure } from './llm-scheduling';
import { SealedNetworkBody } from './sealed-network';
import { AirGapBody } from './air-gap';
import { AnsweringBody } from './answering';
import { OpenSourceBody } from './open-source';
import { BoxStackArt } from '../components/post-art';
import type { AreaId } from './taxonomy';

// One entry per blog post. Display order comes from `date` (see taxonomy.ts).
export type PostMeta = {
  slug: string;
  title: string;
  summary: string;
  Body: ComponentType;
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
    title: 'When everyone asks the LLM at once',
    summary:
      'GPU time is the scarce resource of an AI-native platform. We flooded a model until an urgent agent couldn\'t get through, put a scheduler in front of it, and simulated what that means for a whole fab.',
    Body: LlmSchedulingBody,
    Figure: LlmSchedulingFigure,
    video: { src: '/blog/ai-native/video.mp4', poster: '/blog/ai-native/video-poster.jpg' },
  },
  {
    slug: 'whats-inside-the-box',
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-11-10',
    readingMinutes: 7,
    author: 'NuFi team',
    title: 'Everything inside the box, by name',
    summary:
      'What open source is actually inside NuFi Box? Every project, the version we run, its license and its job, read straight from the install files. Plus the two places the answer isn\'t simply "open source".',
    Body: OpenSourceBody,
    Figure: BoxStackArt,
  },
  {
    slug: 'how-the-box-answers',
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
    title: 'How the box answers from your files',
    summary:
      "How does it know what's in your documents? It reads them on the box, finds the passages that match your question, and answers from those — with the source attached.",
    Body: AnsweringBody,
  },
  {
    slug: 'air-gapped-ai-for-real',
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
    title: 'We unplugged the internet, and the box kept answering',
    summary:
      "Some sites can't have internet at all. We built the box so you can carry it in, load it, pull the cable, and still ask your documents questions.",
    Body: AirGapBody,
  },
  {
    slug: 'no-road-to-the-internet',
    area: 'nufi-box',
    series: 'how-it-works',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
    title: 'The box has no road to the internet',
    summary:
      '"Private AI" has become a checkbox. Here\'s the version we can show you, not just promise: on a sealed box, your documents have no route out to take.',
    Body: SealedNetworkBody,
  },
  {
    slug: 'hr-private-document-qa',
    area: 'nufi-box',
    series: 'field-notes',
    date: '2026-10-29',
    readingMinutes: 4,
    author: 'NuFi team',
    title: 'We put our HR handbook on a box and let the team interrogate it',
    summary:
      'One handbook, one box on the office network, an afternoon of the questions people actually email HR. Every answer quoted the document, and nothing left the building.',
    Body: HrBody,
  },
];

export const postBySlug = (slug: string): PostMeta | undefined => POSTS.find((p) => p.slug === slug);
