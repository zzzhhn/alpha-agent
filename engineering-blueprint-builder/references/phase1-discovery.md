# Phase 1: Discovery — Constraint-Gathering Protocol

**Purpose:** Extract all hard constraints before design. Missing constraints = rework later. Your job is to surface what the user hasn't said yet.

---

## AskUserQuestion Pattern

Use this exact format when Claude prompts for constraints:

```
📋 I need clarity on [category]:

Option A: [specific choice]
Option B: [specific choice]
Option C: [something else entirely]

Which applies? Or describe your situation.
```

Do not ask open-ended "tell me about X" questions. Force choice boundaries.

---

## Seven Constraint Categories

### 1. SCOPE
**Prompt:**
```
📋 What's the scale of this project?

Option A: Single feature/module (limited scope)
Option B: Full product MVP with multiple modules
Option C: Major platform redesign across existing systems

Which is this?
```

**What you're detecting:**
- Full rewrite vs. surgical change
- Number of modules (1–3 vs. 10+)
- Cross-system dependencies
- Legacy integration needs

**Follow-up if vague:** "When you say 'rebuild the auth system,' does that include payment flows, or just login/signup?"

---

### 2. MARKET / AUDIENCE
**Prompt:**
```
📋 Who are the primary users?

Option A: Internal team / power users (small group)
Option B: General public / broad audience
Option C: Enterprise customers with compliance needs

Who's using this?
```

**What you're detecting:**
- Accessibility requirements (WCAG)
- Compliance scope (HIPAA, GDPR, SOC2)
- Localization needs (English only vs. 10 languages)
- User sophistication level
- Support burden

---

### 3. BUDGET (Time + Resources)
**Prompt:**
```
📋 What's your timeline?

Option A: ASAP — this week or next (urgent)
Option B: 2-4 weeks (normal sprint cycle)
Option C: Open-ended (quality > speed)

What's realistic for you?
```

**What you're detecting:**
- Can't use bleeding-edge tech (only stable, documented)
- Can't do heavy custom work (must use libraries)
- Can't iterate with user feedback (must get it right first)
- Can afford small team or just 1 person
- Whether to parallelize work

**Hidden budget constraint:** If user says "use the best model" without mentioning cost → assume they mean best available, which may mean GPT-4 at $0.03/1K tokens. STOP and ask: "Does that include LLM costs? What's your token budget monthly?"

---

### 4. SECURITY & COMPLIANCE
**Prompt:**
```
📋 Any regulatory or security constraints?

Option A: No special requirements (standard web security)
Option B: PII/payment data (must encrypt, audit logs)
Option C: Regulated industry (HIPAA, PCI-DSS, SOC2 audit)

What applies?
```

**What you're detecting:**
- Database encryption requirements
- Audit logging depth
- API key storage (environment vs. secrets manager)
- Rate limiting rules
- DLP (data loss prevention) tools needed
- Vendor requirements (must use their approved stack)

**Red flag:** User says "keep it private" but hasn't mentioned who accesses what. STOP and ask for explicit ACL rules.

---

### 5. DELIVERY FORMAT
**Prompt:**
```
📋 How will the blueprint be delivered?

Option A: Single comprehensive document (PDF/DOCX)
Option B: Modular docs (separate files per component)
Option C: Interactive markdown in repo + wiki

What works for your workflow?
```

**What you're detecting:**
- Is .docx okay or only markdown?
- Will it be printed or screen-only?
- Does version control matter (git-friendly)?
- Must include diagrams in-doc or separate?
- Bilingual support needed?

---

### 6. TECHNOLOGY STACK
**Prompt:**
```
📋 Any hard tech requirements?

Option A: You pick the best approach
Option B: Must use [specific language/framework]
Option C: Must integrate with [specific system]

What's non-negotiable?
```

**What you're detecting:**
- Language constraints (Python, Node.js, Go, Rust)
- Framework lock-in (React, Vue, FastAPI, Django)
- Cloud vendor (AWS, GCP, Azure, self-hosted)
- Database type (SQL vs. NoSQL, which flavor)
- LLM provider (OpenAI, Anthropic, Ollama, local)
- Hosting environment (serverless, Docker, K8s)

**Red flag:** "Use whatever" often means they care but haven't said. Ask: "If I propose Node.js + PostgreSQL, any objections? Or must it be Python?"

---

### 7. TIMELINE / DELIVERY DATE
**Prompt:**
```
📋 When do you need this delivered?

Option A: This week
Option B: Next month
Option C: No hard deadline, but sooner is better

What's realistic?
```

