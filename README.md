# tap-salesforce-meltano-sdk

A Singer tap for extracting data from Salesforce, built with the [Singer SDK](https://sdk.meltano.com).

## Features

- Support for REST, Bulk, and Bulk 2.0 APIs
- OAuth 2.0 and password-based authentication
- Automatic schema discovery
- Incremental replication
- Deleted record tracking
- Rate limiting and error handling
- Configurable batch sizes and timeouts

## Installation

```bash
pipx install tap-salesforce-meltano-sdk
```

## Quick Start

1. Set up your Salesforce credentials
2. Create a config file:
```json
{
    "auth_type": "oauth2",
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "refresh_token": "your_refresh_token",
    "start_date": "2023-01-01T00:00:00Z"
}
```
3. Run the tap:
```bash
tap-salesforce --config config.json --discover > catalog.json
tap-salesforce --config config.json --catalog catalog.json
```

## Documentation

- [Authentication](doc/authentication.md)
  - OAuth 2.0 setup
  - Password authentication
  - Security considerations
  - Sandbox support

- [API Types](doc/apis.md)
  - REST API usage and configuration
  - Bulk API features
  - Bulk 2.0 API advantages
  - Best practices for each API

- [Configuration](doc/configuration.md)
  - Full configuration options
  - Environment variables
  - API-specific settings
  - Examples

- [Troubleshooting](doc/troubleshooting.md)
  - Common issues
  - Debugging tips
  - Performance optimization
  - Support resources

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/tap-salesforce-sdk.git
cd tap-salesforce-sdk

# Install dependencies
poetry install
```

### Testing

```bash
# Unit tests
poetry run pytest tests/unit/

# Integration tests
poetry run pytest tests/integration/
```

See [Development Guide](doc/development.md) for more details.

## Release Process

For detailed instructions on releasing new versions, see our [Release Guide](doc/releasing.md).

## About

`tap-salesforce-sdk` is built with the [Singer SDK](https://sdk.meltano.com) and adheres to the [Singer Spec](https://hub.meltano.com/spec).


## License

Apache 2.0 (see [LICENSE](LICENSE))
