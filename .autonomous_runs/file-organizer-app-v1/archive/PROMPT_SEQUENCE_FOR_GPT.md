# Sequenced GPT Prompts for FileOrganizer Project

**Purpose**: Break down research into focused, sequential prompts instead of one massive request
**Created**: 2025-11-26

---

## Prompt 1: Market Analysis & Competitive Advantage

**Objective**: Analyze existing solutions and identify what makes our project unique

**Attach**:
- `REF_01_EXISTING_SOLUTIONS_COMPILED.md`

**Prompt**:
```
I'm building a context-aware file organizer desktop application. I've compiled research on 16 existing solutions (attached).

Please analyze:

1. **Strengths Matrix**: For each solution, list its top 3 strengths
2. **Weakness Matrix**: For each solution, list its top 3 limitations
3. **Market Gaps**: Based on the compiled research, identify gaps that NO existing solution addresses well
4. **Consolidation Opportunity**: If we were to combine the best features from multiple solutions, what would that look like?
5. **Competitive Advantage**: Given the gaps and consolidation opportunities, what 5-7 features would make our solution uniquely valuable?

Focus your analysis on:
- Privacy vs accuracy trade-offs
- Cross-platform support
- Legal case management needs
- Accessibility for non-technical users
- Local vs cloud processing

Please provide specific recommendations, not generic statements.
```

**Expected Output**:
- Strengths/weakness tables
- 5-10 critical market gaps
- Feature consolidation recommendation
- 5-7 unique value propositions for our app

---

## Prompt 2: Technology Stack Recommendation

**Objective**: Get specific technology choices with justifications

**Attach**:
- `REF_01_EXISTING_SOLUTIONS_COMPILED.md` (for what others use)
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md` (for our specific needs)

**Prompt**:
```
Based on the market research (REF_01) and user requirements (REF_02), recommend a technology stack for a cross-platform desktop file organizer.

Requirements:
- Cross-platform (Windows, macOS, Linux preferred)
- Local-first AI processing (with cloud opt-in)
- OCR for images and PDFs
- LLM for context understanding
- Accessible UI for elderly users
- Must handle sensitive legal documents (privacy critical)

Please provide recommendations for:

1. **Desktop Framework**:
   - Options: Electron vs Tauri vs Qt vs other
   - Pros/cons table for each
   - Your recommendation with justification

2. **OCR Engine**:
   - Options: Tesseract vs cloud (Azure/Google) vs LLM vision (GPT-4 Vision)
   - Accuracy vs privacy vs cost trade-off
   - Your recommendation (can be hybrid approach)

3. **LLM for Context Understanding**:
   - Local options: Llama 3.2, Mistral, Phi-3
   - Cloud options: GPT-4o, Claude 3.5 Sonnet
   - Can local models (3B-7B) handle legal document context understanding?
   - Your recommendation

4. **Database for Metadata**:
   - Options: SQLite vs DuckDB vs JSON files
   - Your recommendation for file metadata, analysis results, user prefs

5. **Additional Libraries**:
   - PDF text extraction
   - Image processing
   - File operations (cross-platform path handling)
   - UI components

Please be specific: version numbers, library names, concrete choices.
```

**Expected Output**:
- Specific framework recommendation (e.g., "Tauri 2.0")
- OCR strategy (e.g., "Tesseract 5.x for basic, fallback to GPT-4 Vision for complex")
- LLM choice (e.g., "Llama 3.2 7B for categorization, GPT-4o for legal context")
- Database choice
- List of specific libraries with versions

---

## Prompt 3: Architecture Design

**Objective**: Get high-level architecture and component breakdown

**Attach**:
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md` (for multi-pass requirement)
- Output from Prompt 2 (technology stack decisions)

**Prompt**:
```
Based on the technology stack recommendations from our previous discussion, design a high-level architecture for the FileOrganizer desktop app.

Requirements (from REF_02):
- Multi-pass architecture: Discovery → Analysis → Review → Execution → Validation
- Human checkpoints at critical stages
- Rollback capability for all operations
- Cross-reference tracking
- Pattern validation

Using the tech stack we decided on [INSERT PROMPT 2 RESULTS], please provide:

1. **Component Diagram** (text description):
   - Core components and their responsibilities
   - How they interact
   - Data flow between components

2. **Module Breakdown**:
   - Scanner Module (file discovery)
   - OCR Module (text extraction)
   - Analyzer Module (context understanding)
   - Categorizer Module (use case detection + file classification)
   - Renamer Module (pattern-based naming)
   - Organizer Module (folder structure creation)
   - Validator Module (integrity checks)
   - UI Module (wizard flow)

   For each module: inputs, outputs, key logic, dependencies

3. **Data Models**:
   - File metadata structure
   - Analysis result structure
   - User preferences structure
   - Operation log structure (for rollback)

4. **Critical Workflows**:
   - User initiates organization → final result (step-by-step)
   - Error handling: what happens when OCR fails? LLM errors? User cancels?
   - Rollback workflow

Please provide enough detail for an implementation plan but avoid code-level specifics.
```