**What you're detecting:**
- Can include iteration rounds or just one pass
- Can do thorough testing or move fast
- Whether phased delivery is acceptable
- If documentation depth can vary

---

## Detecting Implicit Constraints

These are NOT in the user's message but are critical:

### Pattern: "Use the best X"
**Example:** "Use the best model for this."
**Implicit constraint:** No budget constraint mentioned!
**Action:** STOP and ask: "Cost-wise, are you okay with OpenAI's GPT-4 (~$0.03/1K input tokens), or do you need a cheaper option?"

### Pattern: "Make it scalable"
**Example:** "This needs to scale to millions of users."
**Implicit constraint:** No current load mentioned, no peak vs. baseline
**Action:** Ask: "What's your expected concurrency today vs. year 1? Is this Stripe webhook traffic or real-time interactive users?"

### Pattern: "Better security than we have now"
**Example:** "Current system is totally open, make it more secure."
**Implicit constraint:** They're accepting tech debt
**Action:** Ask: "Are you planning to migrate data from the old system? If so, does migration path need to preserve user sessions?"

### Pattern: Vague timeline
**Example:** "We need to launch soon."
**Implicit constraint:** May mean 2 weeks or 6 months
**Action:** Pin it: "Define 'soon' in days or weeks. And do you need one round of review or iterate?"

### Pattern: No mention of existing system
**Implicit constraint:** Either greenfield OR they assume you know about it
**Action:** Ask: "Are we building from scratch or integrating with an existing product?"

---

## Constraint Matrix Template

Include this in your Phase 1 output document:

```markdown
## Constraint Summary

| Category | Constraint | Impact | Notes |
|----------|-----------|--------|-------|
| **Scope** | [e.g., Full MVP with 4 modules] | Design must cover all modules; no cutting scope mid-project | User has 2 backend engineers |
| **Audience** | [e.g., Internal team, not public] | Can use advanced UI patterns; no need for mobile | 15 power users max |
| **Timeline** | [e.g., 3 weeks to launch] | Must use proven tech; no experimentation allowed | Hard deadline is May 15 |
| **Budget** | [e.g., ~80 engineer hours total] | Must leverage libraries, not build custom | No LLM cost budget if avoidable |
| **Tech Stack** | [e.g., Python, PostgreSQL, React] | Architecture locked to these choices | Must integrate with existing S3 bucket |
| **Security** | [e.g., PII = encrypted at rest + HTTPS only] | Encrypt database, audit logs, no plaintext storage | Internal tool, but handles user SSN |
| **Delivery** | [e.g., Single DOCX file, no separate markdown] | All content in one doc; include all diagrams | Will be printed, so page layout matters |
```

---

## Warning Signs (Stop and Re-Ask)

| Warning | Example | Action |
|---------|---------|--------|
| **Tech stack unknown** | "Just build it with whatever" | Force specificity: language, database, cloud |
| **Budget vs. scope mismatch** | "10 modules in 1 week with 1 person" | Negotiate scope down or timeline up |
| **Silent stakeholders** | User designs but CTO hasn't signed off | Ask: "Will your CTO review this? Any constraints from them?" |
| **Competing constraints** | "Cheapest possible but also highest performance" | Make tradeoff explicit: "If we pick option A (slow, cheap), impact is X. Option B (fast, expensive) is Y." |
| **Vague acceptance criteria** | "It should be user-friendly" | STOP. This is not a constraint, it's a wish. Ask for testable outcomes |
| **No mention of data** | Feature design with zero mention of data model | Ask: "What's the core data entity? How much volume?" |
| **API gaps** | "Works with our CRM" but no API docs provided | Ask: "Can you share API docs or sandbox access?" |
| **Localization skipped** | "Mostly English" | Probe: "Will any users see non-English? Date/currency formatting matter?" |

---

## Discovery Checklist

Before moving to Phase 2, verify you have:

- [ ] Scope explicitly bounded (what's IN, what's OUT)
- [ ] Timeline with hard date or sprint count
- [ ] Tech stack locked (language, DB, cloud, framework)
- [ ] Budget statement (time, money, token limits)
- [ ] Security/compliance checklist (none vs. some vs. regulated)
- [ ] Delivery format confirmed (DOCX, markdown, both)
- [ ] Audience defined (internal, public, enterprise)
- [ ] Existing system integration points identified (or confirmed it's greenfield)
- [ ] Stakeholder sign-off path clear (who approves what)
- [ ] Any "red flags" resolved or explicitly accepted

**If any are missing, ask before Phase 2.**
