# NuFi Agent — hands-on scenarios

Three scenarios you can build yourself, in order, on a running NuFi Agent.
Nothing here is a slide: every step below was executed against the build on
`develop`, and the answers quoted are the answers the flows actually returned.

Scenario 1 takes about two minutes and proves the product runs. Scenario 2 is
document question-answering with verifiable sources. Scenario 3 is an agent
that reaches into an internal system through MCP and quotes what it finds.

| | Scenario | Time | What it demonstrates |
|---|---|---|---|
| 1 | Chat agent from an empty canvas | ~2 min | The builder itself: components, wiring, the Playground |
| 2 | Document Q&A with source citations | ~15 min | Retrieval over your own documents, with provenance |
| 3 | Tool-calling agent over MCP | ~10 min | An agent that calls internal systems and quotes them |

---

## Before you start

### What you need

- NuFi Agent running. Locally: `apps/nufi-agent/.venv/bin/langflow run --host 127.0.0.1 --port 7860`, then open <http://127.0.0.1:7860>.
- A NuFi gateway API key, for the language model.
- For Scenario 2 only: an embedding model. This guide uses a local one so that
  document text never leaves the machine.

### Connect the language model — once

**Settings → Model Providers → OpenAI Compatible.**

| Field | Value |
|---|---|
| Base URL | `https://api.codechi.me/v1` |
| API Key | your NuFi gateway key |

Press **Save**. The panel then lists the models the gateway offers and you
enable the ones you want; `gemini` is the one used throughout this guide.

Two things worth noticing here, because they are the reason this product is
worth deploying rather than handing people a chat window:

- The provider is **OpenAI Compatible pointed at NuFi's own gateway**, not at a
  vendor endpoint. Every token any flow spends is routed, metered and logged by
  us, and the key is stored once, centrally, instead of being pasted into
  individual flows by individual people.
- After saving, the key renders as dots. It is not recoverable through the UI.

### Connect an embedding model — Scenario 2 only

**Settings → Model Providers → Ollama.** Base URL `http://127.0.0.1:11434`,
**Save**, then enable `nomic-embed-text:latest` in the model list below.

Install it first if you have not: `ollama pull nomic-embed-text` (274 MB).

This puts the embedding step on the machine itself. Document text is turned
into vectors locally and stored locally; only the retrieved passage and the
question travel to the gateway. For a bid that has to answer "where does the
data go", that split is worth being deliberate about.

---

## Scenario 1 — a chat agent from an empty canvas

**Goal:** the shortest path from nothing to a working answer.

```
Chat Input  ──▶  Language Model  ──▶  Chat Output
```

### Steps

1. **New Flow → Browse more → Blank Flow.**
2. In the left palette, search `Chat Input`. Hover the result and press **+**.
   Drag the node to the left of the canvas.
3. Search `Language Model`, press **+**, drag it to the middle.
4. Search `Chat Output`, press **+**, drag it to the right.
5. Connect them: press on the dot on the right edge of *Chat Input*, drag to
   the **Input** dot on the left edge of *Language Model*, release. Then drag
   from *Language Model*'s **Model Response** dot to *Chat Output*'s input dot.
6. On the *Language Model* node the model field should already show `gemini` —
   it inherits the provider you configured above. If it does not, click the
   field, then **Manage Model Providers**.
7. Press **Playground** (top right), type a question, press Enter.

### What you should see

An answer, in a few seconds, with a token count and a duration next to it. The
flow you just built did not exist three minutes ago and no code was written.

---

## Scenario 2 — document Q&A with source citations

**Goal:** answers drawn only from your documents, where every answer carries
the exact passages it was drawn from, so a reader can check it.

This is the shape the JDC requirement **SFR-001** asks for.

```
                      ┌──▶ Parser (context)  ──▶ Prompt ──▶ Language Model ──┐
Chat Input ──▶ Knowledge                                                     ├──▶ Prompt ──▶ Chat Output
     │                └──▶ Parser (sources) ──────────────────────────────┐  │      (answer + sources)
     └────────────────────────────────────────────────────────────────────┴──┘
```

### 2a. Build the knowledge base

1. **Knowledge** (left sidebar) → **Add Knowledge**.
2. Name it — this guide uses `Company Policies`.
3. **Embedding Model**: `nomic-embed-text:latest`.
4. **DB Provider**: `Chroma Local`. Vectors stay on this machine.
5. **Add Files → Upload Files**, and select your documents.
6. Leave chunking at the defaults (1000 characters, 200 overlap) for a first
   pass. **Next Step**, review the summary, **Create**.

