"""Regression guards for the deploy/ scripts: things that only ever
surface by actually running them against a real GCP project, checked
here mechanically and offline instead.

1. GCP IAM service-account display names cap at 100 characters (`gcloud
   iam service-accounts create --display-name`); setup_gcp.sh builds each
   one as `"BULWARK: ${SERVICE_ACCOUNTS[$SA]}"`, so a future edit that
   lengthens a description past the limit needs catching before a deploy
   attempt, not during one.
2. deploy_cloud_run.sh pushes to an Artifact Registry repository named
   literally `cloud-run-source-deploy`; setup_gcp.sh is what creates that
   repository (Artifact Registry never auto-creates one, unlike the
   legacy gcr.io registry). If the two scripts' repo names ever drift
   apart, the image push fails with "Repository ... not found" -- this
   asserts they still agree.
"""

from __future__ import annotations

import re
from pathlib import Path

_DEPLOY_DIR = Path(__file__).resolve().parent.parent / "deploy"
_SETUP_SCRIPT = _DEPLOY_DIR / "setup_gcp.sh"
_DEPLOY_SCRIPT = _DEPLOY_DIR / "deploy_cloud_run.sh"
_DISPLAY_NAME_MAX_LENGTH = 100
_DISPLAY_NAME_PREFIX = "BULWARK: "
_ENTRY_PATTERN = re.compile(r'\["(sa-[\w-]+)"\]="([^"]*)"')


def _service_account_descriptions() -> dict[str, str]:
    text = _SETUP_SCRIPT.read_text()
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


def test_setup_gcp_sh_creates_the_artifact_registry_repo_deploy_cloud_run_sh_pushes_to():
    setup_text = _SETUP_SCRIPT.read_text()
    deploy_text = _DEPLOY_SCRIPT.read_text()

    created_repo_match = re.search(r"gcloud artifacts repositories create (\S+)", setup_text)
    assert created_repo_match, "setup_gcp.sh no longer creates an Artifact Registry repository"

    pushed_repo_match = re.search(r"docker\.pkg\.dev/\$\{PROJECT_ID\}/([\w-]+)/", deploy_text)
    assert pushed_repo_match, "deploy_cloud_run.sh's IMAGE variable format changed in a way this check doesn't recognize"

    assert created_repo_match.group(1) == pushed_repo_match.group(1), (
        f"setup_gcp.sh creates repository {created_repo_match.group(1)!r} but "
        f"deploy_cloud_run.sh pushes to {pushed_repo_match.group(1)!r} -- the image push will 404"
    )
