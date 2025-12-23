"""Example usage of circuit breaker pattern.

Demonstrates various circuit breaker patterns and use cases.
"""
import time
import random
import logging
from typing import Optional

from src.autopack.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState
)
from src.autopack.circuit_breaker_registry import get_global_registry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UnreliableService:
    """Simulates an unreliable external service."""
    
    def __init__(self, failure_rate: float = 0.3):
        self.failure_rate = failure_rate
        self.call_count = 0
        self.is_down = False
    
    def call(self, data: str) -> str:
        """Make a call to the service."""
        self.call_count += 1
        
        if self.is_down:
            raise ConnectionError("Service is down")
        
        if random.random() < self.failure_rate:
            raise ConnectionError("Random service failure")
        
        return f"Success: {data}"
    
    def set_down(self, down: bool):
        """Simulate service going down or recovering."""
        self.is_down = down
        logger.info(f"Service is now {'DOWN' if down else 'UP'}")


def example_basic_usage():
    """Example 1: Basic circuit breaker usage."""
    logger.info("\n=== Example 1: Basic Usage ===")
    
    # Create service and circuit breaker
    service = UnreliableService(failure_rate=0.5)
    breaker = CircuitBreaker(
        name="basic_service",
        config=CircuitBreakerConfig(failure_threshold=3, timeout=2.0)
    )
    
    # Make calls until circuit opens
    for i in range(10):
        try:
            result = breaker.call(service.call, f"request_{i}")
            logger.info(f"Call {i}: {result}")
        except CircuitBreakerOpenError:
            logger.warning(f"Call {i}: Circuit is OPEN, call rejected")
        except ConnectionError as e:
            logger.error(f"Call {i}: Service error - {e}")
        
        time.sleep(0.1)
    
    # Show final state
    logger.info(f"Final state: {breaker.get_state().value}")
    logger.info(f"Metrics: {breaker.get_metrics()}")


def example_with_fallback():
    """Example 2: Circuit breaker with fallback."""
    logger.info("\n=== Example 2: With Fallback ===")
    
    service = UnreliableService(failure_rate=0.7)
    breaker = CircuitBreaker(
        name="fallback_service",
        config=CircuitBreakerConfig(failure_threshold=2)
    )
    
    def call_with_fallback(data: str) -> str:
        """Call service with fallback on failure."""
        try:
            return breaker.call(service.call, data)
        except (CircuitBreakerOpenError, ConnectionError):
            logger.warning("Using fallback value")
            return f"Fallback: {data}"
    
    # Make calls with fallback
    for i in range(8):
        result = call_with_fallback(f"request_{i}")
        logger.info(f"Call {i}: {result}")
        time.sleep(0.1)


def example_recovery():
    """Example 3: Circuit breaker recovery."""
    logger.info("\n=== Example 3: Recovery ===")
    
    service = UnreliableService(failure_rate=0.0)
    breaker = CircuitBreaker(
        name="recovery_service",
        config=CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=1.0
        )
    )
    
    # Phase 1: Service fails, circuit opens
    logger.info("Phase 1: Service failing...")
    service.set_down(True)
    
    for i in range(5):
        try:
            breaker.call(service.call, f"request_{i}")
        except (CircuitBreakerOpenError, ConnectionError) as e:
            logger.warning(f"Call {i}: {type(e).__name__}")
        time.sleep(0.1)
    
    logger.info(f"State after failures: {breaker.get_state().value}")
    
    # Phase 2: Service recovers
    logger.info("\nPhase 2: Service recovering...")
    service.set_down(False)
    time.sleep(1.5)  # Wait for timeout
    
    # Phase 3: Circuit recovers
    logger.info("\nPhase 3: Testing recovery...")
    for i in range(5):
        try:
            result = breaker.call(service.call, f"recovery_{i}")
            logger.info(f"Call {i}: {result} (State: {breaker.get_state().value})")
        except CircuitBreakerOpenError:
            logger.warning(f"Call {i}: Still open")
        time.sleep(0.1)
    
    logger.info(f"Final state: {breaker.get_state().value}")


