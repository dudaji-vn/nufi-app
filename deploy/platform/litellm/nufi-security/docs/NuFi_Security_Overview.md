# NuFi Security — Technical Overview for Prospective Customers

> **Audience:** Security engineers, architects, and technical decision-makers evaluating LLM data-loss prevention for regulated environments.

---

## What Is NuFi Security?

NuFi Security is an **on-premises LLM egress security gateway** purpose-built for organizations that must use large language models — both cloud-hosted and private — while keeping sensitive data inside their network perimeter. It intercepts every outbound LLM request, detects Korean and international PII, enforces configurable data policies, intelligently routes traffic between private and public LLM backends, and produces tamper-evident audit logs suitable for regulatory inspection — all without a single byte leaving your infrastructure until NuFi Security has decided it is safe to do so.

Think of NuFi Security as a strict, cryptographically accountable DLP layer placed at the exact point where your systems talk to LLMs, capable of routing each request to the right backend while enforcing a uniform security policy across both.

---

## The Problem NuFi Security Solves

### The Hybrid LLM Reality

Most production AI deployments today are not purely cloud or purely on-prem — they are **hybrid**. Organizations run a private LLM (self-hosted Llama, on-prem Mistral, internal inference cluster) for cost control and data sensitivity, while simultaneously relying on public cloud LLMs (OpenAI, Anthropic, Google) for tasks that require frontier-model capability.

This creates a critical security gap: **how do you guarantee that a request containing PII never reaches a public cloud endpoint?** Without a policy-aware router sitting in the middle, the answer is: you cannot. Engineers route requests manually, PII leaks happen at the application layer, and auditors see no reliable evidence either way.

### What's Missing in Existing Tools

Most organizations already have perimeter DLP for email and file transfer. What they lack is equivalent protection for **LLM prompt traffic** — a fast-growing, hard-to-audit channel where:

- Employees routinely paste customer data, medical records, or financial documents into prompts
- Standard DLP tools cannot parse the free-form, conversational structure of LLM requests
- Korean PII (주민등록번호, 계좌번호, 사업자번호) is systematically missed by English-centric tools
- Regulatory bodies (금융감독원, 개인정보보호위원회, ISMS-P) require documented evidence that PII did not egress — not just intent
- Requests that bypass the HTTP gateway reach public LLMs through direct TCP connections, invisible to application-layer tools

NuFi Security closes this gap with **detection-first, fail-closed architecture**: every request is classified, routed to the appropriate backend, and denied if the engine cannot make a safe determination.

---

## The Core Use Case: Secure Hybrid LLM Routing

NuFi Security is designed specifically for environments that **must run both private and public LLMs simultaneously** while maintaining a strong security posture.

### How It Works

```
Incoming Request
       │
       ▼
 ┌─────────────────────────┐
 │  NuFi Security Gateway  │
 │                         │
 │  1. Detect PII / secrets│
 │  2. Classify sensitivity│
 │  3. Route decision      │
 └──────────┬──────────────┘
            │
     ┌──────┴───────┐
     │              │
     ▼              ▼
Private LLM    Public LLM
(on-prem)    (OpenAI / Anthropic)
     │              │
     │   PII found  │  No PII found
     │  → forced    │  → allowed
     │    private   │    public
     └──────┬───────┘
            │
      Audit log (both paths)
```

The router makes a **policy-aware, PII-informed decision on every request**:

| Request Contains | Router Decision | Rationale |
|---|---|---|
| Strong PII (KR_RRN, KR_ACCOUNT, etc.) | **Private LLM only** | Hard block on public egress |
| Weak PII (name, phone, email) + pseudonymization enabled | **Pseudonymize → Public LLM** | Surrogate tokens sent; originals stay on-prem |
| No PII, non-sensitive | **Public LLM** (cost-optimal) | No restriction applies |
| Prompt injection detected | **Block entirely** | Injections never reach any backend |

This means your developers write code against a **single endpoint** — NuFi Security's OpenAI-compatible gateway — and the routing, PII enforcement, and audit happen automatically. No manual classification. No per-application security logic.

### Why This Matters for Security-Critical Environments

