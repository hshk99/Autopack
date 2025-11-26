# Autopack Project Initialization Template

**Version**: 1.0
**Created**: 2025-11-26
**Purpose**: Standardized template for initiating new Autopack autonomous builds

---

## Template Usage

When user says: "I want to build [APPLICATION] with [FEATURES]..."

Follow these steps **automatically**:

---

## Step 1: Create Build Branch

```bash
git checkout -b build/[project-name]-v1
```

**Naming Convention**: `build/[project-slug]-v[version]`
- Examples: `build/file-organizer-app-v1`, `build/task-tracker-v1`, `build/api-gateway-v1`

---

## Step 2: Gather Context

### 2.1 Read Relevant Documentation

If user mentions existing work, read:
- Limitation/improvement documents
- Prior implementation notes
- Configuration files
- Prompts/templates from previous work

**Example**:
```
User: "Build on top of C:\path\to\project"
→ Read: C:\path\to\project\CURRENT_LIMITATIONS.md
→ Read: C:\path\to\project\*.md
→ Glob: C:\path\to\project/**/*prompt*
```

### 2.2 Search for Existing Solutions

Run web searches for:
1. `[application type] desktop application AI-powered 2025`
2. `[use case] automatic [key feature] open source`
3. `github [keywords] AI [technology]`

**Example**:
```
Application: File organizer
→ Search: "intelligent file organizer desktop application automatic context-aware 2025"
→ Search: "AI file organization [domain] documents timeline"
→ Search: "github AI file organizer context-aware OCR document understanding 2025"
```

### 2.3 Search GitHub Repositories

Look for:
- Open source implementations
- Relevant libraries/frameworks
- Similar projects to learn from
- Avoid reinventing the wheel

---

## Step 3: Create Research Report for GPT

Generate comprehensive report in `.autonomous_runs/[project-name]-v1/GPT_RESEARCH_REQUEST.md`

### Report Structure

#### Part 1: Executive Summary
- What we're building (1-2 paragraphs)
- Core functionality (bullet points)
- Key differentiators from existing solutions

#### Part 2: Detailed Requirements
- Must-have features
- Should-have features
- Nice-to-have features (defer to Phase 2)
- Use cases and personas

#### Part 3: Known Challenges
- Lessons from prior implementations (if any)
- Technical challenges anticipated
- UX/accessibility considerations
- Cross-platform requirements

#### Part 4: Research Findings
- Existing solutions (open source + commercial)
- GitHub projects reviewed
- Market analysis
- Gaps in existing solutions

#### Part 5: Proposed Architecture
- Technology stack options (with trade-offs)
- Component breakdown
- Data flow diagram (text description)
- Database/storage considerations

#### Part 6: Critical Design Decisions
For each major decision:
- Options (A, B, C...)
- Pros/cons table
- Trade-offs
- **GPT Question**: Request input on best choice

**Example**:
```markdown
### Decision 1: Desktop Framework

**Options**:
| Framework | Pros | Cons |
|-----------|------|------|
| Electron | Cross-platform, easy UI, rich ecosystem | Heavy memory, slow startup |
| Tauri | Lightweight, fast, secure | Smaller ecosystem, steeper curve |
| Qt | Native performance, mature | Complex, licensing issues |

**GPT Question**: Which framework best balances cross-platform support, performance, and developer experience for [use case]?
```

#### Part 7: Research Gaps
List specific research questions for GPT:
- "Research Gap 1: [Topic]"
  - **Question**: [Specific question]
  - **Request**: [What GPT should investigate]
- "Research Gap 2: [Topic]"
  - ...

**Minimum 5 research gaps**, covering:
- Technology choices
- Best practices
- User studies/preferences
- Performance benchmarks
- Security/privacy considerations

#### Part 8: Alternative Approaches
Brainstorm 3-5 alternative implementation strategies:
- Approach 1: [Name]
  - Pros:
  - Cons:
  - **GPT Question**: Is this safer for Phase 1?

#### Part 9: Success Criteria
Define measurable success metrics:
- Functional (accuracy, speed, cross-platform)
- Quality (consistency, integrity, reliability)
- User experience (time savings, confidence, error recovery)

#### Part 10: Risks and Mitigation
List 5+ risks with mitigation strategies:
- Risk 1: [Description]
  - **Mitigation**: [Strategy]
- **GPT Question**: What other risks are we missing?

#### Part 11: Questions for GPT
Numbered list (20+ questions) across:
- Architecture & Technology (5 questions)
- Design & UX (5 questions)
- Research Requests (5 questions)
- Strategic Guidance (5 questions)

