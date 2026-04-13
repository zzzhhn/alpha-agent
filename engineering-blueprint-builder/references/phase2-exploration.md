# Phase 2: Exploration — Codebase Assessment Protocol

**Purpose:** Understand the current system before proposing changes. Every design decision must be grounded in what exists.

---

## File Pattern Search

These glob patterns uncover the codebase structure. Run them in order:

### Tier 1: Project Root (Always run)
```
README*, CONTRIBUTING*, package.json, pyproject.toml, requirements.txt, 
setup.py, Cargo.toml, go.mod, composer.json, .env.example
```

**What you're looking for:**
- Project name, purpose, dependencies
- Build/run commands
- Contributing guidelines (hints at architecture)
- Environment variable names (config shape)

### Tier 2: Source Code Structure
```
src/**, lib/**, app/**, src/**, backend/**, frontend/**
```

**Glob specifics:**
```
src/**/*.py, src/**/*.js, src/**/*.ts, src/**/*.go, src/**/*.rs
lib/**, app/**, backend/**, frontend/**
```

### Tier 3: Configuration & Tooling
```
config/*, scripts/*, .github/workflows/*, Makefile, docker-compose.yml, 
k8s/**, terraform/**, .eslintrc*, tsconfig.json, pytest.ini, 
.gitignore, .env*
```

**What you're looking for:**
- Deployment pipeline (CI/CD)
- Environment config (dev, staging, prod)
- Infrastructure as code (cloud shape)
- Linting/testing rules (quality gates)

### Tier 4: API & Data Contracts
```
api/**, **/openapi.yml, **/swagger.json, **/schema.sql, 
**/models.py, **/types.ts, **/dto.go, database/migrations/**
```

**What you're looking for:**
- API endpoints (REST, GraphQL, gRPC)
- Data schema (tables, fields, relationships)
- Type definitions (contracts)
- Migration history (version tracking)

### Tier 5: Tests & Documentation
```
**/__tests__/**, **/test_*.py, **/*.test.js, **/tests/**, 
docs/**, **/*.md (excluding node_modules)
```

**What you're looking for:**
- Test coverage (what's tested, what isn't)
- Doc structure (where knowledge lives)
- Architecture decisions (ADRs, design docs)

---

## Module Maturity Assessment

For each module/service, answer these to gauge % complete:

### 1. API Endpoints (40%)
**Check:**
- Are endpoints documented?
- Do they have request/response examples?
- Are error codes defined?
- Are they tested?

**Scoring:**
- 0%: No endpoints documented or inconsistent
- 50%: Some endpoints documented, partial examples
- 100%: Full OpenAPI/GraphQL schema, all responses defined

### 2. Tests (25%)
**Check:**
- Unit test coverage (use pytest --cov or jest --coverage output)
- Integration test coverage (API tests)
- Are edge cases tested? (empty state, errors, concurrency)

**Scoring:**
- 0%: No tests
- 50%: Some unit tests, few integration tests
- 100%: 80%+ coverage, integration tests, edge cases covered

### 3. Data Contracts (20%)
**Check:**
- Is database schema defined?
- Are fields typed?
- Are constraints documented (nullable, unique, foreign keys)?
- Are migrations tracked?

**Scoring:**
- 0%: Ad-hoc schema, no migrations
- 50%: Schema defined, inconsistent migrations
- 100%: Versioned schema, clear migrations, constraints documented

### 4. UI Components (15%)
**Check (if applicable):**
- Are components reusable (library vs. one-off)?
- Do they have prop documentation?
- Do they cover happy path + error states?
- Are they responsive?

**Scoring:**
- 0%: Inline JSX, no reusable components
- 50%: Some shared components, inconsistent documentation
- 100%: Component library with Storybook or equivalent

---

## Current State Assessment Template

Include this in Phase 2 output:

