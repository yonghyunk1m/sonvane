# Versioning and release updates

The repository begins with a consolidated source commit, **`Sonvane v0.0.0`**. This is the source-history baseline; the application’s existing preview versions and their changes remain recorded in `docs/CHANGELOG.md`. Commit titles do not change the deployed application version.

## One source of truth

`.github/releases.json` contains the release version, date, user-visible changes and limitations. Run:

```bash
python scripts/build_release_notes.py
python scripts/build_release_notes.py --check
```

The builder updates `VERSION`, `docs/CHANGELOG.md`, the `/updates/` page and the version links in Overview and Studio. Do not edit generated release text independently.

## Each update

1. Add a new entry at the top of `.github/releases.json`. Explain the actual behavior that changed under Added, Improved, Fixed or Scope. Keep incomplete work out of shipped notes.
2. Increment the preview number for the next preview. After a stable release, use a patch for compatible fixes, a minor version for compatible features, and a major version for incompatible changes.
3. Build the notes, run the relevant tests, and inspect the affected screens. Run the release check before committing.
4. Commit the implementation and its release record together. Push the reviewed commit to GitHub.
5. Deploy that commit and verify the visible version, styles, scripts and key interactions on the hosted page. A successful container build alone is insufficient.
6. After verifying deployment, create the matching `vVERSION` Git tag and GitHub release. Mark preview versions as prereleases. Include validation and known limitations in the release body; link to the changelog rather than duplicating a different history.

A version number does not claim that a repository is public, that a license is selected, or that every deployment is available. Track those independently. Keep backend addresses and credentials in server configuration and Space Secrets, never in release notes.
