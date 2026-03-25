import asyncio
from typing import Awaitable, Coroutine


class BroadcastChannel[T]:
    def __init__(self) -> None:
        self.subscriptions: list[asyncio.Queue[T]] = []

    def publish(self, message: T) -> None:
        to_remove = []
        for i, sub in enumerate(self.subscriptions):
            try:
                sub.put_nowait(message)
            except asyncio.QueueShutDown:
                to_remove.append(i)

        for i in reversed(to_remove):
            del self.subscriptions[i]

    def subscribe(self) -> "Subscription[T]":
        return Subscription(self)


class Subscription[T]:
    def __init__(self, channel: BroadcastChannel[T]) -> None:
        self.channel: BroadcastChannel = channel
        self.queue: asyncio.Queue[T] = asyncio.Queue()

    def __enter__(self) -> "Subscription[T]":
        self.channel.subscriptions.append(self.queue)
        return self

    def __exit__(self, type, value, traceback) -> None:
        self.channel.subscriptions.remove(self.queue)

    async def get(self) -> T | None:
        try:
            return await self.queue.get()
        except asyncio.QueueShutDown:
            return None


class StatusIndicator[T]:
    def __init__(self, initial: T) -> None:
        self.channel: BroadcastChannel[T] = BroadcastChannel()
        self.value = initial

    def set_value(self, value: T) -> None:
        self.value = value
        self.channel.publish(value)

    def subscribe(self) -> "Subscription[T]":
        sub = self.channel.subscribe()
        sub.queue.put_nowait(self.value)
        return sub


class CancelToken:
    def __init__(self):
        self.event = asyncio.Event()

    def is_cancelled(self) -> bool:
        return self.event.is_set()

    def cancel(self) -> None:
        return self.event.set()

    async def await_task_or_cancel[T](self, task: Coroutine[None, None, T]) -> T | None:
        main_task = asyncio.create_task(task)
        cancel_task = asyncio.create_task(self.event.wait())
        done, _ = await asyncio.wait(
            [main_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
        )
        if cancel_task in done:
            main_task.cancel()
            return None
        else:
            cancel_task.cancel()
            return await main_task
