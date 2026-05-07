"""
Mock OCR Provider — returns realistic property data without API calls.
Use for: testing, frontend development, demos without OpenAI credits.
"""
import os
import time
import logging
from typing import Dict, Any
from .ocr_interface import BaseOCRProvider, OCRResult, factory

logger = logging.getLogger(__name__)


class MockOCRProvider(BaseOCRProvider):
    """Pre-canned responses for rapid development and testing."""
    
    MOCK_RESPONSES = {
        "default": {
            "document_type": "certificate_of_title",
            "title_reference": "Vol 5678 Fol 90",
            "registered_proprietor": {
                "names": ["Jane Elizabeth Smith", "John Robert Smith"],
                "address": "42 Wallaby Way, Sydney NSW 2000",
                "tenancy": "Joint Tenants"
            },
            "property": {
                "lot": "42",
                "plan": "DP123456",
                "address": "42 Wallaby Way, Sydney NSW 2000",
                "lga": "City of Sydney",
                "state": "NSW"
            },
            "encumbrances": [
                {
                    "type": "Mortgage",
                    "registered_number": "M123456",
                    "to": "Commonwealth Bank of Australia",
                    "amount": 850000,
                    "registered_date": "2023-01-15"
                }
            ],
            "abn": "12345678901",
            "ocr_confidence": 0.92
        },
        "settlement_statement": {
            "document_type": "settlement_statement",
            "matter_number": "KT:200156",
            "date_prepared": "08/04/2024",
            "settlement_date": "09/04/2020",
            "adjustment_date": "09/04/2020",
            "contract_date": "20/01/2020",
            "preparer": "Stellar Conveyancing",
            "preparer_abn": "49160054786",
            "vendor_name": "Rochford",
            "purchaser_name": "Lewinsohn",
            "property_address": "78-80 Main Street, Kandanga QLD 4570",
            "lot_plan": "Lot 1 RP843216",
            "water_reading_kL": 1050,
            "water_rate_per_kL": "$1.170",
            "land_tax": "N/A",
            "body_corp": "N/A",
            "deposit_amount": "$100,000.00",
            "balance_due": "$785,000.00",
            "settlement_time": "2:00 PM",
            "ocr_confidence": 0.90
        },
        "form_2_1": {
            "document_type": "form_2_1",
            "form_number": "Form 2.1",
            "lodgement_date": "17/02/2020",
            "processing_code": "MR",
            "transferor_name": "Rochford Holdings Pty Ltd",
            "transferor_address": "PO Box 123, Brisbane QLD 4000",
            "transferee_name": "Mark Lewinsohn",
            "transferee_address": "78-80 Main Street, Kandanga QLD 4570",
            "title_reference": "1234/789012",
            "lot_plan": "Lot 1 RP843216",
            "parish": "Kandanga",
            "county": "Cunningham",
            "register_type": "Real Property",
            "consideration": "$885,000.00",
            "stamp_duty": "$35,400.00",
            "execution_date": "20/01/2020",
            "witness_name": "J. Smith",
            "witness_occupation": "Solicitor",
            "ocr_confidence": 0.88
        },
        "contract_of_sale": {
            "document_type": "contract_of_sale",
            "contract_date": "20/01/2020",
            "settlement_date": "09/04/2020",
            "vendor_name": "Rochford Holdings Pty Ltd",
            "vendor_abn": "98765432109",
            "purchaser_name": "Mark Lewinsohn",
            "purchaser_address": "15 Hill Street, Noosa Heads QLD 4567",
            "property_address": "78-80 Main Street, Kandanga QLD 4570",
            "lot_plan": "Lot 1 RP843216",
            "title_reference": "1234/789012",
            "purchase_price": "$885,000.00",
            "deposit_amount": "$100,000.00",
            "balance_amount": "$785,000.00",
            "inclusions": "All fixtures and fittings as inspected",
            "exclusions": "Vendor's personal effects",
            "special_conditions": "Subject to satisfactory building and pest inspection",
            "agent_name": "Ray White Gympie",
            "agent_license": "RE/123456",
            "ocr_confidence": 0.90
        },
        "trust_account_statement": {
            "document_type": "trust_account_statement",
            "law_practice": "Stellar Conveyancing Pty Ltd",
            "abn": "49160054786",
            "account_name": "Law Practice Trust Account",
            "account_number": "50815371",
            "client_name": "Mark Lewinsohn",
            "client_reference": "MR/Lewinsohn/Purchase",
            "property_address": "78-80 Main Street, Kandanga QLD 4570",
            "matter_reference": "KT:200156",
            "statement_date": "09/04/2020",
            "statement_period": "01/01/2020 - 09/04/2020",
            "transactions": [
                {"date": "22/01/2020", "description": "Deposit - Ray White", "debit": "$100,000.00", "credit": "", "balance": "$100,000.00"},
                {"date": "09/04/2020", "description": "Settlement - ANZ Bank", "debit": "", "credit": "$785,000.00", "balance": "$885,000.00"},
                {"date": "09/04/2020", "description": "Transfer to vendor", "debit": "$885,000.00", "credit": "", "balance": "$0.00"}
            ],
            "total_debits": "$985,000.00",
            "total_credits": "$985,000.00",
            "closing_balance": "$0.00",
            "ocr_confidence": 0.88
        },
        "final_letter": {
            "document_type": "final_letter",
            "firm_name": "Stellar Conveyancing Pty Ltd",
            "firm_abn": "49160054786",
            "firm_address": "Noosa Civic, Eenie Creek Road, Noosaville QLD 4566",
            "firm_phone": "1300 51 61 71",
            "client_name": "Mark Lewinsohn",
            "client_address": "15 Hill Street, Noosa Heads QLD 4567",
            "property_address": "78-80 Main Street, Kandanga QLD 4570",
            "matter_reference": "KT:200156",
            "settlement_date": "9 April 2020",
            "purchase_price": "$885,000.00",
            "adjustments": "Rates, water, land tax adjusted to settlement date",
            "fees": "$3,850.00 incl GST",
            "total_amount": "$889,850.00",
            "cheque_details": "ANZ Bank cheque to be presented at settlement",
            "keys_collection": "Keys available from agent from 4 PM on settlement day",
            "ocr_confidence": 0.90
        }
    }

    def __init__(self):
        logger.info(f"Mock provider initialized")
        self._response_type = None

    async def extract(self, image_path: str, mime_type: str = "image/png", document_type: str = None) -> OCRResult:
        start = time.time()
        logger.info(f"Mock OCR processing: {image_path}")
        time.sleep(0.5)  # Simulate brief processing
        
        data = self.MOCK_RESPONSES.get(document_type, self.MOCK_RESPONSES["default"]).copy()
        elapsed = int((time.time() - start) * 1000)
        
        return OCRResult(
            raw_text="[MOCK] Property document extracted successfully",
            structured_data=data,
            confidence=data.get("ocr_confidence", 0.92),
            provider=self.name,
            pages_processed=1,
            processing_time_ms=elapsed
        )

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.name,
            "mode": "mock",
            "response_type": self.response_type
        }

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_local(self) -> bool:
        return True


# Register with factory
factory.register("mock", MockOCRProvider)
