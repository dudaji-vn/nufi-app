#!/usr/bin/env node
/**
 * Run the real heartbeat loop against a real NUFI Works instance, then check the
 * database rather than the agent's account of itself.
 *
 * This exists because of one measured failure. A vendor harness driving a
 * mid-tier model reported "First, I'll create a task", "saved it to
 * cloudflow_agreement_brief.md" and "I will mark the task as completed" — and
 * the company still held exactly the two issues a human had made. Every
 * assertion below is on the API's answer, never on what the agent said it did.
 *
 * Usage:
 *   PAPERCLIP_API_URL=https://works.nufi.me \
 *   PAPERCLIP_API_KEY=<board or run token> \
 *   NUFI_MODEL_API_KEY=<gateway key> \
 *   NUFI_COMPANY_ID=<uuid> NUFI_AGENT_ID=<uuid> NUFI_RESPONSIBLE_USER_ID=<id> \
 *   node scripts/live-check.mjs
 *
 * It creates one task, works it, and leaves it in place so a human can read what
 * happened. Point it at a scratch company.
 */

import { randomUUID } from "node:crypto";
import fs from "node:fs";

import { buildModel } from "../dist/server/client.js";
import { runLoop } from "../dist/server/loop.js";
import { systemPrompt, wakeMessage } from "../dist/server/prompt.js";
import { buildTools } from "../dist/server/tools.js";

const need = (name) => {
  const value = process.env[name];
  if (!value) {
    console.error(`missing ${name}`);
    process.exit(2);
  }
  return value;
};

const API = need("PAPERCLIP_API_URL").replace(/\/$/, "");
const TOKEN = need("PAPERCLIP_API_KEY");
const MODEL_KEY = need("NUFI_MODEL_API_KEY");
const COMPANY = need("NUFI_COMPANY_ID");
const AGENT = need("NUFI_AGENT_ID");
const RESPONSIBLE = process.env.NUFI_RESPONSIBLE_USER_ID ?? null;
const GATEWAY = process.env.NUFI_GATEWAY_URL ?? "https://api.codechi.me/v1";
const MODEL = process.env.NUFI_MODEL ?? "gemini";

const http = async ({ method, path, headers, body }) => {
  /**
   * Strip the run id. The tools stamp one on every mutation because a real run
   * has one, but this harness authenticates as a person and has no heartbeat
   * run behind it. Sending a made-up id violates
   * `activity_log_run_id_heartbeat_runs_id_fk`, and the route then answers 500
   * *after* the write has landed — observed on LEG-3, where the comment was
   * stored and the caller was told it had failed.
   */
  const { "X-Paperclip-Run-Id": _runId, ...safe } = headers ?? {};
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { ...safe, authorization: `Bearer ${TOKEN}` },
    ...(body === undefined || method === "GET" ? {} : { body: JSON.stringify(body) }),
  });
  const text = await res.text();
  let parsed = text;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    /* keep the raw body */
  }
  return { status: res.status, body: parsed };
};

/**
 * The production model path, not a copy of it — so this harness exercises the
 * real request shape and the real retry on a guardrail that could not run.
 */
const model = buildModel({
  runId: "live-check",
  agent: { id: AGENT, companyId: COMPANY },
  config: { gatewayUrl: GATEWAY, model: MODEL },
  context: {},
  onLog: async () => {},
});

/**
 * The exact text that killed LEG-8 through the gateway's G1 control: an
 * ordinary HR leave policy, scored 0.99999 by the injection classifier when it
 * arrived as a tool result. If the wake briefing works, this passes.
 */
const TASK = {
  title: "HR: how much notice before unpaid leave?",
  description: [
    "An employee has asked for four weeks of unpaid leave starting next month.",
    "Answer from the policy below, and say plainly if it does not cover the case.",
    "",
    "--- LEAVE POLICY, SECTION 4 ---",
    "4.1 Annual leave requests require fourteen (14) days' notice to the manager.",
    "4.2 Leave exceeding ten (10) consecutive working days additionally requires",
    "    written approval from the department head.",
    "4.3 Unpaid leave is granted at the company's discretion and is not an entitlement.",
    "4.4 Notice periods in 4.1 may be waived by the department head in cases of",
    "    bereavement or medical emergency.",
    "--- END ---",
    "",
    "Tell the employee what notice they must give, whose approval they need, and",
    "whether they are entitled to it.",
  ].join("\n"),
};

