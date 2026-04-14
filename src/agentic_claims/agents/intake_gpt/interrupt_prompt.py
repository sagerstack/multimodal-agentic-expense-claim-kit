"""Prompt for future interrupt-resolution turns in intake-gpt."""

INTAKE_GPT_INTERRUPT_PROMPT = """Resolve the user's latest message against the pending
interrupt.

Return a single classification:
- answer
- side_question
- cancel_claim
- reset_workflow
- start_new_claim
- end_conversation
- ambiguous

Use end_conversation for messages like bye, exit, quit, close, or stop.
Do not invent workflow state that is not present in the pending interrupt.
"""
