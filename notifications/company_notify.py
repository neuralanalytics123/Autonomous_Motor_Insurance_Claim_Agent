import json
import os
import smtplib
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from core.config import settings
from core.schemas import ClaimDecisionResponse

ALERT_LOG_PATH = Path("company_claim_alerts.jsonl")


def _build_email_body(decision: ClaimDecisionResponse, event_type: str) -> tuple[str, str]:
    needs_approval = decision.requires_human_approval or decision.status.value in {
        "PENDING_REVIEW",
        "ESCALATED",
    }

    if event_type == "CLAIM_APPROVED":
        subject = f"[Claim Approved] {decision.claim_id} — Payout ₹{decision.recommended_payout:,.2f}"
        headline = (
            f"Good news: Claim {decision.claim_id} has been APPROVED for a payout of ₹{decision.recommended_payout:,.2f}."
        )
        action_line = "No further approval is needed. The payout can now be processed."
    elif needs_approval:
        subject = f"[Approval Needed] Claim {decision.claim_id} — Damage ₹{decision.claimed_amount:,.2f}"
        headline = (
            f"A customer requested claim {decision.claim_id} and COMPANY APPROVAL IS REQUESTED "
            f"before paying out money."
        )
        action_line = (
            "What to do next: Open the Company Approval tab in the app and click Approve or Reject."
        )
    else:
        subject = f"[Claim Requested] {decision.claim_id} — {decision.status.value}"
        headline = f"A customer requested claim {decision.claim_id} and the system has checked it."
        action_line = "This update has been saved in the company claim log."

    proof_text = ", ".join(decision.proof_files) if decision.proof_files else "No files attached"
    lines = [
        headline,
        action_line,
        "",
        "Claim Summary:",
        f"- Claim ID: {decision.claim_id}",
        f"- Policy Number: {decision.policy_id}",
        f"- Customer: {decision.customer_name or 'Not provided'} ({decision.customer_email or 'No email'}, {decision.customer_phone or 'No phone'})",
        f"- Claim Type: {decision.claims_type}",
        f"- Vehicle Type: {decision.vehicle_category}",
        f"- Current Status: {decision.status.value}",
        f"- Needs Company Approval: {'Yes' if needs_approval else 'No'}",
        f"- Estimated Damage Cost: ₹{decision.claimed_amount:,.2f}",
        f"- Coverage Limit / Vehicle Value: ₹{decision.coverage_cap_applied:,.2f}",
        f"- Deductible (Customer Share): ₹{decision.deductible_applied:,.2f}",
        f"- Payout Amount: ₹{decision.recommended_payout:,.2f}",
        f"- Date of Incident: {decision.incident_date or 'Not given'}",
        f"- Date Reported: {decision.reported_date or 'Not given'}",
        f"- Payout Needed By: {decision.payout_needed_date or 'Not given'}",
        f"- Uploaded Proof Files: {proof_text}",
        f"- Details: {decision.rejection_reason or decision.settlement_summary}",
    ]
    return subject, "\n".join(lines)


def _send_smtp(to_addr: str, subject: str, body: str) -> tuple[bool, str, str]:
    smtp_host = (os.getenv("SMTP_HOST") or settings.smtp_host or "").strip()
    if not smtp_host or not to_addr:
        return (
            False,
            "NOT_CONFIGURED",
            f"Recipient: {to_addr}. Add SMTP_HOST, SMTP_USER, SMTP_PASSWORD, and COMPANY_NOTIFY_EMAIL in .env to send real emails.",
        )

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        sender = (
            os.getenv("SMTP_FROM")
            or settings.smtp_from
            or os.getenv("SMTP_USER")
            or settings.smtp_user
            or to_addr
        ).strip()
        msg["From"] = sender
        msg["To"] = to_addr
        msg.set_content(body)

        smtp_port = int((os.getenv("SMTP_PORT") or str(settings.smtp_port) or "587").strip())
        smtp_user = (os.getenv("SMTP_USER") or settings.smtp_user or "").strip()
        smtp_pass = (os.getenv("SMTP_PASSWORD") or settings.smtp_password or "").strip()

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return True, "SENT", f"Email sent to {to_addr}."
    except Exception as exc:
        return False, "FAILED", f"Could not send email to {to_addr}: {exc}"


def send_claim_email(decision: ClaimDecisionResponse, event_type: str = "CLAIM_REQUESTED") -> dict:
    company_to = (
        os.getenv("COMPANY_NOTIFY_EMAIL") or settings.company_notify_email or "santhoshbharathi82@gmail.com"
    ).strip()
    subject, body = _build_email_body(decision, event_type)
    sent, status, detail = _send_smtp(company_to, subject, body)

    send_to_customer = (
        (os.getenv("SEND_CUSTOMER_EMAILS") or str(settings.send_customer_emails)).strip().lower()
        in {"1", "true", "yes"}
    )
    if send_to_customer and decision.customer_email.strip():
        c_sent, _, c_detail = _send_smtp(decision.customer_email.strip(), subject, body)
        detail = f"{detail} | Customer copy: {c_detail} (sent={c_sent})"

    return {
        "email_sent": sent,
        "email_status": status,
        "email_detail": detail,
        "recipient": company_to,
        "subject": subject,
        "body": body,
    }


def notify_company_of_claim(decision: ClaimDecisionResponse, event_type: str = "CLAIM_REQUESTED") -> dict:
    email_result = send_claim_email(decision, event_type=event_type)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "approval_requested_from_company": bool(
            event_type != "CLAIM_APPROVED"
            and (decision.requires_human_approval or decision.status.value in {"PENDING_REVIEW", "ESCALATED"})
        ),
        "recipient_email": email_result["recipient"],
        "claim_id": decision.claim_id,
        "policy_id": decision.policy_id,
        "customer_name": decision.customer_name,
        "customer_email": decision.customer_email,
        "claims_type": decision.claims_type,
        "vehicle_category": decision.vehicle_category,
        "status": decision.status.value,
        "claimed_amount_inr": decision.claimed_amount,
        "deductible_inr": decision.deductible_applied,
        "recommended_payout_inr": decision.recommended_payout,
        "requires_human_approval": decision.requires_human_approval,
        "incident_date": decision.incident_date,
        "reported_date": decision.reported_date,
        "payout_needed_date": decision.payout_needed_date,
        "proof_files": decision.proof_files,
        "rejection_reason": decision.rejection_reason,
        "summary": decision.settlement_summary,
        "email_sent": email_result["email_sent"],
        "email_status": email_result["email_status"],
        "email_detail": email_result["email_detail"],
        "email_subject": email_result["subject"],
        "email_body": email_result["body"],
    }

    with ALERT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")

    webhook_url = (os.getenv("COMPANY_WEBHOOK_URL") or settings.company_webhook_url or "").strip()
    if webhook_url:
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    return payload


def list_company_alerts(limit: int = 100) -> list[dict]:
    if not ALERT_LOG_PATH.exists():
        return []
    lines = ALERT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    parsed = []
    for line in reversed(lines[-limit:]):
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return parsed