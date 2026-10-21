"""Shared launch pacing and spending admission for background requests."""
from contextlib import contextmanager
import threading
import time

from . import cloud_runtime


class RequestCoordinator:
    def __init__(self, accounting, cap, *, fx=100, interval_seconds=15,
                 max_inflight=2, wait=time.sleep, clock=time.monotonic,
                 error_factory=RuntimeError):
        self.accounting, self.cap = accounting, cap
        self.fx, self.interval_seconds = fx, interval_seconds
        self.wait, self.clock, self.error_factory = wait, clock, error_factory
        self.slots = threading.BoundedSemaphore(max_inflight)
        self.launch_lock = threading.Lock()
        self.last_started = None

    @contextmanager
    def slot(self):
        with self.slots:
            yield

    @contextmanager
    def admission(self):
        with self.launch_lock:
            if self.last_started is not None:
                delay = self.interval_seconds - (self.clock() - self.last_started)
                if delay > 0:
                    self.wait(delay)
            with cloud_runtime.LOCK:
                yield

    def check_budget(self, reservation_usd):
        if self.accounting() + reservation_usd * self.fx > self.cap() + 1e-9:
            raise self.error_factory('The remaining allowance cannot cover another request reservation.')

    def started(self):
        self.last_started = self.clock()
