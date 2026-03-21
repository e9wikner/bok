# GitHub Actions Setup Instructions

The CI/CD workflows are ready but need `workflow` scope in your GitHub token to push.

## Quick Setup (5 minutes)

### Step 1: Create New GitHub Token

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Give it a name: `github-actions-token`
4. **Select these scopes:**
   - ☑️ `repo` (Full control of private repositories)
   - ☑️ `workflow` (Full control of workflows) ← **IMPORTANT**
   - ☑️ `read:org` (Read organization)
5. Click "Generate token"
6. **Copy the token immediately** (you won't see it again!)

### Step 2: Clone Repo Locally

```bash
# Clone
git clone git@github.com:e9wikner/bok.git
cd bok

# Or if already cloned
cd ~/Development/bok  # or wherever you cloned it
```

### Step 3: Update Git Remote

Replace `YOUR_NEW_TOKEN` with the token from Step 1:

```bash
git remote set-url origin https://YOUR_NEW_TOKEN@github.com/e9wikner/bok.git
```

### Step 4: Push GitHub Actions Workflows

```bash
# This will push the workflows that are committed but not yet pushed
git push origin main
```

**Expected output:**
```
To https://YOUR_NEW_TOKEN@github.com/e9wikner/bok.git
   80d2530..48b35cf  main -> main
```

### Step 5: Verify Workflows

1. Go to: https://github.com/e9wikner/bok/actions
2. You should see:
   - ✅ "Docker Build & Test" workflow
   - ✅ "Tests" workflow

Both should show recent runs!

## What Workflows Do

### Docker Build & Test
- Builds Docker image
- Runs docker-compose
- Health checks
- Runs pytest tests
- Security scan

### Tests & Code Quality
- Python tests with coverage
- Code formatting (black)
- Import sorting (isort)
- Linting (flake8)
- Type checking (mypy)

## View Results

1. Go to: https://github.com/e9wikner/bok/actions
2. Click a workflow run to see details
3. Click "Summary" to see results
4. Click "Annotations" to see warnings

## Troubleshooting

### "refusing to allow a Personal Access Token..."

**Solution:** Token needs `workflow` scope. Create new token following Step 1 above.

### "fatal: Authentication failed"

**Solution:** Token might be expired. Create new one and use in Step 3.

### Workflows don't appear after push

**Solution:** 
1. Verify files exist: `.github/workflows/docker-build.yml` and `.tests.yml`
2. Wait 1-2 minutes for GitHub to recognize them
3. Refresh the Actions page

## Next Steps

✅ Push GitHub Actions workflows (Steps 1-4 above)  
✅ View in Actions tab  
✅ Monitor Docker builds  
✅ Track test results  

That's it! CI/CD is now automated. 🎉

---

**Timeline:** Should take ~5 minutes total

**Questions?** See CICD.md for detailed documentation
