# Circuit Breaker Pattern - Usage Guide

## Overview

The circuit breaker pattern provides fault tolerance and resilience for external service calls. It prevents cascading failures by temporarily blocking calls to failing services and allowing them time to recover.

## States

The circuit breaker has three states:

1. **CLOSED** (Normal Operation)
   - All calls pass through to the service
   - Failures are counted
   - Transitions to OPEN when failure threshold is reached

2. **OPEN** (Failing)
   - All calls are immediately rejected
   - No calls reach the service
   - Transitions to HALF_OPEN after timeout period

3. **HALF_OPEN** (Testing Recovery)
   - Limited calls are allowed through
   - Testing if service has recovered
   - Transitions to CLOSED after success threshold
   - Transitions back to OPEN on any failure

## Basic Usage

### Simple Circuit Breaker

```python
from src.autopack.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# Create circuit breaker with default config
breaker = CircuitBreaker(name="api_service")

# Use circuit breaker to protect a call
try:
    result = breaker.call(lambda: external_api_call())
    print(f"Success: {result}")
except CircuitBreakerOpenError:
    print("Circuit is open, using fallback")
    result = fallback_value
```

### Custom Configuration

```python
from src.autopack.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# Create custom configuration
config = CircuitBreakerConfig(
    failure_threshold=3,      # Open after 3 failures
    success_threshold=2,      # Close after 2 successes in HALF_OPEN
    timeout=30.0,            # Wait 30s before trying HALF_OPEN
    half_open_timeout=15.0,  # Stay in HALF_OPEN for 15s max
    expected_exception=ConnectionError  # Only count ConnectionError as failure
)

breaker = CircuitBreaker(name="database", config=config)
```

## Using the Registry

The registry provides centralized management of multiple circuit breakers.

### Basic Registry Usage

```python
from src.autopack.circuit_breaker_registry import get_global_registry
from src.autopack.circuit_breaker import CircuitBreakerConfig

# Get global registry
registry = get_global_registry()

# Register circuit breakers
registry.register(
    "api_service",
    CircuitBreakerConfig(failure_threshold=5)
)

registry.register(
    "database",
    CircuitBreakerConfig(failure_threshold=3, timeout=60.0)
)

# Use circuit breakers
api_breaker = registry.get("api_service")
result = api_breaker.call(lambda: api_call())
```

### Get or Create Pattern

```python
# Get existing or create new circuit breaker
breaker = registry.get_or_create(
    "cache_service",
    CircuitBreakerConfig(failure_threshold=10)
)
```

## Monitoring

### Check Circuit Breaker Status

```python
# Check if circuit will allow calls
if breaker.is_available():
    result = breaker.call(lambda: service_call())
else:
    result = fallback_value

# Get current state
state = breaker.get_state()  # Returns CircuitState enum
print(f"Circuit state: {state.value}")
```

### Get Metrics

```python
# Get detailed metrics
metrics = breaker.get_metrics()

print(f"Total calls: {metrics.total_calls}")
print(f"Successful: {metrics.successful_calls}")
print(f"Failed: {metrics.failed_calls}")
print(f"Rejected: {metrics.rejected_calls}")
print(f"Last failure: {metrics.last_failure_time}")
print(f"State transitions: {metrics.state_transitions}")
```

### Monitor All Circuit Breakers

```python
# Get status of all circuit breakers
statuses = registry.get_all_statuses()

for status in statuses:
    print(f"\nCircuit: {status.name}")
    print(f"  State: {status.state.value}")
    print(f"  Available: {status.is_available}")
    print(f"  Total calls: {status.metrics.total_calls}")
    print(f"  Failed calls: {status.metrics.failed_calls}")
```

## Manual Control

### Reset Circuit Breaker

```python
# Reset single circuit breaker to CLOSED state
breaker.reset()

# Or via registry
registry.reset("api_service")

# Reset all circuit breakers
registry.reset_all()
```

## Advanced Patterns

### Fallback Pattern

```python
def call_with_fallback(breaker, primary_func, fallback_func):
    """Call primary function with fallback on failure."""
    try:
        return breaker.call(primary_func)
    except CircuitBreakerOpenError:
        logger.warning("Circuit open, using fallback")
        return fallback_func()
    except Exception as e:
        logger.error(f"Primary call failed: {e}")
        return fallback_func()

# Usage
result = call_with_fallback(
    breaker,
    lambda: api_call(),
    lambda: cached_value
)
```

### Retry with Circuit Breaker

