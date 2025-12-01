"""Subagent implementation using A2A SDK."""

import asyncio
import logging
import uuid
from typing import Dict

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks.task_store import TaskStore
from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)


class AsyncAgent(AgentExecutor):
    """
    Subagent executor that starts asynchronous tasks
    """

    def __init__(self, task_store: TaskStore) -> None:
        """Initialize the Subagent executor."""
        self._task_store = task_store
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute a task request.

        Args:
            context: Request context containing task information
            event_queue: Queue for sending response events
        """
        # Extract task information from context
        task_id = context.task_id
        context_id = context.context_id

        # Get the user's message
        user_message = ""
        if context.message:
            for part in context.message.parts:
                if part.root.kind == "text":
                    user_message += part.root.text

        # Create and save task with "working" status
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.working),
        )
        await self._task_store.save(task, context.call_context)

        try:
            # Publish initial Task to event queue
            await event_queue.enqueue_event(task)

            # Send initial status update indicating task is working
            status_update = TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.working),
                final=False,
            )
            await event_queue.enqueue_event(status_update)

            # Start heartbeat task to keep connection alive
            heartbeat_task = asyncio.create_task(
                self._send_heartbeat(task_id, context_id, event_queue)
            )

            # Create and start background task to do the actual work
            background_task = asyncio.create_task(
                self._process_task(task_id, context_id, user_message, context, event_queue)
            )
            self.active_tasks[task_id] = background_task

            try:
                # Wait for the background task to complete
                # This keeps the event_queue open until all events are published
                await background_task
            finally:
                # Cancel heartbeat task
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass  # Expected when heartbeat is cancelled

        except Exception as e:
            logging.exception(f"Error starting task {task_id}: {e}")
            # Update task to failed status
            failed_task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.failed),
            )
            await self._task_store.save(failed_task, context.call_context)

            # Send final status update
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    status=TaskStatus(state=TaskState.failed),
                    final=True,
                )
            )

    async def _send_heartbeat(self, task_id: str, context_id: str, event_queue: EventQueue) -> None:
        """
        Send periodic keepalive heartbeat events to prevent client timeout.
        Runs until cancelled.

        Args:
            task_id: The task ID
            context_id: The context ID
            event_queue: Queue for sending response events
        """
        heartbeat_interval = 1.0  # Send heartbeat every second

        try:
            while True:
                await asyncio.sleep(heartbeat_interval)

                # Send keepalive status update
                heartbeat_event = TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    status=TaskStatus(state=TaskState.working),
                    final=False,
                )
                await event_queue.enqueue_event(heartbeat_event)
        except asyncio.CancelledError:
            # Heartbeat was cancelled - task is complete
            logging.debug(f"Heartbeat for task {task_id} cancelled")
            raise

    async def _process_task(
        self, task_id: str, context_id: str, user_message: str, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """
        Background task processing logic.

        Args:
            task_id: The task ID
            context_id: The context ID
            user_message: The user's message
            context: Request context
            event_queue: Queue for sending response events
        """
        try:
            step_progress_artifact = Artifact(
                artifact_id=str(uuid.uuid4()),
                name="Task Progress",
                description="Detailed steps being performed by the agent",
                parts=[Part(root=DataPart(data={"step": "reading"}))],
            )

            progress_event = TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact = step_progress_artifact,
            )
            await event_queue.enqueue_event(progress_event)

            # Simulate some async work
            await asyncio.sleep(2)
            step_progress_artifact.parts.append(Part(root=DataPart(data={"step": "computing"})))
            await event_queue.enqueue_event(progress_event)

            await asyncio.sleep(2)
            step_progress_artifact.parts.append(Part(root=DataPart(data={"step": "writing"})))
            await event_queue.enqueue_event(progress_event)

            # Process the message (reverse it as a simple demonstration)
            reversed_msg = "".join(reversed(user_message))

            # Update task to completed status
            completed_task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.completed),
            )
            await self._task_store.save(completed_task, context.call_context)

            result_artifact = Artifact(
                artifact_id=str(uuid.uuid4()),
                name="Task Result Artifact",
                description="Artifact containing the result of the task",
                parts=[
                    Part(root = DataPart(
                        data={"result": reversed_msg}
                    ))
                ],
            )

            # Send final artifact with task outcome
            final_artifact = TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=result_artifact,
            )
            await event_queue.enqueue_event(final_artifact)

            # Send final status update event
            final_status = TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.completed),
                final=True,
            )
            await event_queue.enqueue_event(final_status)

            # Send completion message after final status
            completion_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                task_id=task_id,
                parts=[Part(root=TextPart(text="Task completed successfully!"))],
            )
            await event_queue.enqueue_event(completion_message)

        except asyncio.CancelledError:
            logging.info(f"Task {task_id} was cancelled")
            # Update task to canceled status
            canceled_task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.canceled),
            )
            await self._task_store.save(canceled_task, context.call_context)

            # Send final status update for cancellation
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    status=TaskStatus(state=TaskState.canceled),
                    final=True,
                )
            )
            raise
        except Exception as e:
            logging.error(f"Error processing task {task_id}: {e}")
            # Update task to failed status
            failed_task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.failed),
            )
            await self._task_store.save(failed_task, context.call_context)

            # Send final status update for failure
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    status=TaskStatus(state=TaskState.failed),
                    final=True,
                )
            )
        finally:
            # Clean up active task
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
            # Cancel the background task
            background_task = self.active_tasks[task_id]
            background_task.cancel()

            try:
                # Wait for the task to handle cancellation
                await background_task
            except asyncio.CancelledError:
                pass  # Expected when task is cancelled
            finally:
                # Ensure task is removed from active_tasks
                # (the finally block in _process_task should do this, but we ensure it here)
                self.active_tasks.pop(task_id, None)

                # Give the event loop a chance to run any pending callbacks
                await asyncio.sleep(0)

            message_text = f"Task {task_id} has been cancelled"
        else:
            message_text = f"Task {task_id} not found or already completed"

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

            # Create response messageFinis
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
