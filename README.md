# Reliable Email Scheduler

A production-style email scheduling platform built with Python, FastAPI, PostgreSQL, Redis, Celery, and React.

The system is designed around reliable background processing, persistent scheduling, retry handling, duplicate prevention, per-recipient delivery tracking, authentication, and recovery from worker or scheduler interruptions.

## Features

- Schedule emails for future delivery
- Persistent email jobs stored in PostgreSQL
- Long-running scheduler with database polling
- Redis + Celery background processing
- Exponential retry backoff
- Maximum retry handling
- Per-recipient delivery status
- Failure reason tracking
- Duplicate prevention and idempotency
- Recovery of stuck `PROCESSING` jobs
- Email cancellation
- Delete scheduled, failed, and cancelled emails
- Manual retry of failed emails
- User ownership and isolation
- Google OAuth authentication
- Sender management with encrypted SMTP passwords
- SMTP configuration per sender
- CSV recipient upload
- Dashboard with live email statistics
- Scheduled, sent, and failed email views
- Toast notifications
- Responsive frontend
- API rate limiting for scheduling requests
- Dockerized PostgreSQL, Redis, backend, scheduler, worker, and frontend

## Architecture

                    +----------------------+
                    |    React Frontend    |
                    |     Vite + TS        |
                    +----------+-----------+
                               |
                              HTTP
                               |
                               v
                    +----------------------+
                    |     FastAPI API      |
                    +----+------------+----+
                         |            |
                      SQL|            |Redis
                         |            |
                         v            v
                 +-----------+   +-----------+
                 | PostgreSQL|   |   Redis   |
                 +-----+-----+   +-----+-----+
                       |               |
                       |               v
                       |        +-------------+
                       |        |Celery Worker|
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
                +---------------+
                |   Scheduler   |
                | Python Poller |
                |    2 seconds  |
                +---------------+


## Email Processing Flow

User schedules email
        |
        v
FastAPI validates request
        |
        v
PostgreSQL stores email + recipients
        |
        v
Scheduler finds due email
        |
        v
Database row lock claims job
        |
        v
Job marked PROCESSING
        |
        v
Celery task queued in Redis
        |
        v
Worker processes recipients
        |
        v
SMTP delivery attempt
        |
        +-------------------+
        |                   |
     Success             Failure
        |                   |
        v                   v
       SENT               Retry
                            |
                            v
                   Exponential Backoff
                            |
                            v
                       Retry Limit
                            |
                       +----+----+
                       |         |
                      SENT     FAILED


## Reliability Design

### Persistent Scheduling

Scheduled emails are stored in PostgreSQL instead of relying on in-memory timers.

This ensures scheduled jobs survive application and process restarts.

### Concurrent-Safe Job Claiming

The scheduler uses PostgreSQL row locking with:

```sql
FOR UPDATE SKIP LOCKED
```

This prevents multiple scheduler processes from claiming and processing the same scheduled email simultaneously.

### Exponential Retry Backoff

Failed email deliveries use exponential backoff:

Attempt 1 → 10 seconds
Attempt 2 → 20 seconds
Attempt 3 → 40 seconds

Retry settings are configurable through application configuration.

### Maximum Retry Handling

After the configured maximum number of attempts, the email is marked as:

```text
FAILED
```

The system stores a failure reason so the delivery history can be inspected later.

### Restart Recovery

Jobs that remain stuck in `PROCESSING` after an interruption can be recovered and rescheduled.

This prevents temporary worker or scheduler failures from leaving jobs permanently stuck.

### Per-Recipient Delivery Tracking

Each recipient is stored separately.

This allows the system to keep successfully delivered recipients as `SENT` while retrying only recipients that failed.

### Idempotency

Scheduling requests use an idempotency key to prevent duplicate email jobs from being created accidentally.

### Duplicate Processing Prevention

Database locking and worker state checks prevent a completed email from being processed again.

## Security

- Google OAuth authentication
- User ownership checks on email resources
- User ownership checks on sender resources
- SMTP passwords encrypted before database storage
- Environment-based application configuration
- `.env` excluded from Git
- `.env.example` provided for setup
- Scheduling endpoint rate limiting
- Dedicated non-root Docker user for Celery worker
- Secrets are not stored in the repository

## Rate Limiting

The scheduling endpoint includes application-level rate limiting backed by Redis.

The configured default limit is:

```text
30 scheduling requests per user per 60 seconds
```

