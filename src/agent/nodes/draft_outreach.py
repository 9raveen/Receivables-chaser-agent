"""
Day 8 — draft_outreach node.

First node that actually invokes an LLM. Reads intervention_tone /
intervention_channels from state (already set by select_intervention),
pulls a real SHAP explanation for this invoice, translates the top
feature-level reasons into plain language (never expose a raw feature
name like "customer_late_rate_feat" to a buyer-facing message — that's a
different problem than the internal SHAP strings inference.py returns),
and asks Gemini to draft an outreach message citing a specific, real
reason rather than a generic reminder.

Does NOT increment attempt_count — select_intervention already does that,
and this node runs after it in the graph (select_intervention ->
draft_outreach).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from src.agent.audit_log import write_entry
from src.agent.bridge import get_invoice_by_id
from src.agent.event_log import append_contact_attempt, append_outreach_draft
from src.agent.inference import get_customer_history, get_shap_contributions
from src.agent.llm_utils import call_with_structured_output
from src.agent.nodes.stopping import _within_contact_window
from src.agent.state import InvoiceState
from src.data.schema import ContactAttempt, ContactChannel, ContactTone
from src.utils.config import load_policy

# Plain-language translations for buyer-facing copy. Deliberately NOT
# exhaustive — one-hot dummy columns (business_code_*, invoice_currency_*,
# terms_code_grouped_*) are intentionally absent: per the known
# categorical-mismatch limitation, these are all-zero for every synthetic
# invoice and shouldn't surface as a "reason" even if one somehow appeared
# with a nonzero value from a future retrain (that would need this map
# revisited, not silently included here).
FEATURE_DESCRIPTIONS = {
    "customer_late_rate_feat": "this customer's history of late payments with us",
    "customer_avg_days_late_feat": "how many days late this customer's payments have tended to run",
    "cust_n_prior_invoices": "the length of this customer's invoice history with us",
    "amount_log": "the size of this invoice",
    "amount_vs_customer_avg": "how this invoice compares to this customer's typical invoice amount",
    "payment_terms_days": "the agreed payment terms on this invoice",
    "terms_code_freq": "how this payment-terms arrangement compares to others",
    "is_cold_start": "limited payment history available for this customer",
}

TONE_GUIDANCE = {
    "friendly_reminder": "warm and low-pressure — a gentle nudge assuming good faith, this is likely just an oversight",
    "firm_reminder": "polite but direct — communicate real urgency without being aggressive",
    "formal_notice": "formal business register — state that continued non-payment has consequences, stay professional, no threats",
    "final_notice": "serious and final in register, but still professional — state next steps clearly, no threats or harassment",
}


class OutreachDraft(BaseModel):
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Full message body")


def _humanize_reasons(contributions: list[tuple[str, float]]) -> list[str]:
    """
    Filters SHAP contributions down to ones with a real plain-language
    translation, dropping anything not in FEATURE_DESCRIPTIONS (e.g. any
    one-hot dummy that isn't meant to be surfaced). If nothing survives the
    filter, returns an empty list — the prompt builder handles that case
    with a generic fallback rather than crashing.
    """
    reasons = []
    for feat, val in contributions:
        if feat in FEATURE_DESCRIPTIONS:
            reasons.append(FEATURE_DESCRIPTIONS[feat])
    return reasons


def _build_prompt(state: InvoiceState, human_reasons: list[str], tone: str) -> str:
    tone_guidance = TONE_GUIDANCE.get(tone, "professional and courteous")
    days_overdue = max((date.today() - state["due_date"]).days, 0)

    if human_reasons:
        reason_text = (
            "Internally, this invoice was flagged based on: " + "; ".join(human_reasons) + "."
            " Weave ONE of these in naturally as context for why you're following up now"
            " (e.g. referencing the customer relationship or invoice history) — do NOT mention"
            " SHAP, models, scores, or that this was 'flagged' by a system."
        )
    else:
        reason_text = "No specific risk signal to cite — write a standard reminder."

    return f"""You are drafting a B2B accounts-receivable follow-up message for an
Indian MSME context (payments in INR). This is a real business relationship,
not a form letter — be specific, not generic.

Invoice: {state['invoice_id']}
Amount: INR {state['amount']:,.2f}
Payment terms: {state['payment_terms_days']} days
Due date: {state['due_date'].isoformat()}
Days overdue: {days_overdue}

Required tone: {tone_guidance}

{reason_text}

Do not fabricate any facts not given above (no invented company names,
no invented prior conversations, no legal threats beyond what the tone
guidance supports). Sign off as "Accounts Receivable Team".

Return a subject line and message body."""


def draft_outreach(state: InvoiceState) -> InvoiceState:
    invoice = get_invoice_by_id(state["invoice_id"])
    history_df = get_customer_history(state["customer_id"], as_of=date.today())
    contributions = get_shap_contributions(invoice, history_df)
    human_reasons = _humanize_reasons(contributions)

    tone = state["intervention_tone"]
    channels = state["intervention_channels"] or ["email"]
    channel = channels[0]

    prompt = _build_prompt(state, human_reasons, tone)
    draft = call_with_structured_output(prompt, OutreachDraft)

    now = datetime.now()
    policy = load_policy()
    within_window = _within_contact_window(now, policy)

    contact_attempt = ContactAttempt(
        invoice_id=state["invoice_id"],
        attempt_number=state["attempt_count"],
        channel=ContactChannel(channel),
        tone=ContactTone(tone),
        sent_at=now,
        within_contact_window=within_window,
        response_received=False,
    )
    append_contact_attempt(contact_attempt)

    append_outreach_draft(
        invoice_id=state["invoice_id"],
        attempt_number=state["attempt_count"],
        subject=draft.subject,
        body=draft.body,
        tone=tone,
        channel=channel,
        sent_at=now,
    )

    new_hash = write_entry(
        invoice_id=state["invoice_id"],
        node="draft_outreach",
        decision="drafted",
        reason=f"drafted {tone} outreach via {channel}"
               + (f", citing: {'; '.join(human_reasons)}" if human_reasons else ", no specific reason cited"),
        prev_hash=state["prev_audit_hash"],
    )

    return {
        **state,
        "prev_audit_hash": new_hash,
    }