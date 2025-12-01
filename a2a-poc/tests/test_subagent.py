"""Tests for SyncAgent and AsyncAgent implementations."""

import asyncio
import uuid
from typing import Any, List

import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.types import (
    Message,
    MessageSendParams,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)

from a2a_poc.subagent import AsyncAgent, SyncAgent


class MockEventQueue:
    """Mock EventQueue for testing."""

    def __init__(self):
        self.events: List[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        """Record enqueued events."""
        self.events.append(event)


class MockTaskStore:
    """Mock TaskStore for testing."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}

    async def save(self, task: Task, call_context: ServerCallContext) -> None:
        """Save a task."""
        self.tasks[task.id] = task

    async def get(self, task_id: str, call_context: ServerCallContext) -> Task | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)


@pytest.fixture
def mock_event_queue():
    """Create a mock event queue."""
    return MockEventQueue()


@pytest.fixture
def mock_task_store():
    """Create a mock task store."""
    return MockTaskStore()


@pytest.fixture
def sync_agent():
    """Create a SyncAgent instance."""
    return SyncAgent()


@pytest.fixture
def async_agent(mock_task_store):
    """Create an AsyncAgent instance."""
    return AsyncAgent(mock_task_store)


@pytest.fixture
def request_context():
    """Create a test request context."""
    task_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    message = Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[TextPart(text="Hello, world!")],
    )
    request = MessageSendParams(message=message)
    return RequestContext(
        request=request,
        task_id=task_id,
        context_id=context_id,
        call_context=ServerCallContext(),
    )


# ==================== SyncAgent Tests ====================


async def test_sync_agent_creation(sync_agent):
    """Test creating a SyncAgent."""
    assert sync_agent is not None


async def test_sync_agent_execute(sync_agent, request_context, mock_event_queue):
    """Test SyncAgent execute method."""
    await sync_agent.execute(request_context, mock_event_queue)

    # Should have sent one message
    assert len(mock_event_queue.events) == 1

    # Check the message content
    message = mock_event_queue.events[0]
    assert isinstance(message, Message)
    assert message.role == Role.agent
    assert len(message.parts) == 1
    assert message.parts[0].root.kind == "text"

    # Message should contain the original text and reversed text
    text = message.parts[0].root.text
    assert "Hello, world!" in text
    assert "!dlrow ,olleH" in text  # reversed


async def test_sync_agent_execute_empty_message(sync_agent, mock_event_queue):
    """Test SyncAgent with no message."""
    # Create context without message
    context = RequestContext(
        task_id=str(uuid.uuid4()),
        context_id=str(uuid.uuid4()),
        call_context=ServerCallContext(),
    )

    result = await sync_agent.execute(context, mock_event_queue)

    # Should return None and not send any events
    assert result is None
    assert len(mock_event_queue.events) == 0


async def test_sync_agent_cancel(sync_agent, request_context, mock_event_queue):
    """Test SyncAgent cancel method."""
    result = await sync_agent.cancel(request_context, mock_event_queue)

    # SyncAgent cancel should return None
    assert result is None


# ==================== AsyncAgent Tests ====================


async def test_async_agent_creation(async_agent):
    """Test creating an AsyncAgent."""
    assert async_agent is not None
    assert async_agent.active_tasks is not None
    assert len(async_agent.active_tasks) == 0


async def test_async_agent_execute(async_agent, request_context, mock_event_queue, mock_task_store):
    """Test full AsyncAgent task lifecycle from start to completion."""
    await async_agent.execute(request_context, mock_event_queue)

    # Task should be removed from active_tasks
    assert request_context.task_id not in async_agent.active_tasks

    # Check event sequence
    events = mock_event_queue.events

    # Should have multiple events
    assert len(events) >= 7

    # Event 0: Initial Task
    assert isinstance(events[0], Task)
    assert events[0].status.state == TaskState.working

    # Event 1: Initial status update
    assert isinstance(events[1], TaskStatusUpdateEvent)
    assert events[1].status.state == TaskState.working
    assert events[1].final is False

    # Event 2+: Progress artifact updates (there are multiple as the task progresses)
    artifact_events = [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]
    assert len(artifact_events) >= 2  # At least progress and final artifact

    # Find the final status update (should be near the end)
    status_updates = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
    final_status = [s for s in status_updates if s.final is True]
    assert len(final_status) == 1
    assert final_status[0].status.state == TaskState.completed

    # Task should be marked as completed in store
    saved_task = await mock_task_store.get(request_context.task_id, request_context.call_context)
    assert saved_task.status.state == TaskState.completed


async def test_async_agent_cancel_task(async_agent, request_context, mock_event_queue, mock_task_store):
    """Test cancelling an active AsyncAgent task."""
    # Start the task
    asyncio.create_task(async_agent.execute(request_context, mock_event_queue))

    # Give the task a moment to start processing
    await asyncio.sleep(0.1)

    # Verify task is active
    assert request_context.task_id in async_agent.active_tasks

    # Clear events from execution
    mock_event_queue.events.clear()

    # Cancel the task
    await async_agent.cancel(request_context, mock_event_queue)

    # Task should be removed from active_tasks
    assert request_context.task_id not in async_agent.active_tasks

    # Should have sent cancellation message
    assert len(mock_event_queue.events) >= 1
    cancel_message = mock_event_queue.events[-1]
    assert isinstance(cancel_message, Message)
    assert "cancelled" in cancel_message.parts[0].root.text.lower()


async def test_async_agent_cancel_nonexistent_task(async_agent, request_context, mock_event_queue):
    """Test cancelling a task that doesn't exist."""
    # Don't start any task, just try to cancel
    await async_agent.cancel(request_context, mock_event_queue)

    # Should have sent message indicating task not found
    assert len(mock_event_queue.events) == 1
    message = mock_event_queue.events[0]
    assert isinstance(message, Message)
    assert "not found" in message.parts[0].root.text.lower()


async def test_async_agent_multiple_tasks(async_agent, mock_event_queue, mock_task_store):
    """Test running multiple AsyncAgent tasks concurrently."""
    # Create multiple request contexts
    contexts = []
    for i in range(3):
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[TextPart(text=f"Message {i}")],
        )
        request = MessageSendParams(message=message)
        contexts.append(
            RequestContext(
                request=request,
                task_id=task_id,
                context_id=context_id,
                call_context=ServerCallContext(),
            )
        )

    # Start all tasks
    for context in contexts:
        asyncio.create_task(async_agent.execute(context, mock_event_queue))

    await asyncio.sleep(0.1)

    # All tasks should be active
    for context in contexts:
        assert context.task_id in async_agent.active_tasks

    # Wait for all tasks to complete
    background_tasks = list(async_agent.active_tasks.values())
    await asyncio.wait_for(asyncio.gather(*background_tasks, return_exceptions=True), timeout=15)

    # All tasks should be removed from active_tasks
    assert len(async_agent.active_tasks) == 0

    # All tasks should be completed in store
    for context in contexts:
        saved_task = await mock_task_store.get(context.task_id, context.call_context)
        assert saved_task.status.state == TaskState.completed

