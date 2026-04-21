import React, { useState, useRef, useEffect } from 'react';
import { api, readSSEStream } from '../services/api.js';

export function Chat({ studentId, courseId, onNewMessage }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');
    setError('');
    setLoading(true);

    // Add user message to chat
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    try {
      // Start streaming response
      const response = await api.chatStream(studentId, courseId, userMessage);

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      let assistantMessage = '';
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

      for await (const chunk of readSSEStream(response)) {
        assistantMessage += chunk;
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: assistantMessage };
          return updated;
        });
      }

      onNewMessage?.();
    } catch (err) {
      setError(`Error: ${err.message}`);
      console.error('Chat error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>No messages yet. Start by asking a question about your course materials!</p>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`message message-${msg.role}`}>
            <div className="message-role">{msg.role === 'user' ? 'You' : 'Study Buddy'}</div>
            <div className="message-content">{msg.content}</div>
          </div>
        ))}
        {loading && (
          <div className="message message-assistant">
            <div className="message-role">Study Buddy</div>
            <div className="message-content typing">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {error && <div className="error-message">{error}</div>}

      <form onSubmit={handleSendMessage} className="chat-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your course..."
          disabled={loading}
          className="chat-input"
        />
        <button type="submit" disabled={loading} className="send-button">
          {loading ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  );
}
