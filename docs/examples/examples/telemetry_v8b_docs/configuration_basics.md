# Configuration Basics

This guide covers the essential configuration options for the telemetry system.

## Overview

The telemetry system can be configured through environment variables, configuration files, or programmatic API calls. This document focuses on the most commonly used settings.

## Key Configuration Settings

### 1. Telemetry Enabled

**Setting:** `TELEMETRY_ENABLED`
**Type:** Boolean
**Default:** `true`

Controls whether telemetry collection is active. When disabled, no metrics or events are collected or transmitted.

### 2. Collection Interval

**Setting:** `TELEMETRY_COLLECTION_INTERVAL`
**Type:** Integer (seconds)
**Default:** `60`

Defines how frequently metrics are collected and aggregated. Lower values provide more granular data but increase overhead.

### 3. Export Endpoint

**Setting:** `TELEMETRY_EXPORT_ENDPOINT`
**Type:** String (URL)
**Default:** `http://localhost:4317`

Specifies the endpoint where telemetry data is exported. Supports OTLP-compatible backends.

### 4. Log Level

**Setting:** `TELEMETRY_LOG_LEVEL`
**Type:** String (DEBUG, INFO, WARNING, ERROR)
**Default:** `INFO`

Controls the verbosity of telemetry system logs. Useful for debugging configuration issues.

### 5. Batch Size

**Setting:** `TELEMETRY_BATCH_SIZE`
**Type:** Integer
**Default:** `100`

Number of telemetry events to batch before export. Higher values reduce network overhead but increase memory usage.

## Example Configuration

Here's a complete example configuration for a production environment:

```yaml
# telemetry-config.yaml
telemetry:
  enabled: true
  collection_interval: 30
  export_endpoint: "https://telemetry.prod.example.com:4317"
  log_level: "WARNING"
  batch_size: 500

  # Resource attributes
  resource_attributes:
    service.name: "my-application"
    service.version: "1.0.0"
    deployment.environment: "production"
```

## Loading Configuration

To load configuration from a file:

```python
import telemetry

# Load from YAML file
telemetry.load_config("telemetry-config.yaml")

# Or configure programmatically
telemetry.configure(
    enabled=True,
    collection_interval=30,
    export_endpoint="https://telemetry.prod.example.com:4317",
    log_level="WARNING",
    batch_size=500
)
```

## Best Practices

1. **Start with defaults**: The default configuration works well for most use cases
2. **Adjust collection interval**: Balance between data granularity and system overhead
3. **Use environment variables**: For deployment-specific settings (endpoints, credentials)
4. **Enable debug logging**: When troubleshooting configuration issues
5. **Monitor batch size**: Ensure it matches your traffic patterns

## Next Steps

- [Installation Steps](installation_steps.md) - Set up the telemetry system
- [Troubleshooting Tips](troubleshooting_tips.md) - Resolve common issues
- Explore advanced features in the API documentation

## Troubleshooting

**Configuration not taking effect?**
- Verify environment variables are set before application start
- Check configuration file path is correct
- Enable debug logging to see loaded configuration

**Connection errors?**
- Verify export endpoint is reachable
- Check firewall rules and network connectivity
- Ensure endpoint supports OTLP protocol
