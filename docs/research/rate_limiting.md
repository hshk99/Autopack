# Rate Limiting Documentation

## Overview

Rate limiting is a critical component in the research system to ensure that API requests do not exceed the allowed limits set by external services like GitHub and Reddit.

## Features

- **Token Bucket Algorithm**: Utilizes a token bucket algorithm to manage request rates.
- **Configurable Limits**: Allows configuration of request limits per service.
- **Retry Mechanism**: Automatically retries requests that are rate-limited after a cooldown period.

## Usage

The rate limiter is used internally by gatherers to manage API request rates.

## Configuration

Rate limits can be configured in the `rate_limiter.py` module. Adjust the `MAX_REQUESTS` and `TIME_WINDOW` constants to suit your needs.

## Best Practices

Always monitor your API usage and adjust rate limits to avoid service disruptions.
