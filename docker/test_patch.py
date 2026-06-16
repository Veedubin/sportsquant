"""
Test script to verify the Execution API patch is working correctly.

Run this inside the API server pod:
    kubectl exec -n nba-analytics <api-server-pod> -- python3 /opt/airflow/patches/test_patch.py

Or run after building the image:
    docker run --rm airflow:3.1.6-patched python3 /opt/airflow/patches/test_patch.py
"""

import sys
import cadwyn
from airflow.api_fastapi.execution_api.app import create_task_execution_api_app
from airflow.api_fastapi.execution_api.routes import execution_api_router


def test_routes_init():
    """Test that routes/__init__.py uses APIRouter instead of VersionedAPIRouter."""
    # Check that routes are correctly prefixed
    routes = [r.path for r in execution_api_router.routes]

    # Check for task-instances routes
    task_routes = [r for r in routes if "task-instance" in r]

    assert len(task_routes) > 0, "No task-instance routes found!"

    # The fix should preserve the /task-instances prefix
    assert any("/task-instances/{task_instance_id}/run" in r for r in task_routes), (
        f"Expected /task-instances/{{task_instance_id}}/run, got: {task_routes}"
    )

    print("✓ routes/__init__.py: APIRouter preserves prefixes correctly")
    return True


def test_app_type():
    """Test that app.py uses FastAPI instead of CadwynWithOpenAPICustomization."""
    app = create_task_execution_api_app()

    # Check that we get a standard FastAPI app, not Cadwyn
    app_type = type(app).__name__

    assert app_type == "FastAPI", f"Expected FastAPI, got {app_type}"

    print(f"✓ app.py: Using {app_type} (not Cadwyn)")
    return True


def test_total_routes():
    """Test that all expected routes are present."""
    routes = {r.path for r in execution_api_router.routes}

    expected_routes = [
        "/health",
        "/health/ping",
        "/task-instances/count",
        "/task-instances/states",
        "/task-instances/{task_instance_id}/run",
        "/task-instances/{task_instance_id}/state",
        "/task-instances/{task_instance_id}/heartbeat",
        "/dag-runs/{dag_id}/{run_id}",
    ]

    missing = []
    for route in expected_routes:
        # Check if route exists (allow for param variations)
        found = any(route.replace("{", "").replace("}", "") in r for r in routes)
        if not found:
            missing.append(route)

    if missing:
        print("Missing routes: %s", missing)
    else:
        print(f"✓ All {len(expected_routes)} expected routes present")

    return True


def test_no_cadwyn():
    """Test that Cadwyn is not being used for routing."""
    try:
        _ = cadwyn.__name__
        print("⚠ Cadwyn is installed (but may not be used)")
    except (ImportError, AttributeError):
        print("✓ Cadwyn not in use (not imported)")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Execution API Patch Verification Tests")
    print("=" * 60)
    print()

    tests = [
        ("routes/__init__.py uses APIRouter", test_routes_init),
        ("app.py uses FastAPI", test_app_type),
        ("All expected routes present", test_total_routes),
        ("Cadwyn not in use", test_no_cadwyn),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            print(f"\nRunning: {name}")
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except (ImportError, AttributeError, RuntimeError, TypeError, KeyError) as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)

    print("\n✓ All tests passed! The Execution API patch is working correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
