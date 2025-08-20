'use client';

import React from 'react';

interface WelcomeScreenProps {
  onSuggestionClick: (suggestion: string) => void;
}

const suggestions = [
  {
    title: '✍️ Writing',
    description: 'Help me write a professional email',
    prompt: 'Help me write a professional email'
  },
  {
    title: '🧠 Learning',
    description: 'Explain quantum computing in simple terms',
    prompt: 'Explain quantum computing in simple terms'
  },
  {
    title: '📋 Planning',
    description: 'Help me plan a productive day',
    prompt: 'Help me plan a productive day'
  },
  {
    title: '💻 Coding',
    description: 'Review my code for best practices',
    prompt: 'Review my code for best practices'
  }
];

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ onSuggestionClick }) => {
  return (
    <div className="welcome-container">
      <h1 className="welcome-title">ChatGPT</h1>
      <p className="welcome-subtitle">How can I help you today?</p>
      
      <div className="suggestions-grid">
        {suggestions.map((suggestion, index) => (
          <div
            key={index}
            className="suggestion-card"
            onClick={() => onSuggestionClick(suggestion.prompt)}
          >
            <div className="suggestion-title">{suggestion.title}</div>
            <div className="suggestion-description">{suggestion.description}</div>
          </div>
        ))}
      </div>
    </div>
  );
};