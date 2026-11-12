"""Lint the documents of a corpus while the import reads them, and report it afterward."""

import logging
import traceback

from aaspect.app.import_corpus import ImportResult
from aaspect.domain.blocks import Finding, Location, Severity
from aaspect.domain.id_collisions import Environment
from aaspect.domain.lint.linter import Linter
from aaspect.domain.lint.section import lint_blocks
from aaspect.domain.report import Section, SectionStatus
from aaspect.domain.templates.catalogue import Catalogue

SECTION_KEY = "lint"
SECTION_TITLE = "Lint"

logger = logging.getLogger(__name__)


class CorpusLint:
    """Fed every environment the import reads. A failure of the linter on one document is
    noted and the next one linted: the import must not count a document as unreadable
    because the linter tripped over it, nor lose the lint of the others."""

    def __init__(self) -> None:
        self._linter = Linter()
        self._failed: list[str] = []
        self._observed: set[str] = set()

    def observe(self, label: str, environment: Environment) -> None:
        self._observed.add(label)
        try:
            self._linter.add(label, environment)
        except Exception as error:  # Noted for the report; the next document is linted.
            self._failed.append(label)
            # Only the type and the stack: the message can quote values from the file.
            # The error is not kept, since its frames hold the whole environment.
            stack = "".join(traceback.format_tb(error.__traceback__))
            logger.error("Lint failed on a document: %s\n%s", type(error).__name__, stack)

    def section(
        self, catalogue: Catalogue | Exception | None, imported: ImportResult | None = None
    ) -> Section:
        """`catalogue`: the templates the corpus was checked against, an exception if
        they could not be loaded, None without templates."""
        template_ids = catalogue.submodel_ids if isinstance(catalogue, Catalogue) else None
        blocks = [*lint_blocks(self._linter.finish(template_ids))]
        if self._failed:
            blocks.append(
                Finding(
                    "lint-failed",
                    Severity.WARNING,
                    f"Linted only in part: the linter failed on {len(self._failed):,} files."
                    " The server log has the details.",
                    tuple(Location(file=label) for label in self._failed[:1_000]),
                )
            )
        unlinted = [
            failure.source
            for failure in (imported.not_imported if imported is not None else ())
            if failure.source not in self._observed
        ]
        if unlinted:
            blocks.append(
                Finding(
                    "lint-coverage",
                    Severity.INFO,
                    f"{len(unlinted):,} files not linted: the import could not read them, or"
                    " refused them for their size or the time limit (see Graph import).",
                    tuple(Location(file=label) for label in unlinted[:1_000]),
                )
            )
        return Section(SECTION_KEY, SECTION_TITLE, SectionStatus.COMPLETED, tuple(blocks))
