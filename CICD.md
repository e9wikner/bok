# CI/CD Pipeline Setup

Automated testing, building, and quality checks with GitHub Actions.

## GitHub Actions Workflows

### 1. Docker Build & Test (`docker-build.yml`)

**Triggers:** Push to main/develop, Pull Requests

**What it does:**
1. ✅ Builds Docker image
2. ✅ Starts docker-compose services
3. ✅ Health check: `GET /health`
4. ✅ API check: `GET /docs`
5. ✅ Runs pytest tests
6. ✅ Security scan (Trivy)
7. ✅ Cleanup

**Success means:**
- Docker image builds without errors
- Service starts correctly
- All health checks pass
- Tests pass in container
- No critical vulnerabilities

### 2. Tests & Code Quality (`tests.yml`)

**Triggers:** Push to main/develop, Pull Requests

**What it does:**
1. ✅ Runs pytest with coverage
2. ✅ Format check (black)
3. ✅ Import sorting (isort)
4. ✅ Linting (flake8)
5. ✅ Type checking (mypy)
6. ✅ Uploads coverage to Codecov

**Success means:**
- All tests pass
- Code is properly formatted
- Imports are sorted correctly
- No linting issues
- Type hints are valid

## Setup Instructions

### For Your Local Machine

Push the GitHub Actions workflows to enable CI/CD:

```bash
# Clone repo locally
git clone git@github.com:e9wikner/bok.git
cd bok

# Verify workflows are present
ls -la .github/workflows/

# Push to GitHub (requires workflow scope in token)
git push origin main
```

**If token error occurs:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Create new token with scopes:
   - `repo` (full control of private repositories)
   - `workflow` (full control of workflows)
   - `read:org` (read organization)
3. Copy new token and use it:
   ```bash
   git remote set-url origin https://<new-token>@github.com/e9wikner/bok.git
   git push origin main
   ```

### View Workflow Status

Once workflows are pushed:

1. Go to: https://github.com/e9wikner/bok/actions
2. Select workflow to view details
3. Click "Run details" to see logs
4. Check "Annotations" for warnings

## Workflow Files

### `.github/workflows/docker-build.yml`

```yaml
on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  docker-build:
    runs-on: ubuntu-latest
    steps:
      - Build Docker image
      - Run docker-compose
      - Health checks
      - Pytest tests
```

### `.github/workflows/tests.yml`

```yaml
on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest
    python-version: [3.11]
  lint:
    runs-on: ubuntu-latest
  type-check:
    runs-on: ubuntu-latest
```

## Status Badges

Add to README.md:

```markdown
## CI/CD Status

![Docker Build](https://github.com/e9wikner/bok/actions/workflows/docker-build.yml/badge.svg)
![Tests](https://github.com/e9wikner/bok/actions/workflows/tests.yml/badge.svg)
```

## Handling Failures

### Docker Build Fails

**Check:**
- Dockerfile syntax
- requirements.txt validity
- Volume mounting issues
- Port conflicts

**Fix:**
```bash
# Test locally
docker-compose build
docker-compose up
curl http://localhost:8000/health
```

### Tests Fail

**Check:**
- pytest output in Actions log
- Test file changes
- Dependencies

**Fix:**
```bash
# Run locally
pytest tests/ -v
```

### Code Quality Warnings

**Format issues:**
```bash
black . --exclude venv
```

**Import issues:**
```bash
isort . --skip venv
```

**Lint warnings:**
```bash
flake8 . --exclude venv
```

**Type issues:**
```bash
mypy . --ignore-missing-imports
```

## Protected Branches (Optional)

To require status checks before merging:

1. Go to: GitHub → Settings → Branches
2. Click "Add rule"
3. Branch name pattern: `main`
4. Require status checks:
   - ✅ Docker Build & Test
   - ✅ Tests & Code Quality

Now PRs cannot merge without passing checks!

## Secrets & Environment

### Public Repo - No Secrets Needed

Current workflows don't require secrets.

### For Production - Add Secrets:

1. Go to: GitHub → Settings → Secrets and variables → Actions
2. Add secrets:
   - `DOCKER_REGISTRY_TOKEN` - For pushing to Docker Hub
   - `DATABASE_URL` - Production database
   - `API_KEY` - Production API key

3. Use in workflow:
```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## Monitoring

### View Workflow Results

1. **Inline in GitHub:**
   - Code tab → green ✅ checkmark means all checks passed
   - Red ❌ means failure

2. **Actions Tab:**
   - https://github.com/e9wikner/bok/actions
   - See real-time build/test progress
   - Download logs

3. **PR Checks:**
   - See status on PR page
   - Click "Details" to view logs
   - Merge only when all ✅ pass

### Codecov (Optional)

Coverage reports at: https://codecov.io/gh/e9wikner/bok

Track test coverage over time!

## Workflow Customization

### Add More Tests

Edit `.github/workflows/tests.yml`:

```yaml
- name: Run integration tests
  run: pytest tests/integration/ -v
```

### Add Different Python Versions

Edit `.github/workflows/tests.yml`:

```yaml
python-version: ['3.10', '3.11', '3.12']
```

### Add Database Tests

Edit `.github/workflows/docker-build.yml`:

```yaml
- name: Database integrity check
  run: docker-compose exec -T bokfoering-api python -c "from db.database import db; db.init_db(); print('✅ DB OK')"
```

## Common Issues

### "refusing to allow a Personal Access Token..."

**Solution:** Token needs `workflow` scope. Create new token with:
- `repo`
- `workflow`
- `read:org`

### Workflow doesn't run after push

**Solution:** 
- Check `.github/workflows/` files exist in repo
- Verify file names end with `.yml`
- Workflows run on `push` to main

### Build times too long

**Solutions:**
- Cache Docker layers: `cache-from: type=gha`
- Cache pip: `pip-cache: true`
- Parallel jobs: add more `jobs:` sections

## Best Practices

1. **Commit messages:** Reference issue numbers `#123`
2. **Branch names:** Use descriptive names `feature/invoicing`
3. **PR descriptions:** Explain what changed
4. **Keep workflows simple:** One job = one responsibility
5. **Test locally first:** Before pushing
6. **Monitor failures:** Fix quickly

## Documentation

- Local testing: See QUICKSTART.md
- Docker setup: See DOCKER.md
- API testing: See API.md

## Support

For workflow issues:
1. Check workflow logs in GitHub Actions tab
2. Review workflow file YAML syntax
3. Test locally first
4. File issue with error message

---

**Status:** GitHub Actions workflows ready to push! 🚀
