"""Run schema validation in worker processes with a time and memory limit.

libxml2 can spend minutes on one crafted value (its pattern matching grows steeply
with the length of a value that fails), and jsonschema-rs aborts the whole process
when an allocation fails. Neither can be interrupted from Python, so each validation
runs in a separate process that is killed and replaced when it exceeds its limits.
"""

import multiprocessing
import queue
import resource
from collections.abc import Callable, Sequence
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess

from aaspect.adapters.schema.violations import unchecked
from aaspect.domain.corpus import AasDocument
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation
from aaspect.ports.schema_validator import SchemaValidator

# spawn, not fork: forking a process that runs threads (the web server) can deadlock.
_CONTEXT = multiprocessing.get_context("spawn")


class IsolatedSchemaValidator:
    """A `SchemaValidator` that delegates to validators built by `factory` in workers.

    `factory` must be picklable (a module-level class or function). Safe to call from
    several threads; each call occupies one worker.
    """

    def __init__(
        self,
        factory: Callable[[], SchemaValidator],
        workers: int,
        timeout_seconds: float,
        memory_bytes: int,
    ) -> None:
        self._factory = factory
        self._timeout = timeout_seconds
        self._memory = memory_bytes
        factory()  # A broken schema must fail here, at startup, not inside a worker.
        # An empty slot (None) is refilled on its next use, so a worker that fails to
        # start costs that call, not the slot.
        self._idle: queue.Queue[_Worker | None] = queue.Queue()
        for _ in range(workers):
            self._idle.put(self._start())

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        worker = self._idle.get()
        try:
            worker = self._usable(worker)
            try:
                outcome = worker.run(document, version, self._timeout)
            except _WorkerGone:
                # It died while idle (e.g. killed by the system); the document is not
                # to blame, so it gets one more try with a fresh worker.
                worker = self._start()
                outcome = worker.run(document, version, self._timeout)
        except _WorkerGone:
            outcome = _ABORTED
        finally:
            self._idle.put(worker if worker is not None and worker.alive else None)
        return outcome if isinstance(outcome, list) else [outcome]

    def close(self) -> None:
        while not self._idle.empty():
            worker = self._idle.get()
            if worker is not None:
                worker.stop()

    def _usable(self, worker: "_Worker | None") -> "_Worker":
        return worker if worker is not None and worker.alive else self._start()

    def _start(self) -> "_Worker":
        return _Worker(self._factory, self._memory)


class _WorkerGone(Exception):
    pass


_ABORTED = unchecked("validation-aborted", "Validation aborted: the worker process stopped.")


class _Worker:
    def __init__(self, factory: Callable[[], SchemaValidator], memory: int) -> None:
        self._connection, child = _CONTEXT.Pipe()
        self._process: BaseProcess = _CONTEXT.Process(
            target=_serve, args=(child, memory), daemon=True
        )
        self._process.start()
        child.close()
        self._memory = memory
        self.alive = True
        # Sent over the connection, not as a start argument: the factory carries the
        # schemas, and a start argument larger than the pipe buffer blocks the parent for
        # good if the new process dies before reading it.
        try:
            self._connection.send(factory)
        except (BrokenPipeError, ConnectionError, EOFError, OSError):
            self.stop()

    def run(
        self, document: AasDocument, version: MetamodelVersion, timeout: float
    ) -> list[SchemaViolation] | SchemaViolation:
        try:
            self._connection.send((document, version))
        except (BrokenPipeError, ConnectionError, EOFError, OSError) as error:
            self.stop()
            raise _WorkerGone from error
        except BaseException:
            self.stop()
            raise
        if not self._connection.poll(timeout):
            self.stop()
            return unchecked(
                "validation-timeout",
                f"Validation stopped after {timeout:g} s. Some values (e.g. very long ones "
                "that fail a pattern) make the schema check extremely slow.",
            )
        try:
            kind, payload = self._connection.recv()
        except (EOFError, OSError):
            self.stop()
            return unchecked(
                "validation-aborted",
                f"Validation aborted: it needed more than {self._memory // 2**20} MB "
                "of memory or crashed.",
            )
        if kind == "error":
            return unchecked("validation-error", f"Validation failed: {payload}")
        return payload

    def stop(self) -> None:
        self.alive = False
        self._process.kill()
        self._process.join()
        self._connection.close()


def _serve(connection: Connection, memory: int) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    try:
        factory = connection.recv()
    except EOFError:
        return
    validator = factory()
    while True:
        try:
            document, version = connection.recv()
        except EOFError:
            return
        try:
            connection.send(("ok", list(validator.validate(document, version))))
        except Exception as error:  # Reported as a violation; the worker stays usable.
            connection.send(("error", repr(error)[:300]))
