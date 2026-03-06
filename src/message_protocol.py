"""
Vsh-reflow - エージェント間通信プロトコル
§4.3 準拠のメッセージフォーマット。
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class MessageConstraints(BaseModel):
    """メッセージ制約"""
    tone: Optional[str] = None  # casual_professional, formal, etc.
    length: Optional[str] = None  # max_280chars, etc.
    platform: Optional[str] = None  # X, Instagram, etc.
    format: Optional[str] = None


class MessagePayload(BaseModel):
    """メッセージペイロード"""
    task: str
    context: str = ""
    constraints: Optional[MessageConstraints] = None
    deadline: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    """
    エージェント間通信メッセージ
    要件定義書 §4.3 準拠のプロトコル
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")
    type: str  # task_request, task_response, meeting_invite, status_update, alert
    priority: str = "normal"  # low, normal, high, critical
    payload: MessagePayload
    require_approval: bool = False
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict[str, Any]:
        """DB保存用の辞書変換"""
        return self.model_dump(by_alias=True)

    @classmethod
    def create(
        cls,
        from_agent: str,
        to_agent: str,
        msg_type: str,
        task: str,
        context: str = "",
        priority: str = "normal",
        require_approval: bool = False,
        constraints: Optional[dict] = None,
        deadline: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> "AgentMessage":
        """ファクトリメソッド"""
        payload = MessagePayload(
            task=task,
            context=context,
            constraints=MessageConstraints(**constraints) if constraints else None,
            deadline=deadline,
            data=data or {},
        )
        return cls(
            **{
                "from": from_agent,
                "to": to_agent,
                "type": msg_type,
                "priority": priority,
                "payload": payload,
                "require_approval": require_approval,
            }
        )


class TaskResult(BaseModel):
    """タスク実行結果"""
    task_id: str
    agent: str
    success: bool
    result_data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    cost_yen: float = 0.0
    execution_time_seconds: float = 0.0

    def to_message(self, to_agent: str) -> AgentMessage:
        """結果をメッセージに変換"""
        return AgentMessage.create(
            from_agent=self.agent,
            to_agent=to_agent,
            msg_type="task_response",
            task="task_result",
            context=f"Task {self.task_id} completed: {'success' if self.success else 'failed'}",
            data=self.model_dump(),
        )


class MeetingInvite(BaseModel):
    """AI会議招待"""
    meeting_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    agenda: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    trigger: str = "manual"  # manual / scheduled
    scheduled_at: Optional[str] = None

    def to_messages(self) -> list[AgentMessage]:
        """各参加者への招待メッセージを生成"""
        messages = []
        for participant in self.participants:
            msg = AgentMessage.create(
                from_agent="PM-Agent",
                to_agent=participant,
                msg_type="meeting_invite",
                task="attend_meeting",
                context=f"AI社内会議: {self.topic}",
                data={
                    "meeting_id": self.meeting_id,
                    "agenda": self.agenda,
                    "participants": self.participants,
                },
            )
            messages.append(msg)
        return messages
