# Development Guide

## Environment Setup

### Prerequisites
- Python 3.8 or later
- Poetry for dependency management
- Git for version control

### Installation
```bash
# Clone the repository
git clone https://github.com/your-org/tap-salesforce-sdk.git
cd tap-salesforce-sdk

# Install dependencies
poetry install

# Install pre-commit hooks
poetry run pre-commit install
```

## Testing

### Unit Tests
```bash
# Run all unit tests
poetry run pytest tests/unit/

# Run specific test file
poetry run pytest tests/unit/test_client.py

# Run with coverage
poetry run pytest --cov=tap_salesforce
```

### Integration Tests
```bash
# Set up test environment
export TAP_SALESFORCE_CLIENT_ID=your_test_client_id
export TAP_SALESFORCE_CLIENT_SECRET=your_test_client_secret
export TAP_SALESFORCE_REFRESH_TOKEN=your_test_refresh_token

# Run integration tests
poetry run pytest tests/integration/
```

## Code Style

### Formatting
```bash
# Format code
poetry run black tap_salesforce/

# Sort imports
poetry run isort tap_salesforce/

# Check types
poetry run mypy tap_salesforce/
```

### Pre-commit Hooks
```bash
# Run all pre-commit hooks
poetry run pre-commit run --all-files
```

## Adding Features

### New Stream
1. Create new stream class
2. Add to stream registry
3. Add tests
4. Update documentation

### New API Type
1. Add client implementation
2. Add stream implementation
3. Add configuration options
4. Add tests and documentation

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release commit
4. Tag release
5. Push to PyPI
```bash
poetry build
poetry publish
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Add tests
5. Submit pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for more details.
