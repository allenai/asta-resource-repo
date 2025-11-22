"""Tests for Agent implementation."""

import pytest

from a2a_poc import Agent, TaskStatus


@pytest.fixture
def agent():
    """Create a test agent."""
    return Agent("test-agent-001")


@pytest.fixture
def handler():
    """Create a simple test handler."""

    async def test_handler(parameters, context):
        return {"echo": parameters.get("message")}

    return test_handler


async def test_agent_creation():
    """Test creating an agent."""
    agent = Agent("test-id")
    assert agent.agent_id == "test-id"
    assert len(agent.task_handlers) == 0


async def test_register_task_handler(agent, handler):
    """Test registering a task handler."""
    agent.register_task_handler("echo", handler)
    assert "echo" in agent.task_handlers
    assert agent.task_handlers["echo"] == handler


async def test_send_request(agent):
    """Test sending a request."""
    request = await agent.send_request(
        recipient="other-agent",
        task_type="test_task",
        parameters={"key": "value"},
        context={"ctx": "data"},
    )

    assert request.sender == agent.agent_id
    assert request.recipient == "other-agent"
    assert request.task_type == "test_task"
    assert request.parameters["key"] == "value"
    assert request.context["ctx"] == "data"
    assert request.message_id is not None
    assert request.task_id is not None


async def test_handle_request_success(agent, handler):
    """Test handling a successful request."""
    agent.register_task_handler("echo", handler)

    request = await agent.send_request(
        recipient=agent.agent_id, task_type="echo", parameters={"message": "hello"}
    )

    response = await agent.handle_request(request)

    assert response.status == TaskStatus.COMPLETED
    assert response.result["echo"] == "hello"
    assert response.error is None
    assert response.task_id == request.task_id


async def test_handle_request_unknown_task(agent):
    """Test handling a request for unknown task type."""
    request = await agent.send_request(
        recipient=agent.agent_id, task_type="unknown", parameters={}
    )

    response = await agent.handle_request(request)

    assert response.status == TaskStatus.FAILED
    assert "No handler registered" in response.error
    assert response.result is None


async def test_handle_request_handler_error(agent):
    """Test handling a request when handler raises exception."""

    async def failing_handler(parameters, context):
        raise ValueError("Handler error")

    agent.register_task_handler("fail", failing_handler)

    request = await agent.send_request(
        recipient=agent.agent_id, task_type="fail", parameters={}
    )

    response = await agent.handle_request(request)

    assert response.status == TaskStatus.FAILED
    assert "Handler error" in response.error
