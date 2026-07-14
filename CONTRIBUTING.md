# Contributing to Arbitrage Bot

Thank you for your interest in contributing! This document outlines how to contribute to the project.

## Code of Conduct

- Be respectful and professional
- Focus on technical merit of ideas
- Ask questions if anything is unclear
- Help others learn

## Development Workflow

### 1. Fork and Clone
```bash
git clone https://github.com/nikhilvarma283/arbitrage.git
cd arbitrage
git remote add upstream https://github.com/nikhilvarma283/arbitrage.git
```

### 2. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
# or: git checkout -b fix/your-bug-fix
```

Branch naming conventions:
- `feature/pool-watcher` — new feature
- `fix/executor-bug` — bug fix
- `docs/safety-guide` — documentation
- `refactor/modularize-ledger` — refactoring
- `chore/update-deps` — maintenance

### 3. Make Changes

**Write Tests First (TDD):**
```bash
# Create or update test file
# tests/test_pool_watcher.py

def test_pool_state_parsing():
    """Test that pool state is correctly parsed from block data."""
    # Arrange
    block_data = {...}
    expected_state = {...}
    
    # Act
    state = pool_watcher.parse_block(block_data)
    
    # Assert
    assert state == expected_state
```

**Then Implement:**
```bash
# src/pool_watcher.py
def parse_block(block_data):
    # Implementation here
    pass
```

**Run Tests:**
```bash
pytest tests/ -v
```

### 4. Code Quality

Before committing, ensure code quality:

```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Type check with mypy
mypy src/ --ignore-missing-imports

# Run all tests
pytest tests/ -v --cov=src

# Run linting in one go
black . && ruff check . && mypy src/ && pytest tests/ -v
```

### 5. Commit with Clear Messages

```bash
git add src/pool_watcher.py tests/test_pool_watcher.py

git commit -m "feat(pool_watcher): implement block listener for Tinyman v2 pools

- Add PoolWatcher class for real-time pool state tracking
- Support subscription to new blocks via Algorand SDK
- Maintain in-memory cache of current reserves
- Emit PoolUpdated events to opportunity_engine

Closes #42
Refs #15 (related discussion)"
```

**Commit message format:**
```
type(scope): subject (50 chars max)

Detailed explanation (72 chars wrap).
- Bullet points for changes
- Multiple paragraphs OK

Closes #123
Refs #45
```

**Types:** feat, fix, docs, style, refactor, perf, test, chore

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then on GitHub:
1. Open a Pull Request against `develop` branch
2. Fill in the PR template:
   - What does this PR do?
   - Why is it needed?
   - How was it tested?
   - Links to issues/discussion

### 7. Code Review

- Be open to feedback
- Respond to comments (don't disappear)
- Request changes if needed, then re-push
- Maintainer will approve and merge

## Testing Guidelines

### Test Coverage
- Aim for ≥80% code coverage
- All public functions must have tests
- Edge cases should be covered

### Test Types
- **Unit tests:** Test individual functions/methods in isolation
- **Integration tests:** Test modules working together (algod, ledger, etc.)
- **Regression tests:** Ensure bugs don't come back

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_pool_watcher.py -v

# Run with coverage report
pytest tests/ -v --cov=src --cov-report=html

# Run only integration tests
pytest tests/integration/ -v
```

## Documentation Guidelines

### Code Comments
- **No comments for obvious code:** `x = 1  # Set x to 1` ❌
- **Comments for WHY, not WHAT:** `y = x * 1.5  # 50% safety margin` ✅
- **Docstrings for public functions:**

```python
def compute_spread(pool_a: PoolState, pool_b: PoolState) -> float:
    """
    Compute effective spread between two pools in basis points.
    
    Args:
        pool_a: First pool state (cheaper pool)
        pool_b: Second pool state (richer pool)
    
    Returns:
        Spread in basis points (e.g., 55.0 = 0.55%)
    
    Raises:
        ValueError: If pools have mismatched assets
    """
```

### Markdown Documentation
- Keep line length to 80-100 chars
- Use clear headings
- Include examples where helpful
- Update docs if behavior changes

## Issue Guidelines

### Reporting a Bug
1. Search existing issues (might be a duplicate)
2. Create a new issue with:
   - Clear title: "[Bug] Bot halts on consecutive failed submissions"
   - Detailed description: what happened, expected vs actual
   - Steps to reproduce
   - Logs/stack trace
   - Environment (Python version, OS, etc.)

### Requesting a Feature
1. Create an issue with:
   - Clear title: "[Feature] Add dashboard export to CSV"
   - Motivation: why this is needed
   - Proposed implementation (if you have ideas)
   - Acceptance criteria

### Assigning Issues
- Only assign to yourself when you're actively working on it
- Link related issues/PRs
- Update status in GitHub Project board

## Sprint & Release Cycle

### Sprint Timeline
- **Sprint starts:** Monday
- **Sprint planning:** 1 hour (Sprint 1, Sprint 2, etc.)
- **Daily standup:** 15 min (async via Slack or sync meeting)
- **Sprint ends:** Friday EOD
- **Sprint review:** Saturday morning

### Release Process
1. Create a release branch: `release/v0.1.0`
2. Update VERSION, CHANGELOG
3. Run full test suite + integration tests
4. Tag the release: `git tag -a v0.1.0 -m "Release v0.1.0"`
5. Merge to `main` and `develop`
6. Deploy to staging first (48 hours)
7. Deploy to production after validation

## Questions or Need Help?

- Open an issue with the `question` label
- Ask in team Slack: #algo-arb
- Review existing documentation: [docs/](docs/)

---

**Thank you for contributing! 🚀**
