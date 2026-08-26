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
3. The Firestore database the app connects to must be a genuinely named
   database, never the special "(default)" one -- confirmed via a real
   Cloud Run deploy crash (see platform/store.py's module docstring):
   google-cloud-firestore's Python client resolves an omitted `database`
   kwarg to the literal string "(default)" just the same as passing it
   explicitly, and something downstream percent-encodes that string's
   parentheses before Firestore sees it, which then rejects the mangled
   result with "Invalid database id %28default%29" on every single
   startup. setup_gcp.sh and deploy_cloud_run.sh must agree on the same
   named database, and neither may fall back to "(default)".
4. deploy_cloud_run.sh sets no `--service-account`, so Cloud Run runs the
   app as the project's default Compute Engine service account --
   confirmed via a real Cloud Run crash (a permission error on the first
   real Firestore/Vertex AI/Pub/Sub call) that setup_gcp.sh must grant
   that same identity the app's actual runtime permissions
   (roles/datastore.user, roles/aiplatform.user, roles/pubsub.publisher).
   None of the twelve per-agent service accounts setup_gcp.sh creates are
   suitable for this -- sa-supervisor in particular is deliberately
   Firestore-less by the zero-trust identity model's own design, and the
   single Cloud Run process makes every agent's actual GCP calls, so its
   own runtime identity needs to be broad enough for the app to function
   at all; platform/identity.py's per-agent grant table is what enforces
   least-privilege at the application level instead.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_DEPLOY_DIR = Path(__file__).resolve().parent.parent / "deploy"
_SETUP_SCRIPT = _DEPLOY_DIR / "setup_gcp.sh"
_DEPLOY_SCRIPT = _DEPLOY_DIR / "deploy_cloud_run.sh"
_FRONTEND_DEPLOY_SCRIPT = _DEPLOY_DIR / "deploy_frontend.sh"
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


def test_setup_gcp_sh_and_deploy_cloud_run_sh_agree_on_a_named_firestore_database():
    setup_text = _SETUP_SCRIPT.read_text()
    deploy_text = _DEPLOY_SCRIPT.read_text()

    setup_match = re.search(r'gcloud firestore databases create --database="\$\{FIRESTORE_DATABASE:-([^}"]+)\}"', setup_text)
    assert setup_match, "setup_gcp.sh's Firestore database creation command changed in a way this check doesn't recognize"

    deploy_match = re.search(r"FIRESTORE_DATABASE=\$\{FIRESTORE_DATABASE:-([^},]+)\}", deploy_text)
    assert deploy_match, "deploy_cloud_run.sh no longer sets FIRESTORE_DATABASE in --set-env-vars"

    setup_db, deploy_db = setup_match.group(1), deploy_match.group(1)
    assert setup_db == deploy_db, (
        f"setup_gcp.sh creates Firestore database {setup_db!r} but deploy_cloud_run.sh points the "
        f"app at {deploy_db!r} -- the app will fail to find/write to it"
    )
    assert setup_db != "(default)", (
        'The default Firestore database id must never be the literal string "(default)" -- confirmed '
        "via a real Cloud Run crash that the Python client resolves to that literal string regardless "
        "of how it's passed, and something downstream percent-encodes its parentheses, which Firestore "
        "then rejects with 'Invalid database id %28default%29' on every startup."
    )


def test_deploy_cloud_run_sh_sets_no_service_account_flag():
    deploy_text = _DEPLOY_SCRIPT.read_text()
    assert "--service-account=" not in deploy_text, (
        "deploy_cloud_run.sh now sets --service-account, so Cloud Run no longer runs the app as the "
        "default Compute Engine SA setup_gcp.sh grants runtime permissions to -- if this is deliberate, "
        "make sure whatever identity is set here actually has roles/datastore.user, "
        "roles/aiplatform.user, and roles/pubsub.publisher (none of the twelve per-agent service "
        "accounts setup_gcp.sh creates do; sa-supervisor in particular is deliberately Firestore-less)."
    )


def test_setup_gcp_sh_grants_the_compute_sa_the_apps_runtime_permissions():
    setup_text = _SETUP_SCRIPT.read_text()
    for role in ("roles/datastore.user", "roles/aiplatform.user", "roles/pubsub.publisher"):
        assert f'--role="{role}"' in setup_text, (
            f"setup_gcp.sh no longer grants {role} to the default Compute Engine service account -- "
            "confirmed via a real Cloud Run crash that the app runs as that identity (deploy_cloud_run.sh "
            "sets no --service-account) and fails on its first real GCP call without these roles."
        )


def test_deploy_frontend_sh_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(_FRONTEND_DEPLOY_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, f"deploy/deploy_frontend.sh has a syntax error:\n{result.stderr}"


def test_deploy_cloud_run_sh_threads_seed_demo_data_through():
    deploy_text = _DEPLOY_SCRIPT.read_text()
    assert "BULWARK_SEED_DEMO_DATA=${BULWARK_SEED_DEMO_DATA:-false}" in deploy_text, (
        "deploy_cloud_run.sh's --set-env-vars no longer threads BULWARK_SEED_DEMO_DATA through from the "
        "caller's shell -- confirmed via a real deploy where `BULWARK_SEED_DEMO_DATA=true "
        "./deploy/deploy_cloud_run.sh` silently deployed with no demo data, because every other var here "
        "(FIRESTORE_DATABASE, GEMINI_FLASH_MODEL, ...) is threaded through with a ${VAR:-default} "
        "fallback except this one, which was simply missing from the --set-env-vars list."
    )
