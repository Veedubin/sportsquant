# Release Process

## Quick release

```bash
# 1. Update version in BOTH places:
#    - pyproject.toml: version = "X.Y.Z"
#    - src/quantitative_sports/__init__.py: __version__ = "X.Y.Z"
#
# The release workflow verifies these match before publishing.

git add pyproject.toml src/quantitative_sports/__init__.py
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push origin master --tags
```

This triggers `.github/workflows/release.yml` which:
1. Runs lint + tests
2. Verifies `pyproject.toml` version matches `__version__` in `__init__.py`
3. Verifies the tag version matches `pyproject.toml`
4. Builds sdist (before `.venv` exists to avoid bloat) then wheel
5. Creates a GitHub Release
6. Publishes to PyPI via trusted publishing (no API token)

## Trusted publishing setup (one-time, per PyPI project)

In PyPI project settings → Publishing → Add a new pending publisher:
- Owner: Veedubin
- Repository: quantitative-sports
- Workflow filename: release.yml
- Environment name: pypi

## Manual release (workflow_dispatch)

You can also trigger the release workflow manually from the Actions tab by providing the tag name as input.