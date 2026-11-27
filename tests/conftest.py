"""Shared pytest fixtures. Populated as adapters and rules come online."""

from __future__ import annotations

import pytest

# The generators read these variables to find an Adobe credential. sdr-grader
# reads none of them, but its generator child inherits the environment, so no
# test may see the developer's own values.
ADOBE_CREDENTIAL_VARIABLES = (
    "ORG_ID",
    "CLIENT_ID",
    "SECRET",
    "SCOPES",
    "SANDBOX",
    "AA_PROFILE",
    "CJA_PROFILE",
)


@pytest.fixture(autouse=True)
def _clear_adobe_credential_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ADOBE_CREDENTIAL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
