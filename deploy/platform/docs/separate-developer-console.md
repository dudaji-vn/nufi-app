# Architecture Proposal: Keep the Developer Console Separate from the Chat Product

**Author:** [Your name] · **Date:** 2026-05-19 · **Audience:** Architecture decision for the internal AI platform

## TL;DR (30-second read)

> **Recommendation:** Keep **NPUOps Console** as a standalone application. **Do NOT** fold it into the LibreChat fork.
> Instead, use **shared SSO + cross-navigation links** so users still perceive a unified product.
>
> **Why:** This is the pattern adopted by Anthropic, OpenAI, and Google — not because they lack resources to merge, but because merging creates five concrete risks around security, operations, and long-term maintenance cost.
>
> **Cost:** Near zero — the Console is already built; we only need to add an SSO bridge.

---

## 1. Context

The NUFI platform currently has **three frontend products**:

| Product | Purpose | Audience |
|---|---|---|
| **LibreChat (fork)** | AI chat UI | All employees |
| **Admin Panel** | Manage workspaces, models, budgets | Admins, team leads |
| **NPUOps Console** | API key issuance, usage tracking | Developers integrating the API |

**The question:** Now that we have forked LibreChat (full control over the code), should we merge NPUOps Console into LibreChat to reduce the number of applications we maintain?

---

## 2. Comparing the two options

| Criterion | Option A: Merge into LibreChat | Option B: Keep separate (recommended) |
|---|---|---|
| Number of codebases | 1 (LibreChat fork) | 2 (LibreChat fork + Console) |
| User experience | Single login, single URL | Single SSO, two URLs with cross-navigation |
| Industry alignment | ❌ No major platform does this | ✅ Aligned with Anthropic, OpenAI, Google |
| Security (blast radius) | ⚠️ High — a chat bug can reach key management | ✅ Low — risks are isolated |
| Maintenance vs LibreChat upstream | ⚠️ Merge conflicts every upstream release | ✅ Unaffected |
| Reusability | ❌ Console is locked into the chat product | ✅ Can serve future products (RAG, embeddings…) |
| Compliance/audit scope | ⚠️ One large scope, complex audits | ✅ Clean scope separation |
| Initial development cost | High (must port existing code) | Low (already built) |
| Long-term cost | High (merge debt accumulates) | Low (independent release cycles) |

---

## 3. Five concrete reasons to keep them separate

### Reason 1 — Industry standard (proof point)

Every major AI platform separates these two products:

| Company | Chat product | Developer Console |
|---|---|---|
| Anthropic | claude.ai | console.anthropic.com |
| OpenAI | chatgpt.com | platform.openai.com |
| Google | gemini.google.com | aistudio.google.com |
| Mistral | chat.mistral.ai | console.mistral.ai |

→ This is not a coincidence. These companies do it **despite having more than enough resources to merge**. The reasons are the four points below.

### Reason 2 — Security: shrink the blast radius

The two products have **completely different threat models**:

| | Chat product | Developer Console |
|---|---|---|
| **Dangerous inputs** | User prompts (prompt injection, jailbreak, XSS via markdown) | Admin forms (CSRF, privilege escalation) |
| **Asset protected** | Conversations, attachments | **API keys — credentials** |
| **Attack frequency** | Continuous (every keystroke is an attack surface) | Rare but targeted |
| **Impact when compromised** | One conversation leaked | **Stolen key → attacker drains the company's entire budget** |

> **Concrete risk scenario if merged:** A prompt-injection flaw in chat → the attacker tricks the system into calling internal APIs → creates a new key with a large budget → exfiltrates. With separation, a chat-side flaw **cannot reach** the key-issuance logic.

This is the **least privilege** principle in security — not optional.

### Reason 3 — Maintenance: avoid "merge debt" with LibreChat upstream

LibreChat is a fast-moving open-source project (hundreds of commits per month). When we fork:

- **Every business feature** we add to the fork becomes a **patch** we must re-apply on every upstream update
- The more patches accumulate, the more **merge conflicts** appear → at some point merging becomes infeasible → the fork is **frozen** and stops receiving upstream security patches

> **Lesson from large forks:** Companies that forked GitLab CE or Strapi often had to abandon their forks after 12–18 months because merging became too painful. The consequence: they stopped receiving security updates.

**Keeping Console separate:** key/usage management code lives in its own repo → the LibreChat fork stays clean → upstream merges remain smooth → we keep getting security updates long-term.

### Reason 4 — Reusability (long-term strategy)

Today NPUOps Console serves NUFI Chat. But the company's **roadmap** likely includes:

