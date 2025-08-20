"""
ReAct Planner for HR Agent
Implements Reason -> Act -> Observe loop with guardrail protection
"""
import json
import logging
import re
import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client with proper error handling
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
class ReasoningStep:
    """A single step in the ReAct reasoning process"""
    thought: str
    action: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    is_final: bool = False

@dataclass
class PlannerResult:
    """Result from the planner execution"""
    success: bool
    final_answer: str
    reasoning_steps: List[ReasoningStep]
    tool_calls: List[Dict[str, Any]]
    error: Optional[str] = None

class GuardrailChecker:
    """Checks for destructive actions and required confirmations"""
    
    DESTRUCTIVE_ACTIONS = {
        'delete_document', 'delete_employee', 'delete_task', 'delete_meeting',
        'remove_employee', 'terminate_employee', 'cancel_meeting', 'remove_task'
    }
    
    CONFIRMATION_PHRASES = {
        'yes, delete it', 'force=true', 'confirm delete', 'yes delete', 'delete confirmed'
    }
    
    @classmethod
    def is_destructive_action(cls, action_type: str, action_args: Dict[str, Any]) -> bool:
        """Check if an action is potentially destructive"""
        if action_type in cls.DESTRUCTIVE_ACTIONS:
            return True
        
        # Check for update actions that might be destructive
        if action_type in ['tasks_log', 'attendance_mark'] and action_args.get('status') == 'deleted':
            return True
            
        return False
    
    @classmethod
    def check_user_confirmation(cls, user_message: str) -> bool:
        """Check if user message contains explicit confirmation"""
        user_message_lower = user_message.lower()
        return any(phrase in user_message_lower for phrase in cls.CONFIRMATION_PHRASES)
    
    @classmethod
    def get_confirmation_message(cls, action_type: str) -> str:
        """Get message explaining required confirmation"""
        return (
            f"The action '{action_type}' is potentially destructive. "
            "To proceed, please confirm with one of these phrases: "
            f"{', '.join(repr(phrase) for phrase in cls.CONFIRMATION_PHRASES)}"
        )

