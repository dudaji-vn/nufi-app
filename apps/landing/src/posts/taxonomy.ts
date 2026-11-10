import type { PostMeta } from './registry';

// The blog is a small library: areas → series → posts. Series without posts yet are shown greyed
// ("next" / "soon") so readers can see where a topic is going.
export type AreaId = 'engineering' | 'nufi-box';
export type SeriesStatus = 'live' | 'next' | 'soon';
export type Series = { id: string; name: string; intro: string; status: SeriesStatus };
export type Area = { id: AreaId; name: string; intro: string; series: Series[] };

export const AREAS: Area[] = [
  {
    id: 'engineering',
    name: 'Engineering',
    intro:
      'How factories can run their data platforms on AI: GPUs, agents and real-time data. Every number comes from a real run or a clearly labelled simulation.',
    series: [
      {
        id: 'ai-native-platform',
        name: 'AI-native platform',
        intro: 'What it means to run AI as shared infrastructure, and how to build it from open source.',
        status: 'live',
      },
      { id: 'aiops', name: 'AIOps', intro: 'The AI platform watching itself.', status: 'next' },
      { id: 'apache-flink', name: 'Apache Flink', intro: 'Real-time streams that wake agents up.', status: 'soon' },
    ],
  },
  {
    id: 'nufi-box',
    name: 'NuFi Box',
    intro: 'How the private AI box works, and what happened when real teams used it.',
    series: [
      { id: 'how-it-works', name: 'How it works', intro: 'What happens inside the box.', status: 'live' },
      { id: 'field-notes', name: 'Field notes', intro: 'Real teams, real documents, real questions.', status: 'live' },
    ],
  },
];

export const areaById = (id: string): Area | undefined => AREAS.find((a) => a.id === id);

export function seriesOf(post: PostMeta): Series {
  const s = areaById(post.area)?.series.find((x) => x.id === post.series);
  if (!s) throw new Error(`post ${post.slug}: unknown series ${post.area}/${post.series}`);
  return s;
}

export const postPath = (post: PostMeta): string => `${areaById(post.area)!.name} › ${seriesOf(post).name}`;

const byDateAsc = (a: PostMeta, b: PostMeta) => a.date.localeCompare(b.date) || a.slug.localeCompare(b.slug);

export const postsInSeries = (posts: PostMeta[], areaId: AreaId, seriesId: string): PostMeta[] =>
  posts.filter((p) => p.area === areaId && p.series === seriesId).sort(byDateAsc);

export const latest = (posts: PostMeta[]): PostMeta[] =>
  [...posts].sort((a, b) => b.date.localeCompare(a.date) || a.slug.localeCompare(b.slug));

export const areaSummary = (posts: PostMeta[], area: Area): { series: Series; count: number }[] =>
  area.series.map((series) => ({ series, count: postsInSeries(posts, area.id, series.id).length }));

export function adjacentInSeries(posts: PostMeta[], slug: string): { prev?: PostMeta; next?: PostMeta } {
  const post = posts.find((p) => p.slug === slug);
  if (!post) return {};
  const list = postsInSeries(posts, post.area, post.series);
  const i = list.findIndex((p) => p.slug === slug);
  const out: { prev?: PostMeta; next?: PostMeta } = {};
  if (i > 0) out.prev = list[i - 1];
  if (i < list.length - 1) out.next = list[i + 1];
  return out;
}

export const formatDate = (iso: string): string => iso.replaceAll('-', '.');
