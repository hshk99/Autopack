-- Initialize database for Autopack
-- This script runs automatically when the PostgreSQL container starts

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone
SET timezone = 'UTC';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE autopack TO autopack;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO autopack;
