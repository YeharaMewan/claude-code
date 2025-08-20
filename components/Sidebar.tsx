'use client';

import React from 'react';
import { ChatSession } from '@/hooks/useChat';

interface SidebarProps {
  sessions: ChatSession[];
  currentSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClearAll: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  currentSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClearAll,
}) => {
  const sortedSessions = sessions
    .sort((a, b) => new Date(b.lastActivity).getTime() - new Date(a.lastActivity).getTime())
    .slice(0, 20);

  const handleDeleteSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this chat? This action cannot be undone.')) {
      onDeleteSession(sessionId);
    }
  };

  const handleClearAll = () => {
    const chatCount = sessions.length;
    if (chatCount === 0) {
      alert('No chats to clear.');
      return;
    }
    
    if (confirm(`Are you sure you want to delete all ${chatCount} chat(s)? This action cannot be undone.`)) {
      onClearAll();
    }
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <button className="new-chat-btn" onClick={onNewChat}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 5V19M5 12H19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          New chat
        </button>
        <button className="clear-all-btn" onClick={handleClearAll}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 6H5H21M8 6V4C8 3.44772 8.44772 3 9 3H15C15.5523 3 16 3.44772 16 4V6M19 6V20C19 20.5523 18.4477 21 18 21H6C5.44772 21 5 20.5523 5 20V6H19Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Clear all chats
        </button>
      </div>
      
      <div className="sidebar-content">
        {sortedSessions.map((session) => (
          <div
            key={session.id}
            className={`chat-item ${session.id === currentSessionId ? 'active' : ''}`}
          >
            <div 
              className="chat-item-content"
              onClick={() => onSelectSession(session.id)}
            >
              {session.title || 'New Chat'}
            </div>
            <button
              className="chat-item-delete"
              onClick={(e) => handleDeleteSession(e, session.id)}
              title="Delete chat"
            >
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};