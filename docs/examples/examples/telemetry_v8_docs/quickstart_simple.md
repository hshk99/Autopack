# Quickstart Guide

Get started with AutoPack in minutes.

## Installation

Install AutoPack using pip:

```bash
pip install autopack
```

Or install from source:

```bash
git clone https://github.com/yourusername/autopack.git
cd autopack
pip install -e .
```

## Configuration

Create a configuration file `autopack.yaml` in your project root:

```yaml
project:
  name: my-project
  version: 1.0.0

build:
  output_dir: dist
  include:
    - src/**/*.py
    - README.md
```

Optional: Set environment variables for advanced features:

```bash
export AUTOPACK_LOG_LEVEL=INFO
export AUTOPACK_CACHE_DIR=~/.autopack/cache
```

## Run Your First Command

Build your project:

```bash
autopack build
```

This will:
- Read your configuration
- Process source files
- Generate build artifacts in the output directory

Check the build status:

```bash
autopack status
```

## Next Steps

- Explore advanced configuration options in the [Configuration Guide](configuration.md)
- Learn about autonomous build features in the [User Guide](user_guide.md)
- Review [Examples](../examples/) for common use cases
