"""Handler agent implementation using A2A SDK."""
import logging
import uuid
from typing import Optional

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, Role, TextPart

from a2a_poc.storage import (
    IArtifactStore,
    IConversationHistory,
    InMemoryArtifactStore,
    InMemoryConversationHistory,
)


class PassThroughHandler(AgentExecutor):
    """
    Handler agent executor that forwards messages to a single subagent

    The Handler is responsible for:
    - Managing conversation history
    - Persisting artifacts created by the subagent
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

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a task request from the user.

        Args:
            context: Request context containing task information
            event_queue: Queue for sending response events
        """
        if not context.message:
            return None

        # Store user message in conversation history
        await self.conversation_history.add_message(context.message)

        # Send request to Subagent using A2A client
        try:
            # Attach conversation history to the message
            all_messages = await self.conversation_history.get_all_messages()
            history_data = [msg.model_dump() for msg in all_messages]
            asta_metadata = {"asta": {
                "conversation_history": history_data,
                "history_length": len(all_messages),
            }
            }
            merged_metadata = (context.message.metadata or {}) | asta_metadata
            # The handler and subagent will have distinct task_ids for the same request
            # Clear the auto-assigned task_id here to allow the subagent to assign its own task_id
            # Below, we reassign the handler's task_id to the response
            handler_task_id = context.task_id
            message = context.message.model_copy(
                deep=True,
                update = {"metadata": merged_metadata, "task_id": None }
            )

            # Send message and forward response
            # Increase timeout to handle long-running subagent operations
            httpx_client = httpx.AsyncClient(timeout=120.0)
            client_config = ClientConfig(httpx_client=httpx_client, streaming=True)
            a2a_client = await ClientFactory.connect(
                agent=self.subagent_url,
                client_config=client_config,
            )
            async for event in a2a_client.send_message(message):
                # For each forwarded message/event, we need to:
                # 1. Convert hydrated DataParts to artifact references
                # 2. Store assistant response in conversation history
                # 3. Send response to user with artifact references
                if isinstance(event, Message):
                    logging.info(f"Received Message with {len(event.parts)} parts")
                    ref_parts = await self.artifact_store.persist(event.parts)
                    modified_message = event.model_copy(deep=True, update = {"parts": ref_parts})
                    await event_queue.enqueue_event(modified_message)
                    await self.conversation_history.add_message(modified_message)

                # Handle Task events (tuple of Task and UpdateEvent)
                elif isinstance(event, tuple) and len(event) == 2:
                    task, update_event = event
                    if not update_event:
                        # Initial task creation
                        logging.info(f"Received Task: {task.id}, ")
                        modified_artifacts = []
                        for artifact in (task.artifacts or []):
                            ref_parts = await self.artifact_store.persist(artifact.parts)
                            modified_artifact = artifact.model_copy(deep=True, update = {"parts": ref_parts})
                            modified_artifacts.append(modified_artifact)
                        # Reassign the handler's task_id to the result
                        modified_task = task.model_copy(deep=True, update = {"artifacts": modified_artifacts, "id": handler_task_id})
                        await event_queue.enqueue_event(modified_task)
                    else:
                        # Task update event
                        logging.info(f"Received {type(update_event).__name__} for Task: {task.id}")
                        modified_event = update_event.model_copy(deep=True, update = {"task_id": handler_task_id})
                        if hasattr(update_event, "artifact") and update_event.artifact:
                            ref_parts = await self.artifact_store.persist(update_event.artifact.parts)
                            modified_artifact = update_event.artifact.model_copy(deep=True, update = {"parts": ref_parts})
                            modified_event = modified_event.model_copy(deep=True, update = {"artifact": modified_artifact})
                        await event_queue.enqueue_event(modified_event)

        except Exception as e:
            logging.exception(e)
            error_msg = f"Error communicating with Subagent: {str(e)}"
            error_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[TextPart(text=error_msg)],
            )
            await event_queue.enqueue_event(error_message)

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
        await event_queue.enqueue_event(cancel_message)

    async def close(self) -> None:
        """
        Clean up resources.

        Note: The Client created by ClientFactory manages its own resources.
        """
        pass