const results = [];
const check = (name, pass, detail) => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "  ok  " : " FAIL "} ${name}${detail ? ` — ${detail}` : ""}`);
};

/**
 * A check whose precondition did not hold must say so, not print "ok".
 *
 * The two handover checks below only mean anything when the task ended in
 * `in_review`. Written as `status !== "in_review" || …` they printed a
 * confident green on a run that ended `done` — including one where the agent
 * still held the task. A check that cannot fail is not a check, and one that
 * reports success for not running is worse than none.
 */
const checkIf = (applies, name, pass, detail) => {
  if (!applies) {
    console.log(`  --   ${name} — not applicable${detail ? ` (${detail})` : ""}`);
    return;
  }
  check(name, pass, detail);
};

async function main() {
  console.log(`\ncreating a task in company ${COMPANY}\n`);
  /**
   * The title carries a nonce because Paperclip deduplicates identical creates
   * and returns the existing issue with HTTP 200. Without it a second run reads
   * the first run's leftovers and every assertion passes on stale state — a
   * check that cannot fail is not a check.
   */
  const nonce = randomUUID().slice(0, 8);
  const created = await http({
    method: "POST",
    path: `/api/companies/${COMPANY}/issues`,
    headers: { "content-type": "application/json" },
    body: {
      ...TASK,
      title: `${TASK.title} (${nonce})`,
      status: "todo",
      priority: "high",
      // Deliberately unassigned. The same agent is live on this instance and is
      // woken by `issue_assigned`, so assigning here makes the deployed adapter
      // race this harness for the task — which it wins, and then every
      // assertion below passes on a run that did nothing but read a conflict.
    },
  });
  if (created.body?.deduplicated) {
    console.error("refusing to assert on a deduplicated issue; change the task text");
    process.exit(1);
  }
  if (created.status >= 300) {
    console.error("could not create the task:", created.status, created.body);
    process.exit(1);
  }
  const issue = created.body;
  console.log(`task ${issue.identifier} (${issue.id})\n`);

  const tools = buildTools(
    {
      apiUrl: "",
      // Present so the tools behave exactly as they will in production; the
      // transport above drops the header, since this harness has no real run.
      runId: randomUUID(),
      agentId: AGENT,
      companyId: COMPANY,
      issueId: issue.id,
      responsibleUserId: RESPONSIBLE,
    },
    http,
  );

  /**
   * Capture what was actually sent when the gateway refuses.
   *
   * Diagnosing a guardrail block otherwise means asking someone to grep the
   * VM's logs for the `grd_` reference — three round trips so far, each one
   * slower than the fix it led to. The messages are here; write them down.
   */
  const capture = { turns: [] };
  const watched = {
    async turn(messages, tools) {
      capture.turns.push(
        messages.map((m) => ({ role: m.role, bytes: (m.content || "").length, head: (m.content || "").slice(0, 120) })),
      );
      try {
        return await model.turn(messages, tools);
      } catch (err) {
        const path = "/tmp/live-check-blocked.json";
        fs.writeFileSync(path, JSON.stringify({ error: String(err), messages }, null, 2));
        console.error(`\nblocked on turn ${capture.turns.length}; spans:`);
        for (const m of capture.turns.at(-1)) {
          console.error(`   ${m.role.padEnd(10)} ${String(m.bytes).padStart(6)} bytes  ${JSON.stringify(m.head.slice(0, 70))}`);
        }
        console.error(`full payload written to ${path}`);
        throw err;
      }
    },
  };

  const started = Date.now();
  // Prefetched and handed to the wake, exactly as execute.ts now does.
  const context = (
    await http({ method: "GET", path: `/api/issues/${issue.id}/heartbeat-context`, headers: {} })
  ).body;

  const outcome = await runLoop({
    model: watched,
    tools,
    system: systemPrompt(),
    wake: wakeMessage({
      issueId: issue.id,
      companyId: COMPANY,
      agentId: AGENT,
      issue: context?.issue?.title
        ? {
            title: context.issue.title,
            description: context.issue.description ?? "",
            status: context.issue.status ?? null,
            priority: context.issue.priority ?? null,
            goal: context.goal?.title ?? null,
          }
        : null,
    }),
  });
  const seconds = ((Date.now() - started) / 1000).toFixed(1);

  console.log(`\n${outcome.iterations} turn(s) in ${seconds}s`);
  console.log(`stop reason: ${outcome.stopReason}`);
  console.log(`tools used:  ${outcome.toolsUsed.join(", ") || "none"}`);
  console.log(`closing text: ${JSON.stringify(outcome.text.slice(0, 160))}\n`);

  // --- everything below asks the API, never the agent -----------------------
  const after = (await http({ method: "GET", path: `/api/issues/${issue.id}`, headers: {} })).body;
  const comments = (
    await http({ method: "GET", path: `/api/issues/${issue.id}/comments?order=asc&limit=50`, headers: {} })
  ).body;
  const list = Array.isArray(comments) ? comments : (comments?.comments ?? []);
  const children = (
    await http({ method: "GET", path: `/api/companies/${COMPANY}/issues?descendantOf=${issue.id}`, headers: {} })
  ).body;
  const kids = Array.isArray(children) ? children : (children?.issues ?? []);
  const interactions = (
    await http({ method: "GET", path: `/api/issues/${issue.id}/interactions`, headers: {} })
  ).body;
  const cards = Array.isArray(interactions) ? interactions : (interactions?.interactions ?? []);

  console.log("what the database says\n");
  check("the agent called at least one tool", outcome.toolsUsed.length > 0, outcome.toolsUsed.join(", "));
  check(
    "it got past claiming the task",
    !/checked out by another agent/i.test(outcome.text),
    outcome.toolsUsed.includes("checkout_issue") ? "checkout succeeded" : "no checkout attempted",
  );
  check("it actually worked the task, not just claimed it", outcome.toolsUsed.length > 1, outcome.toolsUsed.join(", "));
  check("the task reached a final state", ["done", "in_review", "blocked"].includes(after.status), after.status);
  check("durable progress was left on the task", list.length > 0, `${list.length} comment(s)`);
  const inReview = after.status === "in_review";
  checkIf(inReview, "no agent still holds a task that went to review",
    after.assigneeAgentId === null, `status=${after.status}`);
  checkIf(inReview, "a task in review has a person on it",
    Boolean(after.assigneeUserId), `status=${after.status}`);

  // Narration check: if the agent said it created or proposed something, it must exist.
  const claimed = /\b(created|proposed|suggested)\b/i.test(outcome.text);
  if (claimed) {
    check(
      "anything it claimed to create actually exists",
      kids.length > 0 || cards.length > 0,
      `${kids.length} child issue(s), ${cards.length} interaction(s)`,
    );
  } else {
    console.log(`  --   it claimed no creations (${kids.length} child issue(s), ${cards.length} interaction(s))`);
  }

  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  console.log(`read it at: ${API}/${issue.identifier.split("-")[0]}/issues/${issue.identifier}\n`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((err) => {
  console.error("\nlive-check threw:", err);
  process.exit(1);
});
