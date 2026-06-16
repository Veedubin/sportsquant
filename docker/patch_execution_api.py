#!/usr/bin/env python3
"""
Airflow 3.1.6 Execution API Patch Script

This script fixes the Cadwyn VersionedAPIRouter prefix stripping bug that causes
KubernetesExecutor worker pods to fail with 404 errors.

Root Cause:
-----------
The Cadwyn library's VersionedAPIRouter strips the `prefix` parameter from
included routers during version generation. This causes routes defined as
`/task-instances/{id}/run` to be served at `/{id}/run`, breaking worker SDK
communication.

Fix:
----
1. Replace VersionedAPIRouter with APIRouter in routes/__init__.py
2. Replace CadwynWithOpenAPICustomization with FastAPI in app.py
3. Replace generate_and_include_versioned_routers with include_router in app.py

Usage:
------
# During container startup (in pod command):
python /opt/airflow/patches/patch_execution_api.py

# Or during Docker build (more efficient):
COPY k8s/airflow/patches/patch_execution_api.py /opt/airflow/patches/
RUN python /opt/airflow/patches/patch_execution_api.py

Author: NBA Analytics Pipeline
Issue: apache/airflow#51235
"""

import os
import sys

# Paths to patch
APP_PY = (
    "/home/airflow/.local/lib/python3.12/site-packages/"
    "airflow/api_fastapi/execution_api/app.py"
)
ROUTES_INIT_PY = (
    "/home/airflow/.local/lib/python3.12/site-packages/"
    "airflow/api_fastapi/execution_api/routes/__init__.py"
)


def check_file_exists(path: str) -> bool:
    """Check if file exists and is readable."""
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        return False
    return True


def is_already_patched_routes_init(content: str) -> bool:
    """Check if routes/__init__.py is already patched."""
    return (
        "authenticated_router = APIRouter" in content
        and "VersionedAPIRouter(dependencies=[JWTBearerDep])" not in content
    )


def is_already_patched_app(content: str) -> bool:
    """Check if app.py is already patched."""
    return (
        "app = FastAPI(" in content
        and "app.include_router(execution_api_router)" in content
        and "CadwynWithOpenAPICustomization" not in content
        and "generate_and_include_versioned_routers" not in content
    )


