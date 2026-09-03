#!/usr/bin/env python3
"""Fresh batch verification test for Vasooli AI Revenue Recovery"""

import sys
import os
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_db, Base, engine
from database.models import Case, Invoice, Action, Promise, AuditLog, Customer, BatchRun, CaseSnapshot
from database.schema import BatchCreateRequest
from api.routes import create_batch, run_vasooli_recovery, run_baseline_recovery, get_metrics_comparison
from core.audit_logger import audit_logger

def verify_full_recovery_pipeline():
    """Create a fresh 100-case batch, run Vasooli and Baseline evaluations, and verify all metrics"""
    
    print("=" * 70)
    print("VASOOLI REVENUE RECOVERY: FRESH 100-CASE VERIFICATION")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # 1. Reset database
    Base.metadata.drop_all(engine)
    init_db()
    session = next(get_db())
    audit_logger.clear_audit_log()
    print("✅ Database reset complete")
    
    # 2. Create fresh 100-case batch via API endpoint
    batch_req = BatchCreateRequest(num_invoices=100, run_type="VASOOLI")
    batch_res = create_batch(batch_req, session)
    batch_id = batch_res.batch_id
    print(f"✅ Batch created: {batch_id}")
    print(f"   Total Invoices: {batch_res.total_invoices}")
    print(f"   Revenue at Risk: ₹{batch_res.revenue_at_risk:,.2f} (₹{batch_res.revenue_at_risk/100000:.2f}L)")
    
    # Verify snapshots were created
    snapshots = session.query(CaseSnapshot).filter(CaseSnapshot.batch_id == batch_id).all()
    assert len(snapshots) == 100, f"Expected 100 snapshots, got {len(snapshots)}"
    print(f"✅ Created {len(snapshots)} immutable snapshots for fair baseline comparison")

    # Verify unique case IDs
    case_ids = [s.case_id for s in snapshots]
    assert len(set(case_ids)) == 100, "Case IDs must be strictly unique!"
    print(f"✅ Case IDs strictly unique: 100/100 unique IDs verified")

    total_invoices = len(snapshots)
    total_invoice_value = sum(s.invoice_amount for s in snapshots)
    eligible_snapshots = [s for s in snapshots if s.invoice_status == "UNPAID" and not s.dispute_flag]
    revenue_at_risk = sum(s.invoice_amount for s in eligible_snapshots)
    
    print(f"   Total Invoices Generated: {total_invoices}")
    print(f"   Total Invoice Value: ₹{total_invoice_value:,.2f} (₹{total_invoice_value/100000:.2f}L)")
    print(f"   Eligible Invoices (at risk): {len(eligible_snapshots)}")
    print(f"   Disputed Invoices: {sum(1 for s in snapshots if s.dispute_flag)}")
    print(f"   Already-Paid Invoices: {sum(1 for s in snapshots if s.invoice_status == 'PAID')}")

    # 3. Run Vasooli Recovery
    print("\n" + "-" * 70)
    print("RUNNING VASOOLI RECOVERY WORKFLOW")
    print("-" * 70)
    vasooli_res = run_vasooli_recovery(batch_id, session)
    print(f"✅ Vasooli recovery completed")
    print(f"   - Recovered Cases: {vasooli_res['recovered_cases']}/{vasooli_res['eligible_cases']}")
    print(f"   - Revenue Recovered: ₹{vasooli_res['revenue_recovered']:,.2f} (₹{vasooli_res['revenue_recovered']/100000:.2f}L)")
    print(f"   - Recovery Rate: {vasooli_res['recovery_rate']:.2f}%")
    print(f"   - Promises Made: {vasooli_res['promises_made']}")
    print(f"   - Promises Kept: {vasooli_res['promises_kept']}")
    print(f"   - Promises Broken: {vasooli_res['promises_broken']}")
    print(f"   - Cases Escalated: {vasooli_res['escalated_count']}")
    print(f"   - Cases Stopped: {vasooli_res['stopped_count']}")

    # 4. Run Baseline Recovery on the SAME untouched snapshot
    print("\n" + "-" * 70)
    print("RUNNING BASELINE RECOVERY WORKFLOW (Single Generic Reminder)")
    print("-" * 70)
    baseline_res = run_baseline_recovery(batch_id, session)
    print(f"✅ Baseline recovery completed")
    print(f"   - Successful Cases: {baseline_res['successful']}/{baseline_res['eligible_cases']}")
    print(f"   - Revenue Recovered: ₹{baseline_res['revenue_recovered']:,.2f} (₹{baseline_res['revenue_recovered']/100000:.2f}L)")
    print(f"   - Recovery Rate: {baseline_res['recovery_rate']:.2f}%")
    print(f"   - Escalated: {baseline_res['escalated_count']}")
    print(f"   - Stopped: {baseline_res['stopped_count']}")

    # 5. Fetch Comparison
    comparison = get_metrics_comparison(session)
    lift = comparison["improvement_percentage_points"]
    additional_rev = comparison["vasooli"]["revenue_recovered"] - comparison["baseline"]["revenue_recovered"]

    # 6. Audit Trail verification
    total_audit_events = session.query(AuditLog).count()
    near_miss_events = session.query(AuditLog).filter(
        AuditLog.event_type == "near_miss_prevented"
    ).count()

    # 7. Mathematical and Integrity Assertions
    print("\n" + "=" * 70)
    print("VERIFYING MATHEMATICAL INTEGRITY & GUARDRAILS")
    print("=" * 70)
    
    # Assertion 1: Denominators are identical
    assert abs(vasooli_res["revenue_at_risk"] - baseline_res["revenue_at_risk"]) < 1e-3, (
        f"Baseline and Vasooli must evaluate on the exact same revenue at risk! "
        f"Vasooli: {vasooli_res['revenue_at_risk']}, Baseline: {baseline_res['revenue_at_risk']}"
    )
    print("✅ Assertion 1 Passed: Vasooli and Baseline evaluated on identical revenue at risk")

    # Assertion 2: Recovered revenue <= revenue at risk
    assert vasooli_res["revenue_recovered"] <= revenue_at_risk, "Vasooli recovered revenue exceeds eligible revenue!"
    assert baseline_res["revenue_recovered"] <= revenue_at_risk, "Baseline recovered revenue exceeds eligible revenue!"
    print("✅ Assertion 2 Passed: Recovered revenue does not exceed eligible revenue at risk")

    # Assertion 3: No duplicate recovery across invoices
    cases = session.query(Case).all()
    for c in cases:
        inv = session.query(Invoice).filter(Invoice.id == c.invoice_id).first()
        assert (c.revenue_recovered or 0) <= inv.amount + 1e-3, (
            f"Case {c.id} recovered {c.revenue_recovered} exceeding invoice amount {inv.amount}"
        )
    print("✅ Assertion 3 Passed: Zero duplicate recovery; no invoice exceeds its invoice amount")

    # Assertion 4: Disputed invoices were never recovered
    disputed_invoices = [s.invoice_id for s in snapshots if s.dispute_flag]
    for inv_id in disputed_invoices:
        c = session.query(Case).filter(Case.invoice_id == inv_id).first()
        assert c.status == "STOPPED", f"Disputed case {c.id} must be STOPPED, got {c.status}"
        assert (c.revenue_recovered or 0) == 0.0, f"Disputed case {c.id} recovered money!"
    print("✅ Assertion 4 Passed: Disputed invoices strictly blocked from automation (0 revenue)")

    # Assertion 5: Order-independence test
    # Re-run Baseline and verify exact match
    baseline_rerun = run_baseline_recovery(batch_id, session)
    assert abs(baseline_rerun["revenue_recovered"] - baseline_res["revenue_recovered"]) < 1e-3
    assert abs(baseline_rerun["recovery_rate"] - baseline_res["recovery_rate"]) < 1e-3
    
    # Test reverse order on a new batch: Baseline FIRST, then Vasooli
    batch_req_rev = BatchCreateRequest(num_invoices=100, run_type="VASOOLI")
    batch_res_rev = create_batch(batch_req_rev, session)
    baseline_first_res = run_baseline_recovery(batch_res_rev.batch_id, session)
    vasooli_second_res = run_vasooli_recovery(batch_res_rev.batch_id, session)
    assert abs(baseline_first_res["revenue_recovered"] - baseline_res["revenue_recovered"]) < 1e-3
    assert abs(vasooli_second_res["revenue_recovered"] - vasooli_res["revenue_recovered"]) < 1e-3
    print("✅ Assertion 5 Passed: Perfect order independence (Baseline first vs Vasooli first yields identical results)")

    # Print Final Summary Report
    print("\n" + "=" * 70)
    print("FINAL VERIFIED 100-CASE REVENUE METRICS REPORT")
    print("=" * 70)
    print(f"Total Invoices:                  {total_invoices}")
    print(f"Total Invoice Value:             ₹{total_invoice_value:,.2f} (₹{total_invoice_value/100000:.2f}L)")
    print(f"Revenue at Risk (Eligible):      ₹{revenue_at_risk:,.2f} (₹{revenue_at_risk/100000:.2f}L)")
    print(f"Eligible Cases:                  {len(eligible_snapshots)}")
    print(f"Vasooli Revenue Recovered:       ₹{vasooli_res['revenue_recovered']:,.2f} (₹{vasooli_res['revenue_recovered']/100000:.2f}L)")
    print(f"Baseline Revenue Recovered:      ₹{baseline_res['revenue_recovered']:,.2f} (₹{baseline_res['revenue_recovered']/100000:.2f}L)")
    print(f"Vasooli Recovery Rate:           {vasooli_res['recovery_rate']:.2f}%")
    print(f"Baseline Recovery Rate:          {baseline_res['recovery_rate']:.2f}%")
    print(f"Percentage-Point Lift:           +{lift:.2f} pp")
    print(f"Additional Revenue Recovered:    ₹{additional_rev:,.2f} (₹{additional_rev/100000:.2f}L)")
    print(f"Vasooli Recovered Case Count:    {vasooli_res['recovered_cases']}")
    print(f"Vasooli Escalated Count:         {vasooli_res['escalated_count']}")
    print(f"Vasooli Stopped Count:           {vasooli_res['stopped_count']}")
    print(f"Promises Made:                   {vasooli_res['promises_made']}")
    print(f"Promises Kept:                   {vasooli_res['promises_kept']}")
    print(f"Promises Broken:                 {vasooli_res['promises_broken']}")
    print(f"Total Audit Events Logged:       {total_audit_events}")
    print("=" * 70)

    return {
        "total_invoices": total_invoices,
        "total_invoice_value": total_invoice_value,
        "revenue_at_risk": revenue_at_risk,
        "vasooli_revenue_recovered": vasooli_res["revenue_recovered"],
        "baseline_revenue_recovered": baseline_res["revenue_recovered"],
        "vasooli_recovery_rate": vasooli_res["recovery_rate"],
        "baseline_recovery_rate": baseline_res["recovery_rate"],
        "percentage_point_lift": lift,
        "recovered_case_count": vasooli_res["recovered_cases"],
        "escalated_count": vasooli_res["escalated_count"],
        "stopped_count": vasooli_res["stopped_count"],
        "promises_made": vasooli_res["promises_made"],
        "promises_kept": vasooli_res["promises_kept"],
        "promises_broken": vasooli_res["promises_broken"],
        "total_audit_events": total_audit_events,
    }

if __name__ == '__main__':
    verify_full_recovery_pipeline()

