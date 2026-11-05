import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import BoundedSemaphore, Lock
from credit.security.worker import environment


class WorkerError(ValueError):
    pass


class Runner:
    def __init__(self, limits):
        self.limits = limits
        self.slots = BoundedSemaphore(limits["concurrency"])
        self.active = {}
        self.cancelled = set()
        self.lock = Lock()

    def cancel(self, key):
        with self.lock:
            process = self.active.get(key)
            if process is None or process.poll() is not None:
                return False
            self.cancelled.add(key)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return False
            return True

    def run(self, operation, parameters, sources=None):
        if not self.slots.acquire(
            timeout=min(5, max(0, float(os.getenv("CREDIT_SCAN_QUEUE_WAIT_SECONDS", "5"))))
        ):
            raise WorkerError("busy")
        task_key = parameters.get("task_key")
        try:
            with tempfile.TemporaryDirectory(prefix="credit_scan_") as directory:
                root = Path(directory)
                refs = {}
                for key, source in (sources or {}).items():
                    path = root / f"source_{len(refs)}.bin"
                    path.write_bytes(source["payload"])
                    refs[key] = {"path": str(path), "inspection": source.get("inspection")}
                effective = {
                    key: min(value, parameters.get("limits", self.limits)[key])
                    for key, value in self.limits.items()
                }
                job = {
                    "operation": operation,
                    "parameters": parameters,
                    "sources": refs,
                    "limits": effective,
                }
                input_path, output_path = root / "job.json", root / "result.json"
                input_path.write_text(json.dumps(job))
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "credit.documents.worker",
                        str(input_path),
                        str(output_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env={**environment(), "TMPDIR": str(root)},
                )
                if task_key:
                    with self.lock:
                        self.active[task_key] = process
                try:
                    process.wait(timeout=effective["timeout_seconds"])
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                    raise WorkerError("processing_timeout") from None
                if task_key in self.cancelled:
                    raise WorkerError("processing_cancelled")
                if process.returncode or not output_path.exists():
                    raise WorkerError("worker_failed_or_resource_limit")
                answer = json.loads(output_path.read_text())
                if "error" in answer:
                    raise WorkerError(answer["error"])
                for key in ["derivative_pdf", "preview_png"]:
                    if key in answer:
                        path = (root / answer[key]).resolve()
                        if not path.is_relative_to(root):
                            raise WorkerError("invalid_worker_output")
                        answer[key] = path.read_bytes()
                return answer
        except OSError:
            raise WorkerError("worker_io_unavailable") from None
        finally:
            if task_key:
                with self.lock:
                    self.active.pop(task_key, None)
                    self.cancelled.discard(task_key)
            self.slots.release()
