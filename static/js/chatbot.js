// Sanjaya Chatbot JavaScript
class SanjayaChatbot {
    constructor() {
        this.isOpen = false;
        this.isLoading = false;
        this.chatHistory = [];
        this.initializeElements();
        this.bindEvents();
        this.addWelcomeMessage();
    }

    initializeElements() {
        this.chatbotIcon = document.getElementById('chatbot-icon');
        this.chatbotContainer = document.getElementById('chatbot-container');
        this.chatbotHeader = document.getElementById('chatbot-header');
        this.chatbotBody = document.getElementById('chatbot-body');
        this.chatbotInput = document.getElementById('chatbot-input');
        this.chatbotSendBtn = document.getElementById('chatbot-send-btn');
        this.chatbotCloseBtn = document.getElementById('chatbot-close-btn');
        this.chatbotMinimizeBtn = document.getElementById('chatbot-minimize-btn');
    }

    bindEvents() {
        this.chatbotIcon.addEventListener('click', () => this.toggleChat());
        this.chatbotCloseBtn.addEventListener('click', () => this.closeChat());
        this.chatbotMinimizeBtn.addEventListener('click', () => this.minimizeChat());
        this.chatbotSendBtn.addEventListener('click', () => this.sendMessage());
        this.chatbotInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (this.isOpen && !this.chatbotContainer.contains(e.target) && !this.chatbotIcon.contains(e.target)) {
                this.closeChat();
            }
        });
    }

    addWelcomeMessage() {
        const welcomeMessage = {
            type: 'bot',
            message: "👋 Hello! I'm here to help you understand Sanjaya – The Observer. Ask me anything about our program, how it works, or which role might be right for you!",
            timestamp: new Date()
        };
        this.chatHistory.push(welcomeMessage);
        this.renderMessage(welcomeMessage);
    }

    toggleChat() {
        if (this.isOpen) {
            this.closeChat();
        } else {
            this.openChat();
        }
    }

    openChat() {
        this.isOpen = true;
        this.chatbotContainer.classList.add('chatbot-open');
        this.chatbotIcon.classList.add('chatbot-icon-active');
        this.chatbotInput.focus();
        this.scrollToBottom();
    }

    closeChat() {
        this.isOpen = false;
        this.chatbotContainer.classList.remove('chatbot-open');
        this.chatbotIcon.classList.remove('chatbot-icon-active');
    }

    minimizeChat() {
        this.closeChat();
    }

    async sendMessage() {
        const message = this.chatbotInput.value.trim();
        if (!message || this.isLoading) return;

        // Add user message
        const userMessage = {
            type: 'user',
            message: message,
            timestamp: new Date()
        };
        this.chatHistory.push(userMessage);
        this.renderMessage(userMessage);
        this.chatbotInput.value = '';
        this.setLoading(true);

        try {
            const response = await fetch('/api/chatbot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message })
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            
            // Add bot response
            const botMessage = {
                type: 'bot',
                message: data.response,
                timestamp: new Date()
            };
            this.chatHistory.push(botMessage);
            this.renderMessage(botMessage);

        } catch (error) {
            console.error('Chatbot error:', error);
            const errorMessage = {
                type: 'bot',
                message: "I'm sorry, I'm having trouble connecting right now. Please try again in a moment, or feel free to contact our support team directly.",
                timestamp: new Date()
            };
            this.chatHistory.push(errorMessage);
            this.renderMessage(errorMessage);
        } finally {
            this.setLoading(false);
        }
    }

    renderMessage(messageObj) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chatbot-message chatbot-message-${messageObj.type}`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'chatbot-message-content';
        messageContent.textContent = messageObj.message;
        
        const messageTime = document.createElement('div');
        messageTime.className = 'chatbot-message-time';
        messageTime.textContent = this.formatTime(messageObj.timestamp);
        
        messageDiv.appendChild(messageContent);
        messageDiv.appendChild(messageTime);
        
        this.chatbotBody.appendChild(messageDiv);
        this.scrollToBottom();
    }

    setLoading(loading) {
        this.isLoading = loading;
        this.chatbotSendBtn.disabled = loading;
        this.chatbotInput.disabled = loading;
        
        if (loading) {
            this.chatbotSendBtn.innerHTML = '<div class="chatbot-loading"></div>';
        } else {
            this.chatbotSendBtn.innerHTML = 'Send';
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatbotBody.scrollTop = this.chatbotBody.scrollHeight;
        }, 100);
    }

    formatTime(timestamp) {
        return timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

// Initialize chatbot when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new SanjayaChatbot();
});

