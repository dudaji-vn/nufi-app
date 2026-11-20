import type { ComponentType } from 'react';
import { HrBody } from './hr';
import { LlmSchedulingBody, LlmSchedulingFigure } from './llm-scheduling';
import { DeepStoreCompareBody, DeepStoreCompareFigure } from './deep-store-compare';
import { OneNightBody, OneNightFigure } from './one-night';
import { FlinkAlertsBody, FlinkAlertsFigure } from './flink-alerts';
import { EquipmentCheckBody, EquipmentCheckFigure } from './equipment-check';
import { ClickHouseHistoryBody, ClickHouseHistoryFigure } from './clickhouse-history';
import { FlowcoBody, FlowcoFigure } from './flowco';
import { SemanticOperatorsBody, SemanticOperatorsFigure } from './semantic-operators';
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
    slug: 'clickhouse-sensor-history-213-mib',
    area: 'engineering',
    series: 'realtime-data',
    date: '2026-11-20',
    readingMinutes: 9,
    author: 'Dudaji AI team',
    title: "93 million readings in 213 MiB: storing a fab's sensor history in ClickHouse",
    summary:
      'Measured one change at a time: two column codecs made the table 3.6 times smaller, the sort key decides what a query can skip, a 0.3 MB skip index finds a lot 90 times faster than a scan in the lab (7 times on the de-duplicating store), and the roll-ups that worked in the lab would have double-counted on the real table, so Flink computes them.',
    Body: ClickHouseHistoryBody,
    Figure: ClickHouseHistoryFigure,
  },
  {
    slug: 'equipment-check-before-a-lot',
    area: 'engineering',
    series: 'realtime-data',
    date: '2026-11-20',
    readingMinutes: 9,
    author: 'Dudaji AI team',
    title: 'Holding a lot before the pump fails: three versions of an equipment check',
    summary:
      'A Flink check that holds a lot before a chamber\'s pump reaches its alarm. The textbook join silently withheld its most important answer; a 5-minute trend would raise 87 false alarms per chamber-day on simulated wandering sensors, a significance test and the chamber\'s own band brought that to 0.016; a pump swap needed a third version.',
    Body: EquipmentCheckBody,
    Figure: EquipmentCheckFigure,
  },
  {
    slug: 'flowco-one-node-many-levels',
    area: 'engineering',
    series: 'semantic-data',
    date: '2026-11-20',
    readingMinutes: 8,
    author: 'Dudaji AI team',
    title: "One node, many levels: what Flowco teaches about keeping an LLM's work in sync",
    summary:
      'A data step you can read as a sentence, a contract or code, and edit in any of them. Flowco is the closest working system; we read its paper and code. Going down is engineered — one node and one level per LLM call, a cache, regeneration from a diff. Going up is left to a chat agent.',
    Body: FlowcoBody,
    Figure: FlowcoFigure,
  },
  {
    slug: 'semantic-operators-rule-or-model',
    area: 'engineering',
    series: 'semantic-data',
    date: '2026-11-20',
    readingMinutes: 8,
    author: 'Dudaji AI team',
    title: 'A keyword rule or a language model? Semantic operators on 200 maintenance notes',
    summary:
      'We ran LOTUS with local models on synthetic maintenance notes, against a keyword rule. The rule was perfect on its own words and found none of the pump problems on new ones; qwen2.5 7B reached F1 0.911. Letting the rule pick the part and asking the model only about the symptom gave 1.000 with 74 model calls instead of 200.',
    Body: SemanticOperatorsBody,
    Figure: SemanticOperatorsFigure,
  },
  {
    slug: 'sensor-reading-to-alert-flink',
    area: 'engineering',
    series: 'realtime-data',
    date: '2026-11-19',
    readingMinutes: 9,
    author: 'Dudaji AI team',
    title: 'From a sensor reading to an alert, in Flink',
    summary:
      'Our Flink alert job, measured: where its 6.5 seconds go, patterns that warn 22 minutes before a limit, matching 100,000 rules in a quarter of a microsecond, exactly-once tested by crashing it — and the traps that dropped alerts without an error.',
    Body: FlinkAlertsBody,
    Figure: FlinkAlertsFigure,
  },
  {
    slug: 'one-night-at-the-fab',
    area: 'engineering',
    series: 'realtime-data',
    date: '2026-11-19',
    readingMinutes: 7,
    author: 'Dudaji AI team',
    title: 'One night at the fab',
    summary:
      'A recipe change drifts one chamber while a pump wears out. We replayed that night through Kafka, Flink and ClickHouse: every alert and lot decision checked and timed, the cause found in milliseconds, and a Flink worker killed live.',
    Body: OneNightBody,
    Figure: OneNightFigure,
    video: { src: '/blog/realtime/one-night.mp4', poster: '/blog/realtime/one-night-poster.jpg' },
  },
  {
    slug: 'clickhouse-postgresql-timescaledb-sensor-history',
    area: 'engineering',
    series: 'realtime-data',
    date: '2026-11-18',
    readingMinutes: 9,
    author: 'Dudaji AI team',
    title: "ClickHouse, PostgreSQL or TimescaleDB for a fab's sensor history?",
    summary:
      'The same 93.5 million synthetic readings, the same guarantees, the same questions in three databases, measured on one laptop. ClickHouse wins writing, storing and scanning history; PostgreSQL wins the lookups an index answers; TimescaleDB is not the middle it looks like.',
    Body: DeepStoreCompareBody,
    Figure: DeepStoreCompareFigure,
    video: { src: '/blog/realtime/deep-store-compare.mp4', poster: '/blog/realtime/deep-store-compare-poster.jpg' },
  },
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
    title: "What's inside the box, by name",
    summary:
      'What open source is actually inside NuFi Box? The projects that do the work, with the version we run, the license and the job of each, read straight from the install files.',
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