- **Eliminates PII routing errors at the application layer** — policy is centralized and enforced at the network layer, not scattered across individual services
- **Full audit trail across both paths** — every request to both private and public backends is logged with the same tamper-detection guarantees
- **Differential logging by path** — private path gets lightweight audit (PII + secrets only); public path gets full audit (all categories, confidential markings, bypass correlation)
- **Bypass prevention** — nftables rules block direct connections to public LLM IPs; applications cannot route around the gateway even if they try

---

## Value You Get

### 1. Deep Korean PII Coverage
NuFi Security detects **12 Korean PII entity classes** with a measured recall of **0.9908 (Wilson CI95 lower-bound ≥ 0.90)** on a 854-sample golden test set:

| Entity Class | Description |
|---|---|
| `KR_RRN` | 주민등록번호 (resident registration number) with checksum validation |
| `KR_PERSON` | Korean personal names via NER + gazetteer |
| `KR_ACCOUNT` | Bank account numbers |
| `KR_PHONE` | Korean phone numbers (landline + mobile) |
| `KR_PASSPORT` | Korean passport numbers |
| `KR_BRN` | 사업자등록번호 with checksum validation |
| `KR_LOCATION` | Korean addresses, city/district names |
| `CREDIT_CARD` | Major card formats with Luhn check |
| `DRIVER_LICENSE` | Korean driver's license format |
| `FOREIGNER_REG` | Foreigner registration numbers |
| `EMAIL` | RFC-compliant email addresses |
| `SECRETS` | API keys, tokens, passwords (entropy-based) |

English-focused open-source tools (Microsoft Presidio, etc.) have no native coverage for most of these classes.

### 2. Regulatory Evidence, Automatically
NuFi Security maps every detection and enforcement event to a structured control catalog covering **5 Korean regulatory frameworks and 48 controls** (금융감독원 IT Supervision, 개인정보보호법, ISMS-P, PIPA, and internal audit requirements). A single CLI command generates a signed compliance report:

```bash
nufi-egress report --format pdf --period 2024-Q1
```

Auditors receive structured evidence with entity counts, policy decisions, routing records, timestamps, and hash-chain verification proofs — not screenshots or manual logs.

### 3. Air-Gap and On-Premises Native
NuFi Security is designed for **zero external network dependencies** in its core path. The detection pipeline runs fully on-premises using one of three selectable backends:

- **Regex + Checksum** — zero-dependency, always available
- **Gazetteer/Dictionary NER** — packaged Korean name lists, no download required
- **KoELECTRA ONNX-INT8** — production accuracy, runs quantized locally

No telemetry. No license server calls. No model updates over the internet unless explicitly configured.

### 4. Three Deployment Modes, One Codebase
Teams at different maturity levels can adopt NuFi Security without rebuilding their infrastructure:

| Mode | How | Best For |
|---|---|---|
| **Standalone HTTP Gateway** | OpenAI-compatible `/v1/chat/completions` endpoint | Teams already using OpenAI SDK — change one URL |
| **LiteLLM Proxy Callback** | Hook into existing multi-provider LiteLLM deployment | Orgs already running LiteLLM; no routing changes |
| **Python SDK (in-process)** | `from nufi import Guard; Guard().inspect(text)` | Applications that want library-level control |

### 5. Network-Layer Bypass Prevention
NuFi Security does not just block at the HTTP level. An optional **nftables enforcement layer** installs packet-filter rules that drop direct TCP connections to public LLM endpoints from unauthorized processes. Even if a developer or rogue process bypasses the gateway entirely, the network blocks the connection and logs a bypass-detection event.

---

## How It Works Internally

### Architecture Overview

NuFi Security is structured around six subsystems that compose a linear pipeline with offline feedback loops:

