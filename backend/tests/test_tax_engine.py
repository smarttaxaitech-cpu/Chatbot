from services.tax_engine import calculate_tax_estimate

def test_tax_engine_basic():
    result = calculate_tax_estimate(
        income=60000,
        expenses=[
            {"category": "general", "amount": 5000}
        ],
        filing_status="single"
    )

    # Basic sanity checks
    assert result["total_income"] == 60000
    assert result["total_expenses"] == 5000
    assert result["net_business_income"] == 60000 - result["allowed_expenses"]
    assert result["total_tax"] >= 0