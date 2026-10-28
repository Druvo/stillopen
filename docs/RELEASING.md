# Releasing StillOpen

A release is a git tag. Everything else follows from it.

## Version numbers

[Semantic versioning](https://semver.org/), `MAJOR.MINOR.PATCH`:

- **PATCH** (0.1.1): fixes only; safe to take with no reading.
- **MINOR** (0.2.0): new things people can do, or a new optional setting; migrations may run on start, existing data is kept.
- **MAJOR** (1.0.0, 2.0.0): something an installer must act on (a removed setting, a changed Docker volume, a database change that cannot be undone). While the version starts with 0, a MINOR bump may do this too; the changelog says so.

A tag is the version with a `v` in front: `v0.1.0`. A tag with a dash (`v0.2.0-rc1`) is published as a pre-release and does not become the image's `latest`.

## Cut a release

1. Make sure `main` is green (the Tests workflow) and you have run the suite yourself if it matters: `python manage.py test`.
2. In `CHANGELOG.md`, move what is under **Unreleased** into a new `## X.Y.Z - YYYY-MM-DD` heading (or turn the `## 0.1.0 - unreleased draft` heading into one by putting the real date there). Write it for a person: what they can now do, not which files changed. Check it with `python scripts/release_notes.py vX.Y.Z`.
3. Put the same version in `VERSION` (and `frontend/package.json` if you keep them in step), commit: `git commit -am "Release X.Y.Z"`, push to `main`.
4. Tag and push: `git tag vX.Y.Z && git push --tags`.

## What happens then

- `.github/workflows/release.yml` copies that changelog section into a GitHub release for the tag (using only the workflow's own `GITHUB_TOKEN`, `contents: write`). It fails, and publishes nothing, if the section is missing, empty, or still says "unreleased draft". It does not run the tests: step 1 is yours.
- `.github/workflows/image.yml` builds the container image and pushes `ghcr.io/druvo/stillopen:X.Y.Z` (and `latest` for a stable tag). The first time, check under the repository's Packages that the image exists and, if you want anyone to pull it, make the package public.
- Nothing else is published: not to PyPI, not to a store.

## Roll back

- **A bad release note:** edit the release on GitHub (Releases > Edit). The notes are not read again.
- **A bad tag, nobody has installed it:** delete the release and the tag (`gh release delete vX.Y.Z`, `git push --delete origin vX.Y.Z`, `git tag -d vX.Y.Z`), fix, and tag again. A pushed image tag stays in the registry until you delete that package version in the repository's Packages page.
- **A bad release people may have installed:** do not move the tag. Fix forward with a PATCH release. People who already updated and need to go back restore the backup they took before updating ([SELF-HOSTING.md](SELF-HOSTING.md#backups)), then `git checkout vPREVIOUS` (or use the previous image tag) and start it again; a database migrated by the newer version should not be run by the older code, which is why the backup comes first.