```
Client Request
      │
      ▼
 ┌────────────────────────────────────────────────┐
 │  Gateway Core                                  │
 │  FastAPI (standalone) or LiteLLM callback hook │
 │  Router.resolve(): private-first, cost-aware   │
 └─────┬──────────────────────────────────────────┘
       │
       ▼
 ┌─────────────────┐
 │  Detection      │
 │  Pipeline       │  Phase 0: Prompt injection (18 patterns, KR+EN)
 │                 │  Phase 1: PII detection (regex + NER + ONNX)
 │                 │  Phase 2: Secret detection (pattern + entropy)
 │                 │  Phase 3: Confidential markings + EDM fingerprints
 └─────┬───────────┘
       │
       ▼
 ┌─────────────┐
 │  Policy     │  Maps entity types → actions (block / redact / pseudonymize / warn)
 │  Engine     │  Routing override: PII → private; safe → public
 └─────┬───────┘
       │
    ┌──┴───────────────┐
    │                  │
    ▼                  ▼
 Private LLM      Public LLM
 (on-prem)        (cloud, pseudonymized)
    │                  │
    └──────┬───────────┘
           ▼
 ┌──────────────────┐
 │  Audit Logger    │  100% coverage, tamper-detection hash chain (HMAC-SHA256)
 │                  │  Differential profiles: lightweight (private path), full (public path)
 └──────────────────┘
       │
       ▼ (async, off user-path)
 ┌────────────┐    ┌──────────────┐
 │  Audit Bot │←───│  Packet Tap  │  Bypass correlation, nftables feedback
 └────────────┘    └──────────────┘
```

### Routing Logic in Detail

`Router.resolve()` makes the backend assignment **after** PII detection but **before** forwarding:

1. If any entity mapped to `block` is found → reject (403), no backend reached
2. If any entity is classified as strong PII (KR_RRN, KR_ACCOUNT, KR_PASSPORT, etc.) → force private backend
3. If weak PII is found and pseudonymization is enabled → pseudonymize, then allow public backend
4. If no PII → select backend by cost policy (configurable `routing.yaml`)

The private backend is always tried first when both are available; the public backend is the fallback for cost-optimized non-sensitive traffic. Backend assignments are recorded in every audit entry, giving you a per-request trail of where each request was ultimately sent.

### Detection Pipeline in Detail

The `DetectionPipeline.analyze()` method runs four phases sequentially. Each phase annotates the request with typed findings; the Policy Engine then acts on the aggregate set.

**Phase 0 — Prompt Injection:** Matches 18 curated Korean/English jailbreak patterns (role-play escapes, system prompt overrides, instruction injection). Findings at this phase trigger an immediate block regardless of policy; there is no redact or pseudonymize path for injections.

**Phase 1 — PII Detection:** Three stacked backends with increasing accuracy:
1. Regex + checksum validators (always on; zero latency cost)
2. Gazetteer NER (packaged Korean surname/given-name lists; ~5 ms overhead)
3. KoELECTRA ONNX-INT8 (optional; quantized transformer, ~35 ms at 512 chars)

The model's recall figure (0.9908) is a Wilson confidence-interval lower-bound on the held-out test set, making it a conservative, statistically defensible claim rather than a best-case number.

**Phase 2 — Secret Detection:** Combines pattern matching (common API key prefixes, password field names) with Shannon entropy scoring. High-entropy strings that match secret patterns are flagged even without a known format.

**Phase 3 — Confidential/EDM:** Checks for document classification markings (`CONFIDENTIAL`, `SECRET`, internal tags) and compares content against an Exact Data Match fingerprint database of known-sensitive documents.

**Latency:** p95 end-to-end gateway latency at 512-character inputs is **41 ms** under single concurrency. Batch throughput scales linearly; the ONNX backend saturates CPU before memory.

### Reversible Pseudonymization

For use cases where the LLM output must reference the original data (e.g., summarizing a contract with public-cloud model quality), NuFi Security supports **reversible pseudonymization** on weak-PII entity classes (KR_PERSON, KR_PHONE, EMAIL, KR_BRN, KR_LOCATION):

1. `SurrogateMinter.mint()` generates a deterministic, format-preserving surrogate token (e.g., `홍길동` → `[PERSON:a3f7]`)
2. The real-value → surrogate mapping is stored in `MappingVault`, encrypted with AES-256-GCM using a session-scoped Data Encryption Key (DEK) sealed by a Key Encryption Key (KEK)
3. The surrogate text is sent to the public LLM; the real value never leaves the host
4. The LLM response is passed through `deanonymize()`, which looks up and restores originals
5. Streaming support handles chunk-boundary surrogate splits via a lookahead buffer

This gives you access to frontier-model capability on data that contains weak PII, without ever exposing real values to the cloud. The vault stores no plaintext keys at rest. Session DEKs are derived fresh per request and not persisted.

### Audit Integrity

Every gateway decision — allow, block, redact, pseudonymize, route-to-private, route-to-public — is written to an append-only audit log with an **HMAC-SHA256 hash chain**: each entry includes the hash of the previous entry. Modifying any historical record breaks every subsequent hash, making tampering immediately detectable during verification.

