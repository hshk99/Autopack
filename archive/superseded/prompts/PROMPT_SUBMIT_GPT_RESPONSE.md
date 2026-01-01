# Universal Prompt: Submit GPT Response to Claude

**Purpose**: Use this prompt to submit GPT Auditor's response back to Claude for implementation or follow-up discussion.

---

## Prompt to Copy-Paste to Claude

```
GPT Auditor has completed the review. Here is the response:

[PASTE THE ENTIRE CONTENTS OF: archive/correspondence/GPT_RESPONSE_[ISSUE_NAME].md]

Please:
1. Review GPT's analysis and recommendations
2. Identify what we should implement immediately vs defer
3. If GPT's analysis requires clarification or raises new questions, prepare a follow-up report
4. If ready to implement, create a plan with specific steps

What do you think of GPT's recommendations?
```

---

## Alternative: If GPT Response is Very Long

If the GPT response is too long to paste directly, use this shorter version:

```
GPT Auditor has completed the review and saved the response at:
archive/correspondence/GPT_RESPONSE_[ISSUE_NAME].md

Please:
1. Read the GPT response file
2. Review the analysis and recommendations
3. Identify what we should implement immediately vs defer
4. If GPT's analysis requires clarification, prepare a follow-up report
5. If ready to implement, create an implementation plan

What do you think of GPT's recommendations?
```

---

## What Claude Will Do

Claude will:
1. **Read and analyze** GPT's response
2. **Evaluate recommendations** for feasibility and priority
3. **Identify conflicts** between GPT's suggestion and existing design
4. **Ask clarifying questions** if GPT's response is ambiguous
5. **Prepare implementation plan** if recommendations are clear
6. **Prepare follow-up report** if more consultation is needed

---

## Possible Outcomes

### Outcome 1: Ready to Implement
Claude will create an implementation plan:
- Specific code changes with file paths
- Order of implementation (what to do first)
- Test cases to add
- Validation steps

### Outcome 2: Need Clarification
Claude will prepare a follow-up report:
- `archive/correspondence/CLAUDE_FOLLOWUP_FOR_GPT_[ISSUE_NAME].md`
- Addresses ambiguities in GPT's response
- Asks specific follow-up questions
- You repeat the process with new Cursor Agent session

### Outcome 3: Disagree with GPT
Claude will:
- Explain which recommendations to accept/reject and why
- Propose alternative approach if GPT's suggestion conflicts with existing design
- May request additional consultation on specific points

---

## Example Usage

**After GPT Auditor analyzes the scope path bug, you paste:**

```
GPT Auditor has completed the review and saved the response at:
archive/correspondence/GPT_RESPONSE_SCOPE_PATH_BUG.md

Please:
1. Read the GPT response file
2. Review the analysis and recommendations
3. Identify what we should implement immediately vs defer
4. If GPT's analysis requires clarification, prepare a follow-up report
5. If ready to implement, create an implementation plan

What do you think of GPT's recommendations?
```

**Claude will respond with:**
- Analysis of GPT's findings
- Implementation priority (Critical, High, Medium, Low)
- Specific code changes to make
- Testing strategy
- Any concerns or disagreements with GPT's approach

---

## Tips

- **Don't edit GPT's response** - paste it as-is so Claude sees the full context
- **If implementing**: Ask Claude to create TODO list for tracking
- **If disagreement**: Ask Claude to explain reasoning before proceeding
- **If follow-up needed**: Claude will prepare a new report automatically
- **Save conversation**: The Claude ↔ GPT exchange is valuable for future reference

---

## Iterative Consultation

You can continue the consultation loop:

```
Round 1:
  Claude Report → GPT Response → Claude Implements

Round 2 (if needed):
  Claude Follow-up → GPT Clarification → Claude Implements

Round 3 (if still needed):
  Claude Specific Question → GPT Targeted Answer → Claude Finalizes
```

Each round should be more focused than the last. If you reach Round 4+, consider whether the issue is too complex and needs to be broken down.

---

**Related**: See `PROMPT_REQUEST_GPT_REVIEW.md` for initiating GPT reviews
