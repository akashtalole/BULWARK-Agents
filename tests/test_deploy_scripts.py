"""Regression guard for deploy/setup_gcp.sh: GCP IAM service-account
display names cap at 100 characters (`gcloud iam service-accounts
create --display-name`); the script builds each one as
`"BULWARK: ${SERVICE_ACCOUNTS[$SA]}"`, so a future edit that lengthens
one of those descriptions past the limit would only be discovered by
actually running the deploy script against a real GCP project. This
parses the same array setup_gcp.sh defines and checks that mechanically
instead, entirely offline."""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "deploy" / "setup_gcp.sh"
_DISPLAY_NAME_MAX_LENGTH = 100
_DISPLAY_NAME_PREFIX = "BULWARK: "
_ENTRY_PATTERN = re.compile(r'\["(sa-[\w-]+)"\]="([^"]*)"')


def _service_account_descriptions() -> dict[str, str]:
    text = _SCRIPT_PATH.read_text()
    array_body = text.split("declare -A SERVICE_ACCOUNTS=(", 1)[1].split("\n)", 1)[0]
    return dict(_ENTRY_PATTERN.findall(array_body))


def test_setup_gcp_sh_defines_the_twelve_service_accounts():
    descriptions = _service_account_descriptions()
    assert len(descriptions) == 12


def test_every_service_account_display_name_fits_gcp_s_limit():
    descriptions = _service_account_descriptions()
    assert descriptions, "failed to parse any SERVICE_ACCOUNTS entries from deploy/setup_gcp.sh"

    too_long = {
        sa: len(_DISPLAY_NAME_PREFIX) + len(description)
        for sa, description in descriptions.items()
        if len(_DISPLAY_NAME_PREFIX) + len(description) > _DISPLAY_NAME_MAX_LENGTH
    }
    assert not too_long, (
        f"These service-account display names exceed gcloud's {_DISPLAY_NAME_MAX_LENGTH}-char "
        f"limit and would fail `gcloud iam service-accounts create` at deploy time: {too_long}"
    )