Excessive requests receive an HTTP:

```text
429 Too Many Requests
```

response.

## Tech Stack

### Backend

- Python
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- Redis
- Celery
- SMTP
- Authlib
- Cryptography

### Frontend

- React
- TypeScript
- Vite
- React Router
- Axios
- Sonner

### Infrastructure

- Docker
- Docker Compose
- PostgreSQL 17
- Redis 7
- Nginx

## Project Structure

reliable-email-scheduler/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── scheduler/
│   │   ├── services/
│   │   └── worker/
│   │
│   ├── alembic/
│   ├── tests/
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   └── pages/
│   ├── Dockerfile
│   └── package.json
│
├── docs/
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── .env.example
└── README.md

## Docker Architecture

The project runs as six Docker services:

+------------------------------------------------------+
|                  Docker Compose                      |
|                                                      |
|  +-------------+       +-------------------------+  |
|  |   Frontend  | ----> |        Backend          |  |
|  |    Nginx    | HTTP  |        FastAPI          |  |
|  +-------------+       +-----------+-------------+  |
|                                      |
|                         +------------+------------+
|                         |                         |
|                         v                         v
|                  +-------------+           +-------------+
|                  | PostgreSQL  |           |    Redis    |
|                  +-------------+           +------+------+
|                                                   |
|                                          +--------+--------+
|                                          |                 |
|                                          v                 v
|                                   +-----------+     +-----------+
|                                   | Scheduler |     |   Worker  |
|                                   +-----------+     +-----------+
|                                                        |
|                                                       SMTP
+------------------------------------------------------+

## Running with Docker

### Prerequisites

Install:

- Docker Desktop
- Git

### Configuration

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Then update `.env` with your own values for:

POSTGRES_PASSWORD
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
SMTP_ENCRYPTION_KEY

Never commit `.env` to Git.

### Start the Full Stack

```powershell
docker compose up -d --build
```

### Check Containers

```powershell
docker compose ps
```

Expected services:

reliable_email_postgres
reliable_email_redis
reliable_email_backend
reliable_email_worker
reliable_email_scheduler
reliable_email_frontend

### View Logs

Backend:

```powershell
docker compose logs backend
```

Worker:

```powershell
docker compose logs worker
```

Scheduler:

```powershell
docker compose logs scheduler
```

### Stop the Stack

```powershell
docker compose down
```

## Application URLs

Frontend:

```text
http://localhost:5173
```

Backend API:

```text
http://localhost:8000
```

Swagger API documentation:

```text
http://localhost:8000/docs
```

## Testing

Run the backend test suite:

```powershell
pytest backend/tests -v
```

The automated tests cover areas including:

- Email scheduling
- Authentication
- User ownership
- Sender management
- Cancellation
- Email deletion
- Manual retry
- Rate limiting
- Duplicate prevention
- Scheduler job claiming
- Restart recovery
- Worker processing
- Retry behavior
- Recipient status tracking
- Failure handling

## API Documentation

When the backend is running, interactive Swagger documentation is available at:

```text
http://localhost:8000/docs
```

The API can be explored directly through the FastAPI Swagger interface.

## Development

### Backend

From the project root:

```powershell
cd backend
uvicorn app.main:app --reload
```

### Frontend

From the project root:

```powershell
cd frontend
npm install
npm run dev
```

## Database Migrations

Alembic is used for database schema migrations.

Create a migration:

```powershell
alembic revision --autogenerate -m "migration message"
```

Apply migrations:

```powershell
alembic upgrade head
```

## Current Status

The core application, reliability features, authentication, sender management, frontend, automated tests, and Docker environment are implemented and locally verified.

The Docker stack has been verified with:
PostgreSQL     
Redis          
FastAPI        
Celery Worker  
Scheduler      
React Frontend 

The complete email processing pipeline has also been verified:

Frontend
   ↓
FastAPI
   ↓
PostgreSQL
   ↓
Scheduler
   ↓
Redis / Celery
   ↓
Worker
   ↓
SMTP
   ↓
SENT

## Portfolio Highlights

This project demonstrates practical experience with:

- Backend API development
- Distributed background processing
- Task queues
- Database concurrency
- Retry and failure recovery
- Idempotent job processing
- Authentication and authorization
- Secure credential storage
- Redis-based rate limiting
- Relational database design
- Automated testing
- React and TypeScript
- Docker containerization
- Production-oriented system architecture

This project is currently provided for portfolio and educational purposes.