The sample corpus used below is four short policy documents — leave,
information security, procurement, travel and expenses — totalling about a
thousand words. Ingestion produced **9 chunks** and took a few seconds.

Use your own documents instead. Prose documents work well. Dense technical
material full of tables and code does not: see *Known limits* at the end.

### 2b. Build the flow

Place these eight components (search, **+**, drag):

`Chat Input` · `Knowledge` · `Parser` ×2 · `Prompt Template` ×2 ·
`Language Model` · `Chat Output`

**Configure the Knowledge node.** Switch its Mode tab to **Retrieve**, then
pick your knowledge base in the **Knowledge** dropdown. Leave *Include
Metadata* on — the file name comes from there, and without it there is nothing
to cite. Set **top_k** to 5 or 6.

**Configure the first Parser** — this one turns retrieved rows into the text
the model reads. Set its template to:

```
[{file_name} · chunk {chunk_index}]
{content}
```

> The Parser ships with a default template of `Text: {text}`. Replace it
> entirely rather than typing after it: `{text}` is not a column the knowledge
> base returns, and leaving it in makes the flow fail at run time with
> `Error building Component Parser: 'text'`.

**Configure the second Parser** — this one builds the source list:

```
- {file_name} · chunk {chunk_index}
```

**Configure the first Prompt Template** (click **Template**, then the expand
icon). Keep it to just the two variables:

```
Context:
{context}

Question: {question}
```

Typing `{context}` and `{question}` creates matching input ports on the node.

**Configure the second Prompt Template**, which assembles the reply:

```
{answer}

---
**Sources retrieved for this answer**
{sources}
```

**Put the instructions in the Language Model's System Message**, not in the
prompt:

```
You answer questions about company policy using only the context supplied in
the user message.

Answer in two to four sentences of plain language, addressing exactly what was
asked. Quote the exact figures, thresholds and deadlines that appear in the
context. Do not invent anything, and do not mention the context or the chunks.
If the context does not answer the question, reply: The documents provided do
not answer that.
```

### 2c. Wire it

| From | To |
|---|---|
| Chat Input → | Knowledge **Search Query** |
| Knowledge **Results** → | Parser 1 **JSON or Table** |
| Knowledge **Results** → | Parser 2 **JSON or Table** |
| Parser 1 → | Prompt 1 **context** |
| Chat Input → | Prompt 1 **question** |
| Prompt 1 → | Language Model **Input** |
| Language Model → | Prompt 2 **answer** |
| Parser 2 → | Prompt 2 **sources** |
| Prompt 2 → | Chat Output |

Nine connections. One output can feed several inputs — Chat Input and
Knowledge each feed two.

### 2d. Try it

> **Q:** How many annual leave days do I get after four years of service, and
> how many can I carry over?
>
> **A:** After four years of service, you are granted 18 days of paid annual
> leave per calendar year. You may carry over up to 5 unused annual leave days
> into the following calendar year. Carried days expire on 31 March.
>
> **Sources retrieved for this answer**
> - HR-01-Leave-Policy.md · chunk 0
> - HR-01-Leave-Policy.md · chunk 1
> - FIN-04-Travel-and-Expenses.md · chunk 1
> - …

Correct on all three figures, and every passage it drew on is listed underneath.

### Why the sources are built by the flow, not written by the model

The obvious design is to instruct the model to add `[file · chunk]` after each
sentence. We tried that first. On this gateway model it is unreliable: it
sometimes emits the tag and no prose, sometimes copies the example from the
instructions verbatim, sometimes omits tags entirely.

Provenance is not something to leave to a model's goodwill. The second Parser
takes the same retrieval result the model was given and prints it directly, so
the source list is correct by construction — it is the retrieval layer's own
output, not a claim about it. Keep the in-text instruction too if you like, but
do not depend on it.

---

## Scenario 3 — a tool-calling agent over MCP

**Goal:** an agent that answers questions it cannot answer from documents,
because the answer lives in a running system — a leave balance, a budget line.

This is the second half of **SFR-008**: not just a canvas, but agents that
reach real systems.

```
Chat Input ──▶ Agent ──▶ Chat Output
                 ▲
                 └── MCP Tools ──▶ internal-systems (stdio)
```

### 3a. A stand-in for the internal system

For the walkthrough, `apps/nufi-agent/nufi/demo/mcp/hr_server.py` exposes two tools over MCP:

