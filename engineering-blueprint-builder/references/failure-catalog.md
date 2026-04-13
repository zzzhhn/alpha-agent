# Failure Catalog — Alpha Core Project Learning Log

**Purpose:** Document every failure encountered during blueprint-builder development. Learn from mistakes and implement preventive rules.

---

## Failure Log

| ID | What Happened | Root Cause | Impact | Fix Applied | Preventive Rule |
|----|---------------|-----------|--------|-------------|-----------------|
| F001 | Empty Table of Contents in final DOCX | docx-js field code generation didn't execute; TOC bookmark references were stale | 1.5 hours wasted; user received doc with blank TOC page | Switched to manual TOC construction with InternalHyperlink + PositionalTab + Bookmark; no field codes | Never rely on DOCX field codes (TOC, date fields). Always build TOC manually with bookmarks and internal hyperlinks. Field codes require user action to update. |
| F002 | .docx won't open in Word on macOS | Python post-processing with zipfile repack corrupted ZIP internal structure; CRC32 checksums mismatch | User had to file support ticket; 2-hour investigation | Removed all Python post-processing. Assembly now 100% complete in Node.js. No repacking after Packer.toFile(). | Never post-process DOCX with Python zipfile. docx library's Packer.toFile() is final. Any repack is fatal. Design content correctly the first time. |
| F003 | Acceptance criteria too vague | Wrote "system should handle errors gracefully" without testable boundary | Engineer built error handler that returned 500 status; PM rejected because not "graceful" | Rewrote 8 acceptance criteria with falsifiability test: concrete input/output, measurable outcomes, no subjective terms | Every acceptance criterion must be testable in one sentence. If it contains "should," "properly," "gracefully," "normally," rewrite it. Include example test case. |
| F004 | Late constraint discovery | User added 4 budget/scope constraints after v1.0 delivered (security audit, 2-language support, mobile optimization, GDPR compliance) | Forced v1.1 redesign; 2-day rework | Added "Constraint Summary" template to Phase 1; forced user sign-off before moving to Phase 2 | Never start Phase 2 without explicit constraint matrix. Include it in generated document. Get sign-off: "User acknowledges these are complete constraints." |
| F005 | npm install fails with EACCES | Used global npm install (-g flag); user ran without sudo; permission denied | 30 minutes troubleshooting; user thought package was broken | Documented npm init -y && npm install (local to project). All docx commands use ./node_modules/.bin/docx | Always use local npm install. Update onboarding to show `npm install` (never -g). For scripts, use npx or ./node_modules/.bin/. |
| F006 | Bookmark ID collisions | Generated bookmarks named "section1," "section2" across two modules; Word's BookmarkStart merging caused duplicate names | TOC hyperlinks jumped to wrong sections; user added bookmarks manually | Prefixed all bookmark IDs: module-0, module-1, architecture, appendices (guaranteed unique) | Bookmark IDs must be globally unique. Use format: [section]-[number] or [section]-[module_name]. Always validate uniqueness before assembly. |
| F007 | Context window exhaustion | Phase 3 spec included full JSON schemas + edge case tables for 8 modules; total token usage 78K | Model stopped mid-sentence; had to break into two responses | Split Phase 3 into two passes: core spec first, then data contracts/edge cases in separate turn | Track token budget per phase. Phase 3 is heaviest (~20K tokens per module). For 5+ modules, allocate 2 turns or use separate reference docs. |
| F008 | No wireframes until v2.0 | Engineer started coding without seeing visual design; built API that didn't match intended UI | 1 week of UI/API mismatch fixes; useless backend work | Added Phase 4 (Visuals) before Phase 5 (Assembly). Wireframes must be embedded in DOCX. | Wireframes are not optional. Generate before assembly. Use Pillow helper functions. Every module needs at least 1 wireframe showing happy path. |
| F009 | Ollama/Gemma references left in v1.1 | User changed LLM constraint mid-project (Ollama → OpenAI); old reference docs weren't updated | Blueprint still recommended local Ollama; user confused | Updated all reference docs. Added validation step: grep -r "ollama\|gemma" to catch leftover references | After constraint changes, audit all generated content. Add script to validate no deprecated tech references remain. |
| F010 | User impatience from repeated stops | Claude stopped 7 times to ask clarifying questions before Phase 2 (bilingual? scope? security? budget? delivery format?) | User feedback: "你怎么又停了?" (You stopped again?). Felt like friction | Batched Phase 1 questions into 3 mega-prompts covering 2-3 categories each. Added note: "I'll ask once, get full clarity, then move forward." | Minimize stops. Batch discovery questions into 3 major prompts max. Say upfront: "I'll ask 3 questions now, then we move fast." Build user confidence. |
| F011 | fix_bookmarks.py rmtree PermissionError | Cleanup script tried to delete temp directory while Word had file handle locked | Script crashed; temp files not cleaned up; 100MB disk bloat over 2 weeks | Removed aggressive cleanup. Now use mktemp for each run; system cleans up daily. Never force delete temp DOCX files. | Don't delete DOCX files in-script. They may be locked by OS or editor. Use temp directories with auto-expiry. Or manually delete after. |
| F012 | Chinese filename encoding issues | Generated file with name "blueprint_计划_2026-04-12.docx" on Linux; some tools couldn't read it | User couldn't download from web interface; filename showed garbled | Changed filename format to ASCII only: "blueprint_zh_2026-04-12.docx"; language in content, not filename | Filenames must be ASCII. Use language code prefix (en_, zh_, etc.) not unicode chars. Test cross-platform file handling. |
| F013 | Missing image altText fields | Embedded image with only altText.title set; Word validation showed error: description and name required | File opened but marked as "malformed" in Word online | Updated Image wrapper to require all three: altText.title, altText.description, altText.name (all same string ok) | All images must have complete altText object with all 3 fields. Validate before assembly. |
| F014 | Table formatting inconsistency | Some tables had ShadingType.CLEAR, others had ShadingType.NONE; DOCX corrupted | File wouldn't open in Google Docs | Standardized all table shading: never use NONE, always use CLEAR (or omit) | Table shading must be CLEAR only. No other types. Add validation rule: grep SHADING to ensure only one pattern used. |
| F015 | Page break in wrong place | Manual PageBreak after each module; some modules had 1 paragraph, wastes pages | Final doc was 150 pages instead of 80 | Removed hard page breaks. Used spacing-after rules instead. Only PageBreak between major sections (TOC, exec summary, modules, appendices) | Use PageBreak only between major document sections. Within modules, use paragraph spacing (spacing: { after: X }). Test on screen/print preview. |

