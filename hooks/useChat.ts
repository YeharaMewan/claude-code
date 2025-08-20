'use client';

import { useState, useCallback, useRef } from 'react';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
  lastActivity: string;
}

export interface StreamEvent {
  type: 'status' | 'reasoning_step' | 'tool_call' | 'final_answer' | 'error' | 'done';
  content?: string;
  step_number?: number;
  thought?: string;
  action?: any;
  observation?: string;
  result?: any;
  success?: boolean;
}

export const useChat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<Record<string, ChatSession>>({});
  const abortControllerRef = useRef<AbortController | null>(null);

  const addMessage = useCallback((role: 'user' | 'assistant', content: string): Message => {
    const newMessage: Message = {
      id: Date.now().toString(),
      role,
      content,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, newMessage]);
    return newMessage;
  }, []);

  const updateLastMessage = useCallback((content: string) => {
    setMessages(prev => {
      const updated = [...prev];
      if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content,
        };
      }
      return updated;
    });
  }, []);

  const sendMessage = useCallback(async (
    content: string,
    onStreamEvent?: (event: StreamEvent) => void
  ): Promise<void> => {
    if (!content.trim() || isLoading) return;

    // Add user message
    const userMessage = addMessage('user', content);
    
    // Add empty assistant message for streaming
    const assistantMessage = addMessage('assistant', '');
    
    setIsLoading(true);

    // Create abort controller for this request
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          message: content,
          session_id: currentSessionId,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let accumulatedContent = '';

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.trim() === '') continue;
            
            if (line.startsWith('data: ')) {
              try {
                const dataStr = line.slice(6).trim();
                if (dataStr === '') continue;
                
                const data: StreamEvent = JSON.parse(dataStr);
                
                // Call the stream event handler if provided
                onStreamEvent?.(data);
                
                switch (data.type) {
                  case 'final_answer':
                    if (data.content) {
                      accumulatedContent = data.content;
                      updateLastMessage(accumulatedContent);
                    }
                    break;
                  
                  case 'error':
                    updateLastMessage(`Error: ${data.content}`);
                    break;
                  
                  case 'done':
                    // Save to session
                    if (accumulatedContent) {
                      saveToSession(userMessage, { ...assistantMessage, content: accumulatedContent });
                    }
                    return;
                }
              } catch (e) {
                console.error('Error parsing SSE data:', e);
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('Request aborted');
        return;
      }
      
      console.error('Chat error:', error);
      updateLastMessage(`Error: ${error.message}`);
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [currentSessionId, isLoading, addMessage, updateLastMessage]);

  const saveToSession = useCallback((userMessage: Message, assistantMessage: Message) => {
    if (!currentSessionId) return;

    const sessionKey = `session_${currentSessionId}`;
    setChatSessions(prev => {
      const session = prev[sessionKey] || {
        id: currentSessionId,
        title: userMessage.content.substring(0, 50),
        messages: [],
        createdAt: new Date().toISOString(),
        lastActivity: new Date().toISOString(),
      };

      const updatedSession = {
        ...session,
        messages: [...session.messages, userMessage, assistantMessage],
        lastActivity: new Date().toISOString(),
      };

      const updated = {
        ...prev,
        [sessionKey]: updatedSession,
      };

      // Save to localStorage
      if (typeof window !== 'undefined') {
        localStorage.setItem('chatSessions', JSON.stringify(updated));
      }

      return updated;
    });
  }, [currentSessionId]);

  const startNewChat = useCallback(() => {
    setMessages([]);
    setCurrentSessionId(null);
  }, []);

  const loadSession = useCallback((sessionId: string) => {
    const sessionKey = `session_${sessionId}`;
    const session = chatSessions[sessionKey];
    
    if (session) {
      setMessages(session.messages);
      setCurrentSessionId(sessionId);
    }
  }, [chatSessions]);

  const deleteSession = useCallback((sessionId: string) => {
    const sessionKey = `session_${sessionId}`;
    setChatSessions(prev => {
      const updated = { ...prev };
      delete updated[sessionKey];
      
      // Update localStorage
      if (typeof window !== 'undefined') {
        localStorage.setItem('chatSessions', JSON.stringify(updated));
      }
      
      return updated;
    });

    // If deleting current session, start new chat
    if (sessionId === currentSessionId) {
      startNewChat();
    }
  }, [currentSessionId, startNewChat]);

  const clearAllSessions = useCallback(() => {
    setChatSessions({});
    
    // Clear localStorage
    if (typeof window !== 'undefined') {
      localStorage.removeItem('chatSessions');
    }
    
    startNewChat();
  }, [startNewChat]);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  return {
    messages,
    isLoading,
    currentSessionId,
    chatSessions,
    sendMessage,
    startNewChat,
    loadSession,
    deleteSession,
    clearAllSessions,
    stopGeneration,
  };
};