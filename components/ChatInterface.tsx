'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useChat, StreamEvent } from '@/hooks/useChat';
import { Sidebar } from './Sidebar';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { WelcomeScreen } from './WelcomeScreen';

export const ChatInterface: React.FC = () => {
  const {
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
  } = useChat();

  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamEvents]);

  // Load chat sessions from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('chatSessions');
      if (saved) {
        try {
          const sessions = JSON.parse(saved);
          // You would need to update the useChat hook to handle this
          // For now, we'll just log it
          console.log('Loaded sessions:', sessions);
        } catch (e) {
          console.error('Error loading sessions:', e);
        }
      }
    }
  }, []);

  const handleSendMessage = async (content: string) => {
    setStreamEvents([]);
    
    await sendMessage(content, (event: StreamEvent) => {
      setStreamEvents(prev => [...prev, event]);
    });
  };

  const handleSuggestionClick = (suggestion: string) => {
    handleSendMessage(suggestion);
  };

  const showWelcome = messages.length === 0;

  return (
    <div className="app-container">
      <Sidebar
        sessions={Object.values(chatSessions)}
        currentSessionId={currentSessionId}
        onNewChat={startNewChat}
        onSelectSession={loadSession}
        onDeleteSession={deleteSession}
        onClearAll={clearAllSessions}
      />
      
      <div className="main-content">
        <div className="chat-container">
          <div className="messages-container">
            {showWelcome ? (
              <WelcomeScreen onSuggestionClick={handleSuggestionClick} />
            ) : (
              <MessageList 
                messages={messages} 
                streamEvents={streamEvents}
                isLoading={isLoading}
              />
            )}
            <div ref={messagesEndRef} />
          </div>

          <ChatInput
            onSendMessage={handleSendMessage}
            disabled={isLoading}
            onStop={stopGeneration}
          />
        </div>
      </div>
    </div>
  );
};