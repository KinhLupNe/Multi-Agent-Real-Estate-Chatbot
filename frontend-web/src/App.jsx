import { useState } from 'react';
import { MessageSquare, BarChart2 } from 'lucide-react';
import ChatLayout from './components/Chat/ChatLayout';
import DashboardLayout from './components/Dashboard/DashboardLayout';

function App() {
  const [activeTab, setActiveTab] = useState('chat');

  return (
    <div className="app-container">
      <header className="app-header glass">
        <div className="app-title">
          <MessageSquare size={24} />
          BDS Analytics
        </div>
        <div className="app-tabs">
          <button 
            className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquare size={18} />
            Chatbot
          </button>
          <button 
            className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <BarChart2 size={18} />
            Dashboard
          </button>
        </div>
      </header>
      
      <main className="app-content">
        {activeTab === 'chat' && <ChatLayout />}
        {activeTab === 'dashboard' && <DashboardLayout />}
      </main>
    </div>
  );
}

export default App;
