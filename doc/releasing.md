# Release Process

This document describes the process for releasing new versions of `tap-salesforce-meltano-sdk`.

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):
- MAJOR version for incompatible API changes
- MINOR version for backwards-compatible functionality additions
- PATCH version for backwards-compatible bug fixes

## Release Steps

1. **Prepare Release**
   ```bash
   # Ensure you're on main branch and up-to-date
   git checkout main
   git pull origin main
   ```

2. **Update Version**
   - Update version in `pyproject.toml`:
   ```toml
   [tool.poetry]
   name = "tap-salesforce-meltano-sdk"
   version = "1.2.3"  # Update this line
   ```

3. **Update CHANGELOG**
   - Add new entry in `CHANGELOG.md`:
   ```markdown
   ## [1.2.3] - YYYY-MM-DD
   ### Added
   - New feature X
   ### Changed
   - Updated behavior Y
   ### Fixed
   - Bug fix Z
   ```

4. **Commit Changes**
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore: prepare release v1.2.3"
   ```

5. **Create and Push Tag**
   ```bash
   # Create tag
   git tag v1.2.3

   # Push changes and tag
   git push origin main
   git push origin v1.2.3
   ```

6. **Monitor Release Process**
   - Go to GitHub Actions tab to monitor the release workflow
   - Verify that the release is created successfully
   - Check the generated release notes and artifacts

## Release Workflow

When you push a tag, the following automated steps occur:
1. CI checks run one final time
2. Release workflow creates a GitHub release
3. Build artifacts are attached to the release
4. Release notes are automatically generated

## Troubleshooting

### Failed Release

If the release fails:
1. Check the GitHub Actions logs
2. Fix any issues
3. Delete the tag locally and remotely:
   ```bash
   # Delete local tag
   git tag -d v1.2.3

   # Delete remote tag
   git push --delete origin v1.2.3
   ```
4. Make necessary fixes
5. Try the release process again

### Version Conflicts

If you accidentally push a tag that already exists:
1. Delete the existing tag (see above)
2. Create a new tag with the correct version
3. Push the new tag

## Post-Release

After a successful release:
1. Verify the GitHub release page
2. Check that all artifacts are present
3. Update any relevant documentation
4. Notify users of the new release if necessary

## Release Schedule

- PATCH releases: As needed for bug fixes
- MINOR releases: When new features are ready
- MAJOR releases: Planned in advance with deprecation notices

## Notes

- Always test thoroughly before releasing
- Update documentation with any relevant changes
- Follow the semantic versioning guidelines strictly
- Keep the changelog up to date
- Monitor the release process to completion

## Quick Reference

```bash
# Full release process
git checkout main
git pull origin main
# Update version in pyproject.toml
# Update CHANGELOG.md
git add pyproject.toml CHANGELOG.md
git commit -m "chore: prepare release v1.2.3"
git tag v1.2.3
git push origin main
git push origin v1.2.3
```
