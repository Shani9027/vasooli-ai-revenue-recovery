from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
import uuid
from typing import List, Optional

from database import get_db
from database.models import (
    Customer, Invoice, Case, Action, Promise, AuditLog, BatchRun, CaseSnapshot
)
from database.schema import (
    CaseResponse, InvoiceResponse, ActionResponse, AuditLogResponse,
    BatchCreateRequest, BatchCreateResponse, MetricsSummary, CustomerResponse,
    PromiseResponse
)
from synthetic_data.generator import SyntheticDataGenerator
from simulator.customer_simulator import CustomerSimulator, CustomerResponseType
from core.risk_scorer import RiskScorer
from core.policy_engine import PolicyEngine
from core.audit_logger import audit_logger
from core.ai_orchestrator import AIOrchestrator
from config.constants import RiskLevel, CaseStatus, Actor, AuditEventType, PromiseStatus, ActionStatus

router = APIRouter(prefix="/api", tags=["api"])


# Helper functions
def _generate_id(prefix: str) -> str:
    """Generate a unique ID"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# BATCH MANAGEMENT ENDPOINTS

@router.post("/batches/create", response_model=BatchCreateResponse)
def create_batch(request: BatchCreateRequest, db: Session = Depends(get_db)):
    """Create and seed a new batch of synthetic invoices with an immutable baseline snapshot"""
    
    try:
        # Clear existing data to allow clean fresh batch creation without UNIQUE constraint collisions
        db.query(CaseSnapshot).delete()
        db.query(Promise).delete()
        db.query(Action).delete()
        db.query(Case).delete()
        db.query(Invoice).delete()
        db.query(Customer).delete()
        db.query(BatchRun).delete()
        db.commit()
        audit_logger.clear_audit_log()

        # Generate synthetic data
        generator = SyntheticDataGenerator()
        customers, invoice_tuples = generator.generate_batch(request.num_invoices)
        
        # Store customers
        for customer in customers:
            db.add(customer)
        db.commit()
        
        # Create batch run record
        batch_id = _generate_id("BATCH")
        batch_run = BatchRun(
            id=batch_id,
            run_type=request.run_type,
            status="CREATED",
            total_invoices=len(invoice_tuples),
            started_at=datetime.utcnow(),
        )
        db.add(batch_run)
        
        # Calculate total revenue at risk and store invoices
        revenue_at_risk = 0.0
        
        for invoice, customer in invoice_tuples:
            db.add(invoice)
            
            # Only count unpaid, non-disputed invoices toward revenue at risk
            if invoice.status == "UNPAID" and not invoice.dispute_flag:
                revenue_at_risk += invoice.amount
        
        db.commit()
        
        # Create cases, score them, and store pristine baseline snapshots
        for invoice, customer in invoice_tuples:
            invoice = db.query(Invoice).filter(Invoice.id == invoice.id).first()
            customer = db.query(Customer).filter(Customer.id == customer.id).first()
            
            case_id = f"CASE-{invoice.id}"
            
            if invoice.dispute_flag:
                risk_level = RiskLevel.BLOCKED
                risk_score = 0.0
                status = CaseStatus.STOPPED
            elif invoice.status == "PAID":
                risk_level = RiskLevel.LOW
                risk_score = 0.0
                status = CaseStatus.PAYMENT_RECEIVED
            else:
                risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
                status = CaseStatus.ACTIVE
            
            case = Case(
                id=case_id,
                invoice_id=invoice.id,
                customer_id=customer.id,
                risk_level=risk_level,
                risk_score=risk_score,
                escalation_stage=1,
                status=status,
                revenue_recovered=invoice.amount if status == CaseStatus.PAYMENT_RECEIVED else 0.0,
            )
            db.add(case)

            # Record immutable baseline snapshot
            snapshot = CaseSnapshot(
                id=f"SNAP-{invoice.id}",
                batch_id=batch_id,
                case_id=case_id,
                invoice_id=invoice.id,
                customer_id=customer.id,
                customer_name=customer.name,
                customer_reliability=customer.reliability_score,
                invoice_amount=invoice.amount,
                invoice_date=invoice.invoice_date,
                invoice_due_date=invoice.due_date,
                invoice_status=invoice.status,
                dispute_flag=invoice.dispute_flag,
                dispute_reason=invoice.dispute_reason,
                delay_reason=invoice.delay_reason,
                risk_level=str(risk_level.value if hasattr(risk_level, 'value') else risk_level),
                risk_score=risk_score,
                initial_status=str(status.value if hasattr(status, 'value') else status),
            )
            db.add(snapshot)
            
            # Log risk scoring to audit trail
            audit_logger.set_session(db)
            audit_logger.log_event(
                event_type=AuditEventType.RISK_SCORE,
                actor=Actor.SYSTEM,
                case_id=case_id,
                input_data={
                    "invoice_id": invoice.id,
                    "amount": invoice.amount,
                    "days_overdue": (date.today() - invoice.due_date).days if invoice.due_date else 0,
                    "dispute_flag": invoice.dispute_flag,
                },
                output_data={
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                },
                passed=True,
                reason=f"Scored invoice {invoice.id}",
            )
        
        db.commit()
        
        # Update batch run with calculated metrics
        batch_run.revenue_at_risk = revenue_at_risk
        db.commit()
        
        return BatchCreateResponse(
            batch_id=batch_id,
            status="CREATED",
            total_invoices=len(invoice_tuples),
            revenue_at_risk=revenue_at_risk,
            message=f"Batch {batch_id} created with {len(invoice_tuples)} invoices and snapshot saved",
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batches/{batch_id}/start")
def start_batch(batch_id: str, db: Session = Depends(get_db)):
    """
    Start batch processing.
    For Day 1, this only performs risk scoring (already done in create).
    Full pipeline will be implemented in Day 2.
    """
    
    try:
        batch_run = db.query(BatchRun).filter(BatchRun.id == batch_id).first()
        if not batch_run:
            raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
        
        batch_run.status = "COMPLETED"
        batch_run.completed_at = datetime.utcnow()
        db.commit()
        
        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "message": "Batch processing complete (Day 1: Risk scoring only)"
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    """Get batch details"""
    
    try:
        batch_run = db.query(BatchRun).filter(BatchRun.id == batch_id).first()
        if not batch_run:
            raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
        
        return {
            "id": batch_run.id,
            "run_type": batch_run.run_type,
            "status": batch_run.status,
            "total_invoices": batch_run.total_invoices,
            "revenue_at_risk": batch_run.revenue_at_risk,
            "revenue_recovered": batch_run.revenue_recovered,
            "recovery_rate": batch_run.recovery_rate,
            "started_at": batch_run.started_at.isoformat() if batch_run.started_at else None,
            "completed_at": batch_run.completed_at.isoformat() if batch_run.completed_at else None,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# CASES ENDPOINTS

@router.get("/cases", response_model=List[CaseResponse])
def list_cases(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all cases with pagination"""
    
    try:
        cases = db.query(Case).offset(skip).limit(limit).all()
        return cases
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    """Get case details"""
    
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
        return case
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/audit", response_model=List[AuditLogResponse])
def get_case_audit(case_id: str, limit: int = 100, db: Session = Depends(get_db)):
    """Get audit trail for a case"""
    
    try:
        audit_logger.set_session(db)
        audit_entries = audit_logger.get_case_audit_trail(case_id, limit)
        return audit_entries
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# METRICS ENDPOINTS

