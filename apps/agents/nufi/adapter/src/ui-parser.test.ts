import { describe, expect, it } from "bun:test";

import { parseStdout } from "./ui-parser";

describe("parseStdout", () => {
  it("splits a normal run into task, answer and disposition", () => {
    const blocks = parseStdout(
      "> Draft the approvals page\nA review gate holds a run\nuntil a role approves.\n\n[disposition: in_review]\n",
    );

    expect(blocks).toEqual([
      { kind: "task", text: "Draft the approvals page" },
      { kind: "answer", text: "A review gate holds a run\nuntil a role approves." },
      { kind: "disposition", text: "in_review" },
    ]);
  });

  it("keeps the answer when the run was blocked", () => {
    const blocks = parseStdout("> T\nI cannot answer that.\n[disposition: blocked]\n");
    expect(blocks.at(-1)).toEqual({ kind: "disposition", text: "blocked" });
    expect(blocks[1]?.text).toBe("I cannot answer that.");
  });

  it("emits the trailing answer when a run ended without a disposition marker", () => {
    const blocks = parseStdout("> T\nhalf an answer");
    expect(blocks).toEqual([
      { kind: "task", text: "T" },
      { kind: "answer", text: "half an answer" },
    ]);
  });

  it("returns nothing for empty output rather than an empty block", () => {
    expect(parseStdout("")).toEqual([]);
  });
});
