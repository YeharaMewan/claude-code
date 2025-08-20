'use client';

import React, { useEffect, useRef } from 'react';

interface MarkdownRendererProps {
  content: string;
}

// Simple markdown parsing utility
const parseMarkdown = (content: string): string => {
  if (!content) return '';

  return content
    // Headers
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    
    // Bold
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/__(.*?)__/gim, '<strong>$1</strong>')
    
    // Italic
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/_(.*?)_/gim, '<em>$1</em>')
    
    // Code blocks
    .replace(/```([\s\S]*?)```/gim, '<pre><code>$1</code></pre>')
    .replace(/`(.*?)`/gim, '<code>$1</code>')
    
    // Line breaks
    .replace(/\n\n/gim, '</p><p>')
    .replace(/\n/gim, '<br>')
    
    // Wrap in paragraphs
    .replace(/^(.*)$/gim, '<p>$1</p>')
    
    // Clean up extra paragraphs
    .replace(/<p><\/p>/gim, '')
    .replace(/<p>(<h[1-6]>.*<\/h[1-6]>)<\/p>/gim, '$1')
    .replace(/<p>(<pre><code>[\s\S]*?<\/code><\/pre>)<\/p>/gim, '$1');
};

const addCopyButtons = (container: HTMLElement) => {
  const codeBlocks = container.querySelectorAll('pre');
  codeBlocks.forEach(pre => {
    // Remove existing copy button if any
    const existingBtn = pre.querySelector('.copy-btn');
    if (existingBtn) {
      existingBtn.remove();
    }

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = 'Copy';
    copyBtn.onclick = (e) => {
      e.preventDefault();
      const code = pre.querySelector('code');
      if (code) {
        navigator.clipboard.writeText(code.textContent || '').then(() => {
          copyBtn.textContent = 'Copied!';
          setTimeout(() => {
            copyBtn.textContent = 'Copy';
          }, 2000);
        }).catch(() => {
          copyBtn.textContent = 'Failed';
          setTimeout(() => {
            copyBtn.textContent = 'Copy';
          }, 2000);
        });
      }
    };
    pre.appendChild(copyBtn);
  });
};

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      addCopyButtons(containerRef.current);
    }
  }, [content]);

  return (
    <div 
      ref={containerRef}
      dangerouslySetInnerHTML={{ 
        __html: parseMarkdown(content) 
      }} 
    />
  );
};