"""A report: corpus metadata plus one section per analysis."""

from dataclasses import dataclass
from enum import StrEnum

from aaspect.domain.blocks import Block


class SectionStatus(StrEnum):
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Section:
    """The result of one analysis. A failed section carries the reason instead of blocks,
    so one failing analysis does not take the rest of the report down."""

    key: str
    title: str
    status: SectionStatus
    blocks: tuple[Block, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is SectionStatus.FAILED and not self.reason:
            raise ValueError("a failed section needs a reason")


@dataclass(frozen=True, slots=True)
class Report:
    aaspect_version: str
    files: tuple[str, ...]
    sections: tuple[Section, ...]

    @property
    def finished(self) -> bool:
        unfinished = (SectionStatus.WAITING, SectionStatus.RUNNING)
        return all(section.status not in unfinished for section in self.sections)
