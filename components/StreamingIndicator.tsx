'use client';

import React from 'react';
import { StreamEvent } from '@/hooks/useChat';

interface StreamingIndicatorProps {
  events: StreamEvent[];
}

export const StreamingIndicator: React.FC<StreamingIndicatorProps> = ({ events }) => {
  if (events.length === 0) return null;

  return (
    <div className="message assistant fade-in">
      <div className="message-content">
        <div className="message-avatar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7V17L12 22L22 17V7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M12 22V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 7L12 12L22 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        
        <div className="message-text">
          {events.map((event, index) => (
            <div key={index}>
              {event.type === 'reasoning_step' && (
                <div className="tool-result">
                  <strong>Step {event.step_number}:</strong> {event.thought}
                  {event.action && (
                    <>
                      <br /><strong>Action:</strong> <pre><code>{JSON.stringify(event.action, null, 2)}</code></pre>
                    </>
                  )}
                  {event.observation && (
                    <>
                      <br /><strong>Observation:</strong> {event.observation}
                    </>
                  )}
                </div>
              )}
              
              {event.type === 'tool_call' && (
                <div className={`tool-result ${event.success ? 'success' : 'error'}`}>
                  <strong>Tool Call:</strong>
                  <pre><code>{JSON.stringify(event.action, null, 2)}</code></pre>
                  <strong>Result:</strong>
                  <pre><code>{
                    typeof event.result === 'object' 
                      ? JSON.stringify(event.result, null, 2)
                      : event.result
                  }</code></pre>
                </div>
              )}
              
              {event.type === 'status' && (
                <div className="tool-result">
                  <strong>Status:</strong> {event.content}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};