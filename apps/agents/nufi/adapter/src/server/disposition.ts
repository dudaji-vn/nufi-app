/**
 * Deciding what state to leave an issue in — the part the spike said matters.
 *
 * Paperclip does not accept "the agent said something" as progress. It wants a
 * disposition. When three consecutive runs failed to produce one, it escalated
 * to a recovery owner and stopped dispatching altogether
 * (docs/2026-08-04-nufi-agents-spike-findings.md §3). An adapter that comments
 * and returns is an adapter that eventually gets its agent switched off.
 *
 * So every run ends in exactly one of two states, and never in neither.
 */

export interface Disposition {
  /** The issue status to set. */
  status: "in_review" | "blocked";
  /** The comment to post. Always non-empty. */
  comment: string;
}

/**
 * Phrases a model reaches for when it will not or cannot do the work. Matched
 * only near the start of the answer: a refusal announces itself immediately,
 * whereas a real answer can use the same words mid-sentence ("the licence
 * cannot be changed retroactively") without being one.
 */
const REFUSAL_MARKERS = [
  "i cannot",
  "i can't",
  "i am unable",
  "i'm unable",
  "i do not have access",
  "i don't have access",
  "no evidence was provided",
  "please provide",
  "as an ai",
];

const REFUSAL_WINDOW = 120;

export function resolveDisposition(answer: string): Disposition {
  const trimmed = answer.trim();

  if (!trimmed) {
    return {
      status: "blocked",
      comment:
        "The agent could not complete this task: it returned an empty answer. " +
        "A human needs to decide whether the task is answerable as written.",
    };
  }

  const opening = trimmed.slice(0, REFUSAL_WINDOW).toLowerCase();
  const refused = REFUSAL_MARKERS.some((marker) => opening.includes(marker));

  if (refused) {
    return {
      status: "blocked",
      comment:
        "The agent could not complete this task. Its own words:\n\n" +
        trimmed +
        "\n\nThis is blocked rather than in review, because there is nothing to review.",
    };
  }

  return { status: "in_review", comment: trimmed };
}

export interface PromptInput {
  goal: string | null;
  title: string;
  description: string;
}

/**
 * The goal leads, because tracing every task to the company goal is the whole
 * point of Paperclip's hierarchy — an agent that cannot see the goal cannot
 * honour it.
 *
 * A missing description throws. Measured during the spike: given a title alone,
 * the model did not fail, it invented a plausible answer and stated it
 * confidently. Refusing to build the prompt is the only place that failure mode
 * can be caught cheaply.
 */
export function buildPrompt(input: PromptInput): string {
  if (!input.description.trim()) {
    throw new Error(
      `Task "${input.title}" has no description — refusing to prompt on a title alone`,
    );
  }

  return [
    input.goal ? `Company goal: ${input.goal}` : null,
    `Task: ${input.title}`,
    "",
    input.description,
  ]
    .filter((line): line is string => line !== null)
    .join("\n");
}
