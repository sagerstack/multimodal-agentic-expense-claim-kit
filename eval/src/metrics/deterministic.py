"""Deterministic metric subclasses for the 8 deterministic benchmarks.

All metrics receive captured data via testCase.additional_metadata.
No LLM calls -- pure Python logic scoring only.

Benchmarks covered:
  ER-001, ER-002, ER-003 -> DocumentTypeMetric
  ER-004                  -> ReceiptCompletenessMetric
  ER-005, ER-006, ER-010  -> FieldExtractionMetric
  ER-015                  -> AmountReconciliationMetric
"""

from datetime import datetime
from typing import Optional

from deepeval.metrics.base_metric import BaseMetric
from deepeval.test_case import LLMTestCase


# ---------------------------------------------------------------------------
# DocumentTypeMetric -- ER-001, ER-002, ER-003
# ---------------------------------------------------------------------------


class DocumentTypeMetric(BaseMetric):
    """Checks if agent classification matches expected document type.

    Reads additional_metadata["agentDecision"] and compares against
    additional_metadata["expectedDecision"].

    Classification logic:
      ER-001: expectedDecision contains "receipt" -> agent output must contain "receipt"
      ER-002: expectedDecision contains "not a receipt" or "needs review" ->
              agent output must contain "not a receipt", "unsupported", or "needs review"
      ER-003: expectedDecision contains "unsupported" ->
              agent output must contain "unsupported" or "not supported" or "cannot"
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
        agentDecision = str(metadata.get("agentDecision", "")).strip().lower()
        expectedDecision = str(metadata.get("expectedDecision", "")).strip().lower()

        matched = self._matchesExpected(agentDecision, expectedDecision)

        self.score = 1.0 if matched else 0.0
        self.success = self.score >= self.threshold
        self.reason = (
            f"Agent decision '{agentDecision}' matches expected '{expectedDecision}'"
            if matched
            else f"Agent decision '{agentDecision}' does NOT match expected '{expectedDecision}'"
        )
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        if self.success is None:
            raise ValueError("Metric has not been measured yet. Call measure() first.")
        return self.success

    def _matchesExpected(self, agentDecision: str, expectedDecision: str) -> bool:
        if not agentDecision:
            return False

        # Receipt type -- positive classification
        if "receipt" in expectedDecision and "not" not in expectedDecision:
            return "receipt" in agentDecision and "not" not in agentDecision

        # Non-receipt / needs review
        if "not a receipt" in expectedDecision or "needs review" in expectedDecision:
            return (
                "not a receipt" in agentDecision
                or "unsupported" in agentDecision
                or "needs review" in agentDecision
                or "not supported" in agentDecision
                or "review" in agentDecision
                or "cannot" in agentDecision
            )

        # Unsupported document type
        if "unsupported" in expectedDecision:
            return (
                "unsupported" in agentDecision
                or "not supported" in agentDecision
                or "cannot" in agentDecision
                or "review" in agentDecision
            )

        # Fallback: check for keyword containment in either direction
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

        presentCount = 0
        missing = []

        for fieldName in self.REQUIRED_FIELDS:
            value = extractedFields.get(fieldName)
            if value is not None and str(value).strip():
                presentCount += 1
            else:
                missing.append(fieldName)

        # Check amount under any alias
        amountPresent = False
        for alias in self.AMOUNT_FIELD_ALIASES:
            value = extractedFields.get(alias)
            if value is not None and str(value).strip():
                amountPresent = True
                break
        if amountPresent:
            presentCount += 1
        else:
            missing.append("total/amount")

        self.score = round(presentCount / 3, 4)
        self.success = self.score >= self.threshold
        self.reason = (
            f"All 3 required fields present (merchant, date, total)"
            if not missing
            else f"Missing required fields: {', '.join(missing)} ({presentCount}/3 present)"
        )
        return self.score

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

        # String comparison: case-insensitive, strip, containment
        extractedStr = str(extracted).strip().lower()
        expectedStr = str(expected).strip().lower()
        return expectedStr in extractedStr or extractedStr in expectedStr

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

        # Support multiple key variants for extracted total
        extractedTotal = None
        for key in ("total", "amount", "totalAmount"):
            value = extractedFields.get(key)
            if value is not None:
                extractedTotal = value
                break

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
        reconciled = difference <= self.TOLERANCE

        self.score = 1.0 if reconciled else 0.0
        self.success = self.score >= self.threshold
        self.reason = (
            f"Extracted {extractedNum} reconciles with claimed {claimedNum} (diff={difference:.4f})"
            if reconciled
            else f"Amount mismatch: extracted {extractedNum} vs claimed {claimedNum} (diff={difference:.4f})"
        )
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        if self.success is None:
            raise ValueError("Metric has not been measured yet. Call measure() first.")
        return self.success


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
