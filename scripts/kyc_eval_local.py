#!/usr/bin/env python3
"""
KYC/AML Local Eval Runner — ZPTPL
===================================
Runs all 40 eval questions against YOUR local FastAPI chatbot
and saves results to a single JSON file for Claude scoring.

Usage:
    # Start the API first:
    uvicorn app.main:app --reload

    # Then run:
    python3 -m scripts.kyc_eval_local
    python3 -m scripts.kyc_eval_local --top-k 7
    python3 -m scripts.kyc_eval_local --api-url http://localhost:8000

After running, upload the output JSON to Claude for scoring.
"""

import argparse
import json
import os
import time
from datetime import datetime

import requests

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BASE_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_TIMEOUT = 120  # seconds — local LLM can be slow

# ─── QUESTIONS (expected answers embedded for Claude scoring) ──────────────────
QUESTIONS = [
    {"id":1,"category":"Account Creation & KYC","difficulty":"Easy","hallucination_trap":False,
     "question":"What is the SLA for handling a new account creation request?",
     "expected":"2 working days from request creation. If moved back from Merchant pending to Analyst pending, also 2 working days."},
    {"id":2,"category":"Account Creation & KYC","difficulty":"Easy","hallucination_trap":False,
     "question":"For a Sole Proprietorship, which documents are mandatory during onboarding and what is the key requirement about one of them?",
     "expected":"Any two from: Udyam Certificate, Shop & Establishment Certificate, GST Certificate, IEC Certificate, License/COP, ITR-3/ITR-4 with acknowledgement or ITR with GST Returns. One document must contain the proprietor's name."},
    {"id":3,"category":"Account Creation & KYC","difficulty":"Medium","hallucination_trap":False,
     "question":"A merchant submits a Board Resolution signed by the same person who is being authorized. Under what conditions is this acceptable?",
     "expected":"Acceptable if the signing person is a director. If not a director, an additional authorization document must be obtained. One signature is sufficient; stamp preferable but not mandatory. BR validity is 6 months from board meeting to onboarding form submission."},
    {"id":4,"category":"Account Creation & KYC","difficulty":"Medium","hallucination_trap":True,
     "question":"When an already onboarded customer requests a new account for the same business, do they need a new V-CIP?",
     "expected":"No new V-CIP required. The existing V-CIP of the parent account can be mapped using UCIC (Unique Customer Identification Code) and tagged to the new account."},
    {"id":5,"category":"Account Creation & KYC","difficulty":"Medium","hallucination_trap":False,
     "question":"For a marketplace merchant requesting split settlements, what is the minimum annual turnover threshold and how is it verified?",
     "expected":"Annual turnover must be greater than Rs.40 lakhs at the time of request. Verified using GST filings or ITR documents."},
    {"id":6,"category":"Account Creation & KYC","difficulty":"Hard","hallucination_trap":False,
     "question":"A sole proprietorship provides a GST Certificate dated March 2020, Udyam Certificate dated June 2022, and FSSAI license dated January 2019. Which date should be used as the Date of Incorporation?",
     "expected":"January 2019 (FSSAI license) — the earliest valid registration date should be used as the Date of Incorporation when any registration document reflects an earlier date than the Udyam or Shops and Establishments Certificate."},
    {"id":7,"category":"Account Creation & KYC","difficulty":"Hard","hallucination_trap":False,
     "question":"During V-CIP, an analyst receives an e-PAN in PDF format with an unverifiable signature. Can this be accepted and what additional steps are required?",
     "expected":"Yes, it can be accepted. Additional steps: verification from the issuing authority source AND matching the image and details using OVD."},
    {"id":8,"category":"Video KYC / V-CIP","difficulty":"Easy","hallucination_trap":False,
     "question":"What is the SLA for completing a VKYC Audit request?",
     "expected":"1 day from the request being created."},
    {"id":9,"category":"Video KYC / V-CIP","difficulty":"Easy","hallucination_trap":False,
     "question":"Under what circumstance should a V-CIP session not be conducted at all?",
     "expected":"V-CIP must not be conducted if the customer is located outside India. The system detects access from IP addresses outside India and prevents spoofed IP connections."},
    {"id":10,"category":"Video KYC / V-CIP","difficulty":"Medium","hallucination_trap":False,
     "question":"During a VKYC session, a third party is briefly seen in the video and appears to be just a passer-by with no prompting suspected. What is the correct audit outcome?",
     "expected":"Not a rejection criterion. The auditor may note it in comments but should not reject the session solely because a passer-by was visible if no prompting is suspected."},
    {"id":11,"category":"Video KYC / V-CIP","difficulty":"Medium","hallucination_trap":False,
     "question":"A business representative states annual turnover as Rs.8 lakhs during V-CIP, but the onboarding form states Rs.15 lakhs — a deviation of about 47%. How should the auditor handle this?",
     "expected":"A deviation of up to 50% is acceptable. This case (47%) falls within the threshold so it does not result in V-CIP rejection. The account creation analyst is responsible for reviewing and capturing the data accurately, with clarifications via RFI if needed."},
    {"id":12,"category":"Video KYC / V-CIP","difficulty":"Medium","hallucination_trap":False,
     "question":"What must an analyst do if the business representative is unable to speak during a V-CIP session?",
     "expected":"The agent may request them to use sign language for communicating the verification code and proceed without questions. This requires approval of the concurrent audit, Principal Officer, and addition to the exception tracker."},
    {"id":13,"category":"Video KYC / V-CIP","difficulty":"Hard","hallucination_trap":False,
     "question":"A V-CIP session is interrupted mid-way due to a network drop and then the call reconnects. What is the correct handling?",
     "expected":"A call drop or disconnection requires a completely fresh session to be initiated. Pausing without dropping does not create multiple files, but an actual drop means a new session must be started."},
    {"id":14,"category":"Video KYC / V-CIP","difficulty":"Hard","hallucination_trap":False,
     "question":"What are the FIU-IND Red Flag Indicators for human trafficking that a VKYC agent must watch for during a session?",
     "expected":"Victims may appear fearful, reluctant to speak, or overly reliant on a third party. Traffickers often act as interpreters. Victims may show physical signs of abuse such as bruises or shaking, or display nervous behaviour due to fear of their abuser."},
    {"id":15,"category":"Transaction Monitoring","difficulty":"Easy","hallucination_trap":False,
     "question":"What is the maximum ticket amount a Risk Analyst can handle independently, and what approval is needed above Rs.5,00,000?",
     "expected":"Risk Analyst: up to Rs.2,50,000. Senior Risk Analyst: up to Rs.5,00,000. Above Rs.5,00,000 requires Risk Specialist approval."},
    {"id":16,"category":"Transaction Monitoring","difficulty":"Easy","hallucination_trap":False,
     "question":"Why are UPI transactions prioritized over Card and Net Banking transactions in the monitoring queue?",
     "expected":"UPI transactions are prioritised due to shorter SLAs compared to the other transaction types."},
    {"id":17,"category":"Transaction Monitoring","difficulty":"Medium","hallucination_trap":False,
     "question":"A merchant's line of business is listed as Educational Services but recent transactions are all for software subscriptions. What should the analyst do?",
     "expected":"Investigate further. If merchant has a valid alternate use case, check if business documents support it. If not, collect additional business proof. Only a Senior Risk Analyst or Risk Specialist can update the MCC. The acquirer must also be informed of any MCC change."},
    {"id":18,"category":"Transaction Monitoring","difficulty":"Medium","hallucination_trap":False,
     "question":"Before moving a high-value Card transaction to Pending for Approval, what specific analysis data points must be filled in?",
     "expected":"Whether the receipt email is verified, whether the analyst can link the receipt email with the cardholder, whether the customer is individual or business, whether the customer is related to the merchant, and whether the invoice is inline."},
    {"id":19,"category":"Transaction Monitoring","difficulty":"Medium","hallucination_trap":False,
     "question":"A long-standing customer has multiple credentials linked to their account flagged under velocity check. What is the action?",
     "expected":"If the customer is a long-standing customer, approve the transaction. Escalation to Risk Specialist and hold is only for non-long-standing customers with multiple credentials in a short span."},
    {"id":20,"category":"Transaction Monitoring","difficulty":"Hard","hallucination_trap":False,
     "question":"An analyst is reviewing a high-risk UPI transaction where the IP shows VPN usage and no invoice is available. Walk through the complete review steps as per the SOP.",
     "expected":"Step 1: Check why flagged as high risk. Step 2: Check merchant business nature. Step 3: No invoice — gauge expected nature from merchant profile. Step 4: Check credentials (IP, VPA, Email); VPN is a red flag. Step 5: Velocity check on identifiers. Step 6: Flag for further review, discuss with Principal Officer or Designated Director. Step 7: If suspicious, file STR with FIU."},
    {"id":21,"category":"FIU Reporting & STR","difficulty":"Easy","hallucination_trap":False,
     "question":"What is the maximum number of days within which an STR must be filed once suspicion is confirmed?",
     "expected":"Seven working days from when suspicion is confirmed."},
    {"id":22,"category":"FIU Reporting & STR","difficulty":"Easy","hallucination_trap":True,
     "question":"Is there a minimum monetary threshold for a transaction to be eligible for STR filing?",
     "expected":"No. There is no monetary threshold applicable for STR filing eligibility. Any one of the four criteria is sufficient regardless of the transaction amount."},
    {"id":23,"category":"FIU Reporting & STR","difficulty":"Medium","hallucination_trap":False,
     "question":"List all four criteria that make a transaction eligible for STR filing under the FIU SOP.",
     "expected":"1) Proceeds of a scheduled offense. 2) Unusual or unjustified complexity. 3) No economic rationale or bona fide purpose. 4) Financing of terrorism-related activities. Any one criterion is sufficient."},
    {"id":24,"category":"FIU Reporting & STR","difficulty":"Medium","hallucination_trap":False,
     "question":"What should an analyst do if they receive communication from FIU or other agencies in their inbox?",
     "expected":"Forward it immediately to the Compliance Team via email with relevant context or supporting documents. The Compliance Team handles further action. The analyst must not respond directly to FIU."},
    {"id":25,"category":"FIU Reporting & STR","difficulty":"Hard","hallucination_trap":False,
     "question":"A Specialist finds a positive FIU alert for one of Zoho Payments active merchants. Walk through the complete sequence of actions from login to task closure.",
     "expected":"1) Login to FIU portal using personal non-shareable credentials. 2) Download latest alerts. 3) Upload to Payments Detective for automated screening. 4) Hit found — notify Principal Officer immediately. 5) Forward any FIU communication to Compliance Team. 6) PO determines STR eligibility under PMLA. 7) If eligible, file STR via FINGATE within 7 working days with PO approval. 8) Update Agent Task in Payments Detective. 9) Close task once all actions verified."},
    {"id":26,"category":"Negative Due Diligence","difficulty":"Easy","hallucination_trap":False,
     "question":"What are the three severity levels for FRI (Fraud Risk Indicator) hits received via DoT Digital Intelligence Platform?",
     "expected":"Medium, High, and Very High."},
    {"id":27,"category":"Negative Due Diligence","difficulty":"Medium","hallucination_trap":False,
     "question":"What does MNRL stand for and what does it mean when a merchant mobile number appears on it?",
     "expected":"Mobile Number Revocation List. It means the number was flagged under FRI but the subscriber failed reverification, so the number has been disconnected in real-time."},
    {"id":28,"category":"Negative Due Diligence","difficulty":"Medium","hallucination_trap":False,
     "question":"A Risk Analyst finds a CIBIL defaulter true hit on a merchant and the exposure is assessed as acceptable. What is the correct action and what must be documented?",
     "expected":"The hit may be discounted as acceptable. The analyst must document the justification and close the alert with documented reasoning. Escalation to Principal Officer is only required when the exposure is assessed as unacceptable."},
    {"id":29,"category":"Negative Due Diligence","difficulty":"Hard","hallucination_trap":False,
     "question":"A merchant has an MCA true hit — company struck off under Companies Act 2013 — and exposure is assessed as unacceptable. What is the exact escalation process?",
     "expected":"Escalate to Principal Officer with supporting analysis and justification. PO makes a decision: onboarding, retention, restriction, or off-boarding. Cannot be closed by the analyst alone. All findings must be documented."},
    {"id":30,"category":"Processing Level Upgrade","difficulty":"Easy","hallucination_trap":False,
     "question":"What is the SLA for handling a PLU request?",
     "expected":"2 days from the request being created."},
    {"id":31,"category":"Processing Level Upgrade","difficulty":"Medium","hallucination_trap":False,
     "question":"A merchant at PLU Level 3 reaches Rs.5 lakhs in yearly calendar volume. What happens next?",
     "expected":"The merchant is moved to PLU Level 4 (Rs.5L to Rs.10L). PLU tracks yearly calendar volume January to December. Crossing the level on any day within the calendar year triggers a new PLU request."},
    {"id":32,"category":"Processing Level Upgrade","difficulty":"Medium","hallucination_trap":True,
     "question":"A PLU alert is triggered for a merchant whose last PLU was closed 3 weeks ago. Is a full-scale review required?",
     "expected":"No. If triggered within one month of a previously closed PLU, only a transaction review limited to the triggering activity is required. However, any anomalies found require a full review regardless."},
    {"id":33,"category":"Processing Level Upgrade","difficulty":"Hard","hallucination_trap":False,
     "question":"During a PLU review, an analyst confirms a merchant is fraudulent. Walk through the complete fraud escalation process.",
     "expected":"Step 1: Analyst/Senior escalates to Risk Specialist; if Specialist identifies, loop in second Risk Specialist. Step 2: Immediately disable payment collection and payouts. Do NOT inform the merchant (tipping-off prevention). Step 3: Post findings in Suspicious Merchants Cliq group to notify PO and senior management. Step 4: Assess STR criteria; file with FIU-IND with PO approval if eligible. Step 5: Document all in Payments Detective. Step 6: Report to Risk Management Committee and Board quarterly."},
    {"id":34,"category":"Disputes","difficulty":"Easy","hallucination_trap":False,
     "question":"For a UPI dispute via ICICI EazyPay, what happens if the merchant fails to submit evidence by the deadline?",
     "expected":"Failure to submit evidence within the specified deadline leads to an immediate chargeback."},
    {"id":35,"category":"Disputes","difficulty":"Medium","hallucination_trap":False,
     "question":"How does Lyra communicate card dispute notifications to Zoho Payments and what happens immediately upon dispute creation?",
     "expected":"Lyra uploads files into Zoho Payments SFTP server. On creation of a card dispute, a chargeback is initiated immediately. Merchants are notified immediately to take necessary action."},
    {"id":36,"category":"Disputes","difficulty":"Medium","hallucination_trap":False,
     "question":"An analyst needs to manually create an IBMB dispute in Payments Detective. What are the required fields?",
     "expected":"Dispute Identifier, Disputed Amount (in rupees), Reason Code, Reconciliation Reference One (RRN), Notification Timestamp, Submit By Date."},
    {"id":37,"category":"Disputes","difficulty":"Hard","hallucination_trap":False,
     "question":"A card dispute via Lyra has been escalated to Pre-Arbitration and the merchant wants to contest. Walk through the complete analyst workflow.",
     "expected":"Same process as initial stage. Monitor Payments Detective for merchant response. If accepted: automated mail to Lyra. If rejected with evidence: system creates Consolidated Evidence file, uploads to SFTP, sends automated mail to Lyra. Lyra polls SFTP or downloads from mail and forwards to card network. Update status via Pay Admin Console to Under Review via Engineering team. Only the dispute state changes (Chargeback to Pre-Arbitration to Arbitration); all operational steps remain the same."},
    {"id":38,"category":"Payment Mode Requests","difficulty":"Easy","hallucination_trap":False,
     "question":"Is Bank Transfer enabled for Individual and Sole Proprietorship merchants?",
     "expected":"No. Bank Transfer shall be enabled for all entity types except Individual and Sole Proprietorship."},
    {"id":39,"category":"Payment Mode Requests","difficulty":"Medium","hallucination_trap":False,
     "question":"A merchant has requested UPI Recurring but their website does not clearly show the use case. What is the next step?",
     "expected":"If the use case cannot be determined from the website or other available sources, it must be requested through the Support Team. Once confirmed, review historical transaction patterns and previous disputes or chargebacks."},
    {"id":40,"category":"Cross-SOP","difficulty":"Hard","hallucination_trap":True,
     "question":"A merchant has a FRI Very High severity NDD hit and is also requesting UPI Recurring payment mode. What should the analyst handle first and what are the dependencies?",
     "expected":"The NDD hit must be handled first as it directly affects merchant account status. Per NDD SOP: conduct independent review, then accept risk with documentation or restrict/suspend. The UPI Recurring request cannot be approved while an unresolved true NDD hit exists without Principal Officer sign-off. If NDD results in restriction, UPI Recurring is rejected. If risk accepted and documented, UPI Recurring can proceed normally."},
]


