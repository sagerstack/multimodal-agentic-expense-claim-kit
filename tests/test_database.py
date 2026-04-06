"""Unit tests for database models."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import JSONB

from agentic_claims.infrastructure.database.models import AuditLog, Base, Claim, Receipt


def testBaseMetadataHasAllTables():
    """Test that Base.metadata includes all expected tables."""
    table_names = set(Base.metadata.tables.keys())
    assert table_names == {"claims", "receipts", "audit_log", "users"}


def testClaimModelStructure():
    """Test Claim model can be instantiated and has correct attributes."""
    claim = Claim(
        claimNumber="CLM-001",
        employeeId="EMP-001",
        status="draft",
        totalAmount=Decimal("100.50"),
        currency="SGD",
    )

    assert claim.claimNumber == "CLM-001"
    assert claim.employeeId == "EMP-001"
    assert claim.status == "draft"
    assert claim.totalAmount == Decimal("100.50")
    assert claim.currency == "SGD"

    # Check relationships exist
    assert hasattr(claim, "receipts")
    assert hasattr(claim, "auditLogs")


def testReceiptModelStructure():
    """Test Receipt model can be instantiated and has correct attributes."""
    line_items = [
        {"description": "Item 1", "amount": 50.0, "category": "meals"},
        {"description": "Item 2", "amount": 30.0, "category": "transport"},
    ]

    receipt = Receipt(
        claimId=1,
        receiptNumber="RCP-001",
        merchant="Test Merchant",
        date=date(2026, 3, 24),
        totalAmount=Decimal("80.00"),
        currency="SGD",
        lineItems=line_items,
    )

    assert receipt.receiptNumber == "RCP-001"
    assert receipt.merchant == "Test Merchant"
    assert receipt.totalAmount == Decimal("80.00")
    assert receipt.lineItems == line_items

    # Check relationship exists
    assert hasattr(receipt, "claim")


def testAuditLogModelStructure():
    """Test AuditLog model can be instantiated and has correct attributes."""
    audit_log = AuditLog(
        claimId=1,
        action="status_change",
        oldValue="draft",
        newValue="pending",
        actor="EMP-001",
    )

    assert audit_log.action == "status_change"
    assert audit_log.oldValue == "draft"
    assert audit_log.newValue == "pending"
    assert audit_log.actor == "EMP-001"

    # Check relationship exists
    assert hasattr(audit_log, "claim")


def testReceiptLineItemsColumnIsJsonb():
    """Test that Receipt.lineItems uses JSONB column type."""
    receipt_table = Base.metadata.tables["receipts"]
    line_items_column = receipt_table.columns["line_items"]

    # Check that the column type is JSONB
    assert isinstance(line_items_column.type, JSONB)


def testClaimReceiptRelationship():
    """Test that Claim and Receipt have bidirectional relationship."""
    claim = Claim(
        claimNumber="CLM-001",
        employeeId="EMP-001",
        status="draft",
        totalAmount=Decimal("100.50"),
    )

    # Verify relationship descriptors exist
    assert hasattr(Claim, "receipts")
    assert hasattr(Receipt, "claim")

    # Verify back_populates is configured
    claim_receipts_property = Claim.receipts.property
    receipt_claim_property = Receipt.claim.property

    assert claim_receipts_property.back_populates == "claim"
    assert receipt_claim_property.back_populates == "receipts"


def testClaimAuditLogRelationship():
    """Test that Claim and AuditLog have bidirectional relationship."""
    # Verify relationship descriptors exist
    assert hasattr(Claim, "auditLogs")
    assert hasattr(AuditLog, "claim")

    # Verify back_populates is configured
    claim_audit_logs_property = Claim.auditLogs.property
    audit_log_claim_property = AuditLog.claim.property

    assert claim_audit_logs_property.back_populates == "claim"
    assert audit_log_claim_property.back_populates == "auditLogs"


def testClaimAgentOutputColumnsExist():
    """Test that Claim model has all 4 agent output columns."""
    claim = Claim(
        claimNumber="CLM-002",
        employeeId="EMP-001",
        status="pending",
        totalAmount=Decimal("200.00"),
        currency="SGD",
    )
    assert hasattr(claim, "complianceFindings")
    assert hasattr(claim, "fraudFindings")
    assert hasattr(claim, "advisorDecision")
    assert hasattr(claim, "approvedBy")


def testClaimAgentOutputColumnsNullable():
    """Test that all 4 agent output columns default to None."""
    claim = Claim(
        claimNumber="CLM-003",
        employeeId="EMP-002",
        status="draft",
        totalAmount=Decimal("50.00"),
    )
    assert claim.complianceFindings is None
    assert claim.fraudFindings is None
    assert claim.advisorDecision is None
    assert claim.approvedBy is None


def testClaimComplianceFraudFindingsAreJsonb():
    """Test that complianceFindings and fraudFindings use JSONB column type."""
    claims_table = Base.metadata.tables["claims"]
    complianceCol = claims_table.columns["compliance_findings"]
    fraudCol = claims_table.columns["fraud_findings"]
    assert isinstance(complianceCol.type, JSONB)
    assert isinstance(fraudCol.type, JSONB)


def testClaimAdvisorDecisionColumnType():
    """Test that advisorDecision is String(50) and approvedBy is String(50)."""
    from sqlalchemy import String

    claims_table = Base.metadata.tables["claims"]
    advisorCol = claims_table.columns["advisor_decision"]
    approvedByCol = claims_table.columns["approved_by"]
    assert isinstance(advisorCol.type, String)
    assert isinstance(approvedByCol.type, String)
