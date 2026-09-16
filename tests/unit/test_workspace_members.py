import pytest
from pydantic import ValidationError

from apps.api.app.workspaces.schemas import WorkspaceMemberCreate


def test_member_email_is_normalized_before_lookup() -> None:
    payload = WorkspaceMemberCreate(email="  Teammate@Example.com ")

    assert payload.email == "teammate@example.com"


@pytest.mark.parametrize("email", ["", "teammate", "@example.com", "teammate@"])
def test_member_email_must_have_a_valid_shape(email: str) -> None:
    with pytest.raises(ValidationError):
        WorkspaceMemberCreate(email=email)
