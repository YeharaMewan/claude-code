# Next.js ChatGPT Interface

This is a modern Next.js implementation of the ChatGPT interface with streaming support, converted from the original HTML/JavaScript version.

## Features

- **Next.js 13+ App Router**: Modern React framework with file-system routing
- **TypeScript**: Full type safety throughout the application
- **Real-time Streaming**: Server-sent events for streaming chat responses
- **Responsive Design**: Works on desktop and mobile devices
- **Session Management**: Chat history with localStorage persistence
- **Markdown Support**: Rich text rendering with syntax highlighting
- **Component-based Architecture**: Modular, reusable React components

## Project Structure

```
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout component
│   ├── page.tsx           # Home page
│   ├── globals.css        # Global styles
│   └── api/
│       └── chat/
│           └── route.ts   # API route for chat streaming
├── components/            # React components
│   ├── ChatInterface.tsx # Main chat interface
│   ├── Sidebar.tsx       # Chat history sidebar
│   ├── MessageList.tsx   # Message display component
│   ├── MessageComponent.tsx # Individual message
│   ├── MarkdownRenderer.tsx # Markdown parsing
│   ├── ChatInput.tsx     # Input form
│   ├── WelcomeScreen.tsx # Welcome/suggestions screen
│   ├── TypingIndicator.tsx # Loading indicator
│   └── StreamingIndicator.tsx # Stream events display
├── hooks/                 # React hooks
│   └── useChat.ts        # Chat management logic
├── next.config.js        # Next.js configuration
├── tsconfig.json         # TypeScript configuration
└── package.json          # Dependencies and scripts
```

## Key Components

### useChat Hook
- Manages chat state, messages, and sessions
- Handles streaming responses with Server-Sent Events
- Provides session management (create, load, delete)
- Local storage integration for persistence

### ChatInterface Component
- Main orchestrator component
- Manages global state and event handling
- Coordinates between sidebar, messages, and input

### Streaming Support
- Real-time message streaming via SSE
- Progressive message updates
- Tool call and reasoning step visualization
- Error handling and recovery

## API Integration

The application connects to the backend via the `/api/chat` endpoint which:
- Proxies requests to the Python backend
- Streams responses back to the client
- Handles session management headers
- Provides error handling and recovery

## Running the Application

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start development server:**
   ```bash
   npm run dev
   ```

3. **Build for production:**
   ```bash
   npm run build
   npm start
   ```

## Environment Setup

Make sure your Python backend is running on `http://localhost:5000` before starting the Next.js development server.

The application will be available at `http://localhost:3000`.

## Key Improvements Over Original

1. **Type Safety**: Full TypeScript integration
2. **Component Architecture**: Modular, maintainable code
3. **Performance**: React optimizations and proper state management
4. **Developer Experience**: Hot reloading, better debugging
5. **Scalability**: Easy to extend with new features
6. **Modern Standards**: Latest React patterns and Next.js features

## Configuration

- **Next.js Config**: Proxy configuration for backend API
- **TypeScript**: Strict type checking enabled
- **Styling**: CSS custom properties for theming
- **Build**: Optimized production builds with static generation