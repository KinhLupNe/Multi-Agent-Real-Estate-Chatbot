import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Plus, Trash2, Send, Loader2 } from 'lucide-react';
import './Chat.css';

const SAMPLE_PROMPTS = [
  "Mua nhà mặt phố Hoàn Kiếm 50 tỷ",
  "Chung cư 2PN Cầu Giấy 3-5 tỷ",
  "Đất nền ở Đà Nẵng dưới 5 tỷ",
  "Biệt thự liền kề Hoài Đức",
];

const generateId = () => Math.random().toString(36).substr(2, 9);

export default function ChatLayout() {
  const [chats, setChats] = useState({});
  const [activeChatId, setActiveChatId] = useState(null);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Load state from localStorage on init
  useEffect(() => {
    const saved = localStorage.getItem('bds_chat_state');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.chats && parsed.activeChatId) {
          setChats(parsed.chats);
          setActiveChatId(parsed.activeChatId);
          return;
        }
      } catch (e) {}
    }
    // Default empty state
    createNewChat();
  }, []);

  // Save to localStorage when state changes
  useEffect(() => {
    if (activeChatId && Object.keys(chats).length > 0) {
      localStorage.setItem('bds_chat_state', JSON.stringify({ chats, activeChatId }));
    }
  }, [chats, activeChatId]);

  // Smooth scroll to bottom
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chats[activeChatId]?.messages]);

  const createNewChat = () => {
    const id = generateId();
    const newChat = {
      title: `Cuộc hội thoại mới ${new Date().toLocaleString()}`,
      messages: []
    };
    setChats(prev => ({ ...prev, [id]: newChat }));
    setActiveChatId(id);
  };

  const deleteChat = (e, id) => {
    e.stopPropagation();
    const newChats = { ...chats };
    delete newChats[id];
    
    const remainingIds = Object.keys(newChats);
    if (remainingIds.length === 0) {
      const newId = generateId();
      newChats[newId] = { title: `Cuộc hội thoại mới`, messages: [] };
      setActiveChatId(newId);
    } else if (activeChatId === id) {
      setActiveChatId(remainingIds[0]);
    }
    
    setChats(newChats);
  };

  const handleSend = async (text) => {
    if (!text.trim() || isLoading) return;

    const currentChat = chats[activeChatId];
    const newMessages = [...currentChat.messages, { role: 'user', content: text }];
    
    setChats(prev => ({
      ...prev,
      [activeChatId]: { ...prev[activeChatId], messages: newMessages }
    }));
    setInput('');
    setIsLoading(true);

    try {
      // Backend expects the list of messages, with chat_id in the last one
      const payload = newMessages.map((m, idx) => {
        if (idx === newMessages.length - 1) return { ...m, chat_id: activeChatId };
        return m;
      });

      const response = await axios.post('/chat/', payload);
      
      const { real_estate_findings, analytics_and_advice, follow_up_questions } = response.data;
      const relevant_q = follow_up_questions ? follow_up_questions.join('\n') : '';
      const final_response = (real_estate_findings || "") + 
        "\n\n# Phân tích:\n" + (analytics_and_advice || "") + 
        (relevant_q ? "\n\n# Câu hỏi có thể bạn quan tâm:\n" + relevant_q : "");

      const updatedMessages = [...newMessages, { role: 'assistant', content: final_response }];
      
      // Attempt to rename if it's the first exchange
      let title = currentChat.title;
      if (updatedMessages.length === 2) {
        try {
          const nameRes = await axios.post('/chat/name_conversation', updatedMessages);
          if (nameRes.data) title = nameRes.data;
        } catch(e) {}
      }

      setChats(prev => ({
        ...prev,
        [activeChatId]: { ...prev[activeChatId], messages: updatedMessages, title }
      }));

    } catch (error) {
      console.error(error);
      setChats(prev => ({
        ...prev,
        [activeChatId]: { 
          ...prev[activeChatId], 
          messages: [...newMessages, { role: 'assistant', content: '⚠️ Lỗi kết nối tới server. Vui lòng kiểm tra lại backend.' }] 
        }
      }));
    } finally {
      setIsLoading(false);
    }
  };

  const activeMessages = chats[activeChatId]?.messages || [];

  return (
    <div className="chat-container">
      {/* Sidebar */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <button className="chat-new-btn" onClick={createNewChat}>
            <Plus size={18} />
            Cuộc hội thoại mới
          </button>
        </div>
        <div className="chat-list">
          {Object.entries(chats).map(([id, chat]) => (
            <div 
              key={id} 
              className={`chat-item ${id === activeChatId ? 'active' : ''}`}
              onClick={() => setActiveChatId(id)}
            >
              <span className="truncate">{chat.title.length > 30 ? chat.title.substring(0, 30) + '...' : chat.title}</span>
              <Trash2 
                size={16} 
                className="chat-item-delete" 
                onClick={(e) => deleteChat(e, id)} 
              />
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="chat-main">
        {activeMessages.length === 0 ? (
          <div className="empty-state animate-fade-in">
            <div className="empty-icon">🏠</div>
            <h2>Bạn muốn tìm BĐS gì?</h2>
            <p>Mình có thể tìm bài đăng từ database + phân tích thị trường giúp bạn.</p>
            
            <div className="sample-prompts">
              {SAMPLE_PROMPTS.map((prompt, idx) => (
                <button 
                  key={idx} 
                  className="sample-prompt-btn"
                  onClick={() => handleSend(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-messages">
            {activeMessages.map((msg, idx) => (
              <div key={idx} className={`message-bubble message-${msg.role} animate-fade-in`}>
                {/* React-Markdown is ideal here, but simple split for now */}
                {msg.content.split('\n').map((line, i) => (
                  <span key={i}>
                    {line.startsWith('#') ? <strong>{line.replace(/#/g, '')}</strong> : line}
                    <br />
                  </span>
                ))}
              </div>
            ))}
            {isLoading && (
              <div className="message-bubble message-assistant animate-fade-in" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Loader2 size={16} className="lucide-spin" /> Đang suy nghĩ...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Input Area */}
        <div className="chat-input-container">
          <div className="chat-input-box">
            <input 
              type="text" 
              className="chat-input"
              placeholder="Nhập tin nhắn của bạn..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSend(input);
              }}
              disabled={isLoading}
            />
            <button 
              className="chat-send-btn" 
              onClick={() => handleSend(input)}
              disabled={isLoading || !input.trim()}
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
