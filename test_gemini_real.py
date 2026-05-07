#!/usr/bin/env python3
"""Quick test: Gemini with settlement statement using working models."""
import os, json, time
from google import genai
from google.genai.types import Part

api_key = os.getenv('GEMINI_API_KEY', '')
client = genai.Client(api_key=api_key)

test_img = '/Users/mrlltd/south-of-truth/uploads/441a3ffd-4989-482e-bde1-fc87b0549c70_page_0.png'
with open(test_img, 'rb') as f:
    img_bytes = f.read()

prompt = '''Extract from this Australian Settlement Statement. Return ONLY valid JSON:
{"document_type":"settlement_statement","matter_number":"e.g. KT:200156","settlement_date":"DD/MM/YYYY","contract_date":"DD/MM/YYYY","preparer":"firm name","preparer_abn":"11-digit or null","vendor_name":"vendor name","purchaser_name":"purchaser name","property_address":"full address","lot_plan":"lot/plan or null","water_reading_kL":number,"deposit_amount":"$X,XXX.XX","balance_due":"$X,XXX.XX","ocr_confidence":0.0-1.0}'''

models = ['gemini-flash-latest', 'gemini-2.5-flash-lite', 'gemini-2.0-flash-lite']

for model in models:
    print(f'Trying {model}...')
    try:
        resp = client.models.generate_content(
            model=model,
            contents=[prompt, Part.from_bytes(data=img_bytes, mime_type='image/png')],
            config={'temperature': 0.0, 'response_mime_type': 'application/json'}
        )
        raw = resp.text or ''
        print(f'✓ {model} -> {len(raw)} chars')
        print(raw[:300])
        data = json.loads(raw.strip())
        print('\nExtracted:')
        for k, v in sorted(data.items()):
            if v:
                print(f'  {k}: {v}')
        print(f'\nConfidence: {data.get("ocr_confidence")}')
        break
    except Exception as e:
        print(f'✗ {model}: {str(e)[:80]}')
        time.sleep(1)