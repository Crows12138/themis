# Releasing themis-causal

> One-shot setup (10 min), then every future release is two shell commands.

## One-time setup

1. **Get API tokens** from PyPI + TestPyPI:
   - TestPyPI: https://test.pypi.org/manage/account/token/ → "Add API token" → scope **"Entire account"** → copy the `pypi-AgEI...` string
   - Real PyPI: https://pypi.org/manage/account/token/ → same

2. **Add tokens as GitHub repo secrets**:
   - Go to https://github.com/Crows12138/themis/settings/secrets/actions
   - Click "New repository secret"
   - Name: `TEST_PYPI_API_TOKEN` — Value: paste the TestPyPI token
   - Click again. Name: `PYPI_API_TOKEN` — Value: paste the real PyPI token

   That's it. The `.github/workflows/publish.yml` workflow now has everything it needs. Tokens never touch the local machine, never appear in git history.

## Every future release

Bump version in `pyproject.toml` (e.g., `0.1.1` → `0.1.2`). Commit the bump:

```bash
git commit -am "bump: 0.1.2"
git push
```

Then **smoke test on TestPyPI** by pushing a `-test` tag:

```bash
git tag v0.1.2-test
git push origin v0.1.2-test
```

Watch the workflow: https://github.com/Crows12138/themis/actions

Once it finishes (~2 min), check https://test.pypi.org/project/themis-causal/0.1.2/ — verify README renders, dependencies list, console scripts, etc.

If TestPyPI looks good, **publish to real PyPI** by pushing the non-test tag:

```bash
git tag v0.1.2
git push origin v0.1.2
```

After workflow finishes, https://pypi.org/project/themis-causal/ shows `Version: 0.1.2`. Anyone can `pip install -U themis-causal` immediately.

## What the workflow does

`.github/workflows/publish.yml` runs on any tag push matching `v*`:

1. Checks out the repo
2. Installs Python 3.11
3. `pip install build twine`
4. `python -m build` → produces `dist/themis_causal-X.Y.Z-py3-none-any.whl` + `.tar.gz`
5. `twine check dist/*` → metadata sanity check
6. Branches on tag suffix:
   - Tag ends with `-test` → `twine upload --repository-url https://test.pypi.org/legacy/ dist/*`
   - Otherwise → `twine upload dist/*` (real PyPI)

The workflow does NOT run on regular pushes — only on tag pushes. This keeps "release" explicit: bumping `pyproject.toml` version and pushing a matching tag is the entire publish command.

## Gotchas

- **PyPI versions are locked once uploaded.** If you push `v0.1.2` and discover a bug 10 minutes later, you can't re-upload `0.1.2` — you must bump to `0.1.3`. (You can "yank" `0.1.2` to mark it as "please don't use", but the bytes stay forever.)
- **TestPyPI versions are also locked**, but bumping in the sandbox has no cost. Use `-test` tags freely.
- **Tag must match a real commit.** If you forget to commit the version bump before tagging, the workflow builds the old version with the new tag — which causes a metadata mismatch on PyPI. Always: bump → commit → push → tag → push tag.
- **First publish after a forced rebase**: GitHub Actions sees the rewritten history; if any commit it depended on is gone, the workflow may fail. Avoid force-pushing branches that have publish workflows configured.

## Optional upgrades

- **Trusted Publishers (OIDC)** — eliminates the need for tokens entirely. PyPI authenticates GitHub Actions via OIDC. Setup is a one-time config on the PyPI side: project page → Manage → Publishing → "Add a pending publisher". Worth migrating to once the release flow is stable. See https://docs.pypi.org/trusted-publishers/.
- **Auto-create GitHub Release**: add a `softprops/action-gh-release@v1` step to attach the wheel + sdist as release assets and generate release notes. Useful once there's a real changelog discipline.
- **Test before publish**: add a `pytest` step before the build. Currently relies on the developer running tests locally before tagging — fast but no enforcement.
