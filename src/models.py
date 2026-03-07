"""
Vsh-reflow - SQLAlchemy データモデル
Task, ApprovalRequest, AuditLog, CostRecord, AgentMessage, MeetingRecord
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# ============================================
# Enums
# ============================================

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    TIMED_OUT = "timed_out"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentRole(str, enum.Enum):
    PM = "PM-Agent"
    GROWTH = "Growth-Agent"
    CONTENT = "Content-Agent"
    DESIGN = "Design-Agent"
    ANALYST = "Analyst-Agent"
    GUARD = "Guard-Agent"
    PUB = "Pub-Agent"


# ============================================
# Models
# ============================================

class Task(Base):
    """タスクテーブル - 全エージェントタスクの記録"""
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    task_code = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text)
    task_type = Column(String(64), nullable=False)  # e.g. content_generation, research, image_gen
    assigned_agent = Column(Enum(AgentRole), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.NORMAL)
    payload = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    error_message = Column(Text)
    require_approval = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)
    discord_channel_id = Column(String(64))

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    deadline = Column(DateTime(timezone=True))

    # Relations
    approval_requests = relationship("ApprovalRequest", back_populates="task")
    audit_logs = relationship("AuditLog", back_populates="task")

    def __repr__(self):
        return f"<Task {self.task_code}: {self.title} [{self.status}]>"


class ApprovalRequest(Base):
    """承認リクエストテーブル"""
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    task_id = Column(UUID(as_uuid=False), ForeignKey("tasks.id"), nullable=False)
    requester_agent = Column(Enum(AgentRole), nullable=False)
    action_type = Column(String(64), nullable=False)  # e.g. sns_post, ad_spend
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.HIGH)
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)

    summary = Column(Text, nullable=False)
    details = Column(JSON, default=dict)
    preview_content = Column(Text)
    preview_image_url = Column(String(512))
    estimated_impact = Column(Text)
    guard_review = Column(Text)  # Guard-Agentの審査結果

    rejection_reason = Column(Text)
    edit_instructions = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    responded_at = Column(DateTime(timezone=True))
    reminder_sent_at = Column(DateTime(timezone=True))
    second_reminder_sent_at = Column(DateTime(timezone=True))
    timeout_at = Column(DateTime(timezone=True))

    # Relations
    task = relationship("Task", back_populates="approval_requests")

    def __repr__(self):
        return f"<ApprovalRequest {self.id[:8]}... [{self.status}]>"


class AuditLog(Base):
    """監査ログテーブル - 全アクションの記録（削除不可）"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    task_id = Column(UUID(as_uuid=False), ForeignKey("tasks.id"), nullable=True)
    agent = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False)
    details = Column(JSON, default=dict)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    cost_yen = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relations
    task = relationship("Task", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.agent}:{self.action} at {self.created_at}>"


class CostRecord(Base):
    """コスト記録テーブル"""
    __tablename__ = "cost_records"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    service = Column(String(64), nullable=False)  # e.g. openai, anthropic, fal_ai
    model = Column(String(64))
    operation = Column(String(64), nullable=False)  # e.g. chat_completion, image_gen
    cost_yen = Column(Float, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    agent = Column(String(64))
    task_id = Column(String(64))

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    period_month = Column(String(7), nullable=False)  # e.g. "2026-03"

    def __repr__(self):
        return f"<CostRecord {self.service}:{self.operation} ¥{self.cost_yen}>"


class AgentMessage(Base):
    """エージェント間メッセージテーブル"""
    __tablename__ = "agent_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    message_id = Column(String(64), unique=True, nullable=False)
    from_agent = Column(String(64), nullable=False)
    to_agent = Column(String(64), nullable=False)
    message_type = Column(String(64), nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.NORMAL)
    payload = Column(JSON, default=dict)
    require_approval = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<AgentMessage {self.from_agent}->{self.to_agent}: {self.message_type}>"


class MeetingRecord(Base):
    """AI会議記録テーブル"""
    __tablename__ = "meeting_records"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    meeting_code = Column(String(64), unique=True, nullable=False)
    topic = Column(String(256), nullable=False)
    trigger = Column(String(64), nullable=False)  # manual / scheduled
    status = Column(String(32), default="in_progress")  # in_progress, completed, cancelled

    agenda = Column(JSON, default=dict)
    participants = Column(JSON, default=list)  # list of AgentRole
    discussions = Column(JSON, default=list)  # [{agent, content, timestamp}]
    decisions = Column(JSON, default=list)
    action_items = Column(JSON, default=list)
    approval_request_id = Column(String(64))

    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<MeetingRecord {self.meeting_code}: {self.topic}>"
