from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    status: StageStatus
    output_path: str | None = None
    error: str | None = None
    metadata: dict | None = None


class Stage(ABC):
    name: str
    depends_on: list[str] = []

    @abstractmethod
    def is_complete(self, job_id: str, db: "JobDB") -> bool:
        ...

    @abstractmethod
    def run(self, job_id: str, db: "JobDB", config: "Settings") -> StageResult:
        ...

    def max_retries(self) -> int:
        return 2
