# Research API Reference

This document provides an overview of the API endpoints available for the research system within the Autopack framework.

## Base URL

All endpoints are prefixed with `/api/research`.

## Endpoints

### GET /api/research/sessions

Retrieve a list of all research sessions.

**Response (200 OK):**
```json
[
  {
    "session_id": "abc123",
    "status": "active",
    "created_at": "2025-12-20T12:00:00Z"
  }
]
```

### POST /api/research/sessions

Create a new research session.

**Request Body:**
```json
{
  "topic": "AI Research",
  "description": "Exploring new AI techniques"
}
```

**Response (201 Created):**
```json
{
  "session_id": "abc123",
  "status": "active",
  "created_at": "2025-12-20T12:00:00Z"
}
```

### Error Responses

All endpoints may return standard error responses with appropriate HTTP status codes and messages.