```markdown
## Current State Assessment

### 1. Tech Stack
- **Language(s):** [e.g., Python 3.11, Node.js 20]
- **Frameworks:** [e.g., FastAPI, React 18]
- **Databases:** [e.g., PostgreSQL 14, Redis]
- **Hosting:** [e.g., Docker on EC2, Vercel, Fly.io]
- **CI/CD:** [e.g., GitHub Actions, CircleCI]

### 2. Project Structure
```
project-root/
├── backend/          [Python, FastAPI, 3 modules]
├── frontend/         [React, TypeScript, SSR]
├── infra/           [Terraform for AWS]
└── docs/            [API docs, architecture]
```

### 3. Module Maturity

| Module | API Endpoints | Tests | Data Contracts | UI Components | Overall |
|--------|---------------|-------|-----------------|---------------|---------|
| Auth | 100% | 80% | 100% | N/A | 93% |
| Billing | 60% | 40% | 70% | N/A | 57% |
| Reports | 50% | 20% | 40% | 70% | 45% |

### 4. Key Gaps
- [ ] Billing module has only 3 tests; refund flow untested
- [ ] Reports API inconsistent with auth API patterns
- [ ] No integration tests between modules
- [ ] UI components missing error state variants

### 5. Known Tech Debt
- Monolithic Node.js backend (should split into services)
- No async task queue (blocking requests on PDF generation)
- Test fixtures outdated (test data doesn't match schema)
```

---

## Identifying Tech Stack & Dependencies

### For Python projects:
```
requirements.txt, setup.py, pyproject.toml, poetry.lock, pipenv
```
**Extract:** framework (Django/FastAPI/Flask), ORM (SQLAlchemy/Django ORM), testing (pytest/unittest), async (asyncio/Celery)

**Check:** 
```
pip show [package] | grep Version
```

### For Node.js projects:
```
package.json, package-lock.json, yarn.lock, pnpm-lock.yaml
```
**Extract:** framework (Express/Next/Fastify), ORM (Prisma/Sequelize/TypeORM), testing (Jest/Mocha), bundler (Webpack/Vite)

### For Go projects:
```
go.mod, go.sum
```
**Extract:** web framework (Gin/Echo/Fiber), ORM (GORM/sqlc), testing patterns

### For Rust projects:
```
Cargo.toml, Cargo.lock
```
**Extract:** web framework (Actix/Axum/Rocket), async runtime (Tokio), ORM (SeaORM/Diesel)

### For frontend:
```
package.json, tsconfig.json, .eslintrc*, webpack.config.js, vite.config.js
```
**Extract:** framework (React/Vue/Svelte), state management (Redux/Zustand/Jotai), styling (Tailwind/styled-components)

---

## Finding What NOT to Change

**Ask user explicitly:**
"Are there any parts of the system I should NOT redesign, even if the blueprint suggests improvements?"

**Then search for user's answers in:**
- Comments like `# DO NOT REFACTOR` or `// STABLE API`
- Version pinning (old library intentionally locked)
- Feature flags that are hardcoded (indicates stability requirement)
- Documented integration contracts (if external systems depend on it)

**Document these clearly:**
```markdown
## Untouchable Components
- [ ] Auth module API must remain 100% compatible (external customers integrate)
- [ ] Database schema must not drop fields (backward compat with v1.2 clients)
- [ ] Billing calculation logic (audited by accountants)
```

---

## Codebase Exploration Checklist

Before Phase 3, verify:

- [ ] All tier 1-5 file patterns searched and categorized
- [ ] Tech stack documented (language, framework, DB, cloud)
- [ ] Module maturity assessed (% complete for each)
- [ ] Key gaps identified (missing tests, incomplete APIs)
- [ ] Existing code patterns observed (naming, structure, error handling)
- [ ] Dependencies understood (internal vs. external, version constraints)
- [ ] Untouchable components identified
- [ ] Any deprecated or planned-to-remove code noted
- [ ] Performance bottlenecks or known issues documented

**If exploration incomplete, go back before Phase 3.**