def patch_routes_init() -> bool:
    """Patch routes/__init__.py to use APIRouter instead of VersionedAPIRouter."""
    print(f"Patching {ROUTES_INIT_PY}...")

    if not check_file_exists(ROUTES_INIT_PY):
        return False

    with open(ROUTES_INIT_PY, "r", encoding="utf-8") as f:
        content = f.read()

    if is_already_patched_routes_init(content):
        print(
            "  INFO: routes/__init__.py already patched (VersionedAPIRouter -> APIRouter)"
        )
        return True

    # Add APIRouter import if not present
    if "from fastapi import APIRouter" not in content:
        content = "from fastapi import APIRouter\n" + content
        print("  Added APIRouter import")

    # Replace VersionedAPIRouter with APIRouter for authenticated_router
    old = (
        "authenticated_router = VersionedAPIRouter(dependencies=[JWTBearerDep])"
        "  # type: ignore[list-item]"
    )
    new = (
        "authenticated_router = APIRouter(dependencies=[JWTBearerDep])"
        "  # PATCH: Replaced VersionedAPIRouter with APIRouter to fix"
        " prefix stripping bug"
    )

    if old in content:
        content = content.replace(old, new)
        print("  Replaced VersionedAPIRouter with APIRouter")
    elif "authenticated_router = VersionedAPIRouter" in content:
        # Handle slight variations in the line
        content = content.replace("authenticated_router = VersionedAPIRouter", new)
        print("  Replaced VersionedAPIRouter with APIRouter (partial match)")
    else:
        print("  WARNING: Could not find authenticated_router definition")
        return False

    with open(ROUTES_INIT_PY, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  SUCCESS: {ROUTES_INIT_PY} patched")
    return True


def replace_cadwyn_with_fastapi(content: str) -> str:
    """Replace Cadwyn import with FastAPI import."""
    if "from fastapi import FastAPI" in content:
        return content

    cadwyn_import = "from cadwyn import (\n    Cadwyn,\n)"
    if cadwyn_import in content:
        content = content.replace(
            cadwyn_import,
            "from fastapi import FastAPI  # PATCH: Use FastAPI instead of Cadwyn",
        )
    else:
        content = content.replace(
            "from cadwyn import (Cadwyn,)",
            "from fastapi import FastAPI  # PATCH: Use FastAPI instead of Cadwyn",
        )
    print("  Replaced Cadwyn import with FastAPI")
    return content


def find_matching_paren(content: str, start: int) -> int:
    """Find the closing parenthesis matching the opening paren at start."""
    depth = 0
    for i in range(start, len(content)):
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def replace_cadwyn_instantiation(content: str) -> str:
    """Replace CadwynWithOpenAPICustomization with FastAPI."""
    start = content.find("app = CadwynWithOpenAPICustomization(")
    if start < 0:
        return content

    end = find_matching_paren(content, start)
    if end < 0:
        return content

    new_block = """app = FastAPI(
        title="Airflow Task Execution API",
        description="The private Airflow Task Execution API.",
        lifespan=lifespan,
    )

    # Restore JWT reissue middleware for token refresh during long-running tasks
    app.add_middleware(JWTReissueMiddleware)"""

    content = content[:start] + new_block + content[end:]
    print(
        "  Replaced CadwynWithOpenAPICustomization with FastAPI"
        " (including JWTReissueMiddleware)"
    )
    return content


def replace_versioned_routers(content: str) -> str:
    """Replace generate_and_include_versioned_routers with include_router."""
    gen_pattern = "app.generate_and_include_versioned_routers(execution_api_router)"
    if gen_pattern not in content:
        return content

    gen_index = content.find(gen_pattern)
    before_gen = content[:gen_index]

    middleware_pattern = "app.add_middleware(JWTReissueMiddleware)"
    middleware_index = before_gen.rfind(middleware_pattern)

    if middleware_index >= 0:
        content = content[:middleware_index] + content[gen_index:]
        print("  Removed duplicate app.add_middleware(JWTReissueMiddleware) call")

    content = content.replace(
        gen_pattern,
        "app.include_router(execution_api_router)"
        "  # PATCH: Use include_router since we disabled Cadwyn versioning",
    )
    print("  Replaced generate_and_include_versioned_routers with include_router")
    return content


def remove_cadwyn_class(content: str) -> str:
    """Remove the CadwynWithOpenAPICustomization class definition."""
    class_start = content.find("class CadwynWithOpenAPICustomization(Cadwyn):")
    if class_start < 0:
        return content

    lines = content.split("\n")
    class_line_idx = None
    for i, line in enumerate(lines):
        if "class CadwynWithOpenAPICustomization(Cadwyn):" in line:
            class_line_idx = i
            break

    if class_line_idx is None:
        return content

    class_indent = len(lines[class_line_idx]) - len(lines[class_line_idx].lstrip())
    class_end_idx = class_line_idx + 1

    for i in range(class_line_idx + 1, len(lines)):
        line = lines[i]
        if line.strip():
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= class_indent and ("class " in line or "def " in line):
                class_end_idx = i
                break
            if i == len(lines) - 1:
                class_end_idx = len(lines)

    new_lines = lines[:class_line_idx] + lines[class_end_idx:]
    content = "\n".join(new_lines)
    print("  Removed CadwynWithOpenAPICustomization class definition")
    return content


def patch_app() -> bool:
    """Patch app.py to use FastAPI instead of CadwynWithOpenAPICustomization."""
    print(f"Patching {APP_PY}...")

    if not check_file_exists(APP_PY):
        return False

    with open(APP_PY, "r", encoding="utf-8") as f:
        content = f.read()

    if is_already_patched_app(content):
        print(
            "  INFO: app.py already patched (CadwynWithOpenAPICustomization -> FastAPI)"
        )
        return True

    content = replace_cadwyn_with_fastapi(content)
    content = replace_cadwyn_instantiation(content)
    content = replace_versioned_routers(content)
    content = remove_cadwyn_class(content)

    with open(APP_PY, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  SUCCESS: {APP_PY} patched")
    return True


def verify_patches() -> bool:
    """Verify that patches were applied correctly."""
    print("\nVerifying patches...")

    all_ok = True

    # Check routes/__init__.py
    with open(ROUTES_INIT_PY, "r", encoding="utf-8") as f:
        content = f.read()

    if (
        "authenticated_router = APIRouter" in content
        and "VersionedAPIRouter(dependencies=[JWTBearerDep])" not in content
    ):
        print("  ✓ routes/__init__.py: VersionedAPIRouter replaced with APIRouter")
    else:
        print("  ✗ routes/__init__.py: Patch verification failed")
        all_ok = False

    # Check app.py
    with open(APP_PY, "r", encoding="utf-8") as f:
        content = f.read()

    checks = [
        ("app = FastAPI(", "FastAPI instantiation"),
        ("app.include_router(execution_api_router)", "include_router call"),
        (lambda c: "JWTReissueMiddleware" in c, "JWTReissueMiddleware preserved"),
        (
            lambda c: "CadwynWithOpenAPICustomization" not in c,
            "CadwynWithOpenAPICustomization removed",
        ),
        (
            lambda c: "generate_and_include_versioned_routers" not in c,
            "generate_and_include_versioned_routers removed",
        ),
    ]

    for check, desc in checks:
        if callable(check):
            check_result = check(content)
            if check_result:
                print(f"  ✓ app.py: {desc}")
            else:
                print(f"  ✗ app.py: {desc}")
                all_ok = False
        else:
            if check in content:
                print(f"  ✓ app.py: {desc}")
            else:
                print(f"  ✗ app.py: {desc}")
                all_ok = False

    return all_ok


def main():
    """Main entry point."""
    print("=" * 60)
    print("Airflow 3.1.6 Execution API Patch Script")
    print("=" * 60)
    print()

    # Check if already patched
    with open(ROUTES_INIT_PY, "r", encoding="utf-8") as f:
        routes_content = f.read()
    with open(APP_PY, "r", encoding="utf-8") as f:
        app_content = f.read()

    if is_already_patched_routes_init(routes_content) and is_already_patched_app(
        app_content
    ):
        print("INFO: All patches already applied. Skipping.")
        print()
        verify_patches()
        sys.exit(0)

    # Apply patches
    print("Applying patches...")
    print()

    routes_ok = patch_routes_init()
    app_ok = patch_app()

    print()

    if not routes_ok or not app_ok:
        print("ERROR: One or more patches failed")
        sys.exit(1)

    # Verify patches
    if verify_patches():
        print()
        print("=" * 60)
        print("SUCCESS: All patches applied and verified!")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("WARNING: Patches applied but verification failed")
        print("Please review the output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
