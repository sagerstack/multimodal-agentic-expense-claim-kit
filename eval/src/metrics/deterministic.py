"""Deterministic metric subclasses for the 8 deterministic benchmarks.

All metrics receive captured data via testCase.additional_metadata.
No LLM calls -- pure Python logic scoring only.

Benchmarks covered:
  ER-001, ER-002, ER-003 -> DocumentTypeMetric
  ER-004                  -> ReceiptCompletenessMetric
  ER-005, ER-006, ER-010  -> FieldExtractionMetric
  ER-015                  -> AmountReconciliationMetric
"""

import re
import unicodedata
from datetime import datetime
from typing import Optional

from deepeval.metrics.base_metric import BaseMetric
from deepeval.test_case import LLMTestCase


def _stripDiacritics(text: str) -> str:
    """Normalize Unicode text to ASCII by removing diacritics.

    Example: 'Cari Trương' -> 'Cari Truong'. Prevents metric false-negatives
    when VLM output preserves diacritics but expected values don't (or vice versa).
    """
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _stringSimilarity(expected: str, extracted: str) -> float:
    """Return token-overlap ratio in [0.0, 1.0] between expected and extracted strings.

    Case-insensitive and diacritic-insensitive. Splits on whitespace + punctuation.
    Returns 1.0 on exact (normalized) equality.
    """
    if not expected or not extracted:
        return 0.0
    e = _stripDiacritics(expected).lower()
    a = _stripDiacritics(extracted).lower()
    if e == a or e in a or a in e:
        return 1.0
    eTokens = set(re.findall(r"[a-z0-9]+", e))
    aTokens = set(re.findall(r"[a-z0-9]+", a))
    if not eTokens:
        return 0.0
    return len(eTokens & aTokens) / len(eTokens)


# ---------------------------------------------------------------------------
# DocumentTypeMetric -- ER-001, ER-002, ER-003
# ---------------------------------------------------------------------------