#### Part 12: Deliverables Requested from GPT

**Immediate** (for build kickoff):
1. Technology stack recommendation
2. Architecture design document
3. Refined tier/phase plan
4. Risk analysis & mitigation plan

**Follow-Up Research** (async):
5. [Domain-specific research reports]
6. Benchmarking results
7. Best practices guides

**Strategic Feedback**:
10. Alternative approach assessment
11. Success criteria validation
12. Long-term roadmap

#### Part 13: Conclusion
- Summary of key challenges
- What we need from GPT
- Estimated timeline
- "Ready to proceed?" prompt

#### References
List all sources:
- Web search results (with hyperlinks)
- GitHub repos (with hyperlinks)
- Documentation links

---

## Step 4: Create Manual Tracking File

Generate `.autonomous_runs/[project-name]-v1/MANUAL_TRACKING.md`

### Tracking File Structure

```markdown
# Manual Phase Tracking - [Project Name] v1

**Run ID**: [project-name]-v1
**Started**: YYYY-MM-DD
**Project Type**: [Description]
**Build Plan**: [Link to build plan when created]

---

## Run Overview

- **Total Planned Phases**: TBD (after GPT response)
- **Tiers**: TBD
- **Goal**: [What we're building]

---

## Phases Executed

### Phase 1.1: [Title]
- **Date**: _Not started yet_
- **Category**: _TBD_
- **Complexity**: _TBD_
- **Builder Model**: _TBD_
- **Auditor Model**: _TBD_
- **Attempts**: _TBD_
- **Tokens**: _TBD_
- **Risk Score**: _TBD_
- **Issues Found**: _TBD_
- **Learned Rules**: _TBD_
- **Notes**: _TBD_

---

## Summary Stats (Running Totals)

### Category Distribution
[To be filled as phases complete]

### Token Usage (Estimated)
- **OpenAI**: 0 tokens
- **Anthropic**: 0 tokens
- **Total**: 0 tokens

### Risk Score Analysis
[To be filled as phases complete]

### Audit Results
[To be filled as phases complete]

### Learned Rules
1. _No rules recorded yet_

---

## Key Observations

[To be filled during build]

---

## Final Review (After All Phases)

[To be completed at end]
```

---

## Step 5: Update Todo List

```markdown
- [x] Create build branch
- [x] Gather context from existing work
- [x] Research existing solutions
- [x] Create GPT research request
- [ ] Wait for GPT response
- [ ] Create detailed build plan based on GPT guidance
- [ ] Set up project structure
- [ ] Begin Phase 1.1
```

---

## Step 6: Communicate to User

Inform user:
1. Branch created: `build/[project-name]-v1`
2. Research completed (list key findings)
3. GPT report created at `.autonomous_runs/[project-name]-v1/GPT_RESEARCH_REQUEST.md`
4. Manual tracking ready
5. Next step: "I've created a comprehensive research request for GPT. Please review and send to GPT for strategic guidance."

---

## Checklist for Template Application

Use this checklist to ensure all steps completed:

- [ ] Build branch created (`git checkout -b build/...`)
- [ ] Relevant documentation read (if referenced by user)
- [ ] Web searches conducted (minimum 3 searches)
- [ ] GitHub projects researched
- [ ] GPT research request created with all 13 parts
- [ ] Manual tracking file created
- [ ] Todo list initialized
- [ ] User informed of next steps

---

## Template Maintenance

**Update this template when**:
- New step proves useful across builds
- GPT feedback suggests improvements
- User requests additional standard sections
- Technology landscape changes (new tools, frameworks)

**Version History**:
- v1.0 (2025-11-26): Initial template based on FileOrganizer project

---

## Example Application

**User Input**:
> "I want to build a recipe manager app that uses AI to suggest recipes based on ingredients I have at home"

**Application**:
1. Create branch: `build/recipe-manager-v1`
2. Search: "AI recipe suggestion ingredients detection 2025", "github recipe manager AI computer vision"
3. Research: GitHub repos for recipe parsers, ingredient detectors, meal planning
4. GPT Report:
   - Part 1: "Smart recipe manager with computer vision ingredient detection..."
   - Part 5: "Technology stack: Electron vs React Native? Image recognition: local YOLO vs cloud Vision API?"
   - Part 7: "Research Gap 1: How accurate is ingredient detection from pantry photos?"
   - Part 11: "GPT Questions: 1. Best ingredient taxonomy database? 2. How to handle recipe scaling?"
5. Tracking file: `.autonomous_runs/recipe-manager-v1/MANUAL_TRACKING.md`
6. User: "Research complete. GPT report ready for review."

---

**End of Template**
