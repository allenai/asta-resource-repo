"""Subagent implementation using A2A SDK."""

import logging
import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks.task_store import TaskStore
from a2a.types import Message, Role, Task, TaskState, TaskStatus, TextPart


class AsyncAgent(AgentExecutor):
    """
    Subagent executor that starts asynchronous tasks
    """

    def __init__(self, task_store: TaskStore) -> None:
        """Initialize the Subagent executor."""
        self._task_store = task_store

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a task request.

        Args:
            context: Request context containing task information
            event_queue: Queue for sending response events
        """
        # Extract task information from context
        task_id = context.task_id
        task = Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.working),
        )
        await self._task_store.save(task, context.call_context)

        try:
            # Get the user's message
            user_message = ""
            if context.message:
                for part in context.message.parts:
                    if part.root.kind == "text":
                        user_message += part.root.text

            # Process the message (simple echo with processing indicator)
            result_text = f"Working on task '{user_message}'"

            # Create response message
            response_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=result_text)],
            )

            # Send message to event queue

            await event_queue.enqueue_event(response_message)

            # Send artifact in another event
            artifact_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=f"Task ID: {task_id}\nProcessed message: {user_message}")],
            )

            await event_queue.enqueue_event(artifact_message)

        except Exception as e:
            logging.error(e)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Cancel a running task.

        Args:
            context: Request context
            event_queue: Queue for sending response events
        """
        task_id = context.task_id
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
            message_text = f"Task {task_id} cancelled"
        else:
            message_text = f"Task {task_id} not found"

        cancel_message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[TextPart(text=message_text)],
        )

        await event_queue.enqueue_event(cancel_message)


class SyncAgent(AgentExecutor):
    """
    Subagent executor that echos a user message
    """

    def __init__(self) -> None:
        """Initialize"""
        pass

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a task request.

        Args:
            context: Request context containing task information
            event_queue: Queue for sending response events
        """

        if not context.message:
            return None

        try:
            # Get the user's message
            user_message = "\n".join(
                part.root.text for part in context.message.parts if part.root.kind == "text")

            # Process the message (simple echo with processing indicator)
            reversed_msg = "".join(c for c in reversed(user_message))
            result_text = f"You say '{user_message}'. I say '{reversed_msg}'"

            # Create response message
            response_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=result_text)],
            )

            await event_queue.enqueue_event(response_message)
        except Exception as e:
            logging.error("Error processing request", e)
            return None

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        No tasks to cancel for SyncAgent.
        """
        return None
