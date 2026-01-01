# Universal Prompt: Request GPT Review via Cursor Agent

**Purpose**: Use this prompt to ask Claude to prepare a GPT review request that you can submit to Cursor Agent mode.

---

## Prompt to Copy-Paste to Claude

```
I need a GPT Auditor review for [DESCRIBE ISSUE/BUG/QUESTION].

Please:
1. Create a report at: archive/correspondence/CLAUDE_REPORT_FOR_GPT_[ISSUE_NAME].md
2. Include:
   - Executive summary of the issue
   - Current setup and limitations
   - Your hypothesis/analysis
   - Specific questions for GPT (numbered Q1, Q2, etc.)
   - Reference files list
3. Provide me with a ready-to-paste Cursor Agent prompt

Context:
[PASTE ANY RELEVANT CONTEXT, FILE PATHS, ERROR MESSAGES, OR BACKGROUND INFO]
```

---

## What Claude Will Deliver

1. **Report File**: `archive/correspondence/CLAUDE_REPORT_FOR_GPT_[ISSUE_NAME].md`
   - Comprehensive analysis of the issue
   - Specific questions for GPT to answer
   - References to relevant code files

2. **Cursor Agent Prompt**: Ready-to-paste prompt for Cursor Agent mode
   - Instructs GPT Auditor role
   - Points to the report file
   - Specifies response format and location

---

## Example Usage

**You say to Claude:**
```
I need a GPT Auditor review for the token estimation bug.

Please:
1. Create a report at: archive/correspondence/CLAUDE_REPORT_FOR_GPT_TOKEN_ESTIMATION.md
2. Include:
   - Executive summary of the issue
   - Current setup and limitations
   - Your hypothesis/analysis
   - Specific questions for GPT (numbered Q1, Q2, etc.)
   - Reference files list
3. Provide me with a ready-to-paste Cursor Agent prompt

Context:
Token estimator is reporting 80k tokens for a "low" complexity task when it should be ~8k.
This is causing inappropriate soft cap warnings and may affect model selection.
Relevant files: src/autopack/llm_service.py (estimate_tokens function)
```

**Claude will:**
1. Analyze the token estimation issue
2. Create the report with detailed questions
3. Give you a prompt to paste into Cursor Agent

**You then:**
1. Copy the Cursor Agent prompt
2. Open new Cursor Agent chat
3. Paste and run
4. Wait for GPT's response
5. Use the companion prompt to submit GPT's response back to Claude

---

## Notes

- Keep context description concise but include key details
- Mention specific error messages, file paths, or line numbers if known
- If you have a hypothesis, include it - Claude will evaluate and refine it
- You can request specific types of analysis (root cause, architectural design, performance optimization, etc.)

---

**Related**: See `PROMPT_SUBMIT_GPT_RESPONSE.md` for submitting GPT's response back to Claude