```python
def retry_with_circuit_breaker(breaker, func, max_retries=3):
    """Retry function with circuit breaker protection."""
    for attempt in range(max_retries):
        try:
            return breaker.call(func)
        except CircuitBreakerOpenError:
            raise  # Don't retry if circuit is open
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff

# Usage
result = retry_with_circuit_breaker(
    breaker,
    lambda: unreliable_service_call()
)
```

### Decorator Pattern

```python
from functools import wraps

def with_circuit_breaker(breaker_name, config=None):
    """Decorator to protect function with circuit breaker."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            registry = get_global_registry()
            breaker = registry.get_or_create(breaker_name, config)
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator

# Usage
@with_circuit_breaker("api_service", CircuitBreakerConfig(failure_threshold=5))
def call_api(endpoint):
    return requests.get(f"https://api.example.com/{endpoint}")

result = call_api("users")
```

## Configuration Guidelines

### Failure Threshold
- **Low (2-3)**: For critical services where failures are unacceptable
- **Medium (5-10)**: For normal services with expected occasional failures
- **High (15+)**: For services with high variability or acceptable failure rates

### Timeout
- **Short (10-30s)**: For services that recover quickly
- **Medium (30-60s)**: For typical services
- **Long (60-300s)**: For services with slow recovery or startup

### Success Threshold
- **Low (1-2)**: For services that recover quickly and reliably
- **Medium (3-5)**: For typical services
- **High (5+)**: For services with unreliable recovery

## Best Practices

1. **Use Meaningful Names**: Name circuit breakers after the service they protect
2. **Configure Appropriately**: Tune thresholds based on service characteristics
3. **Monitor Metrics**: Regularly check circuit breaker metrics
4. **Implement Fallbacks**: Always have a fallback strategy
5. **Log State Changes**: Monitor state transitions for debugging
6. **Test Recovery**: Verify circuit breakers recover correctly
7. **Use Registry**: Centralize circuit breaker management
8. **Document Configuration**: Document why specific thresholds were chosen

## Common Pitfalls

1. **Too Aggressive Thresholds**: Opening circuit too quickly
2. **No Fallback**: Not handling CircuitBreakerOpenError
3. **Ignoring Metrics**: Not monitoring circuit breaker health
4. **Wrong Exception Type**: Not configuring expected_exception correctly
5. **Shared Circuit Breakers**: Using same breaker for different services
6. **No Testing**: Not testing circuit breaker behavior
7. **Manual Resets**: Resetting circuits without understanding root cause

## Testing

```python
import pytest
from src.autopack.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

def test_circuit_breaker_opens_on_failures():
    """Test that circuit opens after threshold failures."""
    config = CircuitBreakerConfig(failure_threshold=3)
    breaker = CircuitBreaker(name="test", config=config)
    
    # Fail 3 times
    for _ in range(3):
        with pytest.raises(Exception):
            breaker.call(lambda: raise_exception())
    
    # Circuit should be open
    assert breaker.get_state() == CircuitState.OPEN
    
    # Next call should be rejected
    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(lambda: "success")
```

## Integration Examples

### With HTTP Client

```python
import requests
from src.autopack.circuit_breaker_registry import get_global_registry
from src.autopack.circuit_breaker import CircuitBreakerConfig

class ResilientHttpClient:
    def __init__(self):
        self.registry = get_global_registry()
        self.registry.register(
            "http_client",
            CircuitBreakerConfig(
                failure_threshold=5,
                timeout=60.0,
                expected_exception=requests.RequestException
            )
        )
    
    def get(self, url):
        breaker = self.registry.get("http_client")
        return breaker.call(lambda: requests.get(url))

client = ResilientHttpClient()
response = client.get("https://api.example.com/data")
```

### With Database

```python
import psycopg2
from src.autopack.circuit_breaker_registry import get_global_registry
from src.autopack.circuit_breaker import CircuitBreakerConfig

class ResilientDatabase:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.registry = get_global_registry()
        self.registry.register(
            "database",
            CircuitBreakerConfig(
                failure_threshold=3,
                timeout=30.0,
                expected_exception=psycopg2.Error
            )
        )
    
    def query(self, sql):
        breaker = self.registry.get("database")
        
        def execute():
            conn = psycopg2.connect(self.connection_string)
            cursor = conn.cursor()
            cursor.execute(sql)
            return cursor.fetchall()
        
        return breaker.call(execute)

db = ResilientDatabase("postgresql://localhost/mydb")
results = db.query("SELECT * FROM users")
```
