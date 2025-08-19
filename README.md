# HR Agent - Modern MCP-Based HR Assistant

A modernized HR Agent application built with the Model Context Protocol (MCP), featuring a ReAct reasoning loop, PostgreSQL with pgvector for document storage, and comprehensive safety guardrails.

## Features

- **MCP Architecture**: Generic `action` tool that routes to various HR sub-actions
- **ReAct Planning**: Reason-Act-Observe loop with guardrail protection
- **Vector Search**: PostgreSQL + pgvector for document embedding and search
- **Safety Guardrails**: Soft-delete with confirmation requirements for destructive actions
- **Modern UI**: ChatGPT-style interface without authentication
- **Real-time Streaming**: Server-Sent Events for live response streaming
- **Data Visualization**: Chart.js integration for data visualization

## Architecture

### Backend Components
- **MCP Server** (`server/mcp_server.py`): Core MCP implementation with generic action tool
- **ReAct Planner** (`server/agents/planner.py`): Reasoning loop with safety checks
- **Database Layer** (`server/db/`): PostgreSQL schema, migrations, and document ingestion
- **HTTP API** (`server/app.py`): Flask server with SSE streaming

### Frontend
- **Modern Web UI** (`web/index.html`): ChatGPT-style interface with sidebar navigation
- **Real-time Updates**: SSE streaming for live responses
- **Chart Integration**: Chart.js for data visualization
- **Local Storage**: Chat history stored in browser localStorage

## Available Actions

The MCP server provides these sub-actions via the generic `action` tool:

- `vector_search` - Search company documents using embeddings
- `ingest_documents` - Add new documents with automatic chunking and embedding
- `attendance_mark` - Mark employee attendance (check-in/check-out)
- `attendance_report` - Generate attendance reports
- `attendance_stats` - Get attendance statistics
- `attendance_my_summary` - Get personal attendance summary
- `tasks_log` - Create or update tasks
- `tasks_my_recent` - Get recent tasks for an employee
- `tasks_report` - Generate comprehensive tasks report
- `company_docs_qa` - Answer questions using company documents
- `meet_create` - Create meetings
- `meet_list` - List upcoming meetings
- `employee_overview` - Get employee overview
- `employee_emails` - Get employee email addresses
- `leave_report` - Generate leave reports
- `visualize` - Generate chart configurations for frontend rendering

## Safety Features

### Soft-Delete Protection
- All delete operations are soft-deletes (set `deleted_at` timestamp)
- Automatic filtering excludes soft-deleted records from queries
- `restore()` function available to recover soft-deleted items

### Guardrail Protection
- ReAct planner checks for destructive actions before execution
- Requires explicit user confirmation phrases like "yes, delete it" or "force=true"
- If no confirmation, performs soft-delete then immediate restore with explanatory message
- Comprehensive audit logging for all actions

### Audit Trail
- All actions logged to `audit_log` table with actor, action, and details
- Immutable log entries for compliance and debugging

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose
- OpenAI API key

### 2. Setup
```bash
# Clone or create the project directory
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start all services
docker-compose up --build
```

### 3. Access the Application
- Web Interface: http://localhost:3000
- API Health Check: http://localhost:5000/api/health

## Development Setup

### Local Development
```bash
# Backend setup
cd server
pip install -r requirements.txt
export OPENAI_API_KEY=your_key_here
export DATABASE_URL=postgresql://hruser:hrpass@localhost:5432/hrdb
python app.py

# Database setup (separate terminal)
python db/migrate.py
```

### Database Schema
The application uses PostgreSQL with pgvector extension:
- `documents` - Document chunks with embeddings
- `employees` - Employee information
- `attendance` - Attendance records
- `tasks` - Task management
- `meetings` - Meeting scheduling
- `leave_requests` - Leave management
- `audit_log` - Action audit trail

## API Endpoints

- `POST /api/chat` - Main chat endpoint with SSE streaming
- `GET /api/health` - Health check
- `GET /api/sessions` - List chat sessions
- `GET /api/sessions/{id}/history` - Get session history
- `DELETE /api/sessions/{id}` - Delete session

## Configuration

### Environment Variables
- `OPENAI_API_KEY` - OpenAI API key (required)
- `DATABASE_URL` - PostgreSQL connection string
- `EMBEDDING_MODEL` - OpenAI embedding model (default: text-embedding-3-small)
- `CHUNK_SIZE` - Document chunk size (default: 1000)
- `CHUNK_OVERLAP` - Chunk overlap (default: 100)
- `PORT` - Server port (default: 5000)

### Docker Services
- `db` - PostgreSQL with pgvector (port 5432)
- `api` - Python Flask API server (port 5000)
- `web` - Nginx static file server (port 8080)

## Usage Examples

### Basic HR Queries
- "Show me attendance statistics"
- "Generate a tasks report"
- "List upcoming meetings"
- "Show employee overview"

### Document Search
- "Search for vacation policy"
- "What are the remote work guidelines?"

### Data Visualization
- "Create a pie chart of attendance data"
- "Show a bar chart of tasks by status"

### Task Management
- "Create a task for John to review the Q4 report"
- "Show my recent tasks"

## Safety Demonstration

### Destructive Action Protection
```
User: "Delete employee EMP001"
Assistant: Action 'delete_employee' was attempted but immediately undone because you did not provide explicit confirmation. To proceed, please confirm with one of these phrases: 'yes, delete it', 'force=true', 'confirm delete', 'yes delete', 'delete confirmed'
```

### Confirmed Destructive Action
```
User: "Delete employee EMP001, yes delete it"
Assistant: Employee EMP001 has been successfully deleted (soft-delete with audit trail).
```

## Troubleshooting

### Common Issues
1. **Database Connection Failed**: Ensure PostgreSQL is running and connection string is correct
2. **OpenAI API Errors**: Check your API key and usage limits
3. **Port Already in Use**: Change ports in docker-compose.yml or stop conflicting services
4. **Docker Build Fails**: Ensure Docker has sufficient resources allocated

### Logs
```bash
# View all service logs
docker-compose logs

# View specific service logs
docker-compose logs api
docker-compose logs db
docker-compose logs web
```

### Database Access
```bash
# Connect to database
docker-compose exec db psql -U hruser -d hrdb

# Run migrations manually
docker-compose exec api python db/migrate.py
```

## Contributing

1. Follow the existing code structure and patterns
2. Add comprehensive error handling
3. Update tests for new functionality
4. Ensure all destructive actions have guardrail protection
5. Document new features in this README

## License

This project is licensed under the MIT License.

## Architecture Decisions

### Why MCP?
- Provides a clean, standardized interface for tool interactions
- Enables easy extension with new actions
- Maintains consistency across different tool types

### Why ReAct?
- Provides transparent reasoning process
- Enables complex multi-step task execution
- Allows for safety checks between reasoning steps

### Why PostgreSQL + pgvector?
- Better performance than cloud vector databases for our use case
- Built-in SQL capabilities for complex queries
- Cost-effective self-hosted solution
- Excellent integration with Python ecosystem

### Why Soft-Delete?
- Prevents accidental data loss
- Maintains audit compliance
- Enables easy data recovery
- Supports the safety-first architecture