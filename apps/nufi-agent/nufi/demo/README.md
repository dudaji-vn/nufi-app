# Demo material for the hands-on scenarios

Everything here exists to be replaced. It is the smallest content that lets
someone follow `docs/2026-08-24-nufi-agent-hands-on-scenarios.md` end to end
without first having to find a corpus or stand up an internal API.

- `policies/` — four short sample policy documents (leave, information
  security, procurement, travel). Prose, with concrete figures and deadlines,
  because that is what retrieval answers well. Roughly 1,000 words in total;
  ingesting them produces 9 chunks.
- `mcp/hr_server.py` — an MCP server over stdio exposing two tools,
  `get_leave_balance` and `get_department_budget`, backed by a dictionary. The
  scenario demonstrates that the agent picks the tool and its arguments; swap
  the function bodies for real API calls and the flow is unchanged.

Neither is customer data and neither is a NuFi product surface. They are not
covered by the brand or locale guards.
