from enum import Enum


class RiskLevel(str, Enum):
    """Risk levels for revenue at risk"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


class ActionType(str, Enum):
    """Approved actions for revenue recovery"""
    GENTLE_NUDGE = "gentle_nudge"
    FIRM_REMINDER = "firm_reminder"
    PAYMENT_RETRY = "payment_retry"
    PAYMENT_LINK = "payment_link"
    PROMISE_TO_PAY = "promise_to_pay"
    HUMAN_ESCALATION = "human_escalation"
    STOP = "stop"


class CaseStatus(str, Enum):
    """Status of a recovery case"""
    ACTIVE = "ACTIVE"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    ESCALATED = "ESCALATED"
    STOPPED = "STOPPED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ActionStatus(str, Enum):
    """Status of an action"""
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class PromiseStatus(str, Enum):
    """Status of a promise-to-pay"""
    MADE = "MADE"
    KEPT = "KEPT"
    BROKEN = "BROKEN"
    RENEGOTIATED = "RENEGOTIATED"


class AuditEventType(str, Enum):
    """Types of audit events"""
    RISK_SCORE = "RISK_SCORE"
    DIAGNOSIS = "DIAGNOSIS"
    ACTION_PROPOSAL = "ACTION_PROPOSAL"
    POLICY_CHECK = "POLICY_CHECK"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    PROMISE_EXTRACTED = "PROMISE_EXTRACTED"
    PROMISE_STATUS_CHANGED = "PROMISE_STATUS_CHANGED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    ESCALATION = "ESCALATION"
    CASE_CREATED = "CASE_CREATED"
    CASE_COMPLETED = "CASE_COMPLETED"
    NEAR_MISS_PREVENTED = "near_miss_prevented"


class Actor(str, Enum):
    """System actors"""
    SYSTEM = "SYSTEM"
    LLM = "LLM"
    POLICY_ENGINE = "POLICY_ENGINE"
    SIMULATOR = "SIMULATOR"
    ADMIN = "ADMIN"
    RAZORPAY_TEST = "razorpay_test"


# Policy thresholds
MAX_CONTACT_ATTEMPTS = 5
COOLDOWN_AFTER_PROMISE_DAYS = 7
CONTACT_FREQUENCY_PER_DAY = 2
PROMISE_CONFIDENCE_THRESHOLD = 0.6
LOW_RISK_SCORE = 30
MEDIUM_RISK_SCORE = 60
HIGH_RISK_SCORE = 80
