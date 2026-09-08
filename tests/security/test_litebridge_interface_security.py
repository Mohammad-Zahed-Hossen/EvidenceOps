from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.api.routes.litebridge import (
    AnswerApiRequest,
    CompressContextApiRequest,
    PrepareContextApiRequest,
)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (PrepareContextApiRequest, {"query": "q", "url": "https://example.invalid"}),
        (PrepareContextApiRequest, {"query": "q", "path": "C:/secret"}),
        (AnswerApiRequest, {"provider_id": "local", "model": "override"}),
        (AnswerApiRequest, {"provider_id": "local", "api_key": "secret"}),
        (CompressContextApiRequest, {"shell_command": "whoami"}),
    ],
)
def test_real_api_request_models_reject_unapproved_fields(
    model: type, payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)
