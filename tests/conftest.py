import pytest
from datetime import date
from lexau.models import ActMetadata


@pytest.fixture
def privacy_meta() -> ActMetadata:
    return ActMetadata(
        name="Privacy Act 1988",
        title_id="C2004A03712",
        comp_id="C2024C00280",
        comp_num="52",
        year=1988,
        number=119,
        effective_date=date(2024, 1, 1),
    )