**Fail-closed recording:** If the audit write fails for any reason, the request is blocked. No request passes through without a corresponding, verified log entry.

**Differential profiles** reduce log volume without losing coverage:
- **Private path** (on-prem LLM): lightweight logging — secrets and strong PII only, sampled
- **Public path** (cloud LLM): full logging — all categories, confidential markings, bypass correlation events

### Policy Engine and Operations

`PolicyEngine.apply()` maps each detected entity type to one of four actions:

| Action | Behavior |
|---|---|
| `block` | Reject the entire request with a 403 response |
| `redact` | Replace entity spans with type tags (`[KR_RRN]`) |
| `pseudonymize` | Replace with reversible surrogate tokens before public routing |
| `warn` | Allow but emit a policy warning in the audit log |

Policy is loaded from `config/policy.yaml` and supports **hot-reload**: changing the file takes effect within the next request cycle without restarting the service. Multiple named policy profiles can coexist, bound to different routes or tenants, with zero-downtime rollback via version snapshots. All policy changes are themselves recorded in the audit chain.

### Network Enforcement

The `enforcement/` subsystem generates and applies **nftables rulesets** that whitelist specific UIDs and cgroups for outbound connections to public LLM endpoints. All other processes receive a DROP verdict at the kernel packet filter — below the application layer.

An async `AuditBot` consumes three event streams (message store, content dump writer, packet flow tap) asynchronously, deduplicates cross-stream events, and emits bypass-detection findings back to enforcement for automated ruleset tightening.

---

## Integration in 5 Minutes

**SDK:**
```python
from nufi import Guard

guard = Guard()
result = guard.inspect("고객명 홍길동, 주민번호 900101-1234567을 포함한 문서입니다.")

if result.decision == "block":
    raise ValueError(f"PII detected: {result.findings}")
```

**REST API:**
```bash
nufi-egress serve --port 8000 &

curl -X POST http://localhost:8000/inspect \
  -H "Content-Type: application/json" \
  -d '{"text": "계좌번호 110-123-456789 송금 요청"}'
```

**OpenAI-compatible gateway with automatic private/public routing (drop-in replacement):**
```python
import openai

# Change one line — routing, PII enforcement, and audit happen automatically
openai.base_url = "http://nufi-security-gateway:8000/v1"

# Requests with PII → private LLM automatically
# Requests without PII → public LLM (cost-optimal)
# All requests → tamper-evident audit log
response = openai.chat.completions.create(
    model="auto",   # NuFi Security selects backend per policy
    messages=[{"role": "user", "content": prompt}]
)
```

---

## Competitive Position

| | English OSS (Presidio) | Commercial SaaS DLP | **NuFi Security** |
|---|---|---|---|
| Korean PII coverage | Minimal | Product-dependent | **12 classes, recall 0.99** |
| Air-gap / on-prem | Library only | Cloud-required | **Core = 0 external deps** |
| Korean regulatory evidence | None | Partial | **5 frameworks, 48 controls, auto-generated** |
| Network-layer bypass block | None | None | **nftables packet DROP** |
| Audit tamper detection | None | Proprietary | **Open HMAC hash chain** |
| Reversible pseudonymization | None | Partial | **AES-256-GCM, session DEK** |
| Deployment modes | Library | SaaS | **CLI + HTTP + SDK** |
| Hybrid public/private routing | None | None | **Policy-aware, PII-driven, cost-optimal** |

---

## Summary

NuFi Security is a production-grade egress security layer for organizations that need to use **both private and public LLMs simultaneously** in regulated, data-sensitive environments. It provides a single policy-enforcement point across all LLM backends: strong PII stays on private infrastructure, safe traffic is routed to the best available model, and every decision is recorded with cryptographic audit guarantees.

It is technically straightforward to integrate (a single base URL change for OpenAI SDK users), operationally auditable (hash-chain logs, automated compliance reports), and built specifically for the Korean regulatory and linguistic landscape.

For evaluation, a Docker Compose environment with 24 end-to-end demo scenarios is available. A full benchmark reproduction — including the golden test set and statistical validation — can be run offline against your own infrastructure.

> **Contact your NuFi Security representative for a private evaluation kit and architecture walkthrough.**
