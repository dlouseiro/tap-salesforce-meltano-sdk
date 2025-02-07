# Configuration Guide

## Basic Configuration

### Required Settings
```json
{
    "auth_type": "oauth2",
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "refresh_token": "your_refresh_token",
    "start_date": "2023-01-01T00:00:00Z"
}
```

### Optional Settings
```json
{
    "api_type": "REST",              // REST, BULK, or BULK2
    "select_fields_by_default": true, // Auto-select all fields
    "include_deleted": false,         // Include deleted records
    "is_sandbox": false              // Use sandbox environment
}
```

## API-Specific Configuration

### REST API
```json
{
    "api_type": "REST",
    "page_size": 2000
}
```

### Bulk API
```json
{
    "api_type": "BULK",
    "batch_size": 10000,
    "bulk_api_hints": true,
    "bulk_poll_interval": 10
}
```

### Bulk 2.0 API
```json
{
    "api_type": "BULK2",
    "bulk2_use_locator": true,
    "bulk2_poll_interval": 5,
    "bulk2_timeout": 1800
}
```

## Environment Variables

All configuration options can be set using environment variables:

```bash
export TAP_SALESFORCE_CLIENT_ID=your_client_id
export TAP_SALESFORCE_CLIENT_SECRET=your_client_secret
export TAP_SALESFORCE_REFRESH_TOKEN=your_refresh_token
```

## Advanced Configuration

### Custom Filters
```json
{
    "custom_filters": {
        "Account": "Industry != null",
        "Opportunity": "Amount > 0"
    }
}
```

### Field Selection
```json
{
    "select_fields_by_default": false,
    "selected_fields": {
        "Account": ["Id", "Name", "Industry"],
        "Contact": ["Id", "Email", "Phone"]
    }
}
```

### Rate Limiting
```json
{
    "request_timeout": 300,
    "max_retries": 5,
    "retry_interval": 30
}
```