---

## Failure Categories & Frequency

```
Document Format Issues (DOCX/PDF):     5 failures
Vague Specifications:                   2 failures
Architecture/Design Issues:             3 failures
Process/Workflow Issues:                3 failures
User Experience/Communication:          1 failure
Environment/Configuration:              2 failures
```

**Most Common Category:** Document format issues (DOCX assembly, field codes, post-processing).

**Highest Impact:** F004 (late constraints) and F009 (leftover references). Both could have been prevented with better validation.

---

## Preventive Rules (Summary)

### Phase 1: Discovery
1. Never start Phase 2 without signed-off constraint matrix
2. Explicitly ask: "Are these ALL constraints, or might you add more later?"
3. Document untouchable components separately
4. For budget: always ask about LLM token costs explicitly

### Phase 2: Exploration
1. Never skip searching for existing system docs
2. Validate tech stack matches Phase 1 constraints
3. Look for deprecated code that might resurface in blueprint

### Phase 3: Specification
1. Every acceptance criterion: pass falsifiability test
2. Include example test cases alongside each criterion
3. For edge cases: use standard checklist (stale data, API failure, NaN, mobile, empty, rate-limited, auth expired)
4. Track token usage; split into 2 turns if >40K tokens for single module

### Phase 4: Visuals
1. Every module gets at least 1 wireframe (no "we'll add visuals later")
2. All wireframes: standard sizes (1800x1000 or 1800x900)
3. Include sample data; never use placeholder text
4. Color palette defined once; use COLOR dict everywhere

### Phase 5: Assembly
1. ZIP integrity test before delivery
2. XML parsing test on all files
3. All images must have complete altText (3 fields)
4. All tables must use ShadingType.CLEAR only
5. Never use \n; use separate Paragraphs
6. Never use unicode bullets; use bullet property
7. Bookmarks must be unique (validate programmatically)
8. Test document opens in Word, Google Docs, PDF viewer

### Phase 6: Delivery
1. Run full validation pipeline (ZIP, XML, structure, bookmarks)
2. Never post-process DOCX with Python zipfile
3. Filenames must be ASCII (en_, zh_ prefixes, not unicode)
4. Generate PDF with LibreOffice only if explicitly requested
5. Present via computer:// links grouped by language

---

## Testing Checklist (Before Release)

- [ ] Constraint matrix signed off by user
- [ ] All acceptance criteria are falsifiable (have test case examples)
- [ ] All wireframes at correct dimensions
- [ ] All images embedded with complete altText
- [ ] Document opens in Word without corruption warning
- [ ] Document opens in Google Docs
- [ ] TOC bookmarks are clickable
- [ ] No \n characters in any Paragraph
- [ ] All tables have borders and consistent shading (CLEAR only)
- [ ] Chinese characters (if bilingual) render correctly
- [ ] File size reasonable (>100KB, <50MB)
- [ ] ZIP integrity verified (testzip() passes)
- [ ] XML well-formed (all .xml files parse)
- [ ] No leftover deprecated tech references (grep validated)
- [ ] Filename is ASCII-safe
- [ ] PDF generated without errors (if requested)

---

## Lessons Learned

1. **Document format is fragile.** Don't trust field codes, post-processing, or shortcuts. Assemble once, assemble right.

2. **Specifications must be testable.** "Correct" is not testable. "Returns 201 with subscription JSON and status='active'" is.

3. **Constraints leak.** Force Phase 1 sign-off. Assume user will add constraints later if you don't lock them down.

4. **Visuals matter early.** Engineers code to wireframes, not specs. Missing wireframes = wasted coding.

5. **User patience is finite.** Batch questions. Stop only when truly necessary. Move fast between phases.

6. **Validation is non-negotiable.** Test DOCX before delivery. Corrupt files destroy trust.

7. **Language-specific issues are real.** Test Chinese filenames, unicode in content, encoding edge cases. Don't assume ASCII-only.

8. **Bookmarks are error-prone.** Validate uniqueness programmatically. Don't rely on manual checks.

---

## Failure Report Template (For Future)

When a new failure occurs, document it:

```
**Failure ID:** F[next]
**What Happened:** [1-2 sentence description of symptom]
**Root Cause:** [Why it happened; technical details]
**Impact:** [User-facing consequences; time/effort lost]
**Fix Applied:** [What we changed to solve it]
**Preventive Rule:** [One rule to prevent recurrence]
```

Then add to the failure log table, update the checklist, and communicate to the team.
