# Pre-Publication Checklist for Autopack-Built Projects

**Purpose**: Ensure projects built with Autopack have all necessary artifacts, documentation, and metadata before public release.

**Target Audience**: Autopack users preparing to publish projects (like file-organizer-app-v1) to npm, PyPI, GitHub, Docker Hub, etc.

**Last Updated**: 2025-12-09

---

## Quick Start

```bash
# Run automated checklist
python scripts/pre_publish_checklist.py --project-path .autonomous_runs/file-organizer-app-v1

# Strict mode (warnings treated as errors)
python scripts/pre_publish_checklist.py --project-path /path/to/project --strict

# Save results to JSON
python scripts/pre_publish_checklist.py --project-path /path/to/project --output checklist_results.json
```

---

## Checklist Categories

### 1. Core Artifacts (CRITICAL)

These are **mandatory** for any public release:

- [ ] **README.md** with essential sections:
  - Main title and description
  - Installation instructions
  - Usage examples
  - Feature list
  - License information

- [ ] **LICENSE** file:
  - MIT, Apache-2.0, GPL, or appropriate license
  - Match license in package metadata

- [ ] **CHANGELOG.md** with version history:
  - Follow [Keep a Changelog](https://keepachangelog.com/) format
  - Semver versioning (v1.0.0, v1.1.0, etc.)
  - Separate sections: Added, Changed, Fixed, Removed

- [ ] **Version metadata**:
  - VERSION file, package.json, setup.py, or pyproject.toml
  - Consistent version across all files
  - Follow semantic versioning (MAJOR.MINOR.PATCH)

---

### 2. Distribution Artifacts (CRITICAL)

Required for users to install/use your project:

- [ ] **Package metadata**:
  - `package.json` (Node.js/npm)
  - `setup.py` or `pyproject.toml` (Python/PyPI)
  - `Cargo.toml` (Rust/crates.io)
  - `go.mod` (Go)

- [ ] **Dependency lockfile**:
  - `package-lock.json` or `yarn.lock` (Node.js)
  - `Pipfile.lock` or `poetry.lock` (Python)
  - `Cargo.lock` (Rust)
  - Ensures reproducible builds

- [ ] **Build artifacts**:
  - Run build: `npm run build`, `python setup.py build`, etc.
  - Verify `dist/` or `build/` directory created
  - Test built artifacts before publishing

- [ ] **Git tags for releases**:
  - Tag releases: `git tag -a v1.0.0 -m "Release 1.0.0"`
  - Push tags: `git push origin v1.0.0`
  - Follow semver: v1.0.0, v1.1.0, v2.0.0

---

### 3. Packaged Binaries (OPTIONAL but recommended)

For end-user distribution (non-developers):

#### Node.js/Electron Apps:
```bash
# Windows installer
npm run build:win  # Creates .exe or .msi

# macOS app
npm run build:mac  # Creates .dmg or .app

# Linux packages
npm run build:linux  # Creates .deb, .rpm, or AppImage
```

#### Python Apps:
```bash
# PyInstaller for standalone executables
pyinstaller --onefile main.py

# Or use cx_Freeze, py2app, py2exe
```

#### Docker Images:
```bash
# Build and tag
docker build -t yourusername/project-name:1.0.0 .
docker tag yourusername/project-name:1.0.0 yourusername/project-name:latest

# Push to Docker Hub
docker push yourusername/project-name:1.0.0
docker push yourusername/project-name:latest
```

---

### 4. Documentation (HIGH PRIORITY)

Essential for users to understand and use your project:

- [ ] **User documentation** (`docs/` directory):
  - Getting started guide
  - Tutorials
  - Configuration reference
  - FAQ

- [ ] **API documentation** (if applicable):
  - `docs/api/` or `docs/API.md`
  - JSDoc, Sphinx, rustdoc, or similar
  - Auto-generate from code comments

- [ ] **Installation guide**:
  - Step-by-step installation
  - System requirements
  - Troubleshooting common issues

- [ ] **Usage examples** (`examples/` directory):
  - Basic usage
  - Advanced examples
  - Sample configurations
  - Real-world use cases

---

### 5. Quality Assurance (HIGH PRIORITY)

Verify quality before release:

- [ ] **Test suite** (`tests/` directory):
  - Unit tests
  - Integration tests
  - End-to-end tests
  - Run: `npm test`, `pytest`, `cargo test`, etc.

- [ ] **All tests passing**:
  ```bash
  npm test              # Node.js
  pytest                # Python
  cargo test            # Rust
  go test ./...         # Go
  ```

- [ ] **Build succeeds**:
  ```bash
  npm run build         # Node.js
  python setup.py build # Python
  cargo build --release # Rust
  go build              # Go
  ```

- [ ] **CI/CD configured**:
  - `.github/workflows/` (GitHub Actions)
  - `.gitlab-ci.yml` (GitLab CI)
  - Automated testing on push/PR
  - Automated builds for releases

---

### 6. Legal & Compliance (CRITICAL)

Protect yourself legally:

- [ ] **LICENSE file present**:
  - Choose appropriate license
  - Add to repository root
  - Reference in README and package metadata

- [ ] **License headers in source files**:
  ```python
  # Copyright (c) 2025 Your Name
  # Licensed under the MIT License
  ```

- [ ] **Third-party licenses documented**:
  - `THIRD_PARTY_LICENSES.md` or `NOTICE` file
  - List dependencies and their licenses
  - Required if bundling dependencies in binaries

- [ ] **No secrets in repository**:
  - Check `.env` files are in `.gitignore`
  - No API keys, passwords, tokens committed
  - Use tools: `git-secrets`, `truffleHog`, `gitleaks`

- [ ] **No personal data/PII**:
  - Remove email addresses from code comments
  - No personally identifiable information
  - GDPR compliance if applicable

---

### 7. Metadata & Release Management (HIGH PRIORITY)

Proper versioning and release process:

- [ ] **Semantic versioning**:
  - v1.0.0 for first stable release
  - v1.1.0 for new features (minor)
  - v1.1.1 for bug fixes (patch)
  - v2.0.0 for breaking changes (major)

- [ ] **Git tags for versions**:
  ```bash
  git tag -a v1.0.0 -m "Release 1.0.0"
  git push origin v1.0.0
  ```

- [ ] **GitHub Releases**:
  - Create release from tag
  - Add release notes (from CHANGELOG)
  - Attach binaries/artifacts if applicable

- [ ] **Release notes format**:
  ```markdown
  ## [1.0.0] - 2025-12-09

  ### Added
  - Feature X for Y
  - Support for Z

  ### Changed
  - Improved performance of A

  ### Fixed
  - Bug in B causing C
  ```

---

### 8. Optional but Recommended

Enhance discoverability and community:

- [ ] **README badges**:
  ```markdown
  ![Build Status](https://img.shields.io/github/actions/workflow/status/user/repo/test.yml)
  ![Version](https://img.shields.io/npm/v/package-name)
  ![License](https://img.shields.io/github/license/user/repo)
  ```

- [ ] **Demo or screenshots**:
  - GIF/video demonstration
  - Screenshots in README
  - Live demo link if web app

- [ ] **Docker support**:
  - `Dockerfile` for containerization
  - `docker-compose.yml` for multi-service apps
  - Published Docker image on Docker Hub

- [ ] **Security policy** (`SECURITY.md`):
  - How to report security vulnerabilities
  - Supported versions
  - Security update policy

- [ ] **Contributing guide** (`CONTRIBUTING.md`):
  - How to contribute
  - Code style guidelines
  - PR process

- [ ] **Code of Conduct** (`CODE_OF_CONDUCT.md`):
  - Expected behavior
  - Enforcement guidelines
  - Use Contributor Covenant template

- [ ] **Roadmap** (`ROADMAP.md`):
  - Future features
  - Known issues
  - Development priorities

---

## Distribution Platform Specifics

### npm (Node.js)

Before `npm publish`:

```bash
# 1. Verify package.json
cat package.json | jq '.name, .version, .license, .main, .files'

# 2. Test local install
npm pack
npm install ./package-name-1.0.0.tgz

# 3. Check what will be published
npm publish --dry-run

# 4. Publish
npm publish

# 5. Tag as latest (if appropriate)
npm dist-tag add package-name@1.0.0 latest
```

### PyPI (Python)

Before `twine upload`:

```bash
# 1. Build distributions
python setup.py sdist bdist_wheel

# 2. Check build
twine check dist/*

# 3. Test on TestPyPI first
twine upload --repository testpypi dist/*

# 4. Install from TestPyPI and test
pip install --index-url https://test.pypi.org/simple/ package-name

# 5. Upload to production PyPI
twine upload dist/*
```

### Docker Hub

Before `docker push`:

```bash
# 1. Build and test locally
docker build -t username/project:1.0.0 .
docker run --rm username/project:1.0.0

# 2. Tag versions
docker tag username/project:1.0.0 username/project:latest

# 3. Login to Docker Hub
docker login

# 4. Push
docker push username/project:1.0.0
docker push username/project:latest

# 5. Update Docker Hub README (via web UI or Docker Hub API)
```

### GitHub Releases

Creating a release:

```bash
# 1. Tag the release
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0

# 2. Via GitHub web UI:
#    - Go to repository > Releases > Draft a new release
#    - Select tag v1.0.0
#    - Add release title: "v1.0.0 - Initial Release"
#    - Add release notes (from CHANGELOG.md)
#    - Attach binaries if applicable
#    - Publish release

# 3. Or via GitHub CLI:
gh release create v1.0.0 \
  --title "v1.0.0 - Initial Release" \
  --notes-file RELEASE_NOTES.md \
  dist/*.tar.gz dist/*.whl
```

---

## Common Mistakes to Avoid

1. **Version mismatch**: Ensure version is consistent in:
   - CHANGELOG.md
   - package.json / setup.py / Cargo.toml
   - Git tag
   - README (if version is mentioned)

2. **Uncommitted changes**: Publish from clean working tree:
   ```bash
   git status  # Should be clean
   ```

3. **Missing files in package**: Check what's included:
   ```bash
   npm pack && tar -tzf *.tgz  # npm
   python setup.py sdist && tar -tzf dist/*.tar.gz  # Python
   ```

4. **Broken links in README**: Verify all links work:
   - Documentation links
   - Badge URLs
   - Demo/screenshot URLs

5. **Platform-specific paths**: Use `/` not `\` in documentation:
   ```bash
   # Good
   npm install package-name

   # Bad (Windows-specific)
   npm install package-name
   cd package-name\src
   ```

6. **Secrets in git history**: Even if removed, secrets remain in history:
   ```bash
   # Use BFG Repo-Cleaner or git-filter-repo to remove
   git filter-repo --invert-paths --path .env
   ```

7. **No .gitignore for build artifacts**: Ensure these are ignored:
   ```
   node_modules/
   dist/
   build/
   *.egg-info/
   __pycache__/
   .env
   ```

---

## Automation

### Pre-publish Hook

Add to `package.json` (Node.js):

```json
{
  "scripts": {
    "prepublishOnly": "npm run test && npm run build && python ../scripts/pre_publish_checklist.py --project-path . --strict"
  }
}
```

### GitHub Actions Workflow

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run pre-publish checklist
        run: |
          python scripts/pre_publish_checklist.py --project-path . --strict

      - name: Build
        run: npm run build

      - name: Run tests
        run: npm test

      - name: Publish to npm
        run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

      - name: Create GitHub Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          draft: false
          prerelease: false
```

---

## Resources

- [Keep a Changelog](https://keepachangelog.com/) - Changelog format
- [Semantic Versioning](https://semver.org/) - Versioning scheme
- [Choose a License](https://choosealicense.com/) - License picker
- [Shields.io](https://shields.io/) - README badges
- [GitHub Packaging](https://docs.github.com/en/packages) - GitHub package registry
- [npm Documentation](https://docs.npmjs.com/cli/v9/commands/npm-publish) - npm publishing
- [PyPI Packaging](https://packaging.python.org/tutorials/packaging-projects/) - Python packaging

---

## Summary

**Minimum requirements for publication**:
1. ✅ README, LICENSE, CHANGELOG
2. ✅ Package metadata (package.json, setup.py, etc.)
3. ✅ Working build and passing tests
4. ✅ Semantic version tag
5. ✅ No secrets or PII in repository

**Run the automated checker**:
```bash
python scripts/pre_publish_checklist.py --project-path /path/to/project
```

**Fix all ERRORS before publishing. Consider fixing WARNINGS. RECOMMENDATIONS are optional but improve quality.**
