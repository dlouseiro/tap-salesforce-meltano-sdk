# Contributing to tap-salesforce-meltano-sdk

First off, thanks for taking the time to contribute! 🎉

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [issue list](https://github.com/your-org/tap-salesforce-sdk/issues) as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

* Use a clear and descriptive title
* Describe the exact steps which reproduce the problem
* Provide specific examples to demonstrate the steps
* Describe the behavior you observed after following the steps
* Explain which behavior you expected to see instead and why
* Include logs if relevant

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

* A clear and descriptive title
* A detailed description of the proposed functionality
* Explain why this enhancement would be useful
* List any alternative solutions or features you've considered

### Pull Requests

1. Fork the repo and create your branch from `main`
2. If you've added code that should be tested, add tests
3. If you've changed APIs, update the documentation
4. Ensure the test suite passes
5. Make sure your code follows the existing style
6. Issue that pull request!

## Development Process

1. Clone the repository
```bash
git clone https://github.com/your-org/tap-salesforce-meltano-sdk.git
cd tap-salesforce-meltano-sdk
```

2. Create a virtual environment and install dependencies
```bash
poetry install
```

3. Install pre-commit hooks
```bash
poetry run pre-commit install
```

4. Make your changes
   * Write meaningful commit messages
   * Include tests
   * Update documentation

5. Run tests
```bash
poetry run pytest
```

6. Submit a pull request

## Style Guidelines

### Git Commit Messages

* Use the present tense ("Add feature" not "Added feature")
* Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit the first line to 72 characters or less
* Reference issues and pull requests liberally after the first line

### Python Style Guide

This project uses:
* [Black](https://black.readthedocs.io/) for code formatting
* [isort](https://pycqa.github.io/isort/) for import sorting
* [mypy](http://mypy-lang.org/) for type checking
* [flake8](https://flake8.pycqa.org/) for style guide enforcement

Run all style checks:
```bash
poetry run pre-commit run --all-files
```

### Documentation Style

* Use Markdown for documentation
* Keep language clear and concise
* Update relevant documentation with code changes
* Include docstrings for all public methods

## Additional Notes

### Issue and Pull Request Labels

* `bug`: Something isn't working
* `enhancement`: New feature or request
* `documentation`: Documentation only changes
* `good first issue`: Good for newcomers
* `help wanted`: Extra attention is needed

## Questions?

Feel free to contact the maintainers if you have any questions about contributing.

Thank you for your contributions! 🙏
