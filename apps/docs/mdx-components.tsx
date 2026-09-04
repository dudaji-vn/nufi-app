import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Card, Cards } from 'fumadocs-ui/components/card';
import { Callout } from 'fumadocs-ui/components/callout';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import { Accordion, Accordions } from 'fumadocs-ui/components/accordion';
import { Steps, Step } from 'fumadocs-ui/components/steps';
import {
  BookMarked,
  Bot,
  Code,
  Compass,
  FileText,
  Users as GroupIcon,
  Key,
  Library,
  MessageSquare,
  Mic,
  Rocket,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Workflow,
} from 'lucide-react';
import type { MDXComponents } from 'mdx/types';

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Card,
    Cards,
    Callout,
    Tab,
    Tabs,
    Accordion,
    Accordions,
    Steps,
    Step,
    // Card icons. Exposed to MDX so a card can carry the same lucide glyph the
    // sidebar section uses, instead of an emoji in its title -- emoji rendered at a
    // different size on every platform and matched nothing else in the product.
    BookMarked,
    Bot,
    Code,
    Compass,
    FileText,
    GroupIcon,
    Key,
    Library,
    MessageSquare,
    Mic,
    Rocket,
    Search,
    ShieldCheck,
    SlidersHorizontal,
    Sparkles,
    Workflow,
    ...components,
  };
}
