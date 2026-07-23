# CI/CD And Release Gates

CI runs on pull requests and pushes to `main`. The workflow follows the IFC-Converter pattern with 4 separate jobs plus weekly CodeQL security scanning.

## CI Jobs

### 1. Lint & Format (ubuntu-latest)

```bash
ruff check .
ruff format --check .
```

### 2. Dependency Audit (ubuntu-latest)

```bash
pip-audit --strict -r requirements.txt
```

### 3. Test & Coverage (windows-latest)

```powershell
pip install -r requirements.txt
pip install ruff pytest coverage

# Core validation suites with coverage (>= 60%)
python -m coverage erase
python -m coverage run -a --source=core,licensing,vault,intake,search,rag,backup,wakilios,ui tests\validate_license.py
python -m coverage run -a --source=core,licensing,vault,intake,search,rag,backup,wakilios,ui tests\validate_wakilios_backend.py
# ... (12 core suites)
python -m coverage report --fail-under=60

# UI validation (separate, needs PySide6)
set QT_QPA_PLATFORM=offscreen
python tests\validate_ui.py

# Selftest
python main.py --selftest
```

### 4. Build Bundle Smoke (windows-latest)

```powershell
pip install -r requirements.txt
pip install "cython>=3,<4"
python scripts\obfuscate_licensing.py
pyinstaller main.spec --noconfirm --clean
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
```

### 5. CodeQL (weekly, ubuntu-latest)

Weekly Python security scan using `security-extended` queries. Requires code scanning enabled in GitHub repo settings.

## PR Gate

Every feature PR must include:

- Documentation updates.
- Implementation or validator changes.
- Local validation notes in the PR description.
- No real client documents or secrets.
- CI passing before merge.

The feature branch must be merged before the next feature branch starts.

## Release Workflow

Tag-triggered (push a version tag like `v0.1.0`). See [RELEASE.md](../../RELEASE.md).

## Required Enterprise Gate

Before any enterprise release is published, run:

```powershell
python tests\validate_docs.py
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_e2e.py
python tests\validate_wakilios_backend.py
python tests\validate_wakilios_api.py
python main.py --selftest
python main.py --products
```

All must pass before the release tag is pushed.
