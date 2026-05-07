"""
Australian property document validators.
Title reference regex by state, ABN checksum, cross-field validation.
"""
import re
from typing import List, Dict, Any, Optional

# Title reference patterns by Australian state/territory
TITLE_PATTERNS = {
    "VIC": re.compile(r"^(?:Vol\s+\d+\s+Fol\s+\d+|LP\d+)$"),
    "NSW": re.compile(r"^(?:\d+/\d+|DP\d+|SP\d+)$"),
    "QLD": re.compile(r"^Lot\s+\d+\s+on\s+(?:SP|RP|CP)\d+$"),
    "SA": re.compile(r"^(?:CT\s+\d+|CR\s+\d+)$"),
    "WA": re.compile(r"^(?:Volume\s+\d+\s+Folio\s+\d+|L\s?\d+)$"),
    "TAS": re.compile(r"^(?:CT\s+\d+|B?\d+/\d+)$"),
    "ACT": re.compile(r"^(?:CT\s+\d+|L\s?\d+)$"),
    "NT": re.compile(r"^(?:CT\s+\d+|L\s?\d+)$"),
}

# Document type detection patterns
DOC_TYPE_PATTERNS = {
    "certificate_of_title": [
        re.compile(r"certificate\s+of\s+title", re.I),
        re.compile(r"title\s+reference", re.I),
        re.compile(r"registered\s+proprietor", re.I),
    ],
    "contract_of_sale": [
        re.compile(r"contract\s+of\s+sale", re.I),
        re.compile(r"vendor", re.I),
        re.compile(r"purchaser", re.I),
    ],
    "strata_title": [
        re.compile(r"strata", re.I),
        re.compile(r" Owners?\s+Corporation", re.I),
    ],
    "section_32": [
        re.compile(r"section\s+32", re.I),
        re.compile(r"vendor\s+statement", re.I),
    ],
}


def validate_title_reference(title: str, state: Optional[str] = None) -> Dict[str, Any]:
    """Validate an Australian title reference string."""
    if not title or not title.strip():
        return {"valid": False, "error": "Title reference is empty", "state": None}
    
    title_clean = title.strip()
    
    if state and state.upper() in TITLE_PATTERNS:
        if TITLE_PATTERNS[state.upper()].match(title_clean):
            return {"valid": True, "state": state.upper(), "format": "matched"}
        return {"valid": False, "error": f"Does not match {state} format", "state": state.upper()}
    
    # Try all states
    for state_code, pattern in TITLE_PATTERNS.items():
        if pattern.match(title_clean):
            return {"valid": True, "state": state_code, "format": "auto-detected"}
    
    return {"valid": False, "error": "No state format matched", "state": None}


def validate_abn(abn: str) -> bool:
    """Validate an Australian Business Number using weighted checksum."""
    abn = re.sub(r"\D", "", abn)
    if len(abn) != 11:
        return False
    
    weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    digits = [int(c) for c in abn]
    digits[0] -= 1
    
    total = sum(d * w for d, w in zip(digits, weights))
    return total % 89 == 0


def detect_document_type(text: str) -> str:
    """Detect document type from raw text using pattern matching."""
    text_lower = text.lower()
    scores = {}
    for doc_type, patterns in DOC_TYPE_PATTERNS.items():
        scores[doc_type] = sum(1 for p in patterns if p.search(text_lower))
    
    if not scores:
        return "unknown"
    
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


def validate_extracted_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all validations on extracted document data. Returns list of errors/warnings."""
    errors = []
    
    # Title reference validation
    title = data.get("title_reference", "")
    state = data.get("property", {}).get("state")
    title_check = validate_title_reference(title, state)
    if not title_check["valid"]:
        errors.append({"field": "title_reference", "severity": "error", "message": title_check["error"]})
    else:
        errors.append({"field": "title_reference", "severity": "ok", "message": f"Valid ({title_check['state']})"})
    
    # ABN validation
    abn = data.get("abn", "")
    if abn:
        if validate_abn(str(abn)):
            errors.append({"field": "abn", "severity": "ok", "message": "Valid ABN"})
        else:
            errors.append({"field": "abn", "severity": "warning", "message": "Invalid ABN checksum"})
    
    # Proprietor presence
    proprietor = data.get("registered_proprietor", {})
    if not proprietor.get("names"):
        errors.append({"field": "registered_proprietor", "severity": "error", "message": "No proprietor names found"})
    else:
        errors.append({"field": "registered_proprietor", "severity": "ok", "message": f"Found {len(proprietor['names'])} name(s)"})
    
    # Property address
    prop = data.get("property", {})
    if not prop.get("address"):
        errors.append({"field": "property.address", "severity": "warning", "message": "No property address extracted"})
    else:
        errors.append({"field": "property.address", "severity": "ok", "message": "Address present"})
    
    # Confidence threshold
    conf = data.get("ocr_confidence", 0)
    if conf < 0.6:
        errors.append({"field": "ocr_confidence", "severity": "warning", "message": f"Low confidence: {conf:.2f}"})
    
    return errors
