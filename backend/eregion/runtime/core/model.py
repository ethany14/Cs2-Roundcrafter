"""Interruptible provider requests; browser actions always stay on their owner thread."""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, wait
from contextvars import copy_context
from uuid import uuid4
from threading import Event
from eregion.runtime.provider_usage import current_scope, usage_scope


class ModelInterrupted(Exception):
    pass


class ModelRequests:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='agent-provider')

    def _detach(self, future, request_id, discarded):
        discarded.set()
        future.cancel()
        # Python cannot stop an in-flight SDK call. Its eventual result is
        # ignored; a fresh executor lets new steering proceed immediately.
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='agent-provider')
        self._discard(request_id)

    @staticmethod
    def _discard(request_id):
        ledger = current_scope().get('ledger')
        if ledger is not None:
            try:
                ledger.discard(request_id)
            except Exception as exc:
                logging.getLogger(__name__).warning('Usage discard marker failed: %s', type(exc).__name__)

    def call(self, invoke, *, active, timeout=45, pump=None):
        if not active():
            raise ModelInterrupted()
        request_id = str(uuid4())
        discarded = Event()
        with usage_scope(request_id=request_id, request_discarded=discarded):
            context = copy_context()
        queued = time.monotonic()
        def dispatched():
            with usage_scope(queue_wait_seconds=time.monotonic() - queued):
                return invoke()
        future = self.executor.submit(context.run, dispatched)
        deadline, next_check = time.monotonic() + timeout, time.monotonic() + .1
        while not future.done():
            moment = time.monotonic()
            if moment >= next_check:
                if not active():
                    self._detach(future, request_id, discarded)
                    raise ModelInterrupted()
                next_check = time.monotonic() + .1
            if moment >= deadline:
                self._detach(future, request_id, discarded)
                raise TimeoutError('Model request deadline exceeded.')
            if pump:
                pump()  # Keep Playwright events on the browser's owner thread.
            else:
                # Wakes immediately on completion; no fixed sleep added to replies.
                wait([future], timeout=max(0, min(next_check, deadline) - time.monotonic()))
        # Always check fresh state before accepting even an immediately finished call.
        if not active():
            discarded.set()
            self._discard(request_id)
            raise ModelInterrupted()
        return future.result()

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
