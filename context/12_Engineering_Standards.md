# 12 · Engineering Standards (backend, security, database, codebase)

Your bar (13 Oct): "market gold standard best practice" for backend, security, functionality, DB structure and codebase. This doc is that bar, written down, matched to the stack in 02 and 03.
Labels: ✅ verified (official doc opened, or ran in our phase 1 scaffold) · 🟡 inference / our design choice.

## 0. Hard truth first

- Gold standard on **security, schema, tests and CI** is doable in 5 days and is non negotiable. ✅ Phase 1 scaffold already has it running (section 12).
- Gold standard on **everything** is not. A 3 person team with ~120 must hrs (doc 07) can't also do pen tests, multi region, SLOs, load tests. Section 11 lists exactly what we skip and why, so a judge asking "is this production ready?" gets an honest answer, not a bluff. 🟡
- Judges score Tech 40%. A clean repo with rules tests, CI badge and a threat model is cheap evidence of quality that most hackathon repos don't have. 🟡

## 1. Baseline we measure against

| Standard | Use | Source |
|---|---|---|
| OWASP ASVS (v5) | checklist for auth, session, validation, logging; we target Level 1 fully, Level 2 on auth + validation 🟡 | ✅ [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) |
| OWASP API Security Top 10 (2023) | API threats: broken object level auth, unrestricted resource use, SSRF | ✅ [API Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) |
| OWASP LLM01 Prompt Injection | fetched web pages are hostile input to Gemini | ✅ [genai.owasp.org LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) |
| Google Cloud IAM best practice | least privilege service accounts | ✅ [Using IAM securely](https://cloud.google.com/iam/docs/using-iam-securely) |

## 2. Authentication and authorization

| Rule | How | Source |
|---|---|---|
| Every non public API call carries a Firebase ID token; backend verifies it server side, with revocation check | `firebase_admin.auth.verify_id_token(token, check_revoked=True)` in a FastAPI dependency ✅ scaffold `app/auth.py` | ✅ [Verify ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens) |
| Two roles only: admin (Google sign in) creates sessions; viewer (anonymous or no login) reads public cards | anonymous token on an admin route → 403 ✅ tested | 🟡 design |
| Object level authz on every read (API1:2023) | sessions readable only when `owner_uid == request.auth.uid`, enforced in BOTH API and Firestore rules | ✅ [API Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) |
| One generic error for auth failures | always `401 unauthorized`, never "token expired" vs "bad signature" ✅ tested | 🟡 |
| Browser calls carry App Check | blocks scripted abuse of Gemini cost on the public demo | ✅ [App Check](https://firebase.google.com/docs/app-check) |
| Service to service (Cloud Tasks → main, main → fetcher) uses Google signed OIDC tokens, not shared secrets | Cloud Run IAM `run.invoker` on the caller's service account | ✅ [Service to service auth](https://cloud.google.com/run/docs/authenticating/service-to-service), ✅ [HTTP target tasks](https://cloud.google.com/tasks/docs/creating-http-target-tasks) |

## 3. Secrets

| Rule | How | Source |
|---|---|---|
| No secret in code, repo, chat, Docker image or CI logs | Secret Manager only; `.env` gitignored; `.env.example` has names, no values ✅ scaffold | ✅ [Secret Manager best practices](https://cloud.google.com/secret-manager/docs/best-practices) |
| Cloud Run reads secrets as env vars **pinned to a version**, not `latest` | `--set-secrets=PC_TELEGRAM_BOT_TOKEN=tg-bot-token:1` | ✅ [Cloud Run secrets](https://cloud.google.com/run/docs/configuring/services/secrets) ("pin the secret to a particular version instead of using latest") |
| CI deploys with Workload Identity Federation, never a downloaded JSON key | `google-github-actions/auth` with a WIF provider | ✅ [WIF for pipelines](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines), ✅ [auth action](https://github.com/google-github-actions/auth) |
| Secrets typed as `SecretStr`, so they never print in logs or reprs | ✅ scaffold `app/config.py` | ✅ [Pydantic](https://docs.pydantic.dev/latest/) |
| Logs redact token shaped strings (Telegram token, bearer, Google API key) | ✅ scaffold `app/logging_setup.py`, tested | 🟡 patterns ours |
| Keys you create (bot token, any API key) reach us only through the private drop link, never pasted in chat | rule from doc 11 | 🟡 |

## 4. Input validation (every boundary)

| Boundary | Rule | Status |
|---|---|---|
| HTTP bodies | Pydantic models with `extra="forbid"`, max lengths, regex ids; unknown field like `is_admin` → 422 | ✅ tested |
| URLs from users | YouTube link must be `https` + YouTube host | ✅ tested |
| Body size | >1 MB rejected with 413 before parsing (configurable) | ✅ tested |
| Telegram updates | `extra="ignore"` (Telegram adds fields any time) but every field we use is typed + capped | ✅ tested |
| Gemini output | always JSON schema constrained output, then parsed by the same Pydantic models; a malformed model reply fails closed (UNVERIFIABLE) 🟡 phase 2 | 🟡 |
| Fetched web pages | treated as untrusted DATA in prompts (delimited, never instructions); Model Armor if time | ✅ [LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), 🟡 Model Armor stretch |
| Verdict faithfulness | TRUE/FALSE/MISLEADING downgraded to UNVERIFIABLE when grounding support < 0.6 (threshold tuned on benchmark) | ✅ `gate_verdict` tested, 🟡 threshold |

## 5. SSRF (the fetcher is our riskiest surface)

We fetch URLs that a model or a user chose. OWASP API7:2023 is exactly this. ✅ [SSRF cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

- https only, port 443 only, no `user:pass@` URLs ✅ tested
- every resolved IP must be public: blocks 127/8, 10/8, 192.168/16, ::1, link local incl. **169.254.169.254 (metadata server = token theft)** ✅ tested
- re check on every redirect hop and connect to the vetted IP (DNS rebinding) 🟡 phase 2
- fetcher runs as its own Cloud Run service with a service account that has **zero** IAM roles, so even a bypass steals nothing ✅ [service identity](https://cloud.google.com/run/docs/securing/service-identity)
- size cap 2 MB, timeout 8 s, content types html/text only 🟡

## 6. Webhooks (Telegram)

- `setWebhook` with `secret_token`; Telegram then sends header `X-Telegram-Bot-Api-Secret-Token` on every update ✅ [Bot API setWebhook](https://core.telegram.org/bots/api#setwebhook)
- constant time compare (`hmac.compare_digest`); unconfigured secret = reject all; wrong secret → 404 (scanners learn nothing) ✅ tested
- junk body → 200 `{"ok":true}` so Telegram does not retry it forever 🟡 ✅ tested
- raw chat ids never logged, only a salted sha256 prefix ✅ tested
- respect limits: 1 msg/s per chat, 20/min per group ✅ [Bot FAQ](https://core.telegram.org/bots/faq)

## 7. Rate limiting and cost guard (API4:2023 unrestricted resource consumption)

| Layer | Rule | Status |
|---|---|---|
| Public endpoints (`/api/check`, verify page) | token bucket per client IP, rightmost `X-Forwarded-For` (leftmost is spoofable) | ✅ tested incl. spoof case |
| Gemini spend | App Check + auth on everything that calls Gemini; only admins trigger prebunk | 🟡 |
| Cloud Run | `--max-instances` cap so a flood can't scale the bill | ✅ [max instances](https://cloud.google.com/run/docs/configuring/max-instances) |
| Billing | budget alert at 50/90/100% | ✅ [budgets](https://cloud.google.com/billing/docs/how-to/budgets) |

Hard truth: our token bucket is per instance memory, so with N instances the real limit is N times higher. Fine for a demo with max instances 3; production would move it to Cloud Armor or Redis. 🟡

## 8. Firestore schema (the DB structure)

Server writes everything with the Admin SDK; browsers only read through realtime listeners. Rules are deny by default. ✅ [Rules get started](https://firebase.google.com/docs/firestore/security/get-started)

| Path | Fields (all validated by a Pydantic model before write) | Client access (rules) |
|---|---|---|
| `sessions/{sid}` | schema_version, owner_uid, topic, speaker, youtube_url, status (draft, prebunking, ready, live, closed), created_at | owner get/list only |
| `sessions/{sid}/claims/{cid}` | schema_version, text, lang (en, hi, hi-Latn), source (predicted, live), status (queued, checking, proved, failed), card_id, embedding (vector, phase 2), created_at | owner read only |
| `cards/{card_id}` | schema_version, claim, verdict (TRUE, MISLEADING, FALSE, UNVERIFIABLE), explanation, sources[1..8]{url, snippet, snapshot_sha256, fetched_at}, support_score 0..1, card_sha256, png_phash, created_at | public **get**, no **list** (no scraping) |
| `tg_checks/{id}`, `jobs/{id}` | server only | none |

Design rules:
- **Immutable cards.** Cards are written with `create()` (fails if id exists), never updated. A correction = new card + `superseded_by` link. That is what makes `card_sha256` meaningful. 🟡 design, ✅ `create()` in scaffold
- **Unguessable ids.** 128 bit random (`secrets.token_urlsafe(16)`), so public get without list is safe. ✅ scaffold
- **schema_version on every doc.** Migration approach: readers accept version N and N-1; a one shot script upgrades old docs; bump only with a test. 🟡 For 5 days we expect to stay on v1.
- **Indexes in code.** `firestore.indexes.json` is in the repo; the vector index for claim embeddings is created with gcloud in phase 2. ✅ [vector search](https://firebase.google.com/docs/firestore/vector-search)
- Follow Firestore limits: avoid monotonically increasing doc ids and hot documents. ✅ [Firestore best practices](https://cloud.google.com/firestore/docs/best-practices)
- Backup: one export to Cloud Storage before the demo. ✅ [export/import](https://cloud.google.com/firestore/docs/manage-data/export-import)

## 9. Codebase layout and standards

```
proofcard-backend/
  app/
    main.py           FastAPI app factory, routes, security headers, body limit
    auth.py           Firebase ID token dependency, roles
    config.py         typed settings, secrets as SecretStr, prod guards
    schemas.py        every request + Firestore doc model, verdict gate
    security.py       webhook secret, SSRF guard, canonical hashing, rate limiter
    store.py          data access layer (in memory for tests, Firestore for prod)
    logging_setup.py  JSON logs for Cloud Logging, redaction
    asgi.py           uvicorn entrypoint
  tests/              unit + API tests (pytest)
  rules-tests/        Firestore rules tests on the emulator
  firestore.rules, firestore.indexes.json, firebase.json
  Dockerfile          slim, non root user
  .github/workflows/ci.yml, .github/dependabot.yml
```

| Practice | Tool | Source |
|---|---|---|
| Lint incl. security rules (bandit set `S`), bugbear, async pitfalls | ruff | ✅ [ruff](https://docs.astral.sh/ruff/) |
| Formatting | `ruff format` | ✅ same |
| Types | mypy `--strict` + pydantic plugin | ✅ [mypy](https://mypy.readthedocs.io/en/stable/) |
| Routes never touch Firestore directly; they call the Store layer | dependency injection | 🟡 |
| Pinned deps + weekly Dependabot + `pip-audit` in CI | | ✅ [Dependabot](https://docs.github.com/en/code-security/dependabot) |
| Security headers on every response (nosniff, frame deny, HSTS, CSP) | middleware | ✅ tested |
| API docs (`/docs`) off in prod | | ✅ scaffold |
| Container runs as non root | Dockerfile `USER 10001` | 🟡 |

## 10. Tests and CI gates

| Gate | Blocks merge when | Status today |
|---|---|---|
| `ruff check` + `ruff format --check` | any lint or format issue | ✅ green |
| `mypy --strict` | any type error | ✅ green |
| `pytest` with coverage floor 85% | any failure or coverage drop | ✅ green |
| `pip-audit` | known CVE in runtime deps | ✅ "No known vulnerabilities found" |
| Firestore rules tests on emulator | any rule regression | ✅ 6/6 green |
| GitHub Actions hardening | token `contents: read`, actions pinned to commit SHA, `persist-credentials: false` | ✅ [Actions hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions) |

Test pyramid for later phases: unit (pure functions) → API (TestClient, fake verifier) → emulator integration (Firestore + rules) → one end to end demo script on the real deploy. Gemini calls are mocked in CI, run live only in the benchmark script. 🟡 ✅ [Emulator suite](https://firebase.google.com/docs/emulator-suite), ✅ [rules unit tests](https://firebase.google.com/docs/rules/unit-tests)

## 10b. Logging and observability

- One JSON object per line with `severity` + `message`, parsed natively by Cloud Logging ✅ [structured logging](https://cloud.google.com/logging/docs/structured-logging)
- Never log: tokens, raw Telegram ids, full user text. Log: session id, card id, latency, verdict. ✅ scaffold
- Latency per stage (prebunk, verify, check) shown in the demo as a Tech score point 🟡

## 10c. Threat model (STRIDE light)

| Threat | Where | Mitigation | Status |
|---|---|---|---|
| Spoofing a Telegram update | `/tg/webhook` | secret_token header, constant time compare | ✅ built |
| Reading another admin's session (BOLA) | API + Firestore | owner check in API and rules | ✅ API built, rules 6/6 green on emulator |
| Tampering with an issued card | Firestore | client writes denied, `create()` only, `card_sha256` | ✅ built |
| Forwarded card edited by a user | Telegram | text diff + pHash vs canonical card (sha256 of the image can't survive recompression, see doc 03) | 🟡 phase 4 |
| SSRF to metadata server | fetcher | public IP check, zero role SA, separate service | ✅ guard built, 🟡 service phase 2 |
| Prompt injection from a fetched page | Gemini | page text as data, schema output, grounding gate, Model Armor stretch | 🟡 phase 2 |
| Cost flood (DoS on Gemini bill) | public endpoints | App Check, rate limit, max instances, budget alert | ✅ limiter built, 🟡 rest at deploy |
| Secret leak | repo, logs | Secret Manager pinned, WIF, SecretStr, redaction, gitignore | ✅ built |
| Card enumeration / scraping | `cards` | random 128 bit ids, no list | ✅ built |
| Supply chain | deps, actions | pinned versions + SHAs, pip-audit, Dependabot | ✅ built |

## 11. What we skip in 5 days, and why (say this to a judge if asked)

| Skipped | Why | Production fix |
|---|---|---|
| Distributed rate limit | per instance bucket is enough with max 3 instances | Cloud Armor rate rules or Redis |
| Pen test, formal ASVS audit | no time | external audit |
| Multi region, SLOs, load test | demo scale | regional failover, SLO alerts |
| Full migration framework | one schema version in 5 days | versioned migration scripts + tests |
| Model Armor (if phase 2 slips) | stretch | mandatory before real users |
| Dedicated staging project | one GCP project for the Cup | separate dev/stage/prod projects |
| E2E browser tests for the frontend | frontend is yours, Playwright optional | Playwright suite in CI |

## 12. Phase 1 status (built and run today, 13 Oct)

- ✅ Backend scaffold built fresh (no code copied from InTruth or any non permissive repo).
- ✅ ruff, format, mypy strict: all green.
- ✅ 38 Python tests passing, 97% coverage.
- ✅ pip-audit: no known vulnerabilities.
- ✅ Firestore rules: 6 of 6 emulator tests pass (owner only reads, no client writes, public card get without list, server only collections closed).
- 🟡 Not pushed yet: waiting for your repo + collaborator invite. Plan goes to you first, PR only after your ok (your PR rule).
