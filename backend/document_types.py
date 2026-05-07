"""
Document type definitions and field schemas for South of Truth.

Each document type has:
  - schema: what fields to extract
  - prompt: the AI prompt tailored to that document type
  - validators: field-level validation rules
  - cross_field_rules: multi-field validation
"""

from typing import Dict, Any, List, Callable

DOCUMENT_TYPES = {
    "settlement_statement": {
        "label": "Settlement Statement",
        "description": "Conveyancer's settlement statement showing financial adjustments",
        "examples": ["KT:200156", "Stellar Conveyancing", "78-80 Main Street, Kandanga"],
        "fields": [
            "matter_number", "date_prepared", "settlement_date", "adjustment_date",
            "contract_date", "preparer", "preparer_abn",
            "vendor_name", "purchaser_name",
            "property_address", "lot_plan",
            "adjustments", "rates", "water", "land_tax", "body_corp",
            "deposit_amount", "balance_due", "settlement_time"
        ],
        "ocr_confidence_target": 0.80,
    },
    "form_2_1": {
        "label": "Form 2.1 (Transfer of Land)",
        "description": "Queensland Land Registry transfer form",
        "examples": ["Form 2.1", "Transfer of land", "Lodgement", "MR"],
        "fields": [
            "form_number", "lodgement_date", "processing_code",
            "transferor_name", "transferor_address",
            "transferee_name", "transferee_address",
            "title_reference", "lot_plan", "parish", "county",
            "consideration", "stamp_duty",
            "execution_date", "witness_name", "witness_occupation"
        ],
        "ocr_confidence_target": 0.75,
    },
    "contract_of_sale": {
        "label": "Contract of Sale",
        "description": "Signed contract between vendor and purchaser",
        "examples": ["Contract of Sale", "vendor", "purchaser", "chattels", "inclusions"],
        "fields": [
            "contract_date", "settlement_date", "vendor_name", "vendor_abn",
            "purchaser_name", "purchaser_address",
            "property_address", "lot_plan", "title_reference",
            "purchase_price", "deposit_amount", "balance_amount",
            "inclusions", "exclusions", "special_conditions",
            "agent_name", "agent_license"
        ],
        "ocr_confidence_target": 0.85,
    },
    "certificate_of_title": {
        "label": "Certificate of Title",
        "description": "Land title document from land registry",
        "examples": ["Title Reference", "Registered Proprietor", "Encumbrance", "Folio"],
        "fields": [
            "title_reference", "volume_folio",
            "lot_plan", "parish", "county", "register_type",
            "proprietor_name", "proprietor_address", "proprietor_tenancy",
            "encumbrances", "mortgage_number", "mortgagee",
            "caveats", "easements"
        ],
        "ocr_confidence_target": 0.80,
    },
    "section_32": {
        "label": "Section 32 Vendor Statement",
        "description": "VIC vendor disclosure statement",
        "examples": ["Section 32", "vendor statement", "S.32"],
        "fields": [
            "vendor_name", "vendor_address", "land_address",
            "title_reference", "lot_plan",
            "rates_adjustments", "outgoings", "encumbrances",
            "building_woe_inspection", "pest_ inspection",
            "special_matters", "claims"
        ],
        "ocr_confidence_target": 0.75,
    },
    "trust_account_statement": {
        "label": "Trust Account Statement",
        "description": "Conveyancer's trust account ledger",
        "examples": ["Trust Account", "Stellar Conveyancing", "Transaction History"],
        "fields": [
            "law_practice", "abn", "account_name", "account_number",
            "client_name", "client_reference",
            "property_address", "matter_reference",
            "transactions", "debits", "credits", "balance",
            "statement_date", "statement_period"
        ],
        "ocr_confidence_target": 0.80,
    },
    "final_letter": {
        "label": "Final Settlement Letter",
        "description": "Conveyancer's completion letter to client",
        "examples": ["settlement", "congratulations", "keys", "final figures"],
        "fields": [
            "firm_name", "firm_abn", "firm_address", "firm_phone",
            "client_name", "client_address",
            "property_address", "matter_reference",
            "settlement_date", "purchase_price",
            "adjustments", "fees", "total_amount",
            "cheque_details", "keys_collection"
        ],
        "ocr_confidence_target": 0.80,
    }
}

