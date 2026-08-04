/**
 * Transcript parser, contract version 1.0.0 (see docs/adapters/adapter-ui-parser.md).
 *
 * This adapter's runs are short: one line naming the task, the model's answer,
 * and a disposition marker written by execute.ts. There is no tool-call stream
 * to reconstruct — the harness adapters have that, and this one deliberately
 * does not, because the work happens behind the NUFI gateway rather than in a
 * sandbox on this machine.
 *
 * Kept self-contained: the UI loads this module dynamically and it must not
 * import from the server half.
 */

export interface TranscriptBlock {
  kind: "task" | "answer" | "disposition";
  text: string;
}

const TASK_LINE = /^> (.+)$/;
const DISPOSITION_LINE = /^\[disposition: (in_review|blocked)\]$/;

export function parseStdout(stdout: string): TranscriptBlock[] {
  const blocks: TranscriptBlock[] = [];
  const answer: string[] = [];

  for (const line of stdout.split("\n")) {
    const task = TASK_LINE.exec(line);
    if (task) {
      blocks.push({ kind: "task", text: task[1] });
      continue;
    }

    const disposition = DISPOSITION_LINE.exec(line.trim());
    if (disposition) {
      if (answer.length) {
        blocks.push({ kind: "answer", text: answer.join("\n").trim() });
        answer.length = 0;
      }
      blocks.push({ kind: "disposition", text: disposition[1] });
      continue;
    }

    answer.push(line);
  }

  const tail = answer.join("\n").trim();
  if (tail) blocks.push({ kind: "answer", text: tail });

  return blocks;
}
