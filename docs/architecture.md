# System Architecture

## Overview

Reliable Email Scheduler uses a persistent, queue-based architecture designed for reliable scheduled email delivery.

The system separates:

- HTTP/API handling
- Persistent data storage
- Scheduled job detection
- Background task execution
- SMTP delivery

This separation allows scheduled jobs to survive process restarts and supports retry and recovery behavior.

## High-Level Architecture

```text
                         +----------------------+
                         |    React Frontend    |
                         |    TypeScript/Vite   |
                         +----------+-----------+
                                    |
                                   HTTP
                                    |
                                    v
                         +----------------------+
                         |     FastAPI Backend   |
                         |      REST API        |
                         +----+------------+-----+
                              |            |
                           SQL|            |Redis
                              |            |
                              v            v
                       +-----------+   +-----------+
                       | PostgreSQL|   |   Redis   |
                       |           |   |   Queue   |
                       +-----+-----+   +-----+-----+
                             |               |
                             |               v
                             |        +-------------+
                             |        | Celery      |
                             |        | Worker      |
                             |        +------+------+
                             |               |
                             |              SMTP
                             |               |
                             |               v
                             |        +-------------+
                             |        | SMTP Server |
                             |        +-------------+
                             |
                             v
                       +-------------+
                       |  Scheduler  |
                       | Python poller|
                       | every 2 sec |
                       +-------------+
```

## Components

### React Frontend

The frontend provides the user interface for:

- Google authentication
- Dashboard statistics
- Email composition
- CSV recipient upload
- Scheduled email management
- Sent email tracking
- Failed email management
- Sender management

The frontend communicates with the FastAPI backend through HTTP requests.

### FastAPI Backend

The backend exposes the application's REST API.

Responsibilities include:

- Authentication
- User ownership checks
- Email scheduling
- Email cancellation
- Email deletion
- Failed email retry
- Sender management
- Rate limiting
- Dashboard statistics
- Request validation

### PostgreSQL

PostgreSQL is the persistent source of truth for application state.

The database stores entities including:

- Users
- Email senders
- Scheduled emails
- Email recipients

Scheduled jobs are persisted in PostgreSQL so they do not depend on in-memory timers.

### Scheduler

The scheduler is a long-running Python process.

It periodically checks PostgreSQL for due scheduled emails.

The scheduler:

1. Finds due scheduled emails.
2. Locks eligible rows.
3. Uses `SKIP LOCKED` to avoid competing claims.
4. Marks jobs as `PROCESSING`.
5. Increments the attempt counter.
6. Queues the Celery task.

The scheduler runs independently from the API process.

### Redis

Redis acts as the message broker for Celery.

It is also used for application-level scheduling rate limiting.

The system uses Redis to decouple API/scheduler activity from worker execution.

### Celery Worker

The Celery worker consumes tasks from Redis.

The worker:

1. Receives a scheduled-email task.
2. Loads the email job from PostgreSQL.
3. Verifies the current job state.
4. Processes recipients independently.
5. Sends email through SMTP.
6. Records recipient results.
7. Schedules retries when needed.
8. Marks the email `SENT` or `FAILED`.

### SMTP

The worker sends email through the SMTP server configured for the selected sender.

Each sender has its own SMTP configuration.

SMTP passwords are encrypted before being stored in PostgreSQL.

## Email Lifecycle

```text
SCHEDULED
    |
    v
PROCESSING
    |
    +----------------------+
    |                      |
    v                      v
  SENT                  FAILURE
                           |
                           v
                         RETRY
                           |
                           v
                      PROCESSING
                           |
                    Retry limit reached
                           |
                           v
                         FAILED
```

An email can also be cancelled while it is still eligible for cancellation.

## Scheduler Concurrency

The scheduler uses PostgreSQL row locking:

```sql
FOR UPDATE SKIP LOCKED
```

This allows multiple scheduler processes to safely inspect the same pool of due jobs without claiming the same email.

Conceptually:

```text
Scheduler A                    Scheduler B
    |                              |
    v                              v
Find due email                Find due email
    |                              |
Lock row --------------------------+
    |
    v
Claim job
    |
    v
PROCESSING
```

If Scheduler A has already locked the row, Scheduler B skips it instead of waiting and later attempting to process the same job.