# Field extraction prompts per document type
EXTRACTION_PROMPTS = {
    "settlement_statement": """You are extracting data from an Australian Settlement Statement prepared by a conveyancer.

Extract ALL visible fields. Return ONLY valid JSON.

JSON structure:
{
  "document_type": "settlement_statement",
  "matter_number": "e.g. KT:200156",
  "date_prepared": "DD/MM/YYYY",
  "settlement_date": "DD/MM/YYYY",
  "adjustment_date": "DD/MM/YYYY",
  "contract_date": "DD/MM/YYYY",
  "preparer": "firm name, e.g. Stellar Conveyancing",
  "preparer_abn": "11-digit ABN or null",
  "vendor_name": "vendor name(s)",
  "purchaser_name": "purchaser name(s)",
  "property_address": "full street address with suburb and state",
  "lot_plan": "lot/plan e.g. Lot 1 RP123456",
  "water_reading_kL": number or null,
  "water_rate_per_kL": "$X.XXX",
  "land_tax": "$X,XXX.XX or N/A or null",
  "body_corp": "$X,XXX.XX or N/A or null",
  "deposit_amount": "$X,XXX.XX or null",
  "balance_due": "$X,XXX.XX",
  "settlement_time": "time of settlement",
  "ocr_confidence": 0.0-1.0
}

Rules: Return null for missing fields. Amounts in dollars. State in QLD/NSW/VIC etc.""",

    "form_2_1": """You are extracting data from a Queensland Form 2.1 (Transfer of Land).

This is a scanned government form. Extract ALL visible fields carefully.

JSON structure:
{
  "document_type": "form_2_1",
  "form_number": "e.g. Form 2.1",
  "lodgement_date": "DD/MM/YYYY or null",
  "processing_code": "e.g. MR or null",
  "transferor_name": "name(s) of current owner(s)",
  "transferor_address": "address of transferor or null",
  "transferee_name": "name(s) of new owner(s)",
  "transferee_address": "address of transferee or null",
  "title_reference": "e.g. 1234/567890",
  "lot_plan": "Lot X on Plan YYYY",
  "parish": "parish name or null",
  "county": "county name or null",
  "register_type": "e.g. Real Property or null",
  "consideration": "$amount or null",
  "stamp_duty": "$amount or null",
  "execution_date": "DD/MM/YYYY or null",
  "witness_name": "name of witness or null",
  "witness_occupation": "occupation or null",
  "ocr_confidence": 0.0-1.0
}

Rules: Return null for missing fields. Look for handwritten or typed entries. If scanned, try to read faint text.""",

    "contract_of_sale": """You are extracting data from an Australian Contract of Sale.

Extract ALL visible fields. Return ONLY valid JSON.

JSON structure:
{
  "document_type": "contract_of_sale",
  "contract_date": "DD/MM/YYYY",
  "settlement_date": "DD/MM/YYYY",
  "vendor_name": "full vendor name(s) or company name",
  "vendor_abn": "11-digit ABN or null",
  "purchaser_name": "full purchaser name(s) or company name",
  "purchaser_address": "address or null",
  "property_address": "full street address with suburb and state",
  "lot_plan": "lot/plan e.g. Lot 1 on SP123456",
  "title_reference": "title ref or null",
  "purchase_price": "$X,XXX,XXX.XX",
  "deposit_amount": "$X,XXX.XX",
  "balance_amount": "$X,XXX.XXX.XX",
  "inclusions": "list of chattels/inclusions or null",
  "exclusions": "list of exclusions or null",
  "special_conditions": "any special conditions or null",
  "agent_name": "agent/firm name or null",
  "agent_license": "license number or null",
  "ocr_confidence": 0.0-1.0
}

Rules: Return null for missing. Look for signature blocks. Price in dollars.""",

    "certificate_of_title": """You are extracting data from an Australian Certificate of Title.

Extract ALL visible fields. Return ONLY valid JSON.

JSON structure:
{
  "document_type": "certificate_of_title",
  "title_reference": "e.g. Vol 5678 Fol 90 or LP12345",
  "volume_folio": "e.g. Vol X Fol Y or null",
  "lot_plan": "e.g. Lot X on Plan YYYY",
  "parish": "parish name or null",
  "county": "county name or null",
  "register_type": "Real Property or null",
  "proprietor_name": "registered proprietor name(s)",
  "proprietor_address": "address or null",
  "proprietor_tenancy": "Joint Tenants | Tenants in Common | Sole | null",
  "encumbrances": [{"type": "Mortgage|Caveat|Easement|Covenant", "registered_number": "string", "to": "string", "amount": null, "registered_date": "DD/MM/YYYY or null"}],
  "mortgage_number": "mortgage number or null",
  "mortgagee": "mortgagee bank name or null",
  "caveats": ["caveat holder names"] or [],
  "easements": ["easement descriptions"] or [],
  "ocr_confidence": 0.0-1.0
}

Rules: Return null for missing. Encumbrances as array of objects.""",

    "section_32": """You are extracting data from a Victorian Section 32 Vendor Statement.

Extract ALL visible fields. Return ONLY valid JSON.

JSON structure:
{
  "document_type": "section_32",
  "vendor_name": "vendor name(s)",
  "vendor_address": "address or null",
  "land_address": "address of land being sold",
  "title_reference": "e.g. Vol 1234 Fol 567",
  "lot_plan": "lot/plan or null",
  "rates_adjustments": "rate and adjustment details or null",
  "outgoings": "outgoing amounts or null",
  "encumbrances": "existing encumbrances or null",
  "building_woe_inspection": "date or N/A or null",
  "pest_inspection": "date or N/A or null",
  "special_matters": "special matters or null",
  "claims": "any applicable claims or null",
  "ocr_confidence": 0.0-1.0
}

Rules: Return null for missing.""",

    "trust_account_statement": """You are extracting data from a Conveyancer's Trust Account Statement.

Extract ALL visible fields. Return ONLY valid JSON.

JSON structure:
{
  "document_type": "trust_account_statement",
  "law_practice": "firm name, e.g. Stellar Conveyancing Pty Ltd",
  "abn": "11-digit ABN",
  "account_name": "Trust Account name",
  "account_number": "account number or null",
  "client_name": "client name",
  "client_reference": "matter reference",
  "property_address": "property address",
  "matter_reference": "e.g. KT:200156",
  "statement_date": "DD/MM/YYYY or null",
  "statement_period": "period covered or null",
  "transactions": [{"date": "DD/MM/YYYY", "description": "string", "debit": "$X,XXX.XX", "credit": "$X,XXX.XX", "balance": "$X,XXX.XX"}],
  "total_debits": "$X,XXX.XX or null",
  "total_credits": "$X,XXX.XX or null",
  "closing_balance": "$X,XXX.XX or null",
  "ocr_confidence": 0.0-1.0
}

Rules: Extract transaction rows as array. Amounts in dollars.""",

    "final_letter": """You are extracting data from a Conveyancer's Final Settlement Letter to client.

Extract ALL visible fields. Return ONLY valid JSON.

JSON structure:
{
  "document_type": "final_letter",
  "firm_name": "firm name, e.g. Stellar Conveyancing Pty Ltd",
  "firm_abn": "11-digit ABN",
  "firm_address": "address or null",
  "firm_phone": "phone number or null",
  "client_name": "client name",
  "client_address": "address or null",
  "property_address": "property address",
  "matter_reference": "e.g. KT:200156",
  "settlement_date": "DD/MM/YYYY or null",
  "purchase_price": "$X,XXX,XXX.XX or null",
  "adjustments": "financial adjustments or null",
  "fees": "professional fees or null",
  "total_amount": "total amount or null",
  "cheque_details": "cheque/payment details or null",
  "keys_collection": "keys/possession details or null",
  "ocr_confidence": 0.0-1.0
}

Rules: Return null for missing. Extract all financial figures.""",
}


