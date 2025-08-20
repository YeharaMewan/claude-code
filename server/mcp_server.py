"""
MCP Server for HR Agent
Implements a generic 'action' tool that routes to various HR sub-actions
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, date
import os

import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client with lazy loading
openai_client = None

def get_openai_client():
    """Get OpenAI client with lazy initialization"""
    global openai_client
    if openai_client is None:
        try:
            from openai import OpenAI
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key or api_key == 'your_openai_api_key_here':
                logger.error("OPENAI_API_KEY is not set properly")
                return None
            openai_client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return None
    return openai_client

@dataclass
class ToolResult:
    """Result from a tool execution"""
    success: bool
    data: Any = None
    error: str = None
    
class DatabaseManager:
    """Handles database operations with soft-delete support"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'postgresql://hruser:hrpass@localhost:5432/hrdb')
    
    def get_connection(self):
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
    
    def log_action(self, actor: str, action: str, details: Dict[str, Any]):
        """Log action to audit table"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
                    (actor, action, json.dumps(details))
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
    
    def soft_delete(self, table: str, record_id: str, actor: str = "system"):
        """Soft delete a record"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE {table} SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL",
                    (record_id,)
                )
                affected = cur.rowcount
                conn.commit()
                
                if affected > 0:
                    self.log_action(actor, f"soft_delete_{table}", {"id": record_id})
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to soft delete from {table}: {e}")
            return False
    
    def restore(self, table: str, record_id: str, actor: str = "system"):
        """Restore a soft-deleted record"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE {table} SET deleted_at = NULL WHERE id = %s AND deleted_at IS NOT NULL",
                    (record_id,)
                )
                affected = cur.rowcount
                conn.commit()
                
                if affected > 0:
                    self.log_action(actor, f"restore_{table}", {"id": record_id})
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to restore from {table}: {e}")
            return False

class ToolRouter:
    """Routes generic 'action' calls to specific HR sub-actions"""
    
    def __init__(self):
        self.db = DatabaseManager()
    
    def check_permission(self, actor: str, action: str) -> bool:
        """Check if actor has permission for action (replaces old JWT logic)"""
        # For now, implement basic role-based access
        # In a real system, this would check the actor's role from the database
        hr_only_actions = ['attendance_report', 'tasks_report', 'leave_report', 'employee_overview']
        leader_actions = ['tasks_log', 'attendance_stats']
        
        # For this demo, assume actors with 'hr' or 'admin' in name have HR permissions
        # and 'leader' or 'manager' have leader permissions
        if action in hr_only_actions:
            return 'hr' in actor.lower() or 'admin' in actor.lower()
        elif action in leader_actions:
            return any(role in actor.lower() for role in ['hr', 'admin', 'leader', 'manager'])
        
        return True  # Most actions are available to all users
    
    async def route_action(self, action_type: str, **kwargs) -> ToolResult:
        """Route to appropriate sub-action"""
        actor = kwargs.get('actor', 'system')
        
        if not self.check_permission(actor, action_type):
            return ToolResult(success=False, error=f"Permission denied for action: {action_type}")
        
        # Route to appropriate handler
        handler_map = {
            'vector_search': self._vector_search,
            'ingest_documents': self._ingest_documents,
            'attendance_mark': self._attendance_mark,
            'attendance_report': self._attendance_report,
            'attendance_stats': self._attendance_stats,
            'attendance_my_summary': self._attendance_my_summary,
            'tasks_log': self._tasks_log,
            'tasks_my_recent': self._tasks_my_recent,
            'tasks_report': self._tasks_report,
            'company_docs_qa': self._company_docs_qa,
            'meet_create': self._meet_create,
            'meet_list': self._meet_list,
            'employee_overview': self._employee_overview,
            'employee_emails': self._employee_emails,
            'leave_report': self._leave_report,
            'visualize': self._visualize,
        }
        
        handler = handler_map.get(action_type)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action type: {action_type}")
        
        try:
            return await handler(**kwargs)
        except Exception as e:
            logger.error(f"Error in {action_type}: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _vector_search(self, query: str, limit: int = 5, **kwargs) -> ToolResult:
        """Search documents using vector similarity"""
        try:
            # Get OpenAI client
            client = get_openai_client()
            if not client:
                return ToolResult(success=False, error="OpenAI client not available")
            
            # Generate embedding for query
            response = client.embeddings.create(
                input=query,
                model="text-embedding-3-small"
            )
            query_embedding = response.data[0].embedding
            
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT content, metadata, (1 - (embedding <=> %s::vector)) as similarity
                    FROM documents 
                    WHERE deleted_at IS NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (query_embedding, query_embedding, limit))
                
                results = cur.fetchall()
                
            return ToolResult(success=True, data={
                'results': [dict(r) for r in results],
                'query': query
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Vector search failed: {e}")
    
    async def _ingest_documents(self, documents: List[Dict], **kwargs) -> ToolResult:
        """Ingest documents with embeddings"""
        try:
            # For now, return a simple success message
            # In a full implementation, this would use the ingestion system
            return ToolResult(success=True, data={
                'message': f"Would ingest {len(documents)} documents",
                'documents_count': len(documents)
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Document ingestion failed: {e}")
    
    async def _attendance_mark(self, employee_id: str, action: str = 'check_in', **kwargs) -> ToolResult:
        """Mark attendance for employee"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                today = date.today()
                
                if action == 'check_in':
                    cur.execute("""
                        INSERT INTO attendance (employee_id, date, check_in, status)
                        VALUES (%s, %s, NOW(), 'present')
                        ON CONFLICT (employee_id, date) 
                        DO UPDATE SET check_in = NOW(), status = 'present'
                    """, (employee_id, today))
                elif action == 'check_out':
                    cur.execute("""
                        UPDATE attendance 
                        SET check_out = NOW()
                        WHERE employee_id = %s AND date = %s AND deleted_at IS NULL
                    """, (employee_id, today))
                
                conn.commit()
                self.db.log_action(employee_id, f"attendance_{action}", {"date": str(today)})
                
            return ToolResult(success=True, data={"message": f"Attendance {action} recorded for {employee_id}"})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Attendance marking failed: {e}")
    
    async def _attendance_report(self, start_date: str = None, end_date: str = None, **kwargs) -> ToolResult:
        """Generate attendance report"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                query = """
                    SELECT e.name, e.employee_id, a.date, a.check_in, a.check_out, a.status
                    FROM employees e
                    LEFT JOIN attendance a ON e.employee_id = a.employee_id AND a.deleted_at IS NULL
                    WHERE e.deleted_at IS NULL
                """
                params = []
                
                if start_date:
                    query += " AND a.date >= %s"
                    params.append(start_date)
                if end_date:
                    query += " AND a.date <= %s"
                    params.append(end_date)
                
                query += " ORDER BY a.date DESC, e.name"
                
                cur.execute(query, params)
                results = cur.fetchall()
                
            return ToolResult(success=True, data={
                'attendance_records': [dict(r) for r in results]
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Attendance report failed: {e}")
    
    async def _attendance_stats(self, **kwargs) -> ToolResult:
        """Get attendance statistics"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT(CASE WHEN status = 'present' THEN 1 END) as present_count,
                        COUNT(CASE WHEN status = 'absent' THEN 1 END) as absent_count,
                        COUNT(CASE WHEN status = 'late' THEN 1 END) as late_count
                    FROM attendance 
                    WHERE deleted_at IS NULL 
                    AND date >= CURRENT_DATE - INTERVAL '30 days'
                """)
                
                stats = dict(cur.fetchone())
                
            return ToolResult(success=True, data=stats)
            
        except Exception as e:
            return ToolResult(success=False, error=f"Attendance stats failed: {e}")
    
    async def _attendance_my_summary(self, employee_id: str, **kwargs) -> ToolResult:
        """Get attendance summary for specific employee"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_days,
                        COUNT(CASE WHEN status = 'present' THEN 1 END) as present_days,
                        COUNT(CASE WHEN check_in > TIME '09:00:00' THEN 1 END) as late_days,
                        AVG(EXTRACT(EPOCH FROM (check_out - check_in))/3600) as avg_hours_per_day
                    FROM attendance 
                    WHERE employee_id = %s 
                    AND deleted_at IS NULL 
                    AND date >= CURRENT_DATE - INTERVAL '30 days'
                """, (employee_id,))
                
                summary = dict(cur.fetchone())
                
            return ToolResult(success=True, data=summary)
            
        except Exception as e:
            return ToolResult(success=False, error=f"Attendance summary failed: {e}")
    
    async def _tasks_log(self, task_data: Dict, **kwargs) -> ToolResult:
        """Create or update task"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                if 'id' in task_data:
                    # Update existing task
                    cur.execute("""
                        UPDATE tasks 
                        SET title = %s, description = %s, status = %s, priority = %s, due_date = %s
                        WHERE id = %s AND deleted_at IS NULL
                    """, (
                        task_data.get('title'),
                        task_data.get('description'),
                        task_data.get('status'),
                        task_data.get('priority'),
                        task_data.get('due_date'),
                        task_data['id']
                    ))
                else:
                    # Create new task
                    cur.execute("""
                        INSERT INTO tasks (employee_id, title, description, status, priority, due_date, assigned_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        task_data.get('employee_id'),
                        task_data.get('title'),
                        task_data.get('description'),
                        task_data.get('status', 'pending'),
                        task_data.get('priority', 'medium'),
                        task_data.get('due_date'),
                        task_data.get('assigned_by')
                    ))
                    task_id = cur.fetchone()[0]
                    task_data['id'] = task_id
                
                conn.commit()
                self.db.log_action(kwargs.get('actor', 'system'), 'task_log', task_data)
                
            return ToolResult(success=True, data=task_data)
            
        except Exception as e:
            return ToolResult(success=False, error=f"Task logging failed: {e}")
    
    async def _tasks_my_recent(self, employee_id: str, limit: int = 10, **kwargs) -> ToolResult:
        """Get recent tasks for employee"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT id, title, description, status, priority, due_date, created_at
                    FROM tasks 
                    WHERE employee_id = %s AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (employee_id, limit))
                
                tasks = [dict(r) for r in cur.fetchall()]
                
            return ToolResult(success=True, data={'tasks': tasks})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Recent tasks query failed: {e}")
    
    async def _tasks_report(self, **kwargs) -> ToolResult:
        """Generate tasks report"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT 
                        t.id, t.title, t.status, t.priority, t.due_date, t.created_at,
                        e.name as employee_name, e.employee_id
                    FROM tasks t
                    JOIN employees e ON t.employee_id = e.employee_id
                    WHERE t.deleted_at IS NULL AND e.deleted_at IS NULL
                    ORDER BY t.created_at DESC
                """)
                
                tasks = [dict(r) for r in cur.fetchall()]
                
            return ToolResult(success=True, data={'tasks': tasks})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Tasks report failed: {e}")
    
    async def _company_docs_qa(self, question: str, **kwargs) -> ToolResult:
        """Answer questions using company documents"""
        try:
            # Get OpenAI client
            client = get_openai_client()
            if not client:
                return ToolResult(success=False, error="OpenAI client not available")
            
            # First, search for relevant documents
            search_result = await self._vector_search(question, limit=3)
            if not search_result.success:
                return search_result
            
            context = "\n\n".join([
                result['content'] for result in search_result.data['results']
            ])
            
            # Use OpenAI to answer the question
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an HR assistant. Answer questions based on the provided company documents context."},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
                ]
            )
            
            answer = response.choices[0].message.content
            
            return ToolResult(success=True, data={
                'answer': answer,
                'sources': search_result.data['results']
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"QA failed: {e}")
    
    async def _meet_create(self, meeting_data: Dict, **kwargs) -> ToolResult:
        """Create a meeting"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    INSERT INTO meetings (title, description, start_time, end_time, organizer, attendees, location)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    meeting_data.get('title'),
                    meeting_data.get('description'),
                    meeting_data.get('start_time'),
                    meeting_data.get('end_time'),
                    meeting_data.get('organizer'),
                    json.dumps(meeting_data.get('attendees', [])),
                    meeting_data.get('location')
                ))
                
                meeting_id = cur.fetchone()[0]
                conn.commit()
                self.db.log_action(kwargs.get('actor', 'system'), 'meeting_create', meeting_data)
                
            return ToolResult(success=True, data={'meeting_id': meeting_id, **meeting_data})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Meeting creation failed: {e}")
    
    async def _meet_list(self, **kwargs) -> ToolResult:
        """List upcoming meetings"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT id, title, description, start_time, end_time, organizer, attendees, location
                    FROM meetings 
                    WHERE deleted_at IS NULL 
                    AND start_time >= NOW()
                    ORDER BY start_time ASC
                """)
                
                meetings = [dict(r) for r in cur.fetchall()]
                
            return ToolResult(success=True, data={'meetings': meetings})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Meeting list failed: {e}")
    
    async def _employee_overview(self, **kwargs) -> ToolResult:
        """Get employee overview"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT 
                        employee_id, name, email, role, department, hire_date,
                        (SELECT COUNT(*) FROM tasks WHERE employee_id = e.employee_id AND deleted_at IS NULL) as task_count,
                        (SELECT COUNT(*) FROM attendance WHERE employee_id = e.employee_id AND deleted_at IS NULL AND date >= CURRENT_DATE - INTERVAL '30 days') as attendance_count
                    FROM employees e
                    WHERE e.deleted_at IS NULL
                    ORDER BY e.name
                """)
                
                employees = [dict(r) for r in cur.fetchall()]
                
            return ToolResult(success=True, data={'employees': employees})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Employee overview failed: {e}")
    
    async def _employee_emails(self, **kwargs) -> ToolResult:
        """Get employee email list"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT employee_id, name, email, department
                    FROM employees 
                    WHERE deleted_at IS NULL
                    ORDER BY name
                """)
                
                employees = [dict(r) for r in cur.fetchall()]
                
            return ToolResult(success=True, data={'employees': employees})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Employee emails query failed: {e}")
    
    async def _leave_report(self, **kwargs) -> ToolResult:
        """Generate leave report"""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT 
                        lr.id, lr.type, lr.start_date, lr.end_date, lr.reason, lr.status,
                        e.name as employee_name, e.employee_id
                    FROM leave_requests lr
                    JOIN employees e ON lr.employee_id = e.employee_id
                    WHERE lr.deleted_at IS NULL AND e.deleted_at IS NULL
                    ORDER BY lr.created_at DESC
                """)
                
                leaves = [dict(r) for r in cur.fetchall()]
                
            return ToolResult(success=True, data={'leave_requests': leaves})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Leave report failed: {e}")
    
    async def _visualize(self, chart_type: str, data_source: str, **kwargs) -> ToolResult:
        """Generate chart configuration for frontend"""
        try:
            if data_source == 'attendance':
                with self.db.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT status, COUNT(*) as count
                        FROM attendance 
                        WHERE deleted_at IS NULL 
                        AND date >= CURRENT_DATE - INTERVAL '30 days'
                        GROUP BY status
                    """)
                    data = cur.fetchall()
                
                if chart_type == 'pie':
                    chart_config = {
                        'type': 'pie',
                        'data': {
                            'labels': [d[0].title() for d in data],
                            'datasets': [{
                                'data': [d[1] for d in data],
                                'backgroundColor': ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0']
                            }]
                        },
                        'options': {
                            'responsive': True,
                            'plugins': {
                                'title': {
                                    'display': True,
                                    'text': 'Attendance Distribution (Last 30 Days)'
                                }
                            }
                        }
                    }
                
            elif data_source == 'tasks':
                with self.db.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT status, COUNT(*) as count
                        FROM tasks 
                        WHERE deleted_at IS NULL
                        GROUP BY status
                    """)
                    data = cur.fetchall()
                
                if chart_type == 'bar':
                    chart_config = {
                        'type': 'bar',
                        'data': {
                            'labels': [d[0].title() for d in data],
                            'datasets': [{
                                'label': 'Number of Tasks',
                                'data': [d[1] for d in data],
                                'backgroundColor': '#36A2EB'
                            }]
                        },
                        'options': {
                            'responsive': True,
                            'plugins': {
                                'title': {
                                    'display': True,
                                    'text': 'Tasks by Status'
                                }
                            },
                            'scales': {
                                'y': {
                                    'beginAtZero': True
                                }
                            }
                        }
                    }
            
            return ToolResult(success=True, data={'chart_config': chart_config})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Visualization failed: {e}")

# Global router instance
router = ToolRouter()

class MCPServer:
    """MCP Server implementation"""
    
    def __init__(self):
        self.router = router
    
    def get_tools(self):
        """Return available tools"""
        return [{
            "name": "action",
            "description": "Generic tool that routes to various HR sub-actions",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "description": "The type of action to perform",
                        "enum": [
                            "vector_search", "ingest_documents",
                            "attendance_mark", "attendance_report", "attendance_stats", "attendance_my_summary",
                            "tasks_log", "tasks_my_recent", "tasks_report",
                            "company_docs_qa", "meet_create", "meet_list",
                            "employee_overview", "employee_emails", "leave_report",
                            "visualize"
                        ]
                    }
                },
                "required": ["action_type"],
                "additionalProperties": True
            }
        }]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Handle tool calls"""
        if name != "action":
            return ToolResult(success=False, error="Unknown tool")
        
        action_type = arguments.pop('action_type')
        return await self.router.route_action(action_type, **arguments)

# Global server instance
mcp_server = MCPServer()

if __name__ == "__main__":
    print("MCP Server for HR Agent")
    print("Available tools:", mcp_server.get_tools())