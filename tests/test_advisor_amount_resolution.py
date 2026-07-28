from agentic_claims.agents.advisor.node import _resolveAdvisorAmountSgd


def test_resolve_advisor_amount_prefers_intake_gpt_claimdata_sgd_over_receipt_native_total():
    state = {
        "intakeGpt": {
            "slots": {
                "claimData": {
                    "amountSgd": 19.36,
                    "currency": "SGD",
                    "originalAmount": 15.0,
                    "originalCurrency": "USD",
                }
            }
        },
        "extractedReceipt": {
            "fields": {
                "merchant": "City of Palo Alto",
                "date": "2024-08-19",
                "totalAmount": 15.0,
                "currency": "USD",
            }
        },
        "intakeFindings": {"employeeId": "1010736"},
    }

    amount = _resolveAdvisorAmountSgd(state, state["extractedReceipt"]["fields"])
    assert amount == 19.36
