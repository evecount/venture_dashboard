# Plan: Mamba applicant readiness in Venture Buddy

Status: proposal, nothing built. Written 2026-10-20 from reading CybrDeck-Website `src/lib/mamba/*`, `firestore.rules`, and VentureDash `bot_agent.py`, `bot_skills.py`, `supabase/schema.sql`.

## The idea in one paragraph

Every founder in the cohort applied through the CybrDeck site. That application was scored on seven readiness axes, screened against grants, and its weak answers were flagged for the interview. Today all of that stops at the admission decision. If mentors' Venture Buddy could see a **minimal, de-identified readiness profile** for each enrolled founder, it could say things like "Commitment capacity was their weakest axis at intake, and they've now been quiet for 9 days", or "They were one gap away from Startup SG Founder (no local incorporation). Worth raising now they've registered." Founders would not see any of it.

## What exists today (CybrDeck)

| Thing | Where | Notes |
|---|---|---|
| Application | Firestore `mamba_registrations/{recordKey}` | `recordKey = "mreg_" + sha256(normalised email)[:56]` (`application.ts`). Identity fields, ~40 answers flattened by question id, `track`, `intake`, `status` (`pending → shortlisted → offered → enrolled`, or `declined`). |
| Readiness assessment | Same document, field `assessment` | Written by the Admin SDK in `dossier-build.ts`: `overall`, `band` (cohort-ready / strong / conditional / not-this-cohort), `axes[]` (domain, execution, traction, commitment, persistence, coachability, accountability; `score` 0–1 plus `evidence` = the applicant's own answer that moved it most), `grantRisk` + reasons, `verificationGaps[]`, `scoredAt`. Deterministic, with an optional bounded model nudge (`assessmentReviewedByOne`). |
| Grant screen | Same document, `grantMatches[]` | `{id, name, agency, verdict: eligible/conditional/not-now, gap}` for SSGF, SSGT-PoC and others. |
| Reviewer notes | Firestore `mamba_review_notes/{recordKey}` | Model-drafted interview questions and One's review summary. **Core/Admin only by design**: "a model's read of a person must not sit where that person can query it." |
| Redactor | `deidentify.ts` | `IDENTITY_FIELDS` (name, email, phone, company, employer, venture, third-party contact, references, team...) plus pattern scrub (emails, phones, NRIC, handles, URLs). The file itself says it is a redactor, not an anonymiser. |

The CybrDeck design draws three firm lines this plan must keep: scores **triage, they don't decide**; nothing evaluative is shown to the applicant; and applicant claims never go into a model's memory or training data.

## Recommendation

### 1. Send a derived profile, never the application

Only enrolled (and offered) applicants, and only these fields:

| Send | Why |
|---|---|
| `record_key`, `status`, `track`, `intake` | Join key and lifecycle. |
| `band`, `overall`, `axes[].{axis,label,score}` | The readiness shape a mentor can coach against. |
| `verificationGaps[].label` (the question's label, not the answer) | "What to press on", e.g. "Week plan too thin to trust". |
| `grantMatches[].{id,name,agency,verdict,gap}` | The most actionable part: what public money is one step away. |
| `grantRisk` (low/watch/high) | One word. The reasons need checking first: they may quote answers. |
| `stage` (the select option, e.g. "Prototype or MVP built, no users yet") | Starting point to measure progress against. |
| `scoredAt`, `reviewedByOne` | So the bot can say how old and how derived the reading is. |

| Never send | Why |
|---|---|
| Every `IDENTITY_FIELDS` field, LinkedIn/GitHub/portfolio links | Identity. The join doesn't need them (see 3). |
| `axes[].evidence` and every free-text answer | The applicant's own words; can identify by description. |
| `runway`, `dependents`, `employerAware`, `affordability`, `capitalToMatch` | Personal and financial circumstances: sensitive, not needed to coach. |
| `milestoneContract`, `accountableTo`, references | Names a third party who never agreed to be in Slack. |
| Anything from `mamba_review_notes` (interview draft, One's summary) | Kept Core/Admin-only on purpose; a model's read of a person. |
| `adminNotes`, Drive ids, dossier PDF | Internal to the review. |

Phase 2 (optional, needs the user's call): a short allowlist of *plan* answers the founder wrote for themselves (`firstThirtyDays`, `wrongAssumption`, `failureMode`), passed through `redact()` with identity tokens on the CybrDeck side before sending. These make for great coaching ("you said the riskiest assumption was X; has it been tested?"), but they are the founder's words, so it's their call (see Open questions).

### 2. Transport: CybrDeck pushes, VentureDash stores

```
CybrDeck (Admin SDK)                          VentureDash Worker                    Supabase
dossier built / status changed  ──POST──▶  /api/mamba/readiness  ──service role──▶  mamba_readiness
  builds the profile (allowlist)            HMAC check (same as GitHub webhook)     RLS on, no policies
  signs body with shared secret             validates shape, upsert / delete
```

- **Why push, not pull:** a bot that pulls from Firestore would need a service account that can read every application and review note. A push lets CybrDeck decide exactly what leaves, and each side keeps only its own secrets. One new shared secret (`MAMBA_SYNC_SECRET`) lives in both, never in git.
- **When:** after `buildAndFileDossier` writes back, and whenever `status` changes. Send only for `offered`/`enrolled`. On `declined`, withdrawal or a deletion request, send a delete for that key.
- **Backfill:** a one-off CybrDeck script that pushes the current offered/enrolled records through the same endpoint.
- The Worker route mirrors `src/routes/api/github/webhook.ts`: raw-body HMAC (`src/lib/integrations.ts` already has the helper), strict field allowlist (drop unknown keys), size cap.

### 3. Matching applicants to founders without sharing emails

VentureDash already has `founders.email`. Port `normalizeReplyTo` (trim, lower-case; for gmail.com and googlemail.com, drop dots and `+tag`, and fold googlemail to gmail) and compute `mreg_ + sha256(normalised)[:56]` in Python. The founder's row then joins `mamba_readiness.record_key` directly. No email, name or phone crosses the systems.

- Ship shared test vectors in both repos (e.g. `Bob.Smith+camp@GoogleMail.com` → `mreg_…`) so a change on either side fails a test.
- A founder who applied under a different email simply has no profile. A mentor-only "link this founder to application email X" fix can come later if needed.

### 4. Storage (migration for the user to run)

`supabase/migrations/2026-10-mamba-readiness.sql`:

```sql
create table if not exists public.mamba_readiness (
  record_key   text primary key,           -- mreg_<sha256>, never an email
  status       text not null,              -- offered | enrolled
  track        text, intake text, stage text,
  band         text, overall numeric,
  axes         jsonb not null default '[]', -- [{axis, label, score}]
  gaps         jsonb not null default '[]', -- [label]
  grant_risk   text,
  grants       jsonb not null default '[]', -- [{id, name, agency, verdict, gap}]
  reviewed_by_one boolean default false,
  scored_at    timestamptz,
  received_at  timestamptz not null default now()
);
alter table public.mamba_readiness enable row level security;  -- no policies: service role only
```

The bot must degrade gracefully when the table doesn't exist (`_q` already returns empty). Retention: delete rows 90 days after the cohort ends (see Open questions).

### 5. Who sees what

| | Mentors | Founders | Dashboard |
|---|---|---|---|
| Band, axes, gaps | Yes, in Slack, via a mentor-only tool | **No** | No (RLS: service role only) |
| Grant matches | Yes | Phase 2: only "eligible" schemes as suggestions, worded as opportunities, if the user agrees | No |

Why not founders: CybrDeck deliberately never shows applicants their own read. A founder told "Not this cohort: conditional" or "Coachability 0.4" by a chatbot would undo that design, and that's a trust problem the program can't take back.

### 6. How the bot would use it

- **New mentor-only look-up `readiness(startup)`**, gated in code like `add_note`. It's not in founder tools at all. It joins founders → record key → profile, and returns a block headed *"Intake readiness (from the Mamba application, scored <date>): triage, not a verdict"*.
- **`startup_detail` for mentors** gains a one-line summary (band plus the two weakest axes). Founder calls never query the table.
- **New skill `skills/readiness-coaching.md`** (mentor, `tools: readiness, startup_detail, github_activity`, `effort: low`). Triggers: readiness, intake, application, axes, grants, SSGF, eligible. Rules:
  - Compare the intake reading with what's happening now. A weak axis plus a live signal makes a talking point ("low commitment capacity at intake + quiet 9 days → ask about time this week"). A weak axis alone is not a judgement.
  - Always say it's an intake triage and how old it is. Never present scores as facts about the person.
  - Grants: name the scheme, the verdict and the single gap, and suggest the next step.
  - Never repeat readiness content in `announce`, routines or anything a founder receives.
- **Weekly digest skill:** may add "Watch: weak at intake on X, and the signals match" for at most one or two startups.
- **Guards in code, not just prompt:**
  - the tool only exists for mentors;
  - `announce` and routine `compose` refuse messages that contain band labels or axis scores (a simple pattern check);
  - readiness text is never passed to `remember()` (blocked in `_run_tool`), keeping CybrDeck's "never into memory" rule.

### 7. Phases

1. **Sync and storage** (CybrDeck push and backfill, Worker endpoint, migration, the record-key port with shared tests). Nothing visible yet. About a day.
2. **Mentor look-up and skill** (the `readiness` tool, the `startup_detail` line, `readiness-coaching.md`, the announce/compose/remember guards, tests that a founder can never reach it). About a day.
3. **Optional:** founder-facing grant suggestions and the redacted plan answers, only after the user decides the open questions below.

## Found while reading (CybrDeck, worth a look regardless)

`firestore.rules` still lets an applicant read `mamba_registrations/{uid}` when the document id equals their auth UID (`isOwner`). New records use `mreg_` hashes, so the owner rule never matches them. But `buildAndFileDossier` writes `assessment` and `grantMatches` onto whatever record it's given. Any **legacy record still named after an auth UID** that gets a dossier (re)built would carry its score where that applicant can read it with their own token. This contradicts the rules' own comment ("nothing evaluative may be stored beside their answers"). Worth checking whether any UID-keyed records remain, and moving `assessment` to `mamba_review_notes` or migrating those keys.

## Open questions for the user

1. **Consent:** does the application's disclosure ("nothing you write here is published") cover sharing a derived readiness profile with the program's mentors in Slack? A line added to the offer or enrolment step would make it clear.
2. **Founders:** confirm they see nothing in phase 1. Later, are eligible-grant suggestions OK for them?
3. **Phase 2 plan answers:** worth including (redacted) for coaching, or keep raw answers out entirely?
4. **Which mentors:** all mentors, or only the startup's lead advisor?
5. **Retention:** delete 90 days after the cohort ends, or at enrolment end?
6. **Studio and Lab tracks:** they have no venture or grant questions. Include their axes only, or Venture track only?
7. **Stale readings:** should a mentor be able to re-trigger a dossier rebuild from Slack, or is the intake snapshot enough?
