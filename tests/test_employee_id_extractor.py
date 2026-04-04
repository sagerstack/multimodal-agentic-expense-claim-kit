"""Tests for server-side employee ID extraction from user messages."""

import pytest

from agentic_claims.web.employeeIdExtractor import extractEmployeeId


class TestExtractEmployeeId:
    """Employee ID extraction from free-text user messages."""

    def testExtractsEmpDashFormat(self):
        assert extractEmployeeId("My employee ID is EMP-042") == "EMP-042"

    def testExtractsBareNumericAfterIdColon(self):
        assert extractEmployeeId("ID: 1010736") == "1010736"

    def testExtractsEmpNoDash(self):
        assert extractEmployeeId("EMP001 here") == "EMP001"

    def testExtractsAlphanumericDashFormat(self):
        assert extractEmployeeId("I'm ABC-123") == "ABC-123"

    def testCaseInsensitiveMatchUppercaseOutput(self):
        assert extractEmployeeId("employee id emp-042") == "EMP-042"

    def testBareNumericAfterEmployee(self):
        assert extractEmployeeId("I'm employee 42") == "42"

    def testReturnsNoneWhenNoId(self):
        assert extractEmployeeId("Yes that looks correct") is None

    def testIgnoresDollarAmounts(self):
        assert extractEmployeeId("The amount is $45.20") is None

    def testExtractsIdDespiteDollarAmount(self):
        assert extractEmployeeId("My ID is EMP-042 and the total was $50") == "EMP-042"

    def testLastIdWinsUserCorrection(self):
        assert extractEmployeeId("EMP-001 no wait EMP-042") == "EMP-042"
