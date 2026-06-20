# Release Process

## Quick release

```bash
# 1. Update version in pyproject.toml
# 2. Update CHANGELOG.md (if exists) or commit messages

git add pyproject.toml
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push origin master --tags
```

This triggers `.github/workflows/release.yml` which:
1. Runs lint + tests
2. Verifies the tag version matches pyproject.toml
3. Builds the wheel and sdist
4. Creates a GitHub Release
5. Publishes to PyPI via trusted publishing (no API token)

## Trusted publishing setup (one-time, per PyPI project)

In PyPI project settings → Publishing → Add a new pending publisher:
- Owner: Veedubin
- Repository: quantitative-sports
- Workflow filename: release.yml
- Environment name: pypi

## Manual release (workflow_dispatch)

You can also trigger the release workflow manually from the Actions tab by providing the tag name as input.