## Worker Idempotency

The worker checks the current state of the email before processing.

Terminal states such as:

```text
SENT
CANCELLED
```

are not processed again.

This prevents duplicate execution after retries, duplicate task delivery, or worker recovery scenarios.

## Per-Recipient Processing

Recipients are stored independently.

Example:

```text
Scheduled Email
      |
      +--- recipient A -> SENT
      |
      +--- recipient B -> FAILED
      |
      +--- recipient C -> SENT
```

Only failed recipients need to be retried.

This prevents already successful deliveries from being sent again.

## Retry Strategy

The system uses exponential backoff.

Current retry delays:

```text
Attempt 1 -> 10 seconds
Attempt 2 -> 20 seconds
Attempt 3 -> 40 seconds
```

The delay is calculated from configurable retry settings.

After the maximum number of attempts, the email is marked `FAILED`.

## Restart Recovery

A job can become stuck in `PROCESSING` if a worker or scheduler process terminates unexpectedly.

The recovery mechanism identifies stale processing jobs and moves them back into a retryable state.

This allows the system to recover without permanently losing scheduled work.

## Idempotency

Scheduling requests use an idempotency key.

The database enforces uniqueness for the idempotency key so repeated requests do not create duplicate scheduled emails.

## Rate Limiting

The scheduling endpoint uses Redis-backed rate limiting.

Default configuration:

```text
30 scheduling requests
per user
per 60 seconds
```

Requests exceeding the limit receive:

```text
HTTP 429 Too Many Requests
```

## Security Model

The system includes:

```text
Google OAuth
     |
     v
Authenticated Session
     |
     v
User ID
     |
     +----> Email ownership checks
     |
     +----> Sender ownership checks
```

Users can only operate on resources belonging to their account.

SMTP passwords are encrypted before being persisted.

Secrets are provided through environment variables instead of source-controlled configuration.

## Docker Deployment

The local Docker Compose environment consists of six services:

```text
+----------------------------------------------------+
|                  Docker Compose                    |
|                                                    |
|  +------------+       +--------------------------+ |
|  |  Frontend  | ----> |         Backend          | |
|  |   Nginx    | HTTP  |         FastAPI          | |
|  +------------+       +------------+-------------+ |
|                                      |             |
|                           +----------+----------+  |
|                           |                     |  |
|                           v                     v  |
|                    +-------------+       +---------+
|                    | PostgreSQL  |       |  Redis  |
|                    +-------------+       +----+----+
|                                              |
|                              +---------------+
|                              |               |
|                              v               v
|                       +-----------+     +-----------+
|                       | Scheduler |     |   Worker  |
|                       +-----------+     +-----------+
|                                             |
|                                            SMTP
+----------------------------------------------------+
```

### Docker Services

| Service | Purpose |
|---|---|
| `frontend` | React application served by Nginx |
| `backend` | FastAPI REST API |
| `postgres` | Persistent relational database |
| `redis` | Celery broker and rate limiting |
| `scheduler` | Finds and queues due emails |
| `worker` | Executes email delivery tasks |

## End-to-End Flow

```text
1. User creates an email
             |
             v
2. FastAPI validates request
             |
             v
3. PostgreSQL stores email + recipients
             |
             v
4. Scheduler detects due email
             |
             v
5. PostgreSQL row is safely claimed
             |
             v
6. Job becomes PROCESSING
             |
             v
7. Celery task is published to Redis
             |
             v
8. Worker receives task
             |
             v
9. Worker processes recipients
             |
             v
10. SMTP delivery is attempted
             |
             +----------------------+
             |                      |
             v                      v
          Success                 Failure
             |                      |
             v                      v
           SENT                   RETRY
                                    |
                                    v
                             Backoff delay
                                    |
                                    v
                               Retry again
                                    |
                                    v
                              Retry limit
                                    |
                                    v
                                  FAILED
```

## Design Goals

The architecture is designed to provide:

- Persistent scheduling
- Safe concurrent job claiming
- Asynchronous background processing
- Retry handling
- Restart recovery
- Idempotent execution
- Per-recipient tracking
- User-level isolation
- Secure SMTP credential storage
- Rate-limited scheduling
- Containerized local deployment