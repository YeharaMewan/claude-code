"""
ReAct Planner for HR Agent
Implements Reason -> Act -> Observe loop with guardrail protection
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from openai import OpenAI
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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
        self.max_reasoning_steps = 10
        
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

    async def plan_and_execute(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> PlannerResult:
        """Main planning and execution method"""
        try:
            reasoning_steps = []
            tool_calls = []
            
            # Build conversation context
            messages = [{"role": "system", "content": self.system_prompt}]
            
            if conversation_history:
                messages.extend(conversation_history)
            
            messages.append({"role": "user", "content": user_message})
            
            # Start ReAct loop
            current_reasoning = ""
            step_count = 0
            
            while step_count < self.max_reasoning_steps:
                step_count += 1
                
                # Get reasoning from LLM
                response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=messages + [{"role": "assistant", "content": current_reasoning}],
                    temperature=0.1
                )
                
                reasoning_text = response.choices[0].message.content
                current_reasoning += reasoning_text
                
                # Parse the reasoning step
                step = self._parse_reasoning_step(reasoning_text)
                reasoning_steps.append(step)
                
                if step.is_final:
                    # Extract final answer
                    final_answer = self._extract_final_answer(reasoning_text)
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
            
            # If we've reached max steps without a final answer
            return PlannerResult(
                success=False,
                final_answer="I was unable to complete the task within the reasoning limit. Please try breaking down your request into smaller parts.",
                reasoning_steps=reasoning_steps,
                tool_calls=tool_calls,
                error="Max reasoning steps exceeded"
            )
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return PlannerResult(
                success=False,
                final_answer=f"An error occurred during planning: {str(e)}",
                reasoning_steps=[],
                tool_calls=[],
                error=str(e)
            )
    
    def _parse_reasoning_step(self, reasoning_text: str) -> ReasoningStep:
        """Parse a reasoning step from the LLM output"""
        # Look for "Final Answer:" pattern
        if "Final Answer:" in reasoning_text:
            return ReasoningStep(
                thought="Providing final answer",
                is_final=True
            )
        
        # Extract thought
        thought_match = re.search(r'Thought:\s*(.+?)(?=\nAction:|$)', reasoning_text, re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else ""
        
        # Extract action
        action = None
        action_match = re.search(r'Action:\s*(.+?)(?=\nObservation:|$)', reasoning_text, re.DOTALL)
        if action_match:
            action_text = action_match.group(1).strip()
            action = self._parse_action(action_text)
        
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
            
            if result.success and 'id' in (result.data or {}):
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
    
    def _extract_final_answer(self, reasoning_text: str) -> str:
        """Extract final answer from reasoning text"""
        final_match = re.search(r'Final Answer:\s*(.+)', reasoning_text, re.DOTALL)
        if final_match:
            return final_match.group(1).strip()
        return "Task completed."

# Convenience function for the API server
async def plan_and_execute_query(user_message: str, conversation_history: List[Dict[str, str]] = None) -> PlannerResult:
    """Execute a user query using the ReAct planner"""
    from ..mcp_server import mcp_server
    planner = ReActPlanner(mcp_server)
    return await planner.plan_and_execute(user_message, conversation_history)

if __name__ == "__main__":
    # Test the planner
    import asyncio
    
    async def test_planner():
        # This would normally import the MCP server
        print("ReAct Planner test - would need MCP server to run")
        
        # Test guardrail checker
        checker = GuardrailChecker()
        print(f"Is 'delete_employee' destructive? {checker.is_destructive_action('delete_employee', {})}")
        print(f"Has confirmation 'yes, delete it'? {checker.check_user_confirmation('Please yes, delete it now')}")
        print(f"Has confirmation 'maybe delete'? {checker.check_user_confirmation('maybe delete it')}")
    
    asyncio.run(test_planner())