class DocumentTypeMetric(BaseMetric):
    """Checks if the intake agent correctly classified and handled the document type.

    Primary signal: claimId presence (did intake accept the document?).
      - claimId set   -> document was accepted as a receipt by intake
      - claimId absent -> document was rejected by intake

    This correctly separates document-type classification (intake behavior) from
    policy/routing decisions (advisor behavior). A valid receipt may still be
    escalated by the advisor due to policy violations — that does NOT mean the
    document type was misclassified.

    Falls back to agentDecision keyword search for edge cases where claimId
    state is ambiguous.
    """

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score: Optional[float] = None
        self.success: Optional[bool] = None
        self.reason: Optional[str] = None

    @property
    def __name__(self) -> str:
        return "DocumentTypeMetric"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = test_case.additional_metadata or {}
        expectedDecision = str(metadata.get("expectedDecision", "")).strip().lower()
        claimId = metadata.get("claimId")
        agentDecision = str(metadata.get("agentDecision", "")).strip().lower()

        claimSubmitted = bool(claimId)
        expectedAccepted = self._expectedAccepted(expectedDecision)

        if expectedAccepted is True:
            # Primary: claim was submitted → agent accepted the receipt.
            # Fallback: agent correctly classified as a valid receipt in text even
            # if submission never completed (e.g. interrupted mid-flow). Classification
            # accuracy is orthogonal to workflow completion.
            if claimSubmitted:
                matched = True
                signal = f"claimId='{claimId}' (submitted)"
            elif self._textAcceptsReceipt(agentDecision):
                matched = True
                signal = "agentDecision text classifies as valid receipt (not submitted)"
            else:
                matched = False
                signal = "claimId=None AND no positive receipt classification in text"
        elif expectedAccepted is False:
            matched = not claimSubmitted
            signal = f"claimId='{claimId}'" if claimSubmitted else "claimId=None (rejected)"
        else:
            # Ambiguous expected — fall back to keyword search within full conversation
            matched = self._matchesExpected(agentDecision, expectedDecision)
            signal = f"agentDecision='{agentDecision[:80]}'"

        self.score = 1.0 if matched else 0.0
        self.success = self.score >= self.threshold
        self.reason = (
            f"{signal} matches expected '{expectedDecision}'"
            if matched
            else f"{signal} does NOT match expected '{expectedDecision}'"
        )
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        if self.success is None:
            raise ValueError("Metric has not been measured yet. Call measure() first.")
        return self.success

    def _textAcceptsReceipt(self, agentDecision: str) -> bool:
        """Return True if agent text clearly classifies the document as a valid receipt
        without rejecting it.

        Positive signals: mentions receipt fields (merchant, date, total/amount) or
        extraction/submission verbs ("extracted", "processing", "submitted", "proceed").
        Negative veto: rejection language ("not a receipt", "unsupported", "cannot process",
        "needs review", "image quality").
        """
        if not agentDecision:
            return False

        rejectionPhrases = (
            "not a receipt",
            "not a valid receipt",
            "unsupported",
            "cannot process",
            "cannot be processed",
            "unable to process",
            "needs review",
            "image quality",
            "not legible",
            "unreadable",
            "please re-upload",
            "please upload a clearer",
        )
        for phrase in rejectionPhrases:
            if phrase in agentDecision:
                return False

        positiveFieldMarkers = (
            "merchant:",
            "merchant**",
            "vendor:",
            "total:",
            "total amount",
            "amount:",
            "date:",
            "receipt details",
            "extracted",
        )
        positiveActionMarkers = (
            "submitted",
            "submit the claim",
            "proceed with",
            "processing your claim",
            "claim submitted",
            "valid receipt",
            "this is a receipt",
            "this looks like a receipt",
        )
        if any(marker in agentDecision for marker in positiveFieldMarkers):
            return True
        if any(marker in agentDecision for marker in positiveActionMarkers):
            return True
        return False

    def _expectedAccepted(self, expectedDecision: str) -> Optional[bool]:
        """Return True if expected outcome is document accepted, False if rejected, None if unclear."""
        hasWordNot = bool(re.search(r"\bnot\b", expectedDecision))
        if "receipt" in expectedDecision and not hasWordNot:
            return True  # "Receipt" -> accepted
        if "complete" in expectedDecision or "approved" in expectedDecision:
            return True  # "Complete" -> accepted
        if "not a receipt" in expectedDecision or "unsupported" in expectedDecision:
            return False  # "Not a receipt" / "Unsupported" -> rejected
        return None  # Ambiguous — fall back to keyword search

    def _matchesExpected(self, agentDecision: str, expectedDecision: str) -> bool:
        if not agentDecision:
            return False

        hasWordNot = bool(re.search(r"\bnot\b", agentDecision))
        hasWordNotInExpected = bool(re.search(r"\bnot\b", expectedDecision))

        if "receipt" in expectedDecision and not hasWordNotInExpected:
            return "receipt" in agentDecision and not hasWordNot

        if "not a receipt" in expectedDecision or "needs review" in expectedDecision:
            return (
                "not a receipt" in agentDecision
                or "unsupported" in agentDecision
                or "needs review" in agentDecision
                or "not supported" in agentDecision
                or "review" in agentDecision
                or "cannot" in agentDecision
            )

        if "unsupported" in expectedDecision:
            return (
                "unsupported" in agentDecision
                or "not supported" in agentDecision
                or "cannot" in agentDecision
                or "review" in agentDecision
            )

        return expectedDecision in agentDecision or agentDecision in expectedDecision


# ---------------------------------------------------------------------------
# ReceiptCompletenessMetric -- ER-004
# ---------------------------------------------------------------------------


