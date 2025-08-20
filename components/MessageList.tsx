'use client';

import React from 'react';
import { Message, StreamEvent } from '@/hooks/useChat';
import { MessageComponent } from './MessageComponent';
import { TypingIndicator } from './TypingIndicator';
import { StreamingIndicator } from './StreamingIndicator';

interface MessageListProps {
  messages: Message[];
  streamEvents: StreamEvent[];
  isLoading: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  streamEvents,
  isLoading,
}) => {
  return (
    <>
      {messages.map((message) => (
        <MessageComponent key={message.id} message={message} />
      ))}
      
      {isLoading && (
        <>
          <StreamingIndicator events={streamEvents} />
          <TypingIndicator />
        </>
      )}
    </>
  );
};