from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


def generate_pdf(summary: dict, filename: str):
    doc = SimpleDocTemplate(filename)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("SmartTax AI - Tax Summary Report", styles["Heading1"]))
    elements.append(Spacer(1, 16))

    # Summary table
    summary_table_data = [
        ["Category", "Amount"],
        ["Total Income", f"${summary.get('total_income', 0):,.2f}"],
        ["Total Expenses", f"${summary.get('total_expenses', 0):,.2f}"],
        ["Net Business Income", f"${summary.get('net_business_income', 0):,.2f}"],
        ["Self-Employment Tax (15.3%)", f"${summary.get('self_employment_tax', 0):,.2f}"],
        ["Income Tax Estimate", f"${summary.get('income_tax_estimate', 0):,.2f}"],
        ["Total Estimated Tax", f"${summary.get('total_estimated_tax', 0):,.2f}"],
    ]

    summary_table = Table(summary_table_data, colWidths=[270, 180])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 24))

    # Expense breakdown
    elements.append(Paragraph("Expense Breakdown", styles["Heading2"]))
    elements.append(Spacer(1, 12))

    expense_data = [["Category", "Amount"]]
    for item in summary.get("deductions_by_category", []):
        expense_data.append(
            [
                str(item["category"]).replace("_", " ").title(),
                f"${float(item['amount']):,.2f}",
            ]
        )

    expense_table = Table(expense_data, colWidths=[270, 180])
    expense_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    elements.append(expense_table)
    elements.append(Spacer(1, 24))

    # Assumptions
    elements.append(Paragraph("Assumptions Used", styles["Heading2"]))
    elements.append(Spacer(1, 8))
    for a in summary.get("assumptions_used", []):
        elements.append(Paragraph(f"- {a}", styles["Normal"]))
        elements.append(Spacer(1, 4))

    elements.append(Spacer(1, 16))

    # Disclaimer
    elements.append(
        Paragraph(
            summary.get(
                "disclaimer",
                "This report is for informational purposes only and does not constitute tax advice.",
            ),
            styles["Normal"],
        )
    )

    doc.build(elements)