@router.get("/metrics/summary", response_model=MetricsSummary)
def get_metrics_summary(db: Session = Depends(get_db)):
    """Get summary metrics for all cases"""
    
    try:
        # Count cases and aggregate data
        total_cases = db.query(Case).count()
        
        # Revenue at risk is based on eligible initial revenue (from BatchRun or CaseSnapshot)
        latest_batch = db.query(BatchRun).filter(
            BatchRun.run_type == "VASOOLI"
        ).order_by(BatchRun.started_at.desc()).first()
        
        if latest_batch and latest_batch.revenue_at_risk and latest_batch.revenue_at_risk > 0:
            revenue_at_risk = latest_batch.revenue_at_risk
        else:
            snap_risk = db.query(func.sum(CaseSnapshot.invoice_amount)).filter(
                CaseSnapshot.invoice_status == "UNPAID",
                CaseSnapshot.dispute_flag == False
            ).scalar()
            revenue_at_risk = snap_risk or 0.0
        
        recovered_query = db.query(func.sum(Case.revenue_recovered))
        revenue_recovered = recovered_query.scalar() or 0.0
        if revenue_at_risk > 0:
            revenue_recovered = min(revenue_recovered, revenue_at_risk)
            recovery_rate = (revenue_recovered / revenue_at_risk) * 100
        else:
            recovery_rate = 0.0
        
        # Count by status
        status_counts = {}
        for status in [CaseStatus.ACTIVE, CaseStatus.PAYMENT_RECEIVED, CaseStatus.ESCALATED, CaseStatus.STOPPED, CaseStatus.HUMAN_REVIEW]:
            count = db.query(Case).filter(Case.status == status).count()
            status_counts[status] = count
        
        # Count by risk level
        risk_counts = {}
        for level in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.BLOCKED]:
            count = db.query(Case).filter(Case.risk_level == level).count()
            risk_counts[level] = count
        
        # Promise stats
        promise_count = db.query(Promise).count()
        promise_kept = db.query(Promise).filter(Promise.status == "KEPT").count()
        promise_broken = db.query(Promise).filter(Promise.status == "BROKEN").count()
        
        return MetricsSummary(
            total_invoices=total_cases,
            revenue_at_risk=revenue_at_risk,
            revenue_recovered=revenue_recovered,
            recovery_rate=recovery_rate,
            escalated_count=status_counts.get(CaseStatus.ESCALATED, 0),
            stopped_count=status_counts.get(CaseStatus.STOPPED, 0),
            promise_count=promise_count,
            promise_kept=promise_kept,
            promise_broken=promise_broken,
            average_time_to_recovery=None,
            cases_by_risk_level=risk_counts,
            cases_by_status=status_counts,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ADMIN ENDPOINTS

@router.post("/admin/reset")
def reset_database(db: Session = Depends(get_db)):
    """Reset database and clear all data"""
    
    try:
        # Clear all tables
        db.query(CaseSnapshot).delete()
        db.query(Promise).delete()
        db.query(Action).delete()
        db.query(Case).delete()
        db.query(Invoice).delete()
        db.query(Customer).delete()
        db.query(BatchRun).delete()
        db.query(AuditLog).delete()
        db.commit()
        
        # Clear audit log
        audit_logger.clear_audit_log()
        
        return {
            "status": "SUCCESS",
            "message": "Database reset complete"
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# DAY 2: RECOVERY WORKFLOW ENDPOINTS

@router.post("/batches/{batch_id}/vasooli-recovery")
def run_vasooli_recovery(batch_id: str, db: Session = Depends(get_db)):
    """
    Run complete Vasooli AI-powered recovery on a batch.
    
    Workflow for each case:
    - AI diagnosis
    - Action proposal
    - Policy validation
    - Near-miss pre-check
    - Execution (simulated)
    - Promise extraction if applicable
    """
    
    try:
        batch_run = db.query(BatchRun).filter(BatchRun.id == batch_id).first()
        if not batch_run:
            batch_run = db.query(BatchRun).filter(BatchRun.run_type == "VASOOLI").order_by(BatchRun.started_at.desc()).first()
            if not batch_run:
                raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
        
        batch_id = batch_run.id
        snapshots = db.query(CaseSnapshot).filter(CaseSnapshot.batch_id == batch_id).all()
        if not snapshots:
            # Fallback to latest batch snapshots if any
            latest_snap_batch = db.query(CaseSnapshot.batch_id).order_by(CaseSnapshot.created_at.desc()).first()
            if latest_snap_batch:
                snapshots = db.query(CaseSnapshot).filter(CaseSnapshot.batch_id == latest_snap_batch[0]).all()
        
        # Restore cases and invoices to their pristine snapshot starting conditions
        # This guarantees fair comparison regardless of execution order
        if snapshots:
            case_ids = [s.case_id for s in snapshots]
            db.query(Promise).filter(Promise.case_id.in_(case_ids)).delete(synchronize_session=False)
            db.query(Action).filter(Action.case_id.in_(case_ids)).delete(synchronize_session=False)
            
            for s in snapshots:
                inv = db.query(Invoice).filter(Invoice.id == s.invoice_id).first()
                if inv:
                    inv.status = s.invoice_status
                    inv.dispute_flag = s.dispute_flag
                    inv.dispute_reason = s.dispute_reason
                c = db.query(Case).filter(Case.id == s.case_id).first()
                if c:
                    c.status = s.initial_status
                    c.escalation_stage = 1
                    c.revenue_recovered = s.invoice_amount if s.initial_status == CaseStatus.PAYMENT_RECEIVED else 0.0
            db.commit()

        batch_run.status = "IN_PROGRESS"
        batch_run.run_type = "VASOOLI"
        db.commit()
        
        # Eligible cases: UNPAID and non-disputed invoices
        if snapshots:
            eligible_case_ids = [s.case_id for s in snapshots if s.invoice_status == "UNPAID" and not s.dispute_flag]
            eligible_cases = db.query(Case).filter(Case.id.in_(eligible_case_ids)).all()
            revenue_at_risk = sum(s.invoice_amount for s in snapshots if s.invoice_status == "UNPAID" and not s.dispute_flag)
        else:
            eligible_cases = db.query(Case).join(Invoice, Case.invoice_id == Invoice.id).filter(
                Case.status == CaseStatus.ACTIVE,
                Invoice.status == "UNPAID",
                Invoice.dispute_flag == False
            ).all()
            revenue_at_risk = sum(c.invoice.amount for c in eligible_cases)
        
        orchestrator = AIOrchestrator(db)
        results = []
        successful_count = 0
        
        for case in eligible_cases:
            try:
                result = orchestrator.run_recovery_for_case(case)
                results.append(result)
                if result.get("success"):
                    successful_count += 1
            except Exception as case_err:
                db.rollback()
                results.append({
                    "case_id": case.id,
                    "success": False,
                    "error": str(case_err)[:200],
                })
        
        # Calculate revenue recovered strictly from eligible cases
        if snapshots:
            recovered_query = db.query(func.sum(Case.revenue_recovered)).filter(
                Case.id.in_(eligible_case_ids)
            )
        else:
            recovered_query = db.query(func.sum(Case.revenue_recovered)).filter(
                Case.id.in_([c.id for c in eligible_cases])
            )
        total_recovered = recovered_query.scalar() or 0.0
        
        # Ensure recovered cannot exceed eligible revenue
        if revenue_at_risk > 0:
            total_recovered = min(total_recovered, revenue_at_risk)
            recovery_rate = (total_recovered / revenue_at_risk) * 100
        else:
            recovery_rate = 0.0
        
        # Count statuses
        escalated_count = db.query(Case).filter(Case.status == CaseStatus.ESCALATED).count()
        stopped_count = db.query(Case).filter(Case.status == CaseStatus.STOPPED).count()
        recovered_cases_count = db.query(Case).filter(Case.status == CaseStatus.PAYMENT_RECEIVED).count()
        promise_count = db.query(Promise).count()
        promise_kept = db.query(Promise).filter(Promise.status == "KEPT").count()
        promise_broken = db.query(Promise).filter(Promise.status == "BROKEN").count()
        
        batch_run.status = "COMPLETED"
        batch_run.completed_at = datetime.utcnow()
        batch_run.revenue_at_risk = revenue_at_risk
        batch_run.revenue_recovered = total_recovered
        batch_run.recovery_rate = recovery_rate
        batch_run.escalated_count = escalated_count
        batch_run.stopped_count = stopped_count
        batch_run.promise_count = promise_count
        batch_run.promise_kept = promise_kept
        batch_run.promise_broken = promise_broken
        db.commit()
        
        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "run_type": "VASOOLI",
            "total_cases": len(snapshots) if snapshots else len(eligible_cases),
            "eligible_cases": len(eligible_cases),
            "successful": successful_count,
            "recovered_cases": recovered_cases_count,
            "revenue_at_risk": revenue_at_risk,
            "revenue_recovered": total_recovered,
            "recovery_rate": recovery_rate,
            "escalated_count": escalated_count,
            "stopped_count": stopped_count,
            "promises_made": promise_count,
            "promises_kept": promise_kept,
            "promises_broken": promise_broken,
            "results": results[:10],
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batches/{batch_id}/baseline-recovery")
def run_baseline_recovery(batch_id: str, db: Session = Depends(get_db)):
    """
    Run baseline recovery (single generic reminder per eligible case).
    Evaluated on the exact untouched baseline snapshot for 100% fair comparison,
    independent of whether Vasooli ran before or after.
    """
    
    try:
        snapshots = db.query(CaseSnapshot).filter(CaseSnapshot.batch_id == batch_id).all()
        if not snapshots:
            # Fallback to latest batch snapshots
            latest_snap_batch = db.query(CaseSnapshot.batch_id).order_by(CaseSnapshot.created_at.desc()).first()
            if latest_snap_batch:
                snapshots = db.query(CaseSnapshot).filter(CaseSnapshot.batch_id == latest_snap_batch[0]).all()
        
        if not snapshots:
            raise HTTPException(status_code=404, detail=f"No baseline snapshot found for batch {batch_id}")
        
        # Eligible cases: UNPAID and non-disputed invoices in the untouched snapshot
        eligible_snapshots = [s for s in snapshots if s.invoice_status == "UNPAID" and not s.dispute_flag]
        revenue_at_risk = sum(s.invoice_amount for s in eligible_snapshots)
        
        total_recovered = 0.0
        successful_count = 0
        stopped_count = 0
        escalated_count = 0
        promise_count = 0
        
        sim = CustomerSimulator(seed=42)
        
        for s in eligible_snapshots:
            # Determine customer profile
            score = s.customer_reliability
            if score >= 0.8:
                profile = "Reliable"
            elif score >= 0.6:
                profile = "Stable"
            elif score >= 0.4:
                profile = "Slow"
            elif score >= 0.2:
                profile = "StressPay"
            else:
                profile = "NonResp"
            
            days_overdue = (date.today() - s.invoice_due_date).days if s.invoice_due_date else 0
            
            # Baseline is one generic reminder: gentle_nudge at stage 1
            resp_type, resp_text = sim.simulate_response(
                action="gentle_nudge",
                customer_profile=profile,
                invoice_amount=s.invoice_amount,
                days_overdue=days_overdue,
                escalation_stage=1,
                previous_attempts=0,
                reliability_score=s.customer_reliability,
            )
            
            if resp_type == CustomerResponseType.PAID:
                total_recovered += s.invoice_amount
                successful_count += 1
            elif resp_type == CustomerResponseType.PARTIAL_PAYMENT:
                total_recovered += s.invoice_amount / 2
                successful_count += 1
            elif resp_type == CustomerResponseType.PROMISE_TO_PAY:
                promise_count += 1
            elif resp_type == CustomerResponseType.DISPUTES:
                stopped_count += 1
            else:
                escalated_count += 1
        
        if revenue_at_risk > 0:
            total_recovered = min(total_recovered, revenue_at_risk)
            recovery_rate = (total_recovered / revenue_at_risk) * 100
        else:
            recovery_rate = 0.0
        
        # Create or update baseline batch record (does not mutate live cases/invoices)
        baseline_id = f"BASELINE-{batch_id}"
        batch_run = db.query(BatchRun).filter(BatchRun.id == baseline_id).first()
        if not batch_run:
            batch_run = BatchRun(id=baseline_id)
            db.add(batch_run)
        
        batch_run.run_type = "BASELINE"
        batch_run.status = "COMPLETED"
        batch_run.total_invoices = len(snapshots)
        batch_run.revenue_at_risk = revenue_at_risk
        batch_run.revenue_recovered = total_recovered
        batch_run.recovery_rate = recovery_rate
        batch_run.escalated_count = escalated_count
        batch_run.stopped_count = stopped_count
        batch_run.promise_count = promise_count
        batch_run.promise_kept = 0
        batch_run.promise_broken = 0
        batch_run.completed_at = datetime.utcnow()
        db.commit()
        
        # Log baseline evaluation event in audit trail
        audit_logger.set_session(db)
        audit_logger.log_event(
            event_type=AuditEventType.ACTION_EXECUTED,
            actor=Actor.SYSTEM,
            case_id=None,
            input_data={"run_type": "BASELINE", "eligible_cases": len(eligible_snapshots)},
            output_data={
                "revenue_recovered": total_recovered,
                "recovery_rate": recovery_rate,
                "successful": successful_count,
            },
            passed=True,
            reason=f"Baseline evaluation completed: {successful_count}/{len(eligible_snapshots)} recovered",
        )
        
        return {
            "batch_id": batch_run.id,
            "status": "COMPLETED",
            "run_type": "BASELINE",
            "total_cases": len(snapshots),
            "eligible_cases": len(eligible_snapshots),
            "successful": successful_count,
            "revenue_at_risk": revenue_at_risk,
            "revenue_recovered": total_recovered,
            "recovery_rate": recovery_rate,
            "escalated_count": escalated_count,
            "stopped_count": stopped_count,
            "promises_made": promise_count,
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/comparison")
def get_metrics_comparison(db: Session = Depends(get_db)):
    """Compare Vasooli vs Baseline recovery metrics with identical starting conditions"""
    
    try:
        # Get latest completed Vasooli batch
        vasooli_batch = db.query(BatchRun).filter(
            BatchRun.run_type == "VASOOLI",
            BatchRun.status == "COMPLETED"
        ).order_by(BatchRun.completed_at.desc()).first()
        
        # If no completed Vasooli batch, get any Vasooli batch
        if not vasooli_batch:
            vasooli_batch = db.query(BatchRun).filter(
                BatchRun.run_type == "VASOOLI"
            ).order_by(BatchRun.started_at.desc()).first()
        
        # Get latest completed Baseline batch
        baseline_batch = db.query(BatchRun).filter(
            BatchRun.run_type == "BASELINE",
            BatchRun.status == "COMPLETED"
        ).order_by(BatchRun.completed_at.desc()).first()
        
        vasooli_metrics = {
            "recovery_rate": vasooli_batch.recovery_rate or 0.0,
            "revenue_recovered": vasooli_batch.revenue_recovered or 0.0,
            "total_cases": vasooli_batch.total_invoices or 0,
            "revenue_at_risk": vasooli_batch.revenue_at_risk or 0.0,
        } if vasooli_batch else {"recovery_rate": 0, "revenue_recovered": 0, "total_cases": 0, "revenue_at_risk": 0}
        
        baseline_metrics = {
            "recovery_rate": baseline_batch.recovery_rate or 0.0,
            "revenue_recovered": baseline_batch.revenue_recovered or 0.0,
            "total_cases": baseline_batch.total_invoices or 0,
            "revenue_at_risk": baseline_batch.revenue_at_risk or 0.0,
        } if baseline_batch else {"recovery_rate": 0, "revenue_recovered": 0, "total_cases": 0, "revenue_at_risk": 0}
        
        improvement = vasooli_metrics["recovery_rate"] - baseline_metrics["recovery_rate"]
        
        return {
            "vasooli": vasooli_metrics,
            "baseline": baseline_metrics,
            "improvement_percentage_points": improvement,
            "improvement_lift": f"+{improvement:.1f}%" if improvement >= 0 else f"{improvement:.1f}%",
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/cases/{case_id}/mark-paid")
def mark_case_paid(case_id: str, db: Session = Depends(get_db)):
    """Mark a case as paid (simulating payment received)"""
    
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
        invoice = db.query(Invoice).filter(Invoice.id == case.invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail=f"Invoice not found")
        
        # Update invoice and case
        invoice.status = "PAID"
        case.status = CaseStatus.PAYMENT_RECEIVED
        case.revenue_recovered = invoice.amount
        
        # Log event
        audit_logger.set_session(db)
        audit_logger.log_event(
            event_type=AuditEventType.PAYMENT_RECEIVED,
            actor=Actor.ADMIN,
            case_id=case_id,
            input_data={},
            output_data={"recovered": invoice.amount},
            passed=True,
            reason="Marked as paid by user",
        )
        
        db.commit()
        
        return {
            "case_id": case_id,
            "status": "PAYMENT_RECEIVED",
            "recovered": invoice.amount,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/promises", response_model=List[PromiseResponse])
def get_case_promises(case_id: str, db: Session = Depends(get_db)):
    """Get all promises for a case"""
    try:
        promises = db.query(Promise).filter(Promise.case_id == case_id).all()
        return promises
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/promise/{promise_id}/status")
def update_promise_status(
    case_id: str,
    promise_id: str,
    new_status: str,
    db: Session = Depends(get_db),
):
    """Update promise status (MADE → KEPT/BROKEN/RENEGOTIATED)"""
    
    try:
        promise = db.query(Promise).filter(Promise.id == promise_id).first()
        if not promise:
            raise HTTPException(status_code=404, detail=f"Promise {promise_id} not found")
        
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
        # Validate status
        if new_status not in [PromiseStatus.KEPT, PromiseStatus.BROKEN, PromiseStatus.RENEGOTIATED]:
            raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
        
        old_status = promise.status
        if old_status == new_status:
            return {
                "promise_id": promise_id,
                "status": new_status,
                "amount": promise.promised_amount,
            }

        promise.status = new_status
        promise.resolved_at = datetime.utcnow()
        
        # If promise kept, mark case as payment received exactly once
        if new_status == PromiseStatus.KEPT:
            invoice = db.query(Invoice).filter(Invoice.id == case.invoice_id).first()
            if invoice:
                invoice.status = "PAID"
                case.revenue_recovered = min(invoice.amount, promise.promised_amount or invoice.amount)
            else:
                case.revenue_recovered = promise.promised_amount or 0.0
            case.status = CaseStatus.PAYMENT_RECEIVED
        elif new_status == PromiseStatus.BROKEN:
            # Move to next escalation stage and mark escalated
            case.escalation_stage = min(case.escalation_stage + 1, 4)
            case.status = CaseStatus.ESCALATED
        
        # Log event
        audit_logger.set_session(db)
        audit_logger.log_event(
            event_type=AuditEventType.PROMISE_STATUS_CHANGED,
            actor=Actor.ADMIN,
            case_id=case_id,
            input_data={"promise_id": promise_id, "old_status": old_status},
            output_data={"new_status": new_status, "promised_amount": promise.promised_amount},
            passed=True,
            reason=f"Promise marked as {new_status}",
        )
        
        db.commit()
        
        return {
            "promise_id": promise_id,
            "status": new_status,
            "amount": promise.promised_amount,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
