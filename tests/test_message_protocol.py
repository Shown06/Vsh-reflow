"""
Vsh-reflow - メッセージプロトコル テスト
"""

import pytest
from src.message_protocol import (
    AgentMessage,
    MessageConstraints,
    MessagePayload,
    MeetingInvite,
    TaskResult,
)


class TestAgentMessage:
    def test_create_basic_message(self):
        msg = AgentMessage.create(
            from_agent="Growth-Agent",
            to_agent="Content-Agent",
            msg_type="task_request",
            task="content_generation",
            context="テストコンテキスト",
        )
        assert msg.from_agent == "Growth-Agent"
        assert msg.to_agent == "Content-Agent"
        assert msg.type == "task_request"
        assert msg.payload.task == "content_generation"
        assert msg.payload.context == "テストコンテキスト"
        assert msg.priority == "normal"
        assert msg.require_approval is False

    def test_create_message_with_constraints(self):
        msg = AgentMessage.create(
            from_agent="Growth-Agent",
            to_agent="Content-Agent",
            msg_type="task_request",
            task="content_generation",
            constraints={"tone": "casual_professional", "length": "max_280chars", "platform": "X"},
        )
        assert msg.payload.constraints is not None
        assert msg.payload.constraints.tone == "casual_professional"
        assert msg.payload.constraints.platform == "X"

    def test_create_high_priority_message(self):
        msg = AgentMessage.create(
            from_agent="Guard-Agent",
            to_agent="PM-Agent",
            msg_type="alert",
            task="cost_alert",
            priority="critical",
        )
        assert msg.priority == "critical"

    def test_message_id_is_unique(self):
        msg1 = AgentMessage.create(from_agent="A", to_agent="B", msg_type="test", task="test")
        msg2 = AgentMessage.create(from_agent="A", to_agent="B", msg_type="test", task="test")
        assert msg1.message_id != msg2.message_id

    def test_to_dict(self):
        msg = AgentMessage.create(
            from_agent="PM-Agent",
            to_agent="Growth-Agent",
            msg_type="task_request",
            task="research",
        )
        d = msg.to_dict()
        assert d["from"] == "PM-Agent"
        assert d["to"] == "Growth-Agent"
        assert d["type"] == "task_request"
        assert "message_id" in d
        assert "timestamp" in d

    def test_require_approval(self):
        msg = AgentMessage.create(
            from_agent="Pub-Agent",
            to_agent="PM-Agent",
            msg_type="task_request",
            task="sns_post",
            require_approval=True,
        )
        assert msg.require_approval is True


class TestMeetingInvite:
    def test_create_meeting_invite(self):
        invite = MeetingInvite(
            topic="テストテーマ",
            participants=["Growth-Agent", "Content-Agent", "Design-Agent"],
            agenda=["議題1", "議題2"],
        )
        assert invite.topic == "テストテーマ"
        assert len(invite.participants) == 3

    def test_to_messages(self):
        invite = MeetingInvite(
            topic="テスト",
            participants=["Growth-Agent", "Content-Agent"],
            agenda=["議題1"],
        )
        messages = invite.to_messages()
        assert len(messages) == 2
        assert messages[0].to_agent == "Growth-Agent"
        assert messages[1].to_agent == "Content-Agent"
        assert all(m.type == "meeting_invite" for m in messages)


class TestTaskResult:
    def test_create_task_result(self):
        result = TaskResult(
            task_id="TASK-001",
            agent="Growth-Agent",
            success=True,
            result_data={"research": "テスト結果"},
            cost_yen=1.5,
            execution_time_seconds=3.2,
        )
        assert result.success is True
        assert result.cost_yen == 1.5

    def test_to_message(self):
        result = TaskResult(
            task_id="TASK-001",
            agent="Growth-Agent",
            success=True,
        )
        msg = result.to_message("PM-Agent")
        assert msg.from_agent == "Growth-Agent"
        assert msg.to_agent == "PM-Agent"
        assert msg.type == "task_response"