# Post-processing rules per document type
# Each rule is a function that takes extracted data and returns corrected data
POST_PROCESSORS: Dict[str, List[Callable]] = {}


def validate_settlement_statement(data: Dict[str, Any]) -> List[Dict]:
    """Validate settlement statement fields."""
    errors = []
    if not data.get("property_address"):
        errors.append({"field": "property_address", "severity": "error", "message": "No property address found"})
    if not data.get("settlement_date"):
        errors.append({"field": "settlement_date", "severity": "error", "message": "No settlement date"})
    if data.get("matter_number"):
        errors.append({"field": "matter_number", "severity": "ok", "message": f"Matter: {data['matter_number']}"})
    return errors


def validate_form_2_1(data: Dict[str, Any]) -> List[Dict]:
    """Validate Form 2.1 fields."""
    errors = []
    if not data.get("transferee_name"):
        errors.append({"field": "transferee_name", "severity": "error", "message": "No transferee name found"})
    if not data.get("lot_plan"):
        errors.append({"field": "lot_plan", "severity": "warning", "message": "No lot/plan found — may affect title registration"})
    if data.get("title_reference"):
        errors.append({"field": "title_reference", "severity": "ok", "message": f"Title: {data['title_reference']}"})
    return errors


def validate_contract_of_sale(data: Dict[str, Any]) -> List[Dict]:
    """Validate contract of sale fields."""
    errors = []
    if not data.get("vendor_name"):
        errors.append({"field": "vendor_name", "severity": "error", "message": "No vendor name found"})
    if not data.get("purchase_price"):
        errors.append({"field": "purchase_price", "severity": "error", "message": "No purchase price found"})
    if data.get("property_address"):
        errors.append({"field": "property_address", "severity": "ok", "message": "Property address found"})
    return errors


