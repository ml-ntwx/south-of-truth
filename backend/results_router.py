"""
Results Router — /results + /export/{format}/{session_id}
Supports: CSV, XML, RAW (JSON), TXT, MD, PDF
"""
import csv
import io
import json
import sqlite3
import xml.etree.ElementTree as ET
import os
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["results"])
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "south_of_truth.db")

def _db_get(session_id: str):
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id": row[0], "stage": row[1], "filename": row[2],
        "page_count": row[3], "current_page": row[4], "ocr_provider": row[5],
        "started_at": row[6], "completed_at": row[7],
        "processing_time_ms": row[8],
        "results": json.loads(row[9]) if row[9] else {},
        "error": row[10],
        "extracted_data": json.loads(row[11]) if row[11] else {}
    }

@router.get("/results/{session_id}")
async def get_results(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.get("stage") not in ("completed", "failed"):
        return JSONResponse({"session_id": session_id, "stage": session["stage"], "message": "Processing not complete."}, status_code=202)
    return session

@router.get("/export/csv/{session_id}")
async def export_csv(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    data = session.get("extracted_data", {})
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field", "Value", "Source"])
    def flatten(prefix, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                flatten(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                flatten(f"{prefix}[{i}]", v)
        else:
            writer.writerow([prefix, str(obj), "extracted"])
    flatten("", data)
    output.seek(0)
    return PlainTextResponse(output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=south-of-truth-{session_id[:8]}.csv"})

@router.get("/export/xml/{session_id}")
async def export_xml(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    data = session.get("extracted_data", {})
    root = ET.Element("PropertyDocument")
    root.set("session_id", session_id)
    root.set("stage", session.get("stage", "unknown"))
    root.set("exported", datetime.utcnow().isoformat())
    def build_xml(parent, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                child = ET.SubElement(parent, k.replace(" ", "_").replace("-", "_"))
                build_xml(child, v)
        elif isinstance(obj, list):
            for v in obj:
                item = ET.SubElement(parent, "Item")
                build_xml(item, v)
        else:
            parent.text = str(obj)
    build_xml(root, data)
    xml_str = ET.tostring(root, encoding="unicode")
    return PlainTextResponse(
        f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}',
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=south-of-truth-{session_id[:8]}.xml"})

@router.get("/export/raw/{session_id}")
async def export_raw(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    data = {
        "_meta": {
            "session_id": session_id,
            "exported_at": datetime.utcnow().isoformat(),
            "stage": session.get("stage"),
            "ocr_provider": session.get("ocr_provider"),
            "processing_time_ms": session.get("processing_time_ms"),
            "filename": session.get("filename")
        },
        "extracted_data": session.get("extracted_data", {}),
        "validation": (session.get("results") or {}).get("validation", []),
        "summary": (session.get("results") or {}).get("summary", {})
    }
    return PlainTextResponse(
        json.dumps(data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=south-of-truth-{session_id[:8]}.json"})

@router.get("/export/txt/{session_id}")
async def export_txt(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    e = session.get("extracted_data", {})
    v = (session.get("results") or {}).get("validation", [])
    s = (session.get("results") or {}).get("summary", {})
    doc_type = e.get("document_type", "unknown")
    lines = []
    lines.append("=" * 60)
    lines.append("  SOUTH OF TRUTH -- PROPERTY DOCUMENT VERIFICATION REPORT")
    lines.append("=" * 60)
    lines.append(f"  Session ID: {session_id}")
    lines.append(f"  Exported:   {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"  Provider:   {session.get('ocr_provider', 'unknown')}")
    lines.append(f"  Filename:   {session.get('filename', 'unknown')}")
    lines.append(f"  Doc Type:   {doc_type}")
    lines.append("")
    
    # ── Type-specific extraction ──────────────────────────────────
    if doc_type == "settlement_statement":
        lines.append("-" * 60)
        lines.append("  SETTLEMENT STATEMENT")
        lines.append("-" * 60)
        for field in ["matter_number", "preparer", "preparer_abn", "property_address",
                      "lot_plan", "vendor_name", "purchaser_name",
                      "contract_date", "settlement_date", "adjustment_date",
                      "water_reading_kL", "water_rate_per_kL",
                      "land_tax", "body_corp",
                      "deposit_amount", "balance_due", "settlement_time"]:
            val = e.get(field, "")
            label = field.replace("_", " ").title()
            lines.append(f"  {label:25s} {val or 'N/A'}")
        lines.append("")
        
    elif doc_type == "form_2_1":
        lines.append("-" * 60)
        lines.append("  FORM 2.1 — TRANSFER OF LAND")
        lines.append("-" * 60)
        for field in ["form_number", "lodgement_date", "processing_code",
                      "transferor_name", "transferee_name",
                      "title_reference", "lot_plan", "parish", "county",
                      "consideration", "stamp_duty",
                      "execution_date", "witness_name", "witness_occupation"]:
            val = e.get(field, "")
            label = field.replace("_", " ").title()
            lines.append(f"  {label:25s} {val or 'N/A'}")
        lines.append("")
        
    elif doc_type == "contract_of_sale":
        lines.append("-" * 60)
        lines.append("  CONTRACT OF SALE")
        lines.append("-" * 60)
        for field in ["vendor_name", "vendor_abn", "purchaser_name",
                      "property_address", "lot_plan", "title_reference",
                      "contract_date", "settlement_date",
                      "purchase_price", "deposit_amount", "balance_amount",
                      "inclusions", "special_conditions"]:
            val = e.get(field, "")
            label = field.replace("_", " ").title()
            lines.append(f"  {label:25s} {val or 'N/A'}")
        lines.append("")
        
    elif doc_type == "trust_account_statement":
        lines.append("-" * 60)
        lines.append("  TRUST ACCOUNT STATEMENT")
        lines.append("-" * 60)
        for field in ["law_practice", "abn", "client_name", "matter_reference",
                      "property_address", "statement_date", "statement_period",
                      "total_debits", "total_credits", "closing_balance"]:
            val = e.get(field, "")
            label = field.replace("_", " ").title()
            lines.append(f"  {label:25s} {val or 'N/A'}")
        lines.append("")
        
    elif doc_type == "final_letter":
        lines.append("-" * 60)
        lines.append("  FINAL SETTLEMENT LETTER")
        lines.append("-" * 60)
        for field in ["firm_name", "firm_abn", "client_name",
                      "property_address", "matter_reference",
                      "settlement_date", "purchase_price",
                      "adjustments", "fees", "total_amount",
                      "cheque_details", "keys_collection"]:
            val = e.get(field, "")
            label = field.replace("_", " ").title()
            lines.append(f"  {label:25s} {val or 'N/A'}")
        lines.append("")
        
    else:
        # Generic format (certificate_of_title, section_32, etc.)
        lines.append("-" * 60)
        lines.append("  EXTRACTED DATA")
        lines.append("-" * 60)
        lines.append(f"  Document Type:      {e.get('document_type') or 'Not detected'}")
        lines.append(f"  Title Reference:    {e.get('title_reference') or 'Not detected'}")
        lines.append(f"  ABN:                {e.get('abn') or 'Not detected'}")
        lines.append(f"  Confidence:         {(e.get('ocr_confidence') or 0) * 100:.0f}%")
        lines.append("")
        lines.append("  PROPRIETOR:")
        prop = e.get("registered_proprietor", {})
        names = prop.get("names", [])
        lines.append(f"    Names:            {', '.join(names) if names else 'Not detected'}")
        lines.append(f"    Address:          {prop.get('address') or 'Not detected'}")
        lines.append(f"    Tenancy:          {prop.get('tenancy') or 'Not detected'}")
        lines.append("")
        lines.append("  PROPERTY:")
        pr = e.get("property", {})
        lines.append(f"    Address:          {pr.get('address') or 'Not detected'}")
        lines.append(f"    Lot:              {pr.get('lot') or 'Not detected'}")
        lines.append(f"    Plan:             {pr.get('plan') or 'Not detected'}")
        lines.append(f"    LGA:              {pr.get('lga') or 'Not detected'}")
        lines.append(f"    State:            {pr.get('state') or 'Not detected'}")
        lines.append("")
        enc = e.get("encumbrances", [])
        if enc:
            lines.append("  ENCUMBRANCES:")
            for en in enc:
                lines.append(f"    - {en.get('type', 'Unknown')}: {en.get('to', '')} ({en.get('amount', '')})")
        else:
            lines.append("  Encumbrances:       None detected")
        lines.append("")
    
    lines.append("-" * 60)
    lines.append("  VALIDATION RESULTS")
    lines.append("-" * 60)
    if not v:
        lines.append("  All checks passed")
    else:
        for item in v:
            icon = "OK" if item["severity"] == "ok" else "ERR" if item["severity"] == "error" else "WARN"
            lines.append(f"  [{icon}] {item['field']}: {item['message']}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("  SUMMARY")
    lines.append("-" * 60)
    lines.append(f"  Total checks:       {s.get('total_checks', 0)}")
    lines.append(f"  Passed:             {s.get('passed', 0)}")
    lines.append(f"  Errors:             {s.get('errors', 0)}")
    lines.append(f"  Warnings:           {s.get('warnings', 0)}")
    lines.append(f"  Valid:              {'Yes' if s.get('is_valid') else 'No'}")
    lines.append("")
    lines.append("=" * 60)
    lines.append("  END OF REPORT")
    lines.append("=" * 60)
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=south-of-truth-{session_id[:8]}.txt"})

@router.get("/export/md/{session_id}")
async def export_md(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    e = session.get("extracted_data", {})
    v = (session.get("results") or {}).get("validation", [])
    s = (session.get("results") or {}).get("summary", {})

    enc = e.get("encumbrances", [])
    enc_rows = ""
    if enc:
        enc_rows = "| Type | Registered Number | To | Amount | Date |\n"
        enc_rows += "|:-----|:------------------|:---|:-------|:-----|\n"
        for en in enc:
            enc_rows += f"| {en.get('type','')} | {en.get('registered_number','')} | {en.get('to','')} | {en.get('amount','')} | {en.get('registered_date','')} |\n"
    else:
        enc_rows = "*None detected*\n"

    validation_rows = ""
    if not v:
        validation_rows = "**All checks passed**\n"
    else:
        for item in v:
            icon = "OK" if item["severity"] == "ok" else "ERR" if item["severity"] == "error" else "WARN"
            validation_rows += f"**[{icon}] {item['field']}**: {item['message']}\n\n"

    md = f"""# Property Document Verification Report

> **South of Truth** -- Automated property document intelligence

| | |
|:---|:---|
| **Session ID** | `{session_id}` |
| **Exported** | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} |
| **OCR Provider** | `{session.get('ocr_provider', 'unknown')}` |
| **Original File** | `{session.get('filename', 'unknown')}` |
| **Processing Time** | {session.get('processing_time_ms', 0)}ms |

---

## Extracted Data

### Document

| Field | Value |
|:------|:------|
| **Document Type** | {e.get('document_type') or '*Not detected*'} |
| **Title Reference** | `{e.get('title_reference') or 'N/A'}` |
| **ABN** | {e.get('abn') or 'N/A'} |
| **Confidence** | {(e.get('ocr_confidence') or 0) * 100:.0f}% |

### Registered Proprietor

| Field | Value |
|:------|:------|
| **Names** | {', '.join(e.get('registered_proprietor', {}).get('names', [])) or '*Not detected*'} |
| **Address** | {e.get('registered_proprietor', {}).get('address') or 'N/A'} |
| **Tenancy** | {e.get('registered_proprietor', {}).get('tenancy') or 'N/A'} |

### Property

| Field | Value |
|:------|:------|
| **Address** | {e.get('property', {}).get('address') or '*Not detected*'} |
| **Lot** | {e.get('property', {}).get('lot') or 'N/A'} |
| **Plan** | {e.get('property', {}).get('plan') or 'N/A'} |
| **LGA** | {e.get('property', {}).get('lga') or 'N/A'} |
| **State** | {e.get('property', {}).get('state') or 'N/A'} |

### Encumbrances
{enc_rows}
---

## Validation Results

{validation_rows}
---

## Summary

| Metric | Count |
|:-------|------:|
| Total Checks | {s.get('total_checks', 0)} |
| Passed | {s.get('passed', 0)} |
| Errors | {s.get('errors', 0)} |
| Warnings | {s.get('warnings', 0)} |
| **Valid** | **{'Yes' if s.get('is_valid') else 'No'}** |

---

*This report was generated automatically by South of Truth and should be verified by a licensed conveyancer or legal professional.*
"""
    return PlainTextResponse(
        md, media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=south-of-truth-{session_id[:8]}.md"})

@router.get("/export/pdf/{session_id}")
async def export_pdf(session_id: str):
    session = _db_get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    e = session.get("extracted_data", {})
    v = (session.get("results") or {}).get("validation", [])
    s = (session.get("results") or {}).get("summary", {})
    try:
        from fpdf import FPDF
    except ImportError:
        raise HTTPException(500, "PDF export requires fpdf2. Install: pip install fpdf2")

    class SOTPDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 16)
            self.set_text_color(201, 169, 110)
            self.cell(0, 10, "South of Truth", ln=True, align="C")
            self.set_font("Helvetica", "", 10)
            self.set_text_color(100, 100, 110)
            self.cell(0, 6, "Property Document Verification Report", ln=True, align="C")
            self.ln(2)
            self.set_draw_color(201, 169, 110)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 160)
            self.cell(0, 10, f"Page {self.page_no()} | Session: {session_id[:8]}... | {datetime.utcnow().strftime('%Y-%m-%d')}", align="C")

    pdf = SOTPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)

    # Meta section
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(40, 40, 50)
    pdf.cell(0, 8, "Document Information", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 90)
    pdf.cell(50, 6, "Session ID:", 0)
    pdf.cell(0, 6, session_id, ln=True)
    pdf.cell(50, 6, "Exported:", 0)
    pdf.cell(0, 6, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), ln=True)
    pdf.cell(50, 6, "OCR Provider:", 0)
    pdf.cell(0, 6, session.get("ocr_provider", "unknown"), ln=True)
    pdf.cell(50, 6, "Original File:", 0)
    pdf.cell(0, 6, session.get("filename", "unknown"), ln=True)
    pdf.ln(5)

    def _safe(val):
        """Return display string for any field value."""
        if val is None or val == "" or val == "null":
            return "-"
        if isinstance(val, (int, float)):
            return str(val)
        # Replace em dashes with regular hyphens (helvetica doesn't support Unicode)
        return str(val).replace("\u2014", "-").replace("\u2013", "-").replace("\u2012", "-")

    def _row(label, value, label_width=55):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 110)
        pdf.cell(label_width, 6, label, 0)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(0, 6, _safe(value), ln=True)

    def _section_header(title):
        pdf.ln(2)
        pdf.set_draw_color(201, 169, 110)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(201, 169, 110)
        pdf.cell(0, 7, title, ln=True)
        pdf.ln(1)

    def _divider():
        pdf.ln(2)
        pdf.set_draw_color(200, 200, 210)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    doc_type = e.get("document_type", "unknown")

    if doc_type == "settlement_statement":
        # ── Settlement Statement layout ──────────────────────────────
        _section_header("SETTLEMENT STATEMENT")
        _row("Matter Number",     e.get("matter_number"))
        _row("Preparer",          e.get("preparer"))
        _row("Preparer ABN",      e.get("preparer_abn"))
        _row("Property Address",  e.get("property_address"))
        _row("Lot / Plan",        e.get("lot_plan"))
        pdf.ln(2)
        _row("Vendor",           e.get("vendor_name"))
        _row("Purchaser",        e.get("purchaser_name"))
        pdf.ln(2)
        _row("Contract Date",    e.get("contract_date"))
        _row("Settlement Date",  e.get("settlement_date"))
        _row("Adjustment Date",  e.get("adjustment_date"))
        _row("Settlement Time",  e.get("settlement_time"))
        pdf.ln(2)
        _row("Water Reading",   f"{e.get('water_reading_kL', '—')} kL")
        _row("Water Rate/kL",    e.get("water_rate_per_kL"))
        _row("Land Tax",         e.get("land_tax"))
        _row("Body Corporate",   e.get("body_corp"))
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Deposit Amount", 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 100, 64)
        pdf.cell(0, 7, _safe(e.get("deposit_amount")), ln=True)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Balance Due", 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(201, 169, 110)
        pdf.cell(0, 7, _safe(e.get("balance_due")), ln=True)

    elif doc_type == "form_2_1":
        _section_header("FORM 2.1 — TRANSFER OF LAND")
        _row("Form Number",       e.get("form_number"))
        _row("Lodgement Date",    e.get("lodgement_date"))
        _row("Processing Code",   e.get("processing_code"))
        pdf.ln(2)
        _row("Transferor",        e.get("transferor_name"))
        _row("Transferor Address",e.get("transferor_address"))
        pdf.ln(2)
        _row("Transferee",        e.get("transferee_name"))
        _row("Transferee Address",e.get("transferee_address"))
        pdf.ln(2)
        _row("Title Reference",   e.get("title_reference"))
        _row("Lot / Plan",        e.get("lot_plan"))
        _row("Parish",            e.get("parish"))
        _row("County",            e.get("county"))
        pdf.ln(2)
        _row("Consideration",     e.get("consideration"))
        _row("Stamp Duty",        e.get("stamp_duty"))
        _row("Execution Date",    e.get("execution_date"))
        _row("Witness",           e.get("witness_name"))
        _row("Witness Occupation",e.get("witness_occupation"))

    elif doc_type == "contract_of_sale":
        _section_header("CONTRACT OF SALE")
        _row("Vendor",           e.get("vendor_name"))
        _row("Vendor ABN",       e.get("vendor_abn"))
        _row("Purchaser",        e.get("purchaser_name"))
        _row("Purchaser Address",e.get("purchaser_address"))
        pdf.ln(2)
        _row("Property Address", e.get("property_address"))
        _row("Lot / Plan",       e.get("lot_plan"))
        _row("Title Reference",  e.get("title_reference"))
        pdf.ln(2)
        _row("Contract Date",    e.get("contract_date"))
        _row("Settlement Date",  e.get("settlement_date"))
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Purchase Price", 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(201, 169, 110)
        pdf.cell(0, 7, _safe(e.get("purchase_price")), ln=True)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Deposit", 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(0, 7, _safe(e.get("deposit_amount")), ln=True)
        pdf.cell(55, 7, "Balance", 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, _safe(e.get("balance_amount")), ln=True)
        pdf.ln(2)
        _row("Agent",            e.get("agent_name"))
        _row("Agent License",    e.get("agent_license"))

    elif doc_type == "trust_account_statement":
        _section_header("TRUST ACCOUNT STATEMENT")
        _row("Law Practice",     e.get("law_practice"))
        _row("ABN",             e.get("abn"))
        _row("Account Name",     e.get("account_name"))
        _row("Account Number",   e.get("account_number"))
        pdf.ln(2)
        _row("Client",          e.get("client_name"))
        _row("Matter Reference", e.get("matter_reference"))
        _row("Property Address", e.get("property_address"))
        pdf.ln(2)
        _row("Statement Date",  e.get("statement_date"))
        _row("Period",          e.get("statement_period"))
        pdf.ln(2)
        _row("Total Debits",     e.get("total_debits"))
        _row("Total Credits",    e.get("total_credits"))
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Closing Balance", 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(201, 169, 110)
        pdf.cell(0, 7, _safe(e.get("closing_balance")), ln=True)
        # Transactions
        trans = e.get("transactions") or []
        if trans:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(40, 40, 50)
            pdf.cell(25, 6, "Date", 1)
            pdf.cell(70, 6, "Description", 1)
            pdf.cell(35, 6, "Debit", 1)
            pdf.cell(35, 6, "Credit", 1, ln=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(80, 80, 90)
            for t in trans[:10]:
                pdf.cell(25, 6, _safe(t.get("date")), 1)
                pdf.cell(70, 6, _safe(t.get("description"))[:40], 1)
                pdf.cell(35, 6, _safe(t.get("debit")), 1)
                pdf.cell(35, 6, _safe(t.get("credit")), 1, ln=True)

    elif doc_type == "final_letter":
        _section_header("FINAL SETTLEMENT LETTER")
        _row("Firm",            e.get("firm_name"))
        _row("Firm ABN",        e.get("firm_abn"))
        _row("Firm Address",     e.get("firm_address"))
        _row("Phone",           e.get("firm_phone"))
        pdf.ln(2)
        _row("Client",          e.get("client_name"))
        _row("Property Address", e.get("property_address"))
        _row("Matter Reference", e.get("matter_reference"))
        pdf.ln(2)
        _row("Settlement Date",  e.get("settlement_date"))
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Purchase Price", 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(201, 169, 110)
        pdf.cell(0, 7, _safe(e.get("purchase_price")), ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 50)
        _row("Adjustments",     e.get("adjustments"))
        _row("Fees",            e.get("fees"))
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 50)
        pdf.cell(55, 7, "Total Amount", 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(201, 169, 110)
        pdf.cell(0, 7, _safe(e.get("total_amount")), ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 50)
        _row("Cheque Details",  e.get("cheque_details"))
        _row("Keys / Possession", e.get("keys_collection"))

    else:
        # Generic layout (certificate_of_title, section_32, unknown)
        _section_header("EXTRACTED DATA")
        _row("Document Type:", e.get("document_type"))
        _row("Title Reference:", e.get("title_reference"))
        _row("ABN:", e.get("abn"))
        _row("Confidence:", f"{(e.get('ocr_confidence') or 0) * 100:.0f}%")

        prop = e.get("registered_proprietor", {})
        if prop:
            pdf.ln(3)
            _section_header("REGISTERED PROPRIETOR")
            if prop.get("names"):
                _row("Names:", ", ".join(prop["names"]) if isinstance(prop["names"], list) else prop["names"])
            _row("Address:", prop.get("address"))
            _row("Tenancy:", prop.get("tenancy"))

        pr = e.get("property", {})
        if pr:
            pdf.ln(3)
            _section_header("PROPERTY")
            _row("Address:", pr.get("address"))
            _row("Lot:", pr.get("lot"))
            _row("Plan:", pr.get("plan"))
            _row("LGA:", pr.get("lga"))
            _row("State:", pr.get("state"))

        enc = e.get("encumbrances") or []
        if enc:
            pdf.ln(3)
            _section_header(f"ENCUMBRANCES ({len(enc)})")
            for en in enc:
                _row(f"  {en.get('type', '—')}:", f"{en.get('to', '—')} ({en.get('amount', '—')})")

    # ── Validation results ────────────────────────────────────────────
    _divider()
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(40, 40, 50)
    pdf.cell(0, 8, "Validation Results", ln=True)

    if not v:
        pdf.set_text_color(74, 222, 128)
        pdf.cell(0, 7, "All checks passed", ln=True)
    else:
        for item in v:
            if item["severity"] == "ok":
                pdf.set_text_color(74, 222, 128)
                label = "OK"
            elif item["severity"] == "error":
                pdf.set_text_color(248, 113, 113)
                label = "ERR"
            else:
                pdf.set_text_color(251, 191, 36)
                label = "WARN"
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 7, f"[{label}] {item['field']}", ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(100, 100, 110)
            pdf.cell(0, 6, f"   {item['message']}", ln=True)

    pdf.ln(5)
    pdf.set_draw_color(200, 200, 210)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 160)
    pdf.multi_cell(0, 5, "This report was generated automatically by South of Truth and should be verified by a licensed conveyancer or legal professional.")

    pdf_bytes = pdf.output()
    if isinstance(pdf_bytes, bytearray):
        pdf_bytes = bytes(pdf_bytes)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=south-of-truth-{session_id[:8]}.pdf"})