# ─── API CALL ─────────────────────────────────────────────────────────────────

def query(question: str, top_k: int | None = None) -> dict:
    payload: dict = {"question": question}
    if top_k is not None:
        payload["top_k"] = top_k
    try:
        r = requests.post(
            f"{BASE_URL}/chat",
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return {"ok": True, "data": r.json(), "error": ""}
    except Exception as e:
        err = str(e)
        try:
            err += f" | Response: {r.text[:300]}"
        except Exception:
            pass
        return {"ok": False, "data": None, "error": err}


def extract_sources(resp: dict) -> list:
    if not resp["ok"] or not resp["data"]:
        return []
    return [
        {
            "rank": i + 1,
            "doc_name": s.get("doc_name", ""),
            "section": s.get("section", ""),
            "excerpt": s.get("excerpt", ""),
        }
        for i, s in enumerate(resp["data"].get("sources", []))
    ]


def sources_to_text(sources: list) -> str:
    """Flatten sources into readable text for Claude scoring."""
    if not sources:
        return "NO SOURCES RETURNED"
    parts = []
    for s in sources:
        parts.append(
            f"[Source {s['rank']} | {s['doc_name']} § {s['section']}]\n{s['excerpt']}"
        )
    return "\n\n".join(parts)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run(top_k: int | None = None, api_url: str | None = None) -> None:
    global BASE_URL
    if api_url:
        BASE_URL = api_url.rstrip("/")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f"eval_local_{ts}.json"

    print(f"\n{'='*60}")
    print(f"  KYC/AML Local Eval — ZPTPL Risk Specialist Chatbot")
    print(f"  API: {BASE_URL}/chat")
    print(f"  Questions: {len(QUESTIONS)}")
    if top_k:
        print(f"  top_k override: {top_k}")
    print(f"{'='*60}\n")

    results = []
    for i, q in enumerate(QUESTIONS, 1):
        print(f"  [{i:02d}/{len(QUESTIONS)}] Q{q['id']} [{q['difficulty']:6s}] {q['question'][:60]}...")
        resp = query(q["question"], top_k)
        sources = extract_sources(resp)
        retrieved_text = sources_to_text(sources)

        data = resp["data"] or {}
        answer = data.get("answer", "")
        refused = data.get("refused", False)
        confidence = data.get("confidence", 0.0)
        intent = data.get("intent", "")
        model = data.get("model", "")

        if resp["ok"]:
            status = "✅"
            detail = f"answer_len={len(answer)} | confidence={confidence:.2f} | sources={len(sources)}"
            if refused:
                detail += " | REFUSED"
        else:
            status = "❌"
            detail = resp["error"][:80]
        print(f"          {status} {detail}\n")

        results.append({
            "q_id":               q["id"],
            "category":           q["category"],
            "difficulty":         q["difficulty"],
            "hallucination_trap": q["hallucination_trap"],
            "question":           q["question"],
            "expected":           q["expected"],
            "answer":             answer,
            "refused":            refused,
            "confidence":         confidence,
            "intent":             intent,
            "model":              model,
            "retrieved_text":     retrieved_text,
            "sources":            sources,
            "api_ok":             resp["ok"],
            "api_error":          resp["error"],
        })
        time.sleep(1.2)

    ok_count = sum(1 for r in results if r["api_ok"])
    refused_count = sum(1 for r in results if r["refused"])

    output = {
        "meta": {
            "api_url":        BASE_URL,
            "timestamp":      ts,
            "total":          len(results),
            "successful":     ok_count,
            "refused":        refused_count,
            "top_k_override": top_k,
        },
        "results": results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  ✅ Done — {ok_count}/{len(results)} calls succeeded, {refused_count} refused")
    print(f"  📄 Output saved: {out_file}")
    print(f"\n  👉 Upload {out_file} to Claude for auto-scoring.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KYC/AML Local RAG Eval Runner")
    parser.add_argument(
        "--top-k", type=int, default=None,
        help="Override top_k (number of chunks to retrieve). Default: server setting."
    )
    parser.add_argument(
        "--api-url", type=str, default=None,
        help=f"FastAPI base URL. Default: {BASE_URL} (or $API_URL env var)."
    )
    args = parser.parse_args()
    run(top_k=args.top_k, api_url=args.api_url)