class ReActPlanner:
    """ReAct (Reason-Act-Observe) planner with guardrail protection"""
    
    def __init__(self, mcp_server):
        self.mcp_server = mcp_server
        self.guardrail_checker = GuardrailChecker()
        self.max_reasoning_steps = 20  # Increased from 10
        self.max_timeout_seconds = 60  # 1 minute timeout
        
        # Simple conversational patterns that don't need ReAct
        self.simple_patterns = [
            r'^(hi|hello|hey)$',
            r'^(good morning|good afternoon|good evening)$',
            r'^(how are you|how\'s it going)$',
            r'^(thanks|thank you|bye|goodbye)$',
            r'^(what can you do|help|what do you do)$',
        ]
        
        self.system_prompt = """You are an HR Agent assistant using the ReAct (Reason-Act-Observe) framework.

Your task is to help with HR-related queries by reasoning through problems step by step.

Available actions (via the 'action' tool):
- vector_search: Search company documents
- ingest_documents: Add new documents to the system
- attendance_mark: Mark employee attendance (check_in/check_out)
- attendance_report: Generate attendance reports
- attendance_stats: Get attendance statistics
- attendance_my_summary: Get attendance summary for an employee
- tasks_log: Create or update tasks
- tasks_my_recent: Get recent tasks for an employee  
- tasks_report: Generate tasks report
- company_docs_qa: Answer questions using company documents
- meet_create: Create meetings
- meet_list: List upcoming meetings
- employee_overview: Get employee overview
- employee_emails: Get employee email addresses
- leave_report: Generate leave reports
- visualize: Generate chart configurations (pie/bar charts)

IMPORTANT REASONING FORMAT:
For each step, you must follow this exact format:
Thought: [Your reasoning about what to do next]
Action: [The action to take, or "Final Answer" if done]
Observation: [What you learned from the action]

GUARDRAIL RULES:
1. Before ANY potentially destructive action, you must check if the user provided explicit confirmation
2. If no confirmation is provided for a destructive action, you must:
   - Execute a soft delete (if applicable)
   - Immediately restore it
   - Explain why confirmation is required
3. Never proceed with destructive actions without explicit user confirmation

Continue reasoning until you have a complete answer for the user."""

    def _is_simple_conversational_message(self, message: str) -> bool:
        """Check if message is a simple greeting/conversation that doesn't need ReAct"""
        message_clean = message.lower().strip()
        return any(re.match(pattern, message_clean, re.IGNORECASE) for pattern in self.simple_patterns)
    
    def _get_simple_response(self, message: str) -> str:
        """Generate appropriate response for simple conversational messages"""
        message_clean = message.lower().strip()
        
        if re.match(r'^(hi|hello|hey)$', message_clean):
            return "Hello! I'm your HR assistant. I can help you with employee information, attendance tracking, task management, meetings, and accessing company documents. What can I help you with today?"
        
        elif re.match(r'^(good morning|good afternoon|good evening)$', message_clean):
            return "Good to see you! I'm here to help with all your HR-related needs. How can I assist you today?"
        
        elif re.match(r'^(how are you|how\'s it going)$', message_clean):
            return "I'm doing well and ready to help! I can assist with employee records, attendance, tasks, meetings, and company documents. What would you like to work on?"
        
        elif re.match(r'^(thanks|thank you|bye|goodbye)$', message_clean):
            return "You're welcome! Feel free to ask me anything HR-related anytime. Have a great day!"
        
        elif re.match(r'^(what can you do|help|what do you do)$', message_clean):
            return """I'm your HR assistant! Here's what I can help you with:

📋 **Employee Management**: View employee information and overviews
⏰ **Attendance**: Mark attendance, generate reports, and view statistics  
✅ **Task Management**: Create tasks, view recent tasks, and generate reports
📅 **Meetings**: Schedule meetings and view upcoming meetings
📄 **Company Documents**: Search documents and get answers from company knowledge base
📊 **Reports & Analytics**: Generate various HR reports and visualizations
🏖️ **Leave Management**: Access leave reports and information

Just ask me something like "Show me my recent tasks" or "Mark my attendance" and I'll help you out!"""
        
        return "I'm here to help with your HR needs! What can I assist you with?"

    async def plan_and_execute(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> PlannerResult:
        """Main planning and execution method"""
        try:
            # Check for simple conversational messages first
            if self._is_simple_conversational_message(user_message):
                logger.info("Detected simple conversational message, bypassing ReAct")
                simple_response = self._get_simple_response(user_message)
                return PlannerResult(
                    success=True,
                    final_answer=simple_response,
                    reasoning_steps=[ReasoningStep(thought="Simple conversational response", is_final=True)],
                    tool_calls=[]
                )
            
            # Check if OpenAI client is available
            client = get_openai_client()
            if not client:
                return PlannerResult(
                    success=False,
                    final_answer="I'm sorry, but the OpenAI service is not properly configured. Please check your API key.",
                    reasoning_steps=[],
                    tool_calls=[],
                    error="OpenAI client not available"
                )
            
            reasoning_steps = []
            tool_calls = []
            start_time = time.time()
            
            # Build conversation context
            messages = [{"role": "system", "content": self.system_prompt}]
            
            if conversation_history:
                messages.extend(conversation_history)
            
            messages.append({"role": "user", "content": user_message})
            
            # Start ReAct loop
            current_reasoning = ""
            step_count = 0
            
            while step_count < self.max_reasoning_steps:
                # Check timeout
                if time.time() - start_time > self.max_timeout_seconds:
                    logger.warning(f"ReAct planning timed out after {self.max_timeout_seconds}s")
                    return self._create_timeout_fallback_response(user_message, reasoning_steps, tool_calls)
                
                step_count += 1
                logger.info(f"ReAct step {step_count}/{self.max_reasoning_steps}")
                
                try:
                    # Get reasoning from LLM
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=messages + [{"role": "assistant", "content": current_reasoning}],
                        temperature=0.1,
                        max_tokens=500  # Limit response length
                    )
                    
                    reasoning_text = response.choices[0].message.content
                    current_reasoning += reasoning_text
                    
                    # Parse the reasoning step
                    step = self._parse_reasoning_step(reasoning_text)
                    reasoning_steps.append(step)
                    
                    # Check for final answer with improved detection
                    if step.is_final or self._should_stop_reasoning(current_reasoning, step_count):
                        # Extract final answer
                        final_answer = self._extract_final_answer(reasoning_text, current_reasoning)
                        return PlannerResult(
                            success=True,
                            final_answer=final_answer,
                            reasoning_steps=reasoning_steps,
                            tool_calls=tool_calls
                        )
                    
                    if step.action:
                        # Execute the action with guardrail check
                        observation = await self._execute_action_with_guardrails(
                            step.action, user_message, tool_calls
                        )
                        step.observation = observation
                        
                        # Add observation to the conversation
                        current_reasoning += f"\nObservation: {observation}\n"
                        
                    else:
                        # No action, continue reasoning
                        current_reasoning += "\n"
                        
                except Exception as e:
                    logger.error(f"Error in reasoning step {step_count}: {e}")
                    # Return graceful fallback instead of continuing
                    return self._create_error_fallback_response(user_message, reasoning_steps, tool_calls, str(e))
            
            # If we've reached max steps, provide helpful fallback
            return self._create_max_steps_fallback_response(user_message, reasoning_steps, tool_calls)
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return PlannerResult(
                success=False,
                final_answer=f"I encountered an error while processing your request. Please try again. Error: {str(e)}",
                reasoning_steps=[],
                tool_calls=[],
                error=str(e)
            )
    
    def _should_stop_reasoning(self, current_reasoning: str, step_count: int) -> bool:
        """Determine if reasoning should stop before reaching max steps"""
        reasoning_lower = current_reasoning.lower()
        
        # Stop if we see completion indicators
        completion_indicators = [
            "task completed", "final answer", "conclusion", "done", "completed successfully",
            "here's the information", "based on my search", "according to the documents"
        ]
        
        if any(indicator in reasoning_lower for indicator in completion_indicators):
            return True
        
        # Stop if we're repeating the same actions
        if step_count >= 5:
            action_pattern = re.findall(r'Action:\s*(\w+)', current_reasoning)
            if len(action_pattern) >= 3:
                # If last 3 actions are the same, we're likely stuck
                recent_actions = action_pattern[-3:]
                if len(set(recent_actions)) == 1:
                    logger.warning("Detected repeated actions, stopping reasoning")
                    return True
        
        # Stop if reasoning is getting very long without progress
        if len(current_reasoning) > 5000:  # Very long reasoning
            return True
            
        return False
    
    def _create_timeout_fallback_response(self, user_message: str, reasoning_steps: List[ReasoningStep], tool_calls: List[Dict[str, Any]]) -> PlannerResult:
        """Create response when timeout is reached"""
        summary = self._summarize_progress(reasoning_steps, tool_calls)
        
        fallback_answer = f"""I'm working on your request: "{user_message}"

{summary}

I need a bit more time to complete this fully. Could you please:
- Try asking a more specific question, or  
- Break your request into smaller parts

I'm here to help and will do my best to assist you!"""
        
        return PlannerResult(
            success=True,
            final_answer=fallback_answer,
            reasoning_steps=reasoning_steps,
            tool_calls=tool_calls
        )
    
    def _create_error_fallback_response(self, user_message: str, reasoning_steps: List[ReasoningStep], tool_calls: List[Dict[str, Any]], error: str) -> PlannerResult:
        """Create response when an error occurs"""
        summary = self._summarize_progress(reasoning_steps, tool_calls)
        
        fallback_answer = f"""I encountered an issue while processing your request: "{user_message}"

{summary}

I'd be happy to help you in a different way. Please try:
- Rephrasing your question
- Being more specific about what you need
- Asking about a different HR topic

What else can I help you with?"""
        
        return PlannerResult(
            success=True,
            final_answer=fallback_answer,
            reasoning_steps=reasoning_steps,
            tool_calls=tool_calls
        )
    
    def _create_max_steps_fallback_response(self, user_message: str, reasoning_steps: List[ReasoningStep], tool_calls: List[Dict[str, Any]]) -> PlannerResult:
        """Create response when max reasoning steps are reached"""
        summary = self._summarize_progress(reasoning_steps, tool_calls)
        
        fallback_answer = f"""I've been working on your request: "{user_message}"

{summary}

I've gathered some information but need to provide you with what I found so far. For more detailed assistance, please try:
- Being more specific about what you need
- Breaking complex requests into smaller questions
- Asking about one topic at a time

How else can I help you today?"""
        
        return PlannerResult(
            success=True,
            final_answer=fallback_answer,
            reasoning_steps=reasoning_steps,
            tool_calls=tool_calls
        )
    
    def _summarize_progress(self, reasoning_steps: List[ReasoningStep], tool_calls: List[Dict[str, Any]]) -> str:
        """Summarize what progress was made during reasoning"""
        if not reasoning_steps and not tool_calls:
            return "I was just getting started with your request."
        
        summary_parts = []
        
        if tool_calls:
            successful_calls = [call for call in tool_calls if call.get('success')]
            if successful_calls:
                summary_parts.append(f"✅ Successfully completed {len(successful_calls)} action(s)")
            
            failed_calls = [call for call in tool_calls if not call.get('success')]
            if failed_calls:
                summary_parts.append(f"⚠️ Encountered {len(failed_calls)} issue(s)")
        
        if reasoning_steps:
            thoughts = [step.thought for step in reasoning_steps if step.thought]
            if thoughts:
                summary_parts.append(f"🤔 Analyzed {len(thoughts)} reasoning step(s)")
        
        if summary_parts:
            return "Here's what I accomplished:\n" + "\n".join(f"- {part}" for part in summary_parts)
        else:
            return "I was analyzing your request."
    
    def _parse_reasoning_step(self, reasoning_text: str) -> ReasoningStep:
        """Parse a reasoning step from the LLM output"""
        # Improved final answer detection
        final_patterns = [
            r'Final Answer:',
            r'Final Response:',
            r'Answer:',
            r'Conclusion:',
            r'Result:',
            r'Based on.*here.*(?:is|are)',
            r'(?:I can|I will) (?:conclude|answer|respond)',
        ]
        
        if any(re.search(pattern, reasoning_text, re.IGNORECASE) for pattern in final_patterns):
            return ReasoningStep(
                thought="Providing final answer",
                is_final=True
            )
        
        # Extract thought with more flexible patterns
        thought_patterns = [
            r'Thought:\s*(.+?)(?=\n(?:Action:|Observation:)|$)',
            r'Think:\s*(.+?)(?=\n(?:Action:|Observation:)|$)',
            r'Reasoning:\s*(.+?)(?=\n(?:Action:|Observation:)|$)',
        ]
        
        thought = ""
        for pattern in thought_patterns:
            thought_match = re.search(pattern, reasoning_text, re.DOTALL | re.IGNORECASE)
            if thought_match:
                thought = thought_match.group(1).strip()
                break
        
        # If no structured thought found, use the whole text as thought
        if not thought and reasoning_text.strip():
            # Clean up the text and use first sentence/paragraph
            clean_text = re.sub(r'\n+', ' ', reasoning_text.strip())
            thought = clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
        
        # Extract action with more flexible patterns
        action = None
        action_patterns = [
            r'Action:\s*(.+?)(?=\n(?:Thought:|Observation:)|$)',
            r'Act:\s*(.+?)(?=\n(?:Thought:|Observation:)|$)',
            r'Tool:\s*(.+?)(?=\n(?:Thought:|Observation:)|$)',
        ]
        
        for pattern in action_patterns:
            action_match = re.search(pattern, reasoning_text, re.DOTALL | re.IGNORECASE)
            if action_match:
                action_text = action_match.group(1).strip()
                action = self._parse_action(action_text)
                break
        
        return ReasoningStep(thought=thought, action=action)
    
    def _parse_action(self, action_text: str) -> Optional[Dict[str, Any]]:
        """Parse action from text"""
        try:
            # Try to parse as JSON first
            if action_text.startswith('{'):
                return json.loads(action_text)
            
            # Handle structured format like: action_type(arg1=val1, arg2=val2)
            func_match = re.match(r'(\w+)\((.*)\)', action_text)
            if func_match:
                action_type = func_match.group(1)
                args_str = func_match.group(2)
                
                # Parse arguments
                args = {}
                if args_str.strip():
                    # Simple parsing - in production you'd want more robust parsing
                    for arg_pair in args_str.split(','):
                        if '=' in arg_pair:
                            key, value = arg_pair.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"\'')
                            args[key] = value
                
                return {
                    'action_type': action_type,
                    **args
                }
            
            # Handle simple action type
            return {'action_type': action_text}
            
        except Exception as e:
            logger.error(f"Failed to parse action: {action_text}, error: {e}")
            return None
    
    async def _execute_action_with_guardrails(
        self, 
        action: Dict[str, Any], 
        user_message: str, 
        tool_calls: List[Dict[str, Any]]
    ) -> str:
        """Execute action with guardrail protection"""
        
        action_type = action.get('action_type')
        if not action_type:
            return "Error: No action_type specified"
        
        # Check if action is destructive
        if self.guardrail_checker.is_destructive_action(action_type, action):
            # Check for user confirmation
            if not self.guardrail_checker.check_user_confirmation(user_message):
                # No confirmation - perform protective sequence
                return await self._handle_unconfirmed_destructive_action(action, tool_calls)
        
        # Execute the action
        try:
            result = await self.mcp_server.call_tool('action', action)
            tool_calls.append({
                'action': action,
                'result': result.data if result.success else result.error,
                'success': result.success
            })
            
            if result.success:
                return f"Action completed successfully: {json.dumps(result.data, default=str)}"
            else:
                return f"Action failed: {result.error}"
                
        except Exception as e:
            error_msg = f"Action execution failed: {str(e)}"
            tool_calls.append({
                'action': action,
                'result': error_msg,
                'success': False
            })
            return error_msg
    
    async def _handle_unconfirmed_destructive_action(
        self, 
        action: Dict[str, Any], 
        tool_calls: List[Dict[str, Any]]
    ) -> str:
        """Handle destructive action without user confirmation"""
        
        action_type = action.get('action_type')
        
        # Try to perform a soft delete and immediate restore
        try:
            # First, execute the destructive action (soft delete)
            result = await self.mcp_server.call_tool('action', action)
            
            if result.success and result.data and 'id' in result.data:
                # If we have an ID, try to restore it
                resource_id = result.data['id']
                
                # Determine table/resource type for restore
                table_map = {
                    'delete_document': 'documents',
                    'delete_employee': 'employees',
                    'delete_task': 'tasks',
                    'delete_meeting': 'meetings'
                }
                
                table = table_map.get(action_type, 'unknown')
                if table != 'unknown':
                    # Attempt restore
                    restore_result = await self.mcp_server.router.db.restore(table, resource_id)
                    if restore_result:
                        tool_calls.append({
                            'action': action,
                            'result': 'Soft deleted and immediately restored due to lack of confirmation',
                            'success': True
                        })
                        
                        return (
                            f"Action '{action_type}' was attempted but immediately undone because "
                            f"you did not provide explicit confirmation. "
                            f"{self.guardrail_checker.get_confirmation_message(action_type)}"
                        )
            
            # Fallback message
            return (
                f"Action '{action_type}' requires explicit confirmation to proceed. "
                f"{self.guardrail_checker.get_confirmation_message(action_type)}"
            )
            
        except Exception as e:
            return (
                f"Cannot proceed with '{action_type}' without explicit confirmation. "
                f"{self.guardrail_checker.get_confirmation_message(action_type)}"
            )
    
    def _extract_final_answer(self, reasoning_text: str, full_reasoning: str = "") -> str:
        """Extract final answer from reasoning text"""
        # Try multiple patterns for final answer extraction
        final_patterns = [
            r'Final Answer:\s*(.+)',
            r'Answer:\s*(.+)',
            r'Conclusion:\s*(.+)',
            r'Result:\s*(.+)',
            r'Final Response:\s*(.+)',
            r'Based on.*?(?:here|this).*?(?:is|are):\s*(.+)',
        ]
        
        for pattern in final_patterns:
            final_match = re.search(pattern, reasoning_text, re.DOTALL | re.IGNORECASE)
            if final_match:
                answer = final_match.group(1).strip()
                # Clean up the answer
                answer = re.sub(r'\n+', '\n', answer)  # Remove excessive newlines
                answer = answer[:1000]  # Limit length
                return answer if answer else "Task completed."
        
        # If no explicit final answer found, try to extract meaningful content
        if full_reasoning:
            # Look for the last substantial piece of reasoning
            sentences = re.split(r'[.!?]+', full_reasoning)
            meaningful_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
            if meaningful_sentences:
                return meaningful_sentences[-1] + "."
        
        # Fallback to the reasoning text itself (cleaned)
        if reasoning_text:
            clean_text = re.sub(r'\n+', ' ', reasoning_text.strip())
            return clean_text[:500] if clean_text else "Task completed."
        
        return "I've completed processing your request. Let me know if you need anything else!"

