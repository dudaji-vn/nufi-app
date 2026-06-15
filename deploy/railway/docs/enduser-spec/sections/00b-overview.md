## Product Overview & Architecture

### What NuFi is
NuFi is an AI chat platform delivered as two cooperating end-user products that share a single
sign-in. In production they are served at **https://chat.nufi.me** (NuFi Chat) and
**https://console.nufi.me** (NuFi Console):

1. **NuFi Chat** — the conversational application where users talk to AI models, attach files,
   build Agents with document knowledge (RAG), and manage their conversations. It is a customised
   fork of the open-source LibreChat project, branded as *Nufi Chat* and configured to expose a
   curated subset of LibreChat's features.
2. **NuFi Console** — a self-service developer portal where the same users manage their own
   **LiteLLM API keys**, see their **budget and usage**, and obtain programmatic access to the
   platform. The Console is reached from a **Console** entry in the Chat account menu and trusts
   the same login session as the Chat.

### The single backend model: "Nufi"
NuFi Chat is configured with exactly one chat endpoint, displayed as **Nufi**. It is an
OpenAI-compatible endpoint: the Chat backend forwards requests to a configured upstream
(`BACKEND_BASE_URL`) using an API key (`BACKEND_API_KEY`). In the production topology that upstream
is a **LiteLLM** proxy, which is also the system that the NuFi Console issues API keys and tracks
budgets against. The list of selectable models is fetched live from that backend, so the model
dropdown reflects whatever the backend currently offers.

In addition to the **Nufi** endpoint, the **Agents** endpoint is enabled. Agents are where the
platform's Retrieval-Augmented Generation (RAG) capability lives — see below.

### How a chat message flows
```
User → NuFi Chat (web UI) → Chat API (Express) → BACKEND_BASE_URL (LiteLLM / OpenAI-compatible) → AI model
                                   ↑ response streamed back token-by-token (SSE) ↑
```

The response is streamed back to the browser and rendered live, token by token.

### How Agents & File Search (RAG) work
RAG — letting the model answer from documents the user uploaded — is **only** available through an
**Agent** with the **File Search** capability. The flow is:
```
User creates an Agent (on the Nufi model) → enables File Search → uploads documents into the
Agent's Knowledge → documents are sent to the RAG service (rag_api) → embedded into a vector
database (pgvector) → at chat time, relevant passages are retrieved and given to the model.
```

A critical distinction the tester must internalise:

- **Agent Knowledge** documents are **persistent** — they belong to the Agent and are available in
  *every* conversation with that Agent.
- A **per-message attachment** (the 📎 paper-clip on the message box) is **conversation-scoped** —
  it is context for the current chat only and does not survive into a new conversation, and it does
  **not** populate the vector database.

There is **no plain-chat RAG**: uploading a document on the normal Nufi endpoint adds it as
short-lived context, not as retrievable knowledge.

### How the two products share a session
NuFi Chat issues a JSON Web Token (JWT) on login. The NuFi Console verifies that same JWT, so a
user who is signed into Chat is automatically recognised by the Console. On the user's first visit
to the Console, a corresponding LiteLLM user is created automatically (**just-in-time
provisioning**). If a visitor reaches the Console without a valid session, they are shown an
*unauthorized* page that links back to the Chat sign-in.

### Deployment shape (for context)
NuFi Chat and its supporting services run as separate containers/services:

- **Chat API + web client** — the LibreChat fork image (`ghcr.io/dudaji-vn/nufichat`).
- **MongoDB** — stores users, conversations, messages, agents, presets, prompts, etc.
- **Meilisearch** — powers conversation search (search is unavailable if this service is down).
- **rag_api + pgvector** — embed and store Agent Knowledge documents for File Search.
- **NuFi Console** — a separate service (`ghcr.io/dudaji-vn/nufi-console`) talking to LiteLLM.

Testers do not need to operate these services, but knowing they exist explains certain behaviours
(e.g. *search returns nothing when Meilisearch is down*, or *uploaded knowledge never becomes
retrievable when rag_api is unreachable*).

> **Note.** This architecture summary is provided for orientation only. The authoritative,
> testable behaviour is in the per-feature sections that follow.
