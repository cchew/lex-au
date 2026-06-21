from dataclasses import dataclass
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

    @property
    def _cobalt_uri(self) -> CobaltFrbrUri:
        return CobaltFrbrUri(
            "au", None, "act", None, None,
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