# Convenience function for the API server
async def plan_and_execute_query(user_message: str, conversation_history: List[Dict[str, str]] = None) -> PlannerResult:
    """Execute a user query using the ReAct planner"""
    try:
        from mcp_server import mcp_server
        planner = ReActPlanner(mcp_server)
        return await planner.plan_and_execute(user_message, conversation_history)
    except ImportError as e:
        logger.error(f"Failed to import mcp_server: {e}")
        return PlannerResult(
            success=False,
            final_answer="I'm having trouble accessing the backend services. Please try again later.",
            reasoning_steps=[],
            tool_calls=[],
            error=str(e)
        )

if __name__ == "__main__":
    # Test the planner
    import asyncio
    
    async def test_planner():
        print("ReAct Planner test - OpenAI client check")
        
        client = get_openai_client()
        if client:
            print("✅ OpenAI client initialized successfully")
        else:
            print("❌ OpenAI client initialization failed")
        
        # Test guardrail checker
        checker = GuardrailChecker()
        print(f"Is 'delete_employee' destructive? {checker.is_destructive_action('delete_employee', {})}")
        print(f"Has confirmation 'yes, delete it'? {checker.check_user_confirmation('Please yes, delete it now')}")
        print(f"Has confirmation 'maybe delete'? {checker.check_user_confirmation('maybe delete it')}")
    
    asyncio.run(test_planner())