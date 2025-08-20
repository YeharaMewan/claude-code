"""
Slim HTTP API Server for HR Agent
Provides chat endpoint using ReAct planner and SSE streaming
"""
import json
import logging
import os
import asyncio
import sys
from datetime import datetime
from typing import Dict, Any, List, AsyncGenerator
import uuid

from flask import Flask, request, Response, jsonify
from flask_cors import CORS

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import our components with error handling
try:
    from agents.planner import plan_and_execute_query, PlannerResult
    from db.migrate import run_migrations, check_connection
    logger.info("Successfully imported components")
except ImportError as e:
    logger.error(f"Failed to import components: {e}")
    sys.exit(1)

app = Flask(__name__)
CORS(app)

# Configuration
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

class ChatSession:
    """Manages chat session state"""
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.messages = []
        self.created_at = datetime.now()
    
    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """Add a message to the session"""
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.messages.append(message)
        return message
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history in OpenAI format"""
        return [
            {'role': msg['role'], 'content': msg['content']} 
            for msg in self.messages
        ]

# In-memory session storage
sessions: Dict[str, ChatSession] = {}

async def stream_chat_response(
    user_message: str, 
    session: ChatSession
) -> AsyncGenerator[str, None]:
    """Stream chat response using Server-Sent Events"""
    
    try:
        # Add user message to session
        session.add_message('user', user_message)
        
        # Get conversation history
        conversation_history = session.get_conversation_history()[:-1]
        
        # Start planning
        yield f"data: {json.dumps({'type': 'status', 'content': 'Processing your request...'})}\n\n"
        
        # Execute ReAct planning
        result: PlannerResult = await plan_and_execute_query(user_message, conversation_history)
        
        if result.success:
            # Stream reasoning steps
            for i, step in enumerate(result.reasoning_steps):
                step_data = {
                    'type': 'reasoning_step',
                    'step_number': i + 1,
                    'thought': step.thought,
                    'action': step.action,
                    'observation': step.observation,
                    'is_final': step.is_final
                }
                yield f"data: {json.dumps(step_data)}\n\n"
                await asyncio.sleep(0.1)
            
            # Stream tool calls if any
            if result.tool_calls:
                for tool_call in result.tool_calls:
                    tool_data = {
                        'type': 'tool_call',
                        'action': tool_call['action'],
                        'result': tool_call['result'],
                        'success': tool_call['success']
                    }
                    yield f"data: {json.dumps(tool_data)}\n\n"
                    await asyncio.sleep(0.1)
            
            # Stream final answer
            yield f"data: {json.dumps({'type': 'final_answer', 'content': result.final_answer})}\n\n"
            
            # Add assistant response to session
            session.add_message('assistant', result.final_answer, {
                'reasoning_steps': len(result.reasoning_steps),
                'tool_calls': len(result.tool_calls),
                'success': True
            })
            
        else:
            # Stream error
            error_response = f"I apologize, but I encountered an error: {result.error or 'Unknown error'}"
            yield f"data: {json.dumps({'type': 'error', 'content': error_response})}\n\n"
            
            # Add error to session
            session.add_message('assistant', error_response, {
                'success': False,
                'error': result.error
            })
        
        # End stream
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        error_msg = f"An unexpected error occurred: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        # Add error to session
        session.add_message('assistant', error_msg, {
            'success': False,
            'error': str(e)
        })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database connection with timeout
        db_healthy = check_connection()
        
        health_status = {
            'status': 'healthy' if db_healthy else 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected' if db_healthy else 'disconnected',
            'version': '1.0.0'
        }
        
        status_code = 200 if db_healthy else 503
        return jsonify(health_status), status_code
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chat endpoint with SSE streaming"""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        user_message = data['message']
        session_id = data.get('session_id')
        
        # Get or create session
        if session_id and session_id in sessions:
            session = sessions[session_id]
        else:
            session = ChatSession(session_id)
            sessions[session.session_id] = session
        
        # Return streaming response
        return Response(
            stream_chat_response(user_message, session),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Session-ID': session.session_id
            }
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sessions/<session_id>/history', methods=['GET'])
def get_session_history(session_id: str):
    """Get chat history for a session"""
    try:
        if session_id not in sessions:
            return jsonify({'error': 'Session not found'}), 404
        
        session = sessions[session_id]
        return jsonify({
            'session_id': session.session_id,
            'created_at': session.created_at.isoformat(),
            'messages': session.messages
        })
        
    except Exception as e:
        logger.error(f"History endpoint error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """List available sessions"""
    try:
        session_list = [
            {
                'session_id': session.session_id,
                'created_at': session.created_at.isoformat(),
                'message_count': len(session.messages),
                'last_activity': session.messages[-1]['timestamp'] if session.messages else session.created_at.isoformat()
            }
            for session in sessions.values()
        ]
        
        # Sort by last activity
        session_list.sort(key=lambda x: x['last_activity'], reverse=True)
        
        return jsonify({'sessions': session_list})
        
    except Exception as e:
        logger.error(f"Sessions endpoint error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    """Delete a session"""
    try:
        if session_id not in sessions:
            return jsonify({'error': 'Session not found'}), 404
        
        del sessions[session_id]
        return jsonify({'message': 'Session deleted'})
        
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

def initialize_app():
    """Initialize the application"""
    logger.info("Initializing HR Agent API server...")
    
    # Check required environment variables
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key or openai_key == 'your_openai_api_key_here':
        logger.error("OPENAI_API_KEY is not set properly")
        sys.exit(1)
    
    # Wait for database to be ready with better logging
    logger.info("Waiting for database to be ready...")
    max_retries = 30
    retry_count = 0
    
    for i in range(max_retries):
        try:
            # Use silent check to avoid spam logs
            if check_connection(silent=True):
                logger.info("Database connection successful")
                break
        except Exception as e:
            pass  # Ignore errors during retries
        
        retry_count += 1
        # Only log every 5th attempt to reduce spam
        if retry_count % 5 == 0:
            logger.info(f"Still waiting for database... attempt {retry_count}/{max_retries}")
        
        if i == max_retries - 1:
            logger.error(f"Database connection failed after {max_retries} attempts")
            sys.exit(1)
        
        import time
        time.sleep(2)
    
    # Run database migrations
    try:
        logger.info("Running database migrations...")
        run_migrations()
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        sys.exit(1)
    
    logger.info("HR Agent API server initialized successfully")

if __name__ == '__main__':
    # Initialize before running
    initialize_app()
    
    logger.info(f"Starting HR Agent API server on port {PORT}")
    
    # Use development server
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=DEBUG,
        threaded=True
    )