"""Regression guards for the fullstack-on-Cloud-Run build: the Dockerfile
builds frontend/ as static assets and copies them into the same image as
the backend, and main.py mounts that exact directory at "/" so one Cloud
Run service serves both the API and the dashboard, same-origin. These
two halves have to agree on the directory name mechanically -- nothing
here is checked at type-check time since one side is a Dockerfile and
the other is Python.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DOCKERFILE = _ROOT / "Dockerfile"
_DOCKERIGNORE = _ROOT / ".dockerignore"
_MAIN_PY = _ROOT / "src" / "bulwark" / "main.py"


def test_dockerfile_builds_the_frontend_in_a_separate_stage():
    text = _DOCKERFILE.read_text()
    assert re.search(r"FROM node.* AS frontend-build", text), (
        "Dockerfile no longer has a named frontend-build stage -- the fullstack image "
        "needs the dashboard built with npm before the Python stage can copy it in."
    )
    assert "npm run build" in text, "Dockerfile's frontend-build stage no longer runs `npm run build`."


def test_dockerfile_copies_the_frontend_build_into_the_directory_main_py_mounts():
    dockerfile_text = _DOCKERFILE.read_text()
    main_text = _MAIN_PY.read_text()

    copy_match = re.search(r"COPY --from=frontend-build \S+/dist \./(\S+)", dockerfile_text)
    assert copy_match, "Dockerfile no longer copies the frontend build output into the final image"
    copied_dir_name = copy_match.group(1)

    mount_match = re.search(r'_STATIC_DIR = .* / "(\w+)"', main_text)
    assert mount_match, "main.py's _STATIC_DIR no longer looks like a simple relative directory name"
    mounted_dir_name = mount_match.group(1)

    assert copied_dir_name == mounted_dir_name, (
        f"Dockerfile copies the frontend build to ./{copied_dir_name} but main.py mounts "
        f"{mounted_dir_name!r} -- the dashboard would 404 on every route in the deployed image."
    )


def test_main_py_mounts_static_files_after_the_api_router_not_before():
    text = _MAIN_PY.read_text()
    include_router_pos = text.find("app.include_router(router)")
    mount_pos = text.find("app.mount(")
    assert include_router_pos != -1, "main.py no longer calls app.include_router(router)"
    assert mount_pos != -1, "main.py no longer mounts the dashboard's static files"
    assert include_router_pos < mount_pos, (
        "main.py mounts static files before including the API router -- Starlette matches "
        "routes/mounts in registration order, so this would let the dashboard's catch-all "
        "mount shadow API routes like /vendors instead of the other way around."
    )


def test_dockerignore_excludes_frontend_build_artifacts_from_the_build_context():
    text = _DOCKERIGNORE.read_text()
    for pattern in ("frontend/node_modules", "frontend/dist"):
        assert pattern in text, (
            f"'.dockerignore' no longer excludes {pattern} -- without this, a local npm install/build "
            "gets uploaded into the Cloud Build context and re-copied into the frontend-build stage "
            "before RUN npm ci even runs, which is slow and can shadow what npm ci would otherwise "
            "install fresh."
        )
