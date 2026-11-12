"""Submodel templates uploaded with an analysis, checked against before IDTA's own."""

from collections.abc import Sequence

from aaspect.domain.corpus import Upload
from aaspect.domain.report import ShownError
from aaspect.domain.templates.catalogue import Catalogue, CatalogueProblem, TemplateFile, Tier
from aaspect.ports.corpus_reader import CorpusReader
from aaspect.ports.environment_parser import EnvironmentParser
from aaspect.ports.template_source import TemplateSource


def read_templates(
    uploads: Sequence[Upload], reader: CorpusReader, parser: EnvironmentParser
) -> tuple[list[TemplateFile], list[CatalogueProblem]]:
    """Each AAS document in the uploads as a template file, and why the others are left
    out. They are as untrusted as the corpus and read the same way."""
    corpus = reader.read(uploads)
    files: list[TemplateFile] = []
    problems = [CatalogueProblem(failure.source, failure.reason) for failure in corpus.failures]
    for document in corpus.documents:
        try:
            environment = parser.parse(document)
        except (ValueError, RecursionError) as error:
            reason = str(error) if isinstance(error, ValueError) else "nested too deeply"
            problems.append(CatalogueProblem(document.label, reason))
            continue
        files.append(TemplateFile(document.label, Tier.CUSTOM, environment))
    return files, problems


class WithUploaded:
    """A `TemplateSource`: `base` extended by the templates uploaded with one analysis.
    They are read when the catalogue is asked for, inside the step that reports a
    failure, and only their compiled form is kept. While the base has none to give, the
    uploaded ones are used alone, and the report says why."""

    def __init__(
        self,
        base: TemplateSource | None,
        uploads: Sequence[Upload],
        reader: CorpusReader,
        parser: EnvironmentParser,
    ) -> None:
        self._base = base
        self._uploads = uploads
        self._reader = reader
        self._parser = parser

    def catalogue(self, wait_seconds: float = 0) -> Catalogue:
        files, problems = read_templates(self._uploads, self._reader, self._parser)
        base = unavailable = None
        if self._base is not None:
            try:
                base = self._base.catalogue(wait_seconds)
            except ShownError as error:
                if not files and not problems:
                    raise
                unavailable = str(error)
        return Catalogue(files, base=base, problems=problems, unavailable=unavailable)


def with_uploaded(
    base: TemplateSource | None,
    uploads: Sequence[Upload],
    reader: CorpusReader | None,
    parser: EnvironmentParser | None,
) -> TemplateSource | None:
    """The template source of one analysis: `base`, extended by its uploaded templates.
    `reader` is the one for templates, with a budget of their own."""
    if not uploads or reader is None or parser is None:
        return base
    return WithUploaded(base, uploads, reader, parser)
