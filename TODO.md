# Task TODO (AI assistant rectify flow)

## Plan items
- [ ] Update backend `/api/chat` to return structured proposed extraction (no auto-apply) and an `action_intent` (log/edit/propose).
- [ ] Update backend logic so tool calls (log/edit) happen only when user explicitly confirms (via a dedicated confirm flag/message).
- [x] Update frontend Redux/store to hold `proposedForm` (and optionally `aiIntent`).

- [ ] Update frontend UI: show proposed fields + “Apply proposed changes” and “Rectify with AI” workflow.
- [ ] Wire “Apply” to update the left form only; keep DB writes gated behind existing Save/Log buttons.
- [ ] Quick manual test: first message populates proposals; second message corrects proposals; Apply updates form.