**Expected Output**:
- Component diagram (text/ASCII)
- 8-10 module descriptions with interfaces
- Data model schemas
- 3-5 workflow diagrams (text)

---

## Prompt 4: OCR Quality & Local LLM Capability Research

**Objective**: Get specific research on OCR accuracy and local LLM sufficiency

**Attach**:
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md` (for legal case examples)

**Prompt**:
```
I need specific research on two technical questions:

**Question 1: OCR Accuracy for Legal Documents**

Our use case includes:
- Scanned PDFs (varying quality, some low-res faxes)
- Photos of computer screens (text messages)
- Handwritten notes on forms
- Mixed-format documents (text + tables + handwriting)

Please research:
1. Tesseract 5.x accuracy on these document types (benchmark data if available)
2. Cloud OCR (Azure AI Vision, Google Cloud Vision) accuracy comparison
3. LLM Vision (GPT-4 Vision, Claude 3.5 Sonnet Vision) for OCR - is it reliable?
4. Recommendation: What's the minimum acceptable OCR engine for legal case management?

**Question 2: Local LLM Context Understanding**

Our requirement: Detect that a text message screenshot is "evidence of employer misconduct" (not just "text message").

Please research:
1. Can Llama 3.2 3B/7B handle this level of context understanding?
2. What about Mistral 7B or Phi-3?
3. Benchmark data on legal document understanding (if available)
4. Recommendation: What's the minimum model size for legal context accuracy?

If possible, test with sample prompts:
- Input: "Text message: 'Boss: Tell worker to report as off-duty injury'"
- Expected: "Evidence of employer misconduct, instructing false reporting"
- Can 3B/7B models produce this level of inference?

Provide specific data/benchmarks, not speculation.
```

**Expected Output**:
- OCR accuracy table (Tesseract vs cloud vs LLM vision)
- Local LLM capability assessment (3B vs 7B vs 13B)
- Specific recommendations with confidence levels
- Benchmark citations if available

---

## Prompt 5: UI/UX Design for Elderly Users

**Objective**: Design accessible wizard flow

**Attach**:
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md` (for accessibility requirement)

**Prompt**:
```
Design a wizard-style UI for an elderly-friendly file organizer app.

**Constraint**: User should NOT have to type complex prompts. Use dropdowns, buttons, previews.

**Wizard Flow** (propose structure):
1. Welcome screen → Select folder to organize
2. Use case detection → AI suggests (legal/personal/business), user confirms or overrides
3. Category review → AI proposes categories, user refines via dropdown
4. Naming preview → Show 5-10 example renames, user approves or adjusts pattern
5. Folder structure preview → Show tree view, user confirms
6. Execution → Progress bar, cancelable
7. Validation report → Summary of changes, rollback option if unhappy

For each step, describe:
- What user sees
- What actions they can take (button clicks, dropdown selections)
- How to minimize cognitive load
- Error handling (what if AI can't confidently categorize?)

Also address:
- How to handle ambiguous files (AI unsure of category)
- How to present confidence scores (visual? color-coded?)
- How to explain AI decisions without overwhelming user

Provide specific UI mockup descriptions (text is fine, no need for images).
```

**Expected Output**:
- 7-step wizard flow with screen descriptions
- Interaction patterns for each step
- Ambiguity handling strategy
- Confidence visualization approach

---

## Prompt 6: Build Plan Validation & Phase Breakdown

**Objective**: Validate that 50 phases is realistic and get tier structure

**Attach**:
- Outputs from Prompts 2, 3, 4, 5 (tech stack, architecture, research, UI)
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md` (for must-have features)

**Prompt**:
```
Based on our technology stack, architecture, and UI design decisions, create a build plan for Autopack (autonomous build system).

**Autopack Context**: Each "phase" is a single unit of work (e.g., "Implement OCR module" or "Create wizard step 1 UI").

**Target**: ~50 phases organized into 5-6 tiers (sequential groups of phases)

**Requirements** (from REF_02):
- Must-Have: Multi-pass analysis, OCR, context understanding, renaming, folder structure, index generation, timeline (legal), cross-reference validation, rollback, checkpoints
- Should-Have: Duplicate detection, bulk preview, confidence scores
- Nice-to-Have (defer): Semantic search, continuous monitoring, cloud storage integration

Using the architecture from Prompt 3, break down into:

**Tier 1: Core Infrastructure** (~12 phases)
- Desktop app scaffolding
- File scanner
- Database setup
- Logging/error handling

**Tier 2: AI Processing** (~15 phases)
- OCR integration
- LLM client
- Document classifier
- Entity extraction
- Context analyzer
- Categorizer

**Tier 3: Organization Logic** (~10 phases)
- Renaming engine
- Folder structure generator
- File mover
- Cross-reference tracker

**Tier 4: UI & UX** (~8 phases)
- Wizard screens
- Preview components
- Progress tracking
- Validation report

**Tier 5: Index & Summary** (~5 phases)
- Excel index generator
- Case summary (legal)
- Timeline builder
- Cross-reference validator

