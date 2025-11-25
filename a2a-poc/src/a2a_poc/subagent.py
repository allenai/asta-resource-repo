"""Subagent implementation using A2A SDK."""

import uuid
from typing import Any
from datetime import datetime

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Artifact, Message, Role, TextPart


class SubagentExecutor(AgentExecutor):
    """
    Subagent executor that processes tasks without maintaining state.

    The Subagent is responsible for:
    - Processing task requests from the Handler
    - Returning results with optional artifacts (as hydrated data)
    - Internal task tracking (not persisting conversation history)
    """

    def __init__(self):
        """Initialize the Subagent executor."""
        self.active_tasks: dict[str, dict[str, Any]] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a task request.

        Args:
            context: Request context containing task information
            event_queue: Queue for sending response events
        """
        # Extract task information from context
        task_id = context.task_id

        # Track this task
        self.active_tasks[task_id] = {
            "started_at": str(datetime.now()),
            "has_message": context.message is not None,
        }

        try:
            # Get the user's message
            user_message = ""
            if context.message:
                for part in context.message.parts:
                    if isinstance(part, TextPart):
                        user_message += part.text

            # Process the message (simple echo with processing indicator)
            result_text = f"Subagent processed: {user_message}"

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

        finally:
            # Clean up task tracking
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

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
