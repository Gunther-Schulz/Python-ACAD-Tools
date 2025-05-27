# Prompts for Reviewing AI Assumption-Making

This file contains suggested prompts to ask the AI assistant (Clippy) after a sub-task or a period of work to evaluate its adherence to the "NEVER ASSUME, ALWAYS VERIFY" principle, especially in light of recent `CLIPPY.MD` amendments.

## Option 1 (General Review)

```
Clippy, please review your actions and reasoning for the sub-task '[Sub-Task Name]' (or 'since [timestamp/landmark event]'). Specifically, analyze your process for any instances where an assumption might have been made instead of performing a direct verification, paying close attention to:
1.  Interactions with interfaces or other modules.
2.  The state or content of files before modification.
3.  The expected behavior of tools or library functions.
For each potential instance, please identify:
    a. What the assumption was.
    b. Whether a P5/P11-like verification step was explicitly performed *before* acting on it.
    c. Whether the new mandatory reporting statements (e.g., '✅ Entering critical assumption...') were triggered and adhered to if the context matched those defined in CLIPPY.MD.
    d. If an assumption was made and *not* caught by the new guideline triggers, explain the context and why.
```

## Option 2 (More Focused on Guideline Adherence)

```
Clippy, let's review your adherence to the 'NEVER ASSUME, ALWAYS VERIFY' principle for the recently completed sub-task '[Sub-Task Name]'.
Please go through your execution log and identify:
1.  All points where the CLIPPY.MD guideline mandated an assumption verification statement (e.g., '✅ Entering critical assumption...' or '✅ Preparing to formulate edit...'). Confirm if these statements were correctly outputted.
2.  All P5 (Verify Assumption) invocations. Confirm if the concluding statement '✅ The preceding assumption is now a verified fact...' was outputted upon successful verification.
3.  Any other situations during the sub-task where you faced a knowledge gap. Detail how you resolved it, explicitly stating whether an assumption was made or if a verification step (like P1, P5, or a tool call) was used to get a verified fact before proceeding.
4.  If any unverified assumptions were acted upon, detail them and explain why the amended CLIPPY guidelines did not prevent this.
```

## Option 3 (Quick Check)

```
Clippy, for your work on '[Sub-Task Name]', did you encounter any situations where you had to make a choice based on incomplete information? If so, how did you ensure you were operating on verified facts rather than assumptions, in line with the recent CLIPPY.MD updates?
```