For each tier, list specific phases with:
- Phase name
- Description (1-2 sentences)
- Estimated complexity (low/medium/high)
- Dependencies (which prior phases must complete first)

Validate:
1. Is 50 phases realistic for this feature set?
2. Should any tiers be split or merged?
3. What's the critical path (longest dependency chain)?
```

**Expected Output**:
- 5-6 tiers with phase breakdown (~50 total)
- Each phase: name, description, complexity, dependencies
- Critical path analysis
- Feasibility assessment

---

## Prompt 7: Risk Analysis & Mitigation

**Objective**: Identify risks and mitigation strategies

**Attach**:
- All prior outputs
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md` (for known failure modes)

**Prompt**:
```
Based on lessons learned (REF_02 section on 9 critical failures) and our proposed architecture, identify risks and mitigation strategies.

**Known Failure Modes** (from prior implementation):
1. Lack of holistic review (AI didn't analyze full structure first)
2. Semantic naming failures
3. Category logic errors
4. Incomplete cross-reference updates
5. Duplicate detection gaps
6. Pattern conformity blind spots
7. No preview for bulk operations
8. Over-detailed communication
9. Unicode handling (Windows console)

**New Risks** (given our design):
- What could go wrong with local LLM processing?
- What if OCR fails on critical documents?
- What if user cancels mid-execution?
- Cross-platform file operation bugs?
- Privacy leaks if cloud opt-in enabled?

For each risk:
1. **Risk Description**: What could go wrong?
2. **Likelihood**: Low/Medium/High
3. **Impact**: Low/Medium/High
4. **Mitigation Strategy**: How to prevent or handle it?
5. **Contingency Plan**: If it happens anyway, what's plan B?

Prioritize top 10 risks by (Likelihood × Impact).
```

**Expected Output**:
- 10-15 risks with likelihood/impact scores
- Mitigation strategy for each
- Contingency plans
- Prioritized list

---

## Prompt 8: Success Criteria & Metrics

**Objective**: Define measurable success

**Attach**:
- `REF_02_USER_REQUIREMENTS_AND_LESSONS.md`

**Prompt**:
```
Define success criteria and metrics for the FileOrganizer app.

**Context**: We need to know if the app is successful after Phase 1 build.

Please define:

1. **Functional Metrics**:
   - Categorization accuracy (how to measure?)
   - OCR accuracy (acceptable threshold?)
   - Processing speed (files per minute?)
   - Cross-platform compatibility (how to validate?)

2. **Quality Metrics**:
   - Naming consistency (100% pattern conformity?)
   - Reference integrity (0 broken links?)
   - Duplicate detection (precision/recall targets?)

3. **User Experience Metrics**:
   - Time savings vs manual organization (target: 80% reduction?)
   - User confidence in AI proposals (survey question?)
   - Error recovery success rate (rollback works 100%?)

4. **Acceptance Criteria** (go/no-go for v1.0 release):
   - What must work for this to be useful?
   - What's acceptable to defer to v1.1?

5. **Testing Plan**:
   - How to test with real legal case files (sample data)?
   - How to test cross-platform (CI/CD setup?)
   - How to test with elderly users (usability study?)?

Provide specific, measurable criteria (not vague "works well").
```

**Expected Output**:
- 10-15 measurable metrics with targets
- Acceptance criteria for v1.0
- Testing plan outline

---

## Summary: Prompt Sequence

| Prompt | Focus | Attach | Expected Time | Output |
|--------|-------|--------|---------------|--------|
| **1** | Market analysis | REF_01 | 10-15 min | Gap analysis, competitive advantage |
| **2** | Tech stack | REF_01, REF_02 | 15-20 min | Specific technology choices |
| **3** | Architecture | REF_02, Prompt 2 output | 20-30 min | Component diagram, modules, workflows |
| **4** | OCR & LLM research | REF_02 | 30-45 min | Benchmarks, recommendations |
| **5** | UI/UX design | REF_02 | 15-20 min | Wizard flow, screen descriptions |
| **6** | Build plan | REF_02, all prior outputs | 20-30 min | 50-phase breakdown, tier structure |
| **7** | Risk analysis | REF_02, all prior outputs | 15-20 min | Risk matrix, mitigation strategies |
| **8** | Success criteria | REF_02 | 10-15 min | Metrics, acceptance criteria |

**Total Estimated Time**: 2-3 hours of GPT interaction (spread over multiple sessions if needed)

**Workflow**:
1. Send Prompt 1 → Wait for response
2. Review response, then send Prompt 2 (attach Prompt 1 output if needed)
3. Continue sequentially
4. After Prompt 8, compile all outputs into final BUILD_PLAN

**Benefits of Sequential Approach**:
- GPT focuses on one topic at a time (deeper analysis)
- You can review and redirect after each prompt
- Easier to digest outputs in chunks
- Can pause and resume if needed
- More token-efficient (no redundant re-analysis)

---

**End of Prompt Sequence Guide**
