'use client';

import React from 'react';
import { Message } from '@/hooks/useChat';
import { MarkdownRenderer } from './MarkdownRenderer';

interface MessageComponentProps {
  message: Message;
}

export const MessageComponent: React.FC<MessageComponentProps> = ({ message }) => {
  return (
    <div className={`message ${message.role} fade-in`}>
      <div className="message-content">
        <div className="message-avatar">
          {message.role === 'user' ? (
            'U'
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7V17L12 22L22 17V7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M12 22V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 7L12 12L22 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </div>
        
        <div className="message-text">
          <MarkdownRenderer content={message.content} />
        </div>
      </div>
    </div>
  );
};