def example_registry():
    """Example 4: Using circuit breaker registry."""
    logger.info("\n=== Example 4: Registry ===")
    
    registry = get_global_registry()
    registry.clear()  # Start fresh
    
    # Register multiple circuit breakers
    services = {
        "api": UnreliableService(failure_rate=0.3),
        "database": UnreliableService(failure_rate=0.2),
        "cache": UnreliableService(failure_rate=0.1)
    }
    
    for name, service in services.items():
        registry.register(
            name,
            CircuitBreakerConfig(failure_threshold=3)
        )
    
    # Make calls to different services
    for i in range(10):
        for name, service in services.items():
            breaker = registry.get(name)
            try:
                result = breaker.call(service.call, f"request_{i}")
                logger.info(f"{name}: {result}")
            except (CircuitBreakerOpenError, ConnectionError) as e:
                logger.warning(f"{name}: {type(e).__name__}")
        time.sleep(0.1)
    
    # Show status of all circuit breakers
    logger.info("\nCircuit Breaker Status:")
    for status in registry.get_all_statuses():
        logger.info(
            f"  {status.name}: {status.state.value} "
            f"(calls: {status.metrics.total_calls}, "
            f"failures: {status.metrics.failed_calls})"
        )


def example_monitoring():
    """Example 5: Monitoring circuit breakers."""
    logger.info("\n=== Example 5: Monitoring ===")
    
    service = UnreliableService(failure_rate=0.4)
    breaker = CircuitBreaker(
        name="monitored_service",
        config=CircuitBreakerConfig(failure_threshold=5)
    )
    
    # Make calls and monitor
    for i in range(20):
        try:
            breaker.call(service.call, f"request_{i}")
        except (CircuitBreakerOpenError, ConnectionError):
            pass
        
        # Log metrics every 5 calls
        if (i + 1) % 5 == 0:
            metrics = breaker.get_metrics()
            logger.info(
                f"\nMetrics after {i + 1} calls:\n"
                f"  State: {breaker.get_state().value}\n"
                f"  Total: {metrics.total_calls}\n"
                f"  Success: {metrics.successful_calls}\n"
                f"  Failed: {metrics.failed_calls}\n"
                f"  Rejected: {metrics.rejected_calls}\n"
                f"  Success rate: {metrics.successful_calls / metrics.total_calls * 100:.1f}%"
            )
        
        time.sleep(0.1)


def example_custom_exception():
    """Example 6: Custom exception handling."""
    logger.info("\n=== Example 6: Custom Exception ===")
    
    class ServiceError(Exception):
        """Custom service exception."""
        pass
    
    class UnimportantError(Exception):
        """Exception that shouldn't trigger circuit breaker."""
        pass
    
    def unreliable_call(data: str) -> str:
        """Call that raises different exceptions."""
        rand = random.random()
        if rand < 0.3:
            raise ServiceError("Service error")
        elif rand < 0.4:
            raise UnimportantError("Unimportant error")
        return f"Success: {data}"
    
    # Only count ServiceError as failure
    breaker = CircuitBreaker(
        name="custom_exception_service",
        config=CircuitBreakerConfig(
            failure_threshold=3,
            expected_exception=ServiceError
        )
    )
    
    for i in range(15):
        try:
            result = breaker.call(unreliable_call, f"request_{i}")
            logger.info(f"Call {i}: {result}")
        except CircuitBreakerOpenError:
            logger.warning(f"Call {i}: Circuit OPEN")
        except ServiceError:
            logger.error(f"Call {i}: ServiceError (counted)")
        except UnimportantError:
            logger.info(f"Call {i}: UnimportantError (not counted)")
        
        time.sleep(0.1)
    
    metrics = breaker.get_metrics()
    logger.info(
        f"\nFinal metrics:\n"
        f"  Failed calls: {metrics.failed_calls}\n"
        f"  State: {breaker.get_state().value}"
    )


def main():
    """Run all examples."""
    examples = [
        example_basic_usage,
        example_with_fallback,
        example_recovery,
        example_registry,
        example_monitoring,
        example_custom_exception
    ]
    
    for example in examples:
        try:
            example()
            time.sleep(1)  # Pause between examples
        except Exception as e:
            logger.error(f"Example failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