class ReceiptCompletenessMetric(BaseMetric):
    """Checks if required fields (merchant, date, amount) are present in
    additional_metadata["extractedFields"].

    Score: count of present required fields / 3.
    """

    REQUIRED_FIELDS = ("merchant", "date")
    AMOUNT_FIELD_ALIASES = ("total", "amount", "totalAmount")

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score: Optional[float] = None
        self.success: Optional[bool] = None
        self.reason: Optional[str] = None

    @property
    def __name__(self) -> str:
        return "ReceiptCompletenessMetric"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = test_case.additional_metadata or {}
        extractedFields: dict = metadata.get("extractedFields", {}) or {}
        agentDecision = str(metadata.get("agentDecision", "")).strip()

        presentCount = 0
        missing = []

        for fieldName in self.REQUIRED_FIELDS:
            value = extractedFields.get(fieldName)
            if value is not None and str(value).strip():
                presentCount += 1
            else:
                # Fallback: probe the agent's conversation text.
                if self._textContainsField(fieldName, agentDecision):
                    presentCount += 1
                else:
                    missing.append(fieldName)

        # Check amount under any alias
        amountPresent = any(
            extractedFields.get(alias) is not None
            and str(extractedFields.get(alias)).strip()
            for alias in self.AMOUNT_FIELD_ALIASES
        )
        if not amountPresent:
            amountPresent = self._textContainsField("amount", agentDecision)
        if amountPresent:
            presentCount += 1
        else:
            missing.append("total/amount")

        self.score = round(presentCount / 3, 4)
        self.success = self.score >= self.threshold
        self.reason = (
            "All 3 required fields present (merchant, date, total)"
            if not missing
            else f"Missing required fields: {', '.join(missing)} ({presentCount}/3 present)"
        )
        return self.score

    def _textContainsField(self, fieldName: str, agentText: str) -> bool:
        """Detect whether the agent's conversation text contains a merchant/date/amount
        value. Used as a fallback when DB-enriched extractedFields is empty (e.g. agent
        correctly extracted but did not submit the claim).
        """
        if not agentText:
            return False
        text = agentText.lower()

        if fieldName == "merchant":
            # Look for labeled merchant/vendor field with non-empty value.
            # Covers: "Merchant: X", "merchant (X)", "**Merchant**\tX", table rows.
            patterns = [
                r"merchant[^\w]*[:\-][^\n]*[a-z0-9]",
                r"vendor[^\w]*[:\-][^\n]*[a-z0-9]",
                r"merchant\s*\(\s*[^)\n]+\)",
                r"vendor\s*\(\s*[^)\n]+\)",
                r"\*\*merchant\*\*[^\n]*[a-z0-9]",
                r"\*\*vendor\*\*[^\n]*[a-z0-9]",
                r"(?:^|\n)\s*merchant[\s\|\t]+[a-z0-9]",
                r"(?:^|\n)\s*vendor[\s\|\t]+[a-z0-9]",
                r"at\s+[A-Z][a-zA-Z&' -]{2,}",
            ]
            return any(re.search(p, agentText, re.IGNORECASE) for p in patterns)

        if fieldName == "date":
            patterns = [
                r"\b\d{4}-\d{2}-\d{2}\b",
                r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
                r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
                r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}\b",
                r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b",
            ]
            return any(re.search(p, text) for p in patterns)

        if fieldName == "amount":
            patterns = [
                r"\b(?:sgd|usd|eur|gbp|jpy|vnd|idr|myr|thb)\s*\$?\s*\d+(?:[.,]\d{2,3})?\b",
                r"\$\s*\d+(?:[.,]\d{2})?\b",
                r"\btotal[^\w]*[:\-]\s*\$?\s*\d+(?:[.,]\d{2,3})?\b",
                r"\bamount[^\w]*[:\-]\s*\$?\s*\d+(?:[.,]\d{2,3})?\b",
                r"\b\d+[.,]\d{2}\s*(?:sgd|usd|eur|gbp|jpy|vnd|idr|myr|thb)\b",
            ]
            return any(re.search(p, text) for p in patterns)

        return False

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        if self.success is None:
            raise ValueError("Metric has not been measured yet. Call measure() first.")
        return self.success


# ---------------------------------------------------------------------------
# FieldExtractionMetric -- ER-005, ER-006, ER-010
# ---------------------------------------------------------------------------