| Tool | Arguments | Returns |
|---|---|---|
| `get_leave_balance` | `employee_id` | entitlement, carried over, taken, remaining |
| `get_department_budget` | `department`, `year` | allocated, committed, remaining (KRW) |

The data is a dictionary in the file. That is the point: what the demo proves
is that **the agent decides which tool to call and what to pass it**. Swap the
body for a real API call and nothing else in the flow changes.

### 3b. Register the server

In a flow, open the **MCP** tab in the left sidebar → **Add MCP Server** →
**JSON** tab, and paste:

```json
{
  "mcpServers": {
    "internal-systems": {
      "command": "/absolute/path/to/apps/nufi-agent/.venv/bin/python",
      "args": ["/absolute/path/to/apps/nufi-agent/nufi/demo/mcp/hr_server.py"]
    }
  }
}
```

**Add Server.** NuFi Agent starts the server, asks it what it can do, and the
server appears in the MCP list. Open the node it creates and the **Tool**
dropdown lists `get_leave_balance` and `get_department_budget` — discovered,
not configured by hand.

### 3c. Build the flow

1. Place `Chat Input`, `Agent`, `Chat Output`.
2. From the **MCP** tab, add **internal-systems**. Drag it below the Agent.
3. On the MCP node, turn on **Tool Mode** (select the node; the toggle is in
   the toolbar above it). Its output changes from a table of one tool's result
   to a **Toolset** the agent can choose from. Without this the connection to
   the Agent will not be accepted, because the Agent's *Tools* port takes
   `Tool`, not `Table`.
4. Connect: Chat Input → Agent **Input**; MCP **Toolset** → Agent **Tools**;
   Agent **Response** → Chat Output.
5. Check the Agent's model is `gemini`, not a local model that happens to be
   installed. Agent Instructions:

```
You answer staff questions about HR and finance by calling the tools connected
to you.

Always call a tool when the question needs a fact from the internal systems: a
person's leave balance, a department's budget. Then reply in one or two plain
sentences that quote the tool's figures exactly. Do not output XML or tags of
any kind. Do not guess a number the tool did not return. If a tool reports that
a record does not exist, say so plainly.
```

### 3d. Try it

> **Q:** How many leave days does employee E-1042 have left?
> **A:** Kim Min-jun (Engineering) has 9.5 leave days remaining.

> **Q:** What is left in the Engineering budget for 2026?
> **A:** The Engineering department has 48,500,000 KRW remaining in its budget
> for 2026.

Both figures match what the tool returns exactly — 9.5 days is
`18 + 3 − 11.5`, computed inside the tool, and 48,500,000 KRW is
`480,000,000 − 431,500,000`. The agent chose the tool, passed the argument it
parsed out of the question, and quoted the result.

Ask about an employee who does not exist and it says so, rather than inventing
a balance.

---

## What these scenarios cover, and what they do not

| JDC requirement | Covered by | Status |
|---|---|---|
| SFR-008 no-code agent builder | Scenarios 1 and 3 | Demonstrated |
| SFR-008 MCP integration | Scenario 3 | Demonstrated |
| SFR-001 answers with citations | Scenario 2 | Demonstrated |
| SER-001–003 access control | — | Langflow ships the interface and audit tables; enforcement needs a plugin. Not built. |
| INR-002 AI governance | — | Audit log exists; approval gates do not. Not built. |
| PER-001 KPIs | — | Not started. |

## Known limits

Worth saying plainly, because they shape what to promise.

**The gateway model is weak at threshold reasoning.** Asked who approves a
12,000,000 KRW purchase, it answered "the team manager" when the policy places
that amount in the finance director's band. It reads and quotes accurately; it
is unreliable when the answer requires comparing a number against a range. Any
scenario that hinges on that needs a stronger model behind the gateway, and the
gateway currently offers exactly one.

**In-text citations are not reliable on this model.** Hence the deterministic
source block in Scenario 2.

**Dense technical documents retrieve poorly.** The first version of Scenario 2
ran over this project's own engineering notes — markdown full of code blocks,
tables and long qualified sentences. Retrieval worked, but the answers were
fragments of context rather than answers. Prose documents with clear factual
statements behave far better. This is a chunking and document-preparation
problem, not a product defect, but it will decide how the JDC corpus needs
preparing.

**Korean covers about 40% of the interface** — the paths in these scenarios,
not the whole product, and it has not been reviewed by a native speaker.

**No access control.** Every scenario above runs as a single user. Before this
is put in front of a customer, the authorization plugin has to exist.
