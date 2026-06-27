from dataclasses import dataclass, field
from datetime import date

from cobalt import FrbrUri as CobaltFrbrUri


@dataclass
class ActMetadata:
    name: str
    title_id: str
    comp_id: str
    comp_num: str
    year: int
    number: int
    effective_date: date
    long_title: str = ""
    subject_keywords: list[str] = field(default_factory=list)
    doc_type: str = "act"   # "act" | "regulation" | "instrument"

    @property
    def _cobalt_uri(self) -> CobaltFrbrUri:
        return CobaltFrbrUri(
            "au", None, self.doc_type, None, None,
            str(self.year), str(self.number),
            language="eng",
            expression_date=f"@{self.effective_date.isoformat()}",
        )

    @property
    def frbr_work_uri(self) -> str:
        return self._cobalt_uri.work_uri()

    @property
    def frbr_expression_uri(self) -> str:
        return self._cobalt_uri.expression_uri()

    @property
    def safe_name(self) -> str:
        return self.name.lower().replace(" ", "-").replace("/", "-")


@dataclass
class ParseReport:
    act_name: str
    volumes_fetched: int = 1
    preface_paras: int = 0
    schedules_found: int = 0
    schedule_names: list[str] = field(default_factory=list)
    subsections_parsed: int = 0
    paragraphs_parsed: int = 0
    subparagraphs_parsed: int = 0
    style_fallbacks: int = 0
    refs_resolved: int = 0
    refs_unresolved: int = 0
    # v0.3.0 additions
    schedule_clauses_found: int = 0
    notes_found: int = 0
    examples_found: int = 0
    penalties_found: int = 0
    level4_found: int = 0
    tables_found: int = 0
    # v0.4.0 additions
    terms_found: int = 0
    duplicate_terms: int = 0  # terms whose eId was overwritten (same term defined in 2+ sections)
    quantities_found: int = 0
    roles_found: int = 0
    note_refs_injected: int = 0
    # v0.5.0 additions
    dates_found: int = 0
    amendment_events_parsed: int = 0
    amendment_events_resolved: int = 0
    mods_resolved: int = 0
    mods_unresolved: int = 0
    quoted_structures_found: int = 0
    quoted_structures_unhandled: int = 0