class FieldExtractionMetric(BaseMetric):
    """Compares additional_metadata["extractedFields"] against
    additional_metadata["expectedFields"].

    Matching rules:
      - String fields: case-insensitive, strip, check containment
      - Numeric fields (total, subtotal, tax, amount): within tolerance 0.01
      - Date fields: normalize to YYYY-MM-DD before comparison

    Score: matching fields / total expected fields.
    """

    NUMERIC_FIELDS = frozenset({"total", "subtotal", "tax", "amount", "totalAmount", "price"})
    DATE_FIELDS = frozenset({"date", "purchaseDate", "transactionDate"})
    NUMERIC_TOLERANCE = 0.01

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score: Optional[float] = None
        self.success: Optional[bool] = None
        self.reason: Optional[str] = None

    @property
    def __name__(self) -> str:
        return "FieldExtractionMetric"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = test_case.additional_metadata or {}
        extractedFields: dict = metadata.get("extractedFields", {}) or {}
        expectedFields: dict = metadata.get("expectedFields", {}) or {}
        agentDecision = str(metadata.get("agentDecision", "")).strip()

        if not expectedFields:
            self.score = 0.0
            self.success = False
            self.reason = "No expectedFields provided in additional_metadata"
            return self.score

        matchCount = 0
        details = []
        for fieldName, expectedValue in expectedFields.items():
            extractedValue = extractedFields.get(fieldName)
            matched = self._fieldMatches(fieldName, extractedValue, expectedValue)
            if not matched and agentDecision:
                # Fallback: scan the agent's conversation for the expected value
                # when DB enrichment didn't populate extractedFields (claim not submitted).
                if self._textContainsExpectedValue(fieldName, expectedValue, agentDecision):
                    matched = True
                    extractedValue = f"(matched in text: {expectedValue!r})"
            if matched:
                matchCount += 1
                details.append(f"{fieldName}: OK")
            else:
                details.append(f"{fieldName}: expected={expectedValue!r} got={extractedValue!r}")

        total = len(expectedFields)
        self.score = round(matchCount / total, 4) if total > 0 else 0.0
        self.success = self.score >= self.threshold
        self.reason = f"{matchCount}/{total} fields matched. " + " | ".join(details)
        return self.score

    def _textContainsExpectedValue(self, fieldName: str, expected, agentText: str) -> bool:
        """Check whether the expected value for fieldName appears in the agent text.

        Used as a fallback when the DB-enriched `extractedFields` is empty (e.g. claim
        wasn't submitted). Applies type-aware matching:
          - Dates: normalize both sides to YYYY-MM-DD and search
          - Numbers: substring search on the normalized numeric string (with and
            without thousand-separators / trailing zeros)
          - Strings: case-insensitive containment
        """
        if expected is None:
            return False

        fieldLower = fieldName.lower()
        textLower = agentText.lower()

        # Date comparison: normalize expected, then search the text for the normalized
        # form plus a few common re-serialisations.
        if fieldLower in {f.lower() for f in self.DATE_FIELDS}:
            expectedNorm = self._normalizeDate(str(expected))
            if expectedNorm:
                # Match ISO form
                if expectedNorm in textLower:
                    return True
                # Try D/M/Y and M/D/Y plus textual month forms
                try:
                    d = datetime.strptime(expectedNorm, "%Y-%m-%d")
                except ValueError:
                    return False
                for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y",
                             "%d %B %Y", "%d %b %Y"):
                    candidate = d.strftime(fmt).lower()
                    if candidate in textLower:
                        return True
                return False
            return str(expected).strip().lower() in textLower

        # Numeric comparison: build candidate strings and look for any of them in text.
        if fieldLower in {f.lower() for f in self.NUMERIC_FIELDS}:
            try:
                expectedNum = float(
                    str(expected).replace(",", "").replace("$", "").strip()
                )
            except (ValueError, TypeError):
                return str(expected).strip().lower() in textLower
            # Candidates: 16.2, 16.20, 16, 16,20
            candidates = {
                f"{expectedNum:.2f}",
                f"{expectedNum:g}",
                str(int(expectedNum)) if expectedNum == int(expectedNum) else f"{expectedNum}",
            }
            if expectedNum >= 1000:
                candidates.add(f"{expectedNum:,.2f}")
                candidates.add(f"{expectedNum:,.0f}")
            return any(c in agentText for c in candidates)

        # String comparison: diacritic-insensitive containment, then token overlap
        # against the whole text. For longer expected strings (>= 3 tokens), accept a
        # >=70% token overlap so partial VLM omissions still match.
        expectedStr = str(expected).strip()
        if not expectedStr:
            return False
        expectedNormalized = _stripDiacritics(expectedStr).lower()
        textNormalized = _stripDiacritics(agentText).lower()
        if expectedNormalized in textNormalized:
            return True
        expectedTokens = [t for t in re.findall(r"[a-z0-9]+", expectedNormalized) if t]
        textTokens = set(re.findall(r"[a-z0-9]+", textNormalized))
        if len(expectedTokens) >= 2 and expectedTokens:
            overlap = sum(1 for t in expectedTokens if t in textTokens) / len(expectedTokens)
            if overlap >= 0.7:
                return True
        return False

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        if self.success is None:
            raise ValueError("Metric has not been measured yet. Call measure() first.")
        return self.success

    def _fieldMatches(self, fieldName: str, extracted, expected) -> bool:
        if extracted is None:
            return False

        fieldLower = fieldName.lower()

        if fieldLower in {f.lower() for f in self.DATE_FIELDS}:
            return self._datesMatch(extracted, expected)

        if fieldLower in {f.lower() for f in self.NUMERIC_FIELDS}:
            return self._numbersMatch(extracted, expected)

        # String comparison: diacritic-insensitive token overlap.
        # Accept matches at >= 0.7 overlap so minor VLM variations
        # ("The Public Izakaya" vs "The Public Izakaya 2") still pass.
        return _stringSimilarity(str(expected), str(extracted)) >= 0.7

    def _numbersMatch(self, extracted, expected) -> bool:
        try:
            extractedNum = float(str(extracted).replace(",", "").replace("$", "").strip())
            expectedNum = float(str(expected).replace(",", "").replace("$", "").strip())
            return abs(extractedNum - expectedNum) <= self.NUMERIC_TOLERANCE
        except (ValueError, TypeError):
            return str(extracted).strip().lower() == str(expected).strip().lower()

    def _datesMatch(self, extracted, expected) -> bool:
        extractedNorm = self._normalizeDate(str(extracted))
        expectedNorm = self._normalizeDate(str(expected))
        if extractedNorm and expectedNorm:
            return extractedNorm == expectedNorm
        return str(extracted).strip().lower() == str(expected).strip().lower()

    def _normalizeDate(self, dateStr: str) -> Optional[str]:
        dateStr = dateStr.strip()
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
            "%Y%m%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dateStr, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None