def validate_certificate_of_title(data: Dict[str, Any]) -> List[Dict]:
    """Validate certificate of title fields."""
    errors = []
    if not data.get("title_reference"):
        errors.append({"field": "title_reference", "severity": "error", "message": "No title reference found"})
    if not data.get("proprietor_name"):
        errors.append({"field": "proprietor_name", "severity": "error", "message": "No proprietor name found"})
    enc = data.get("encumbrances") or []
    if enc:
        errors.append({"field": "encumbrances", "severity": "info", "message": f"{len(enc)} encumbrance(s) found"})
    return errors


def validate_trust_account(data: Dict[str, Any]) -> List[Dict]:
    """Validate trust account statement fields."""
    errors = []
    if not data.get("law_practice"):
        errors.append({"field": "law_practice", "severity": "error", "message": "No law practice name found"})
    if not data.get("client_name"):
        errors.append({"field": "client_name", "severity": "warning", "message": "No client name found"})
    trans = data.get("transactions") or []
    if trans:
        errors.append({"field": "transactions", "severity": "ok", "message": f"{len(trans)} transaction(s)"})
    return errors


def validate_final_letter(data: Dict[str, Any]) -> List[Dict]:
    """Validate final letter fields."""
    errors = []
    if not data.get("firm_name"):
        errors.append({"field": "firm_name", "severity": "error", "message": "No firm name found"})
    if not data.get("property_address"):
        errors.append({"field": "property_address", "severity": "warning", "message": "No property address found"})
    return errors


# Route validators
DOCUMENT_VALIDATORS = {
    "settlement_statement": validate_settlement_statement,
    "form_2_1": validate_form_2_1,
    "contract_of_sale": validate_contract_of_sale,
    "certificate_of_title": validate_certificate_of_title,
    "section_32": validate_final_letter,  # reuse
    "trust_account_statement": validate_trust_account,
    "final_letter": validate_final_letter,
}


def get_prompt(document_type: str) -> str:
    """Get the extraction prompt for a document type."""
    return EXTRACTION_PROMPTS.get(document_type, EXTRACTION_PROMPTS.get("settlement_statement"))


def get_validator(document_type: str):
    """Get the validator for a document type."""
    return DOCUMENT_VALIDATORS.get(document_type, lambda d: [])