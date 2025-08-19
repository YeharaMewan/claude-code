#!/usr/bin/env python3
"""
Integration test script for HR Agent application
Tests all major components and endpoints
"""
import asyncio
import requests
import json
import time
import sys
import os

# Add server path to import our modules
sys.path.append('./server')

def test_database_connection():
    """Test database connection"""
    print("Testing database connection...")
    try:
        from server.db.migrate import check_connection
        if check_connection():
            print("✓ Database connection successful")
            return True
        else:
            print("✗ Database connection failed")
            return False
    except Exception as e:
        print(f"✗ Database connection error: {e}")
        return False

def test_mcp_server():
    """Test MCP server functionality"""
    print("Testing MCP server...")
    try:
        from server.mcp_server import mcp_server
        
        # Test getting tools
        tools = mcp_server.get_tools()
        if tools and len(tools) > 0 and tools[0]['name'] == 'action':
            print("✓ MCP server tools available")
            return True
        else:
            print("✗ MCP server tools not found")
            return False
    except Exception as e:
        print(f"✗ MCP server error: {e}")
        return False

def test_react_planner():
    """Test ReAct planner"""
    print("Testing ReAct planner...")
    try:
        from server.agents.planner import GuardrailChecker
        
        checker = GuardrailChecker()
        
        # Test destructive action detection
        is_destructive = checker.is_destructive_action('delete_employee', {})
        has_confirmation = checker.check_user_confirmation('yes, delete it')
        
        if is_destructive and has_confirmation:
            print("✓ ReAct planner guardrails working")
            return True
        else:
            print("✗ ReAct planner guardrails failed")
            return False
    except Exception as e:
        print(f"✗ ReAct planner error: {e}")
        return False

def test_api_health():
    """Test API health endpoint"""
    print("Testing API health endpoint...")
    try:
        response = requests.get('http://localhost:5000/api/health', timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'healthy':
                print("✓ API health check passed")
                return True
            else:
                print(f"✗ API unhealthy: {data}")
                return False
        else:
            print(f"✗ API health check failed: {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"✗ API health check error: {e}")
        return False

def test_chat_endpoint():
    """Test chat endpoint"""
    print("Testing chat endpoint...")
    try:
        response = requests.post(
            'http://localhost:5000/api/chat',
            json={'message': 'Hello, test message'},
            timeout=30,
            stream=True
        )
        
        if response.status_code == 200:
            # Check for SSE stream
            content = response.text
            if 'data:' in content:
                print("✓ Chat endpoint streaming response")
                return True
            else:
                print("✗ Chat endpoint not streaming")
                return False
        else:
            print(f"✗ Chat endpoint failed: {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"✗ Chat endpoint error: {e}")
        return False

def test_web_frontend():
    """Test web frontend"""
    print("Testing web frontend...")
    try:
        response = requests.get('http://localhost:3000', timeout=10)
        if response.status_code == 200:
            content = response.text
            if 'HR Agent' in content and 'Chat Interface' in content:
                print("✓ Web frontend accessible")
                return True
            else:
                print("✗ Web frontend content invalid")
                return False
        else:
            print(f"✗ Web frontend failed: {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"✗ Web frontend error: {e}")
        return False

def run_integration_tests():
    """Run all integration tests"""
    print("=" * 50)
    print("HR AGENT INTEGRATION TESTS")
    print("=" * 50)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("MCP Server", test_mcp_server),
        ("ReAct Planner", test_react_planner),
        ("API Health", test_api_health),
        ("Chat Endpoint", test_chat_endpoint),
        ("Web Frontend", test_web_frontend),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n[{passed + 1}/{total}] {test_name}")
        if test_func():
            passed += 1
        time.sleep(1)  # Brief pause between tests
    
    print("\n" + "=" * 50)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 50)
    
    if passed == total:
        print("🎉 All tests passed! The HR Agent application is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the logs and fix issues.")
        return False

def main():
    """Main test function"""
    if len(sys.argv) > 1 and sys.argv[1] == '--wait-for-services':
        print("Waiting for services to start...")
        time.sleep(30)  # Wait for Docker services to be ready
    
    success = run_integration_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()