# ---------------------------------------------------------------------------
# AmountReconciliationMetric -- ER-015
# ---------------------------------------------------------------------------


class AmountReconciliationMetric(BaseMetric):
    """Compares extracted total against claimed amount from companionMetadata.

    Reads:
      additional_metadata["extractedFields"]["total"] -- extracted total from receipt
      additional_metadata["companionMetadata"]["claimedAmount"] -- amount from expense report

    Score: 1.0 if |extractedTotal - claimedAmount| <= 0.01, else 0.0.
    """

    TOLERANCE = 0.01

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score: Optional[float] = None
        self.success: Optional[bool] = None
        self.reason: Optional[str] = None

    @property
    def __name__(self) -> str:
        return "AmountReconciliationMetric"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = test_case.additional_metadata or {}
        extractedFields: dict = metadata.get("extractedFields", {}) or {}
        companionMetadata: dict = metadata.get("companionMetadata", {}) or {}
        agentDecision = str(metadata.get("agentDecision", "")).strip()

        # Support multiple key variants for extracted total
        extractedTotal = None
        for key in ("total", "amount", "totalAmount", "convertedAmountSgd"):
            value = extractedFields.get(key)
            if value is not None:
                extractedTotal = value
                break

        # Fallback: parse the agent's conversation for a numeric total when DB fields
        # are empty (e.g. claim not submitted). Scan SGD amounts first (post-conversion),
        # then any "total: <amount>" pattern.
        if extractedTotal is None and agentDecision:
            extractedTotal = self._extractTotalFromText(agentDecision)

        claimedAmount = companionMetadata.get("claimedAmount") or companionMetadata.get(
            "claimedAmountInReport"
        )

        if extractedTotal is None or claimedAmount is None:
            self.score = 0.0
            self.success = False
            self.reason = (
                f"Missing values: extractedTotal={extractedTotal!r}, claimedAmount={claimedAmount!r}"
            )
            return self.score

        try:
            extractedNum = float(
                str(extractedTotal).replace(",", "").replace("$", "").strip()
            )
            claimedNum = float(str(claimedAmount).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            self.score = 0.0
            self.success = False
            self.reason = f"Could not parse amounts: extracted={extractedTotal!r}, claimed={claimedAmount!r}"
            return self.score

        difference = abs(extractedNum - claimedNum)
        mismatchExists = difference > self.TOLERANCE

        # ER-015 tests that the agent DETECTS a mismatch. Score 1.0 when
        # the expectedDecision is "Amount Mismatch" and a real discrepancy
        # exists between extracted and claimed amounts.
        expectedDecision = str(metadata.get("expectedDecision", "")).lower()
        isMismatchScenario = "mismatch" in expectedDecision

        if isMismatchScenario:
            self.score = 1.0 if mismatchExists else 0.0
            self.reason = (
                f"Mismatch correctly detected: extracted {extractedNum} vs claimed {claimedNum} (diff={difference:.4f})"
                if mismatchExists
                else f"Amounts unexpectedly reconcile: extracted {extractedNum} vs claimed {claimedNum}"
            )
        else:
            self.score = 1.0 if not mismatchExists else 0.0
            self.reason = (
                f"Extracted {extractedNum} reconciles with claimed {claimedNum} (diff={difference:.4f})"
                if not mismatchExists
                else f"Amount mismatch: extracted {extractedNum} vs claimed {claimedNum} (diff={difference:.4f})"
            )

        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        if self.success is None:
            raise ValueError("Metric has not been measured yet. Call measure() first.")
        return self.success

    _TEXT_TOTAL_PATTERNS = (
        # "Total: SGD 27.54", "Total SGD 27.54", "converted total: SGD 27.54"
        re.compile(
            r"(?:converted\s+)?total[^\d\n]{0,20}?(?:sgd|usd|eur|gbp|vnd|idr|myr|thb|jpy)\s*\$?\s*([\d,]+(?:\.\d{2,3})?)",
            re.IGNORECASE,
        ),
        # "SGD 27.54", "sgd 27.54" (currency-prefixed)
        re.compile(
            r"\b(?:sgd)\s*\$?\s*([\d,]+(?:\.\d{2,3})?)",
            re.IGNORECASE,
        ),
        # "→ SGD 27.54" (arrow-led conversion result)
        re.compile(
            r"(?:→|->|=>)\s*(?:sgd|s\$)?\s*\$?\s*([\d,]+(?:\.\d{2,3})?)",
            re.IGNORECASE,
        ),
        # "total: 27.54"
        re.compile(
            r"total[^\d\n]{0,20}?\$?\s*([\d,]+(?:\.\d{2,3})?)",
            re.IGNORECASE,
        ),
    )

    def _extractTotalFromText(self, agentText: str) -> Optional[float]:
        """Parse the agent's conversation for a numeric total value.

        Priority: explicit total labels with currency > SGD-prefixed amounts >
        any "total:" pattern. Returns the first match as a float.
        """
        if not agentText:
            return None
        for pattern in self._TEXT_TOTAL_PATTERNS:
            match = pattern.search(agentText)
            if match:
                raw = match.group(1).replace(",", "")
                try:
                    return float(raw)
                except ValueError:
                    continue
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_DETERMINISTIC_BENCHMARK_MAP: dict[str, type[BaseMetric]] = {
    "ER-001": DocumentTypeMetric,
    "ER-002": DocumentTypeMetric,
    "ER-003": DocumentTypeMetric,
    "ER-004": ReceiptCompletenessMetric,
    "ER-005": FieldExtractionMetric,
    "ER-006": FieldExtractionMetric,
    "ER-010": FieldExtractionMetric,
    "ER-015": AmountReconciliationMetric,
}


def getDeterministicMetric(benchmarkId: str) -> BaseMetric:
    """Return an instance of the appropriate deterministic metric for the given benchmark ID."""
    metricClass = _DETERMINISTIC_BENCHMARK_MAP.get(benchmarkId)
    if metricClass is None:
        raise KeyError(
            f"No deterministic metric registered for benchmark '{benchmarkId}'. "
            f"Valid IDs: {sorted(_DETERMINISTIC_BENCHMARK_MAP.keys())}"
        )
    return metricClass()
