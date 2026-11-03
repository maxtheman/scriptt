# Releasing

## Versions

- `scriptt` and `scriptt-charts` have the same version. They are released together from one tag.
- The version is in the `version` field of each `pyproject.toml`: `pyproject.toml` and
  `packages/scriptt-charts/pyproject.toml`. There is no other copy. Read it with `uv version --short`.
- The versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0:
  - A change that can break code that uses the library bumps the minor number: 0.1.0 to 0.2.0.
  - Any other change bumps the patch number: 0.1.0 to 0.1.1.
- 1.0.0 is the first version with a stable API. After 1.0.0, a change that breaks code bumps the major number.
- `scriptt-charts` needs `scriptt>=0.X,<0.(X+1)`. Change this range at each minor bump.
- The tag of a release is `v` and the version: `v0.1.0`.

## The changelog

- Each change that a user can see gets a line under `## [Unreleased]` in `CHANGELOG.md`, in the same pull request
  as the change.
- Use the headings of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): Added, Changed, Deprecated,
  Removed, Fixed, Security.
- At a release, the `[Unreleased]` lines move under a new heading `## [X.Y.Z] - YYYY-MM-DD`.
- The release workflow stops when the changelog has no heading for the tag.

## Release a version

1. Start from an up-to-date `main` with a green CI run.
2. Bump both packages. Use `minor` or `patch` (see "Versions"):

    ```bash
    uv version --bump minor
    uv version --bump minor --package scriptt-charts
    ```

3. At a minor bump, change the `scriptt` range in `packages/scriptt-charts/pyproject.toml`.
4. In `CHANGELOG.md`, move the `[Unreleased]` lines under `## [X.Y.Z] - YYYY-MM-DD`. Add the compare link at the
   end of the file.
5. Check the release locally:

    ```bash
    uv lock
    uv run python scripts/release_check.py vX.Y.Z
    mise run check && mise run test && mise run build
    ```

6. Commit with the message `Release X.Y.Z`. Merge it to `main`.
7. Tag the commit on `main` and push the tag:

    ```bash
    git tag -a vX.Y.Z -m "X.Y.Z"
    git push origin vX.Y.Z
    ```

8. The workflow `Release` (`.github/workflows/release.yml`) builds both packages and checks them. The job `pypi`
   then waits for approval in the GitHub environment `pypi`. Approve it. The job publishes to PyPI.
9. Check the release in a new folder:

    ```bash
    uv run --no-project --isolated --with scriptt==X.Y.Z python -c "import scriptt.world"
    ```

To try a build on TestPyPI first, run the workflow `Release` by hand (Actions, Release, Run workflow). A run by
hand publishes to TestPyPI only.

## Before the first release to PyPI

`scriptt` is not on PyPI yet. Do these steps one time, when you decide to publish.

1. Choose the license. Add a `LICENSE` file, and `license = "<SPDX id>"` with `license-files = ["LICENSE"]` to
   both `pyproject.toml` files. The release check stops while a package has no license.
2. Make the GitHub repository. If the name is not `maxtheman/scriptt`, change the URLs in both
   `pyproject.toml` files, `CHANGELOG.md` and `docs/mkdocs.yml`.
3. In the repository settings, make two environments: `pypi` and `testpypi`. Under `pypi`, add yourself as a
   required reviewer and allow deployments from tags `v*.*.*` only.
4. On pypi.org, go to Account settings, Publishing, "Add a new pending publisher". Do this one time for each
   package (`scriptt` and `scriptt-charts`):

    | Field | Value |
    |---|---|
    | PyPI project name | `scriptt` (then `scriptt-charts`) |
    | Owner | `maxtheman` |
    | Repository name | `scriptt` |
    | Workflow name | `release.yml` |
    | Environment name | `pypi` |

   A pending publisher does not reserve the name. The first upload makes the project.
5. Do step 4 again on test.pypi.org with the environment name `testpypi`.

## The site

The site at <https://scriptt.ai> has the landing page at `/` and the docs at `/docs/`. It is a Cloudflare
Worker with static files only, `scriptt-site`. The files are in `web/`.

| File | Contents |
|---|---|
| `web/landing/index.html` | The landing page. |
| `web/build.sh` | Builds the docs and puts the landing page and the docs into `web/public/`. |
| `web/cloudflare.config.ts` | The Worker, its custom domains `scriptt.ai` and `www.scriptt.ai`. |
| `web/wrangler.config.ts` | The folder of the static files, `public`. |

To publish the site:

```bash
sh web/build.sh
cd web && npm install && npx cf deploy
```

`cf` must be signed in to the Cloudflare account that has the zone `scriptt.ai` (`npx cf auth whoami`).
