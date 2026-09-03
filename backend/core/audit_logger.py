import json
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path
from database.models import AuditLog
from config.settings import settings
from config.constants import AuditEventType, Actor


class AuditLogger:
    """
    Centralized audit logging for all system events.
    
    Stores audit records in both SQLite (for querying) and JSONL (for export).
    """
    
    def __init__(self):
        self.db_session = None
        self.jsonl_path = settings.AUDIT_LOG_PATH
        self._ensure_jsonl_file()
    
    def _ensure_jsonl_file(self):
        """Ensure JSONL file exists"""
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.jsonl_path.exists():
            self.jsonl_path.touch()
    
    def set_session(self, db_session):
        """Set the database session for persistence"""
        self.db_session = db_session
    
    def log_event(
        self,
        event_type: str,
        actor: str,
        case_id: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        passed: Optional[bool] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event (RISK_SCORE, DIAGNOSIS, POLICY_CHECK, etc.)
            actor: Who triggered the event (SYSTEM, LLM, POLICY_ENGINE, SIMULATOR)
            case_id: ID of the case (optional)
            input_data: Input to the operation
            output_data: Output from the operation
            passed: Whether the operation passed (True/False/None)
            reason: Human-readable reason for the event
            metadata: Additional metadata
        
        Returns:
            Audit log ID if stored in DB, else None
        """
        
        timestamp = datetime.utcnow()
        
        # Create the audit entry
        audit_entry = {
            "timestamp": timestamp.isoformat(),
            "case_id": case_id,
            "event_type": event_type,
            "actor": actor,
            "input_data": input_data,
            "output_data": output_data,
            "passed": passed,
            "reason": reason,
            "metadata": metadata,
        }
        
        # Write to JSONL file
        self._write_jsonl(audit_entry)
        
        # Write to database if session available
        audit_log_id = None
        if self.db_session is not None:
            audit_log_id = self._write_to_db(
                timestamp, case_id, event_type, actor,
                input_data, output_data, passed, reason, metadata
            )
        
        return audit_log_id
    
    def _write_jsonl(self, entry: Dict[str, Any]):
        """Write audit entry to JSONL file"""
        try:
            with open(self.jsonl_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            # Log to stderr but don't fail the application
            print(f"Warning: Failed to write audit log to JSONL: {e}")
    
    def _write_to_db(
        self,
        timestamp: datetime,
        case_id: Optional[str],
        event_type: str,
        actor: str,
        input_data: Optional[Dict],
        output_data: Optional[Dict],
        passed: Optional[bool],
        reason: Optional[str],
        metadata: Optional[Dict],
    ) -> int:
        """Write audit entry to database"""
        try:
            audit_log = AuditLog(
                timestamp=timestamp,
                case_id=case_id,
                event_type=event_type,
                actor=actor,
                input_data=input_data,
                output_data=output_data,
                passed=passed,
                reason=reason,
                metadata_info=metadata,
            )
            self.db_session.add(audit_log)
            self.db_session.commit()
            return audit_log.id
        except Exception as e:
            # Log error but don't fail
            print(f"Warning: Failed to write audit log to DB: {e}")
            self.db_session.rollback()
            return None
    
    def get_case_audit_trail(self, case_id: str, limit: int = 100) -> List[Dict]:
        """
        Get all audit entries for a case.
        
        Args:
            case_id: Case ID to retrieve audit trail for
            limit: Maximum number of entries to return
        
        Returns:
            List of audit entries
        """
        if self.db_session is None:
            return []
        
        try:
            entries = self.db_session.query(AuditLog).filter(
                AuditLog.case_id == case_id
            ).order_by(AuditLog.timestamp.desc()).limit(limit).all()
            
            return [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "case_id": e.case_id,
                    "event_type": e.event_type,
                    "actor": e.actor,
                    "input_data": e.input_data,
                    "output_data": e.output_data,
                    "passed": e.passed,
                    "reason": e.reason,
                    "metadata_info": e.metadata_info,
                }
                for e in entries
            ]
        except Exception as e:
            print(f"Warning: Failed to retrieve audit trail: {e}")
            return []
    
    def export_jsonl(self, output_path: Optional[Path] = None) -> Path:
        """
        Export audit log as JSONL.
        
        Args:
            output_path: Path to write JSONL file to (defaults to audit.jsonl)
        
        Returns:
            Path to the exported file
        """
        if output_path is None:
            output_path = self.jsonl_path
        
        # File is already in JSONL format
        return self.jsonl_path
    
    def clear_audit_log(self):
        """Clear all audit logs (useful for resetting)"""
        if self.db_session is not None:
            try:
                self.db_session.query(AuditLog).delete()
                self.db_session.commit()
            except Exception as e:
                print(f"Warning: Failed to clear audit log from DB: {e}")
                self.db_session.rollback()
        
        # Clear JSONL file
        try:
            self.jsonl_path.write_text("")
        except Exception as e:
            print(f"Warning: Failed to clear audit log JSONL: {e}")


# Global audit logger instance
audit_logger = AuditLogger()
