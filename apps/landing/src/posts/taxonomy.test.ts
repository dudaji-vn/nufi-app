import { describe, expect, test } from 'bun:test';
import { POSTS, postBySlug, type PostMeta } from './registry';
import {
  AREAS,
  adjacentInSeries,
  areaById,
  areaSummary,
  formatDate,
  latest,
  postPath,
  postsInSeries,
} from './taxonomy';

const fake = (slug: string, date: string, area: PostMeta['area'], series: string): PostMeta => ({
  ...POSTS[0],
  slug,
  date,
  area,
  series,
});

describe('blog taxonomy', () => {
  test('no post slug equals an area id', () => {
    for (const p of POSTS) expect(areaById(p.slug)).toBeUndefined();
  });

  test('the four original slugs still resolve via postBySlug', () => {
    for (const slug of ['how-the-box-answers', 'air-gapped-ai-for-real', 'no-road-to-the-internet', 'hr-private-document-qa'])
      expect(postBySlug(slug)?.slug).toBe(slug);
  });

  test("every post's series exists in its area", () => {
    for (const p of POSTS) {
      const area = areaById(p.area);
      expect(area).toBeDefined();
      expect(area!.series.some((s) => s.id === p.series)).toBe(true);
    }
  });

  test('area names are exactly Engineering and NuFi Box', () => {
    expect(AREAS.map((a) => a.name)).toEqual(['Engineering', 'NuFi Box']);
  });

  test('areaSummary gives count 0 for next/soon series without throwing', () => {
    const eng = areaById('engineering')!;
    const rows = areaSummary(POSTS, eng);
    const aiops = rows.find((r) => r.series.id === 'aiops')!;
    expect(aiops.count).toBe(0);
    expect(aiops.series.status).toBe('next');
    expect(rows.find((r) => r.series.id === 'apache-flink')!.series.status).toBe('soon');
  });

  test('postPath joins area and series names', () => {
    expect(postPath(postBySlug('hr-private-document-qa')!)).toBe('NuFi Box › Field notes');
  });

  test('formatDate uses dots', () => {
    expect(formatDate('2026-11-14')).toBe('2026.11.14');
  });

  test('latest() puts the newest first, then slug order', () => {
    const posts = [fake('b', '2026-10-01', 'nufi-box', 'how-it-works'), fake('c', '2026-11-01', 'nufi-box', 'how-it-works'), fake('a', '2026-10-01', 'nufi-box', 'how-it-works')];
    expect(latest(posts).map((p) => p.slug)).toEqual(['c', 'a', 'b']);
  });

  test('postsInSeries is oldest first (chapter order)', () => {
    const posts = [fake('two', '2026-11-02', 'engineering', 'aiops'), fake('one', '2026-11-01', 'engineering', 'aiops')];
    expect(postsInSeries(posts, 'engineering', 'aiops').map((p) => p.slug)).toEqual(['one', 'two']);
  });

  test('adjacentInSeries returns prev/next within one series only', () => {
    const posts = [
      fake('one', '2026-11-01', 'engineering', 'aiops'),
      fake('other', '2026-11-02', 'nufi-box', 'field-notes'),
      fake('two', '2026-11-03', 'engineering', 'aiops'),
    ];
    const adj = adjacentInSeries(posts, 'two');
    expect(adj.prev?.slug).toBe('one');
    expect(adj.next).toBeUndefined();
    expect(adjacentInSeries(posts, 'other')).toEqual({});
  });
});
