"""VLM structured extraction prompt template."""

VLM_EXTRACTION_PROMPT = """Analyse this image and return a JSON object with these top-level keys:

1. "isReceipt": true if this is a personal expense receipt (restaurant bill, taxi/ride receipt, hotel bill, retail receipt, parking receipt, etc.). false if it is anything else (vendor invoice, bank statement, credit card statement, contract, purchase order, screenshot, etc.)

2. "documentType": A short label describing what this document is. Examples: "receipt", "vendor_invoice", "bank_statement", "credit_card_statement", "contract", "purchase_order", "screenshot", "other"

3. "isReadable": true if the receipt text (merchant, date, line items, total) is clearly legible to a human reading the image. false if the image is too blurry, too dark, too small, cropped, or otherwise illegible such that key fields cannot be read with confidence. Only evaluate this if isReceipt is true; otherwise set to null.

4. "fields": If isReceipt is true AND isReadable is true, extract all of these fields. Otherwise set all fields to null.
   - merchant: Business name (string)
   - date: Transaction date in YYYY-MM-DD format (string)
   - totalAmount: Total amount paid (number)
   - currency: Currency code (string, e.g., "USD", "EUR", "SGD")
   - lineItems: Array of objects with "description" and "amount" keys
   - tax: Tax amount if present (number, or null)
   - paymentMethod: How it was paid (string, e.g., "Credit Card", "Cash")

5. "confidence": If fields were extracted, a dictionary with the same keys as "fields", each containing a confidence score (0.0 to 1.0). Otherwise set to null.

Example response for a valid readable receipt:
{
  "isReceipt": true,
  "documentType": "receipt",
  "isReadable": true,
  "fields": {
    "merchant": "Acme Cafe",
    "date": "2024-03-15",
    "totalAmount": 125.50,
    "currency": "SGD",
    "lineItems": [
      {"description": "Coffee", "amount": 6.50},
      {"description": "Sandwich", "amount": 9.00}
    ],
    "tax": 1.50,
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

Example response for a receipt that is too blurry to read:
{
  "isReceipt": true,
  "documentType": "receipt",
  "isReadable": false,
  "fields": null,
  "confidence": null
}

Example response for a vendor invoice:
{
  "isReceipt": false,
  "documentType": "vendor_invoice",
  "isReadable": null,
  "fields": null,
  "confidence": null
}

Return ONLY the JSON object, no additional text."""
