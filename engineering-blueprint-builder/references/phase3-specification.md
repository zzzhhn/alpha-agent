# Phase 3: Specification — PRD-Level Module Specification Protocol

**Purpose:** Create engineer-ready specifications. Every module has clear responsibilities, testable acceptance criteria, and defined data contracts.

---

## Module Specification Template

Create one of these per module. Replace `[ModuleName]` with actual name.

```markdown
# [ModuleName] Module Specification

## 1. Design Rationale

**Purpose:** One sentence describing why this module exists and what problem it solves.

Example: "The Billing module manages subscription lifecycle, calculates charges, and persists invoices to ensure accurate financial records and audit trails."

**Key Design Decisions:**
- Decision A: Rationale (why not alternative B)
- Decision B: Rationale (why not alternative C)

Example:
- Subscriptions are immutable once created (allows audit trail, prevents charge disputes)
- Invoices generated async via job queue (prevents blocking request; can retry on failure)
- All calculations in UTC (standardizes across time zones)

**Assumptions:**
- Assumption 1
- Assumption 2

Example:
- Payment processor (Stripe) is authoritative for charge status
- One user can have multiple subscriptions simultaneously
- Refunds are manual (not automatic on cancellation)

---

## 2. Component Inventory

| Component | Type | Responsibility | Status |
|-----------|------|-----------------|--------|
| SubscriptionService | Class | Create/read/update subscriptions; persist to DB | New |
| InvoiceCalculator | Class | Given subscription, compute charges (tax, prorations) | New |
| StripeWebhookHandler | Class | Ingest Stripe events; update DB state accordingly | New |
| POST /api/subscriptions | Endpoint | Create new subscription; call SubscriptionService | New |
| POST /api/subscriptions/{id}/cancel | Endpoint | Cancel subscription; emit event to event bus | Existing (extend) |
| GET /api/invoices | Endpoint | List invoices with filters (date, user, status) | New |

**Legend:** New = write from scratch. Existing (extend) = modify existing code. Existing (no change) = leave as-is.

---

## 3. Component Specs

For each component in inventory, include:

### [ComponentName]

**Type:** [Class, Endpoint, Schema, Job]

**Input:**
```
{
  "field1": "type and description",
  "field2": "type and description"
}
```

**Output:**
```
{
  "result": "type and description",
  "metadata": {
    "created_at": "ISO 8601 timestamp"
  }
}
```

**Behavior:**
- Step 1: Description
- Step 2: Description
- Step 3: Description

**Error Handling:**
- Condition: Error code, message, and recovery action

**Example:**

### SubscriptionService.create()

**Type:** Class Method

**Input:**
```
{
  "user_id": "UUID of customer",
  "plan_id": "SKU reference to pricing tier",
  "billing_cycle_days": "30 or 365",
  "start_date": "ISO 8601, defaults to today"
}
```

**Output:**
```
{
  "id": "Generated UUID",
  "user_id": "From input",
  "plan_id": "From input",
  "status": "active",
  "started_at": "ISO 8601",
  "next_charge_at": "ISO 8601, calculated"
}
```

**Behavior:**
1. Validate plan exists in database
2. Validate user account is in good standing (not flagged for fraud)
3. Check for duplicate active subscription (same user + plan)
4. Generate UUID for subscription
5. Insert into database with status='active'
6. Emit 'subscription.created' event to event bus
7. Return subscription object

**Error Handling:**
- Plan not found: Return 404, "Plan {plan_id} does not exist"
- User flagged for fraud: Return 402, "Account review required; contact support"
- Duplicate active subscription: Return 409, "User already has active {plan_id} subscription"
- Database error: Return 500, "Subscription creation failed; try again in 60 seconds"

---

## 4. User Interaction Flows

**Format:** Step-by-step from user action to final state.

### Example: Cancel Subscription Flow

1. **User Action:** Clicks "Cancel Subscription" button in account settings
2. **Frontend:** GET /api/subscriptions/{id} to show confirmation dialog with:
   - Refund amount (prorated if mid-cycle)
   - Last invoice date
   - Warning: "Cancellation is immediate; no access after today"
3. **User Confirms:** Clicks "Confirm Cancellation"
4. **Frontend:** POST /api/subscriptions/{id}/cancel with reason (optional)
5. **Backend:** SubscriptionService.cancel():
   - Validate subscription exists
   - Calculate prorated refund if applicable
   - Update status to 'cancelled'
   - Set cancelled_at timestamp
   - Emit 'subscription.cancelled' event
6. **Event Handler:** RefundProcessor listens for 'subscription.cancelled':
   - If refund > $0: Call Stripe Refund API
   - If Stripe refund succeeds: Update invoice status to 'refunded'
   - If Stripe fails: Emit alert for manual processing
7. **Frontend:** Receives 200 OK; navigates to "Subscription Cancelled" confirmation page
8. **Final State:** Subscription status = 'cancelled', invoice refunded (or flagged), user has no active subscription

---

## 5. Data Contracts

**Format:** JSON Schema for each key data structure.

```json
{
  "name": "Subscription",
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier, generated on creation"
    },
    "user_id": {
      "type": "string",
      "format": "uuid",
      "description": "Foreign key to user table"
    },
    "plan_id": {
      "type": "string",
      "description": "References billing plan (e.g., 'plan_pro_annual')"
    },
    "status": {
      "type": "string",
      "enum": ["active", "paused", "cancelled"],
      "description": "Current state of subscription"
    },
    "billing_cycle_days": {
      "type": "integer",
      "minimum": 1,
      "description": "Billing period length (30, 365, etc.)"
    },
    "started_at": {
      "type": "string",
      "format": "date-time",
      "description": "Subscription activation time in UTC"
    },
    "cancelled_at": {
      "type": ["string", "null"],
      "format": "date-time",
      "description": "Cancellation time if applicable, null otherwise"
    },
    "next_charge_at": {
      "type": "string",
      "format": "date-time",
      "description": "Calculated next billing date, null if cancelled"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "Database insertion timestamp"
    }
  },
  "required": ["id", "user_id", "plan_id", "status", "started_at", "created_at"],
  "additionalProperties": false
}
```

---

## 6. Acceptance Criteria

### The Falsifiability Test

**Good acceptance criteria:**
- Are testable (can write a test case that passes or fails)
- Are observable (something measurable happens)
- Have clear success/failure boundary (not "about," "roughly," "around")

**Bad acceptance criteria:**
- "Works correctly" — too vague
- "Is performant" — no threshold
- "Handles errors gracefully" — what's "graceful"?
- "Displays normally" — which screen size? Which browser?

### BAD vs. GOOD Examples

#### Example 1: Subscription Creation

**BAD:**
```
When a user creates a subscription, the system should handle it properly.
```
(What is "properly"? How do you test this?)

**GOOD:**
```
When POST /api/subscriptions is called with valid plan_id, the system:
1. Creates a subscription with status='active'
2. Returns 201 Created with subscription JSON
3. Emits 'subscription.created' event within 100ms
4. Persists to database (verifiable with SELECT)
5. Rejects duplicate requests with 409 Conflict
```
(Testable: write 5 test cases, each checking one observable behavior)

---

#### Example 2: Refund Calculation

**BAD:**
```
Refund amount should be calculated accurately.
```
(What counts as "accurate"? ±$0.01? ±1%?)

**GOOD:**
```
When subscription is cancelled mid-cycle:
1. Refund = (daily_rate) × (days_remaining), rounded to nearest cent
2. Example: $365/year plan, 100 days remaining = $100.00 refund
3. Refund matches Stripe's proration logic (verify via test data)
4. Refund is issued within 24 hours of cancellation
5. Refund status is visible in /api/invoices/{id} with field refunded_amount
```

---

#### Example 3: API Response Time

**BAD:**
```
The API should be fast.
```
(What's "fast"? 1ms? 5s?)

**GOOD:**
```
POST /api/subscriptions must respond within 500ms (p95) for:
1. Valid request with existing plan
2. Measured from request received to response sent
3. Under load of 100 req/sec (simulated)
4. Excluding network latency (measured locally)
```

---

#### Example 4: Error Handling

**BAD:**
```
The system should handle errors.
```
(Which errors? How?)

**GOOD:**
```
When Stripe API is unavailable:
1. Return 503 Service Unavailable within 1 second
2. Include message: "Payment processor temporarily unavailable; retry in 60 seconds"
3. Emit alert to ops channel (PagerDuty)
4. Don't update subscription state (remain idempotent)
5. Log error with request_id for debugging
```

---

#### Example 5: Concurrent Requests

**BAD:**
```
The system should handle multiple users.
```
(2 users? 1000 users? Same action?)

**GOOD:**
```
When two users simultaneously POST /api/subscriptions with different plan_ids:
1. Both requests complete successfully
2. Both subscriptions are created (separate records)
3. No database constraint violations
4. Both receive 201 responses within 500ms
```

---

#### Example 6: Data Validation

**BAD:**
```
Billing cycle should be validated.
```
(What are valid values?)

**GOOD:**
```
POST /api/subscriptions with billing_cycle_days:
1. Accepts: 30, 365 (documented valid values)
2. Rejects: 0, -1, 999 with 400 Bad Request, "billing_cycle_days must be 30 or 365"
3. Rejects: "monthly", null with 400 Bad Request, "billing_cycle_days must be integer"
4. Rejects: missing field with 400 Bad Request, "billing_cycle_days required"
```

---

#### Example 7: Pagination

**BAD:**
```
The list endpoint should support pagination.
```
(Page size? Sort order? Cursor vs. offset?)

**GOOD:**
```
GET /api/invoices supports pagination:
1. Query params: page (1-indexed, default 1), limit (default 25, max 100)
2. Response includes: items[], total_count, has_next (boolean)
3. Example: ?page=2&limit=50 returns items 51-100
4. Sorted by created_at descending by default
5. Returns 400 Bad Request if page < 1 or limit > 100
```

---

#### Example 8: Timezone Handling

**BAD:**
```
Dates should be handled correctly.
```
(Which timezone?)

**GOOD:**
```
All timestamps in API responses:
1. Are in ISO 8601 format with UTC timezone (e.g., "2026-04-12T14:30:00Z")
2. Stored in database as UTC
3. Next charge calculations use UTC (billing happens at 00:00 UTC)
4. User's local timezone stored separately for UI display only
5. Midnight deadline for cancellations is "before 00:00 UTC"
```

---

## 7. Edge Cases

**Always consider:**

| Category | Examples | How to Test |
|----------|----------|------------|
| **Stale Data** | User cancels, then tries to charge same subscription | Request charges on cancelled sub; verify 409 returned |
| **API Failure** | Payment processor timeout mid-request | Mock Stripe timeout; verify system remains consistent |
| **NaN / Infinity** | Division by zero in calculation (e.g., $0 plan) | Test with 0 billing_cycle_days; verify validation rejects it |
| **Narrow Viewport** | Mobile phone at 320px width | Render wireframe at 320px; verify readability |
| **Empty State** | User has no subscriptions | GET /api/subscriptions returns 200 with empty items[] |
| **Rate Limited** | Stripe API rate limits are hit | Return 429 with Retry-After header; exponential backoff in client |
| **Auth Expired** | User's JWT expires mid-operation | Return 401; client redirects to login |
| **Race Condition** | Two cancellation requests simultaneously | Second request returns 409 "Already cancelled" |
| **Boundary Values** | Refund amount exactly $0.00 | Verify issued without error; appears as "$0.00 refund" |
| **Locale Mismatch** | User in France, plan in USD | Conversion applied; documented in invoice |

---

## 8. Module Dependencies

List external systems this module depends on:

- [ ] Payment Processor: Stripe API (https://stripe.com/docs)
- [ ] Message Queue: Redis PubSub for event bus
- [ ] Database: PostgreSQL 14+
- [ ] Logging: CloudWatch (AWS) or Datadog

For each dependency, document:
- **What it does:** Role in this module
- **Fallback behavior:** What happens if it fails
- **SLA:** Expected availability (99.9%? 99.99%?)
- **Retry policy:** Exponential backoff with max retries

---

## Specification Checklist

Before Phase 4 (Visuals), verify:

- [ ] Design rationale includes key decisions and assumptions
- [ ] Component inventory complete (all new, extend, no-change items listed)
- [ ] All components have detailed specs (input, output, behavior)
- [ ] User interaction flows documented (happy path + error paths)
- [ ] Data contracts in JSON Schema format
- [ ] Every acceptance criterion is falsifiable (testable)
- [ ] Edge cases identified and mapped to test cases
- [ ] External dependencies documented
- [ ] No vague language ("correctly," "properly," "should work")

**If any are incomplete, rework before Phase 4.**