- RAG-as-a-Service
- Embedding API
- Fine-tuning service
- Voice/Vision APIs on the NPU
- Multi-tenant SaaS for external customers

**If Console is standalone:** every new service uses the same console → users have one place to manage keys across every service.

**If Console lives inside LibreChat:** every new service must build its own console → or fork the chat product backwards → which is even more painful.

> Console = **platform infrastructure**. Chat = **one product on top of the platform**. These layers should not be mixed.

### Reason 5 — Operations: independent scaling and deployment

| | Chat product | Developer Console |
|---|---|---|
| Traffic | High, continuous (every message = a request) | Low, sporadic (occasional dev/admin logins) |
| Uptime requirement | 99.9%+ (daily user-facing) | 99% is sufficient |
| Resource profile | High RAM (conversation cache) | Low CPU |
| Deploy cadence | Weekly (upstream + bug fixes) | Monthly |
| Deploy window | Must be off-peak | Anytime |

→ Merging means **optimizing for the less important product at the cost of the more important one** (chat).

---

## 4. Five concrete risks of Option A (merging)

| # | Risk | Likelihood | Consequence |
|---|---|---|---|
| 1 | Chat vulnerability → escalates to API-key creation | Medium | **Financial loss from abused keys, customer data exposure** |
| 2 | A chat crash takes the Console offline | High | Developers cannot retrieve keys during an emergency |
| 3 | LibreChat upstream merges blocked by conflicts | High (within 6–12 months) | **Security patches missed, zero-days remain unpatched** |
| 4 | Audit compliance must scope chat when reviewing key management | Certain | Audit cost increases 2–3× |
| 5 | New services (RAG, Embedding…) must build their own console | High | Duplicated effort, fragmented developer experience |

---

## 5. Proposed architecture

```
┌─────────────────────┐      ┌─────────────────────┐
│  LibreChat (fork)   │      │  NPUOps Console     │
│  chat.nufi.com      │      │  console.nufi.com   │
│                     │      │                     │
│  [Developer →] ─────┼──────►  Keys, Usage, Docs  │
│  (deeplink + SSO)   │      │                     │
└──────────┬──────────┘      └──────────┬──────────┘
           │                            │
           │       Shared Auth (SSO)    │
           │   ┌────────────────────┐   │
           └───►   Identity Service ◄───┘
               │   (user DB, JWT)   │
               └────────────────────┘
           │                            │
           ▼                            ▼
   ┌──────────────────────────────────────┐
   │           LiteLLM Gateway            │
   │  (keys, budgets, routing, audit log) │
   └──────────────────────────────────────┘
```

**User experience:** Visit chat.nufi.com to chat. Click "Developer" in the top nav → automatically signed in to console.nufi.com (SSO). Feels like **one product**.

**Under the hood:** Two independent applications — deployed separately, scaled separately, secured separately.

---

## 6. Implementation cost

| Item | Effort | Notes |
|---|---|---|
| Standalone Console | ✅ Already built | Running in production |
| LibreChat fork customization | ✅ Already in place | No additional work |
| **New work:** SSO bridge between the two apps | ~3–5 days | OIDC or shared JWT |
| "Developer →" link in LibreChat header | ~0.5 day | Small patch on the fork |
| **Total** | **~1 week** | |

Compared to the merge option (~3–4 weeks of code porting + accepting the 5 long-term risks).

---

## 7. Recommended decision

✅ **Approve Option B (keep separate)** with the following conditions:

1. Implement the SSO bridge in the next sprint (~1 week of effort)
2. Add a "Developer →" navigation link in the LibreChat fork header
3. Document the responsibility boundaries between the two applications in the internal wiki
4. Establish a review checklist: every new feature must be classified as belonging to Chat or Console before any code is written

---

## 8. Appendix — Frequently asked questions

**Q: Isn't this wasting infrastructure? Two apps need two servers?**
A: They can be deployed in the same cluster under different namespaces/services. Infrastructure cost stays roughly flat. What increases is **process isolation**, not hardware.

**Q: Do users have to remember two URLs?**
A: No. SSO + a navigation link means one click takes you from chat to console. Same UX as Anthropic: claude.ai links to console.anthropic.com.

**Q: Why not the opposite — put everything in the Console and embed chat inside it?**
A: Wrong layer. The chat product must be optimized for conversational UX (streaming, voice, files…). The Console is optimized for data/form UX. Mixing them produces a poor experience in both.

**Q: Can we merge them later if we change our minds?**
A: Yes, and it's much easier in that direction. Splitting → merging is straightforward; merging → splitting is very difficult (because the code has already become interleaved).

---

*For questions or refinements, please reply to update this document.*
