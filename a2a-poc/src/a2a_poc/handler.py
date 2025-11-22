"""Handler agent implementation using A2A SDK."""

import uuid
from typing import Optional

import httpx
from a2a.client import A2AClient
from a2a.client.helpers import create_text_message_object
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import Event, EventQueue
from a2a.types import DataPart, Message, Role, Task, TextPart

from a2a_poc.storage import (
    IArtifactStore,
    IConversationHistory,
    InMemoryArtifactStore,
    InMemoryConversationHistory,
)


class HandlerExecutor(AgentExecutor):
    """
    Handler agent executor that manages conversation and delegates to Subagent.

    The Handler is responsible for:
    - Managing conversation history
    - Persisting artifacts
    - Building context from conversation history
    - Delegating tasks to the Subagent
    - Converting hydrated artifacts to references
    """

    def __init__(
        self,
        subagent_url: str = "http://localhost:9001",
        artifact_store: Optional[IArtifactStore] = None,
        conversation_history: Optional[IConversationHistory] = None,
    ):
        """
        Initialize the Handler executor.

        Args:
            subagent_url: URL of the Subagent A2A server
            artifact_store: Optional artifact store (creates in-memory if None)
            conversation_history: Optional conversation history (creates in-memory if None)
        """
        self.subagent_url = subagent_url
        self.artifact_store = artifact_store or InMemoryArtifactStore()
        self.conversation_history = conversation_history or InMemoryConversationHistory()

        # Create A2A client for communicating with subagent
        self.httpx_client = httpx.AsyncClient(timeout=30.0)
        self.a2a_client = A2AClient(
            httpx_client=self.httpx_client,
            url=subagent_url,
        )

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a task request from the user.

        Args:
            context: Request context containing task information
            event_queue: Queue for sending response events
        """
        # Extract user message
        user_message_text = ""
        if context.message:
            for part in context.message.parts:
                if isinstance(part, TextPart):
                    user_message_text += part.text

        # Store user message in conversation history
        user_msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[TextPart(text=user_message_text)],
        )
        await self.conversation_history.add_message(user_msg)

        # Build context from conversation history (get all parts)
        history_parts = await self.conversation_history.get_messages()
        history_context_text = ""
        for part in history_parts:
            if isinstance(part, TextPart):
                history_context_text += part.text + "\n"

        # Send request to Subagent using A2A client
        try:
            # Create message for subagent
            all_messages = await self.conversation_history.get_all_messages()
            message_text = f"Context: {len(all_messages)} previous messages\n\n" f"Current request: {user_message_text}"
            message = create_text_message_object(role=Role.user, content=message_text)

            # Send message and collect responses
            response_text = "Subagent response received"
            artifacts_to_persist = []

            async for event in self.a2a_client.send_message(message):
                # Handle Message responses
                if isinstance(event, Message):
                    for part in event.parts:
                        if isinstance(part, TextPart):
                            response_text = part.text
                        # Check if it's a DataPart (artifact)
                        elif isinstance(part, DataPart):
                            # Persist artifact and get file reference
                            file_ref = await self.artifact_store.store(part)
                            artifacts_to_persist.append(file_ref.uri)

                # Handle Task events (tuple of Task and UpdateEvent)
                elif isinstance(event, tuple) and len(event) == 2:
                    task, update_event = event
                    # Could process task status updates here if needed
                    pass

            # Store assistant response in conversation history
            assistant_parts = [TextPart(text=response_text)]
            assistant_msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=assistant_parts,
                metadata={"artifact_refs": artifacts_to_persist} if artifacts_to_persist else None,
            )
            await self.conversation_history.add_message(assistant_msg)

            # Send response to user (with artifact references, not hydrated data)
            response_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=response_text)],
            )

            event_queue.enqueue_event(
                Event(
                    message=response_message,
                    taskId=context.task_id,
                    eventId=str(uuid.uuid4()),
                )
            )

            if artifacts_to_persist:
                artifact_info_message = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.agent,
                    parts=[TextPart(text=f"\nArtifacts stored: {', '.join(artifacts_to_persist)}")],
                )
                event_queue.enqueue_event(
                    Event(
                        message=artifact_info_message,
                        taskId=context.task_id,
                        eventId=str(uuid.uuid4()),
                    )
                )

        except Exception as e:
            error_msg = f"Error communicating with Subagent: {str(e)}"
            error_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=error_msg)],
            )
            event_queue.enqueue_event(
                Event(
                    message=error_message,
                    taskId=context.task_id,
                    eventId=str(uuid.uuid4()),
                )
            )

            # Store error in conversation history
            error_history_msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=error_msg)],
            )
            await self.conversation_history.add_message(error_history_msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Cancel a running task.

        Args:
            context: Request context
            event_queue: Queue for sending response events
        """
        cancel_message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[TextPart(text=f"Task {context.task_id} cancellation requested")],
        )
        event_queue.enqueue_event(
            Event(
                message=cancel_message,
                taskId=context.task_id,
                eventId=str(uuid.uuid4()),
            )
        )

    async def close(self) -> None:
        """
        Close the HTTP client and clean up resources.
        """
        await self.httpx_client.aclose()
