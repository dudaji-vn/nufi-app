## Glossary, Roles & Access

### User roles (end-user scope)
This specification covers the **end user** — a person with a normal account who signs in to chat
and to manage their own keys and usage. Administrative roles (admin panel, user management,
platform configuration) are **out of scope** here. Where a feature is gated by a permission the
user may or may not have, the gate is noted in that feature's *Preconditions*.

| Role | Description | Covered here |
|---|---|---|
| **End user** | Signs in, chats, builds Agents, uploads files, manages own conversations, manages own API keys and budget in the Console. | **Yes** — this document |
| **Administrator** | Configures the platform, manages users, sets global limits via the admin panel. | No (separate document) |
| **Unauthenticated visitor** | Has no valid session; can only reach sign-in / register (Chat) or the *unauthorized* page (Console). | Partially — only the entry/redirect behaviour |

### Glossary
| Term | Meaning |
|---|---|
| **NuFi Chat** | The end-user chat application; a branded fork of LibreChat. |
| **NuFi Console** | The self-service portal for API keys, budget and usage. |
| **Endpoint** | A configured AI provider connection. NuFi exposes two: **Nufi** (the chat model) and **Agents**. |
| **Nufi endpoint** | The single OpenAI-compatible chat endpoint; routes to the configured backend (LiteLLM in production). |
| **Model** | A specific AI model selectable under the Nufi endpoint; the list is fetched live from the backend. |
| **Agent** | A reusable, configured assistant (model + instructions + capabilities + Knowledge). The home of File Search / RAG in NuFi. |
| **File Search** | The Agent capability that enables RAG over the Agent's uploaded Knowledge documents. The only Agent capability enabled in NuFi. |
| **Knowledge** | Documents uploaded into an Agent. Persistent and embedded for retrieval across all conversations with that Agent. |
| **RAG (Retrieval-Augmented Generation)** | Technique where the model answers using passages retrieved from uploaded documents rather than only its training data. |
| **Attachment** | A file added to a single message via the paper-clip. Conversation-scoped; not the same as Knowledge. |
| **Preset** | A saved bundle of endpoint + model + parameter settings that can be applied to new conversations. |
| **Prompt (library)** | A saved, reusable prompt template, optionally with variables, invokable in chat. |
| **Bookmark / Tag** | A label applied to conversations for organisation and filtering. |
| **Multi-conversation (multiConvo)** | Sending one prompt to several conversations side by side for comparison. |
| **Temporary chat** | An ephemeral conversation that is **not** saved to history. |
| **Streaming (SSE)** | Server-Sent Events; the mechanism by which the model's reply is delivered to the browser token by token. |
| **JWT** | JSON Web Token; the signed credential proving a user is signed in. Shared between Chat and Console. |
| **JIT provisioning** | "Just-in-time" creation of the user's LiteLLM account on first Console visit. |
| **LiteLLM** | The proxy that fronts the AI models, enforces API keys and budgets, and records usage. The Console manages keys against it. |
| **Budget / Spend** | The user's spending limit and accumulated cost, tracked by LiteLLM and shown in the Console. |
| **Reveal-once** | The one-time display of a newly created API key's secret; it cannot be retrieved again afterwards. |
| **Endpoints menu** | The Chat menu for switching between the Nufi and Agents endpoints. |
| **pgvector / rag_api** | The vector database and embedding service backing File Search. |
| **Meilisearch** | The search engine backing conversation search. |

### Access summary (what an end user can reach)
- **Without signing in:** the sign-in and registration pages of Chat; the *unauthorized* page of
  the Console. Nothing else.
- **After signing in to Chat:** all chat features in this document, subject to per-feature
  permissions.
- **In the Console (same session):** profile, API keys, and usage for **their own** account only.
