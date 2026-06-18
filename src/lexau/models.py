from dataclasses import dataclass
from datetime import date


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
    def frbr_work_uri(self) -> str:
        return f"/akn/au/act/{self.year}/{self.number}"

    @property
    def frbr_expression_uri(self) -> str:
        d = self.effective_date.isoformat()
        return f"/akn/au/act/{self.year}/{self.number}/eng@{d}"

    @property
    def safe_name(self) -> str:
        return self.name.lower().replace(" ", "-").replace("/", "-")
