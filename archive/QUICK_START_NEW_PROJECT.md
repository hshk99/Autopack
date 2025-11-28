# Quick Start: Building a New Project with Autopack

**Last Updated**: 2025-11-26

---

## TL;DR

Just say: **"I want to build [YOUR PROJECT IDEA]"**

Autopack will automatically handle everything else.

---

## Step-by-Step

### Step 1: Describe Your Idea (1 message)

Tell Claude what you want to build. Include:
- What it does
- Key features
- Target users
- Constraints (if any)

**Example**:
```
I want to build a context-aware file organizer desktop app that can
automatically organize files, rename them contextually, understand file
contents via OCR, and adapt to different use cases like legal case
management. It should be privacy-first with local AI processing,
cross-platform (Windows/Mac), and have an elderly-friendly UI.
```

**That's it!** Claude will automatically trigger the workflow.

---

### Step 2: Autopack Works (Automatic)

Autopack will:
- ✅ Create build branch (`build/{project-name}-v1`)
- ✅ Conduct 8-12 web searches
- ✅ Search GitHub for similar projects
- ✅ Analyze 20-30+ existing solutions
- ✅ Compile pros/cons/limitations for each
- ✅ Research technology benchmarks
- ✅ Identify market gaps
- ✅ Generate reference files
- ✅ Create GPT strategic prompt

**Time**: 15-30 minutes (automatic)

---

### Step 3: Review Files (Optional)

Files generated in `.autonomous_runs/{project-name}-v1/`:

1. **MARKET_RESEARCH_EXTENDED_2025.md** (~25,000 words)
   - 20-30+ solutions analyzed
   - Technology benchmarks (OCR, LLMs, frameworks)
   - Market gaps identified
   - Competitive advantages
   - Strategic recommendations

2. **REF_USER_REQUIREMENTS.md**
   - Your requirements compiled
   - Must-have/should-have features
   - Use cases documented

3. **GPT_STRATEGIC_ANALYSIS_PROMPT.md** (~4,000 words)
   - 25-30 focused questions for GPT
   - Expected deliverables defined

4. **README.md**
   - Guide for next steps

---

### Step 4: Send to GPT

1. Open new ChatGPT conversation
2. **Attach**: `MARKET_RESEARCH_EXTENDED_2025.md`
3. **Send**: `GPT_STRATEGIC_ANALYSIS_PROMPT.md` (copy/paste as message)

**GPT will analyze and provide**:
- Market positioning recommendation
- Technology stack (specific versions)
- Architecture design
- Risk mitigation plan
- Build plan validation (is 50 phases realistic?)
- Success criteria

**Time**: 30-60 minutes (GPT analysis)

---

### Step 5: Return to Claude

Share GPT's recommendations. Claude will:
- Create `BUILD_PLAN_{PROJECT}.md` (50 phases, 5-6 tiers)
- Begin Autopack autonomous build
- Track progress

**Time**: 3-6 weeks (autonomous build)

---

## What You Get

### Comprehensive Market Research
- Not just "here are some tools"
- **27+ solutions** analyzed with detailed pros/cons/limitations
- **Quantitative benchmarks**: OCR accuracy (Tesseract 30%, GPT-4o 80%), Desktop frameworks (Tauri 10x lighter than Electron), LLM performance (7B models score 3.85/5 on legal tasks)
- **Market gap identification**: Specific opportunities (e.g., "Affordable legal tools for individuals vs $$$$ enterprise tools")
- **Strategic recommendations**: Technology stack justified with trade-offs

### Focused GPT Prompt
- 25-30 specific questions organized by topic
- Role clarification (Autopack = implementation, GPT = strategy)
- Expected deliverables defined
- References research file for analysis

### Time Saved
- **Before**: 3-4 hours of manual research + organization
- **After**: 15-30 minutes (automatic) + 1 trigger phrase

---

## Customization

If you want deeper research, edit `.autopack/config/project_init_config.yaml`:

```yaml
research:
  web_search:
    max_results_per_query: 20  # Increase from 10
  github_search:
    max_repos: 10  # Increase from 5
```

---

## Example: FileOrganizer Project

**What I said**:
> "I want to build a context-aware file organizer desktop app..."

**What Autopack Generated**:
- **MARKET_RESEARCH_EXTENDED_2025.md**: 25,000 words
  - 27 solutions analyzed (Local-File-Organizer, FileSense, CaseChronology, ChronoVault, etc.)
  - OCR benchmarks (Tesseract vs GPT-4 Vision vs Claude)
  - Desktop framework comparison (Electron vs Tauri performance data)
  - Local LLM evaluation (SaulLM-7B, Qwen2-7B capabilities)
  - 7 market gaps identified
  - 26 sources with links

- **GPT_STRATEGIC_ANALYSIS_PROMPT.md**: 4,000 words
  - 29 specific questions
  - 10 topic sections (market positioning, tech stack, architecture, risks, etc.)

**Time**: 25 minutes (automatic research + compilation)

---

## Troubleshooting

**Q: It didn't trigger automatically?**

Make sure your message includes a trigger phrase:
- "I want to build [X]"
- "Let's create [X]"
- "I need to develop [X]"

Or manually request:
> "Can you use the project initialization workflow to research [PROJECT]?"

**Q: Can I skip GPT consultation?**

Yes, but not recommended. GPT provides strategic validation that:
- Catches architectural flaws early
- Identifies risks before building
- Validates technology choices
- Ensures build plan is realistic

**Q: Where are files stored?**

`.autonomous_runs/{project-slug}-v1/`

These are gitignored (local only) since they're planning materials.

---

## Future Projects

**Reusable!** Every time you say "I want to build [X]", Autopack runs the same thorough workflow automatically.

No need to remember what to ask for - it's all configured.

---

**Ready? Just say: "I want to build [YOUR_IDEA]"**
