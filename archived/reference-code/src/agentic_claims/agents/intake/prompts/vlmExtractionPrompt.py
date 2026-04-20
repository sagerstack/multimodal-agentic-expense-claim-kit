"""VLM structured extraction prompt template."""

VLM_EXTRACTION_PROMPT = """Extract all expense receipt fields from this image. Return a JSON object with two top-level keys:

1. "fields": A dictionary containing:
   - merchant: Business name (string)
   - date: Transaction date in YYYY-MM-DD format (string)
   - totalAmount: Total amount paid (number)
   - currency: Currency code (string, e.g., "USD", "EUR")
   - lineItems: Array of objects with "description" and "amount" keys
   - tax: Tax amount if present (number, or null)
   - paymentMethod: How it was paid (string, e.g., "Credit Card", "Cash")

2. "confidence": A dictionary with the same keys as "fields", each containing a confidence score (0.0 to 1.0)

Example response format:
{
  "fields": {
    "merchant": "Acme Corp",
    "date": "2024-03-15",
    "totalAmount": 125.50,
    "currency": "USD",
    "lineItems": [
      {"description": "Office Supplies", "amount": 100.00},
      {"description": "Shipping", "amount": 25.50}
    ],
    "tax": 12.50,
    "paymentMethod": "Credit Card"
  },
  "confidence": {
    "merchant": 0.95,
    "date": 0.92,
    "totalAmount": 0.98,
    "currency": 0.99,
    "lineItems": 0.88,
    "tax": 0.85,
    "paymentMethod": 0.90
  }
}

Return ONLY the JSON object, no additional text."""
