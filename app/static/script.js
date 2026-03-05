document.addEventListener('DOMContentLoaded', () => {
    const chatHistory = document.getElementById('chat-history');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const welcomeMessage = document.querySelector('.welcome-message');
    const historyList = document.getElementById('history-list');
    const newChatBtn = document.getElementById('new-chat-btn');

    let currentSessionId = null;

    // --- Session Management ---

    function initSession() {
        const urlParams = new URLSearchParams(window.location.search);
        const urlSessionId = urlParams.get('session_id');

        if (urlSessionId) {
            currentSessionId = urlSessionId;
        } else {
            // Check if we have an active session in local storage or create new
            let storedSession = localStorage.getItem('gemini_current_session_id');
            if (!storedSession) {
                storedSession = crypto.randomUUID();
                localStorage.setItem('gemini_current_session_id', storedSession);
            }
            currentSessionId = storedSession;
        }

        loadSidebar();
        loadChatHistory(currentSessionId);
    }

    function createNewChat() {
        const newId = crypto.randomUUID();
        localStorage.setItem('gemini_current_session_id', newId);
        // Clear query param if exists
        window.history.pushState({}, '', '/');
        currentSessionId = newId;

        // Reset UI
        chatHistory.innerHTML = '';
        chatHistory.appendChild(welcomeMessage);
        welcomeMessage.style.display = 'block';
        messageInput.value = '';
        messageInput.focus();

        loadSidebar();
    }

    function saveSessionToSidebar(id, title) {
        let sessions = JSON.parse(localStorage.getItem('gemini_sessions') || '[]');
        const existing = sessions.find(s => s.id === id);
        if (!existing) {
            sessions.unshift({ id, title, timestamp: Date.now() });
            localStorage.setItem('gemini_sessions', JSON.stringify(sessions));
            loadSidebar();
        }
    }

    function loadSidebar() {
        if (!historyList) return;
        historyList.innerHTML = '';
        const sessions = JSON.parse(localStorage.getItem('gemini_sessions') || '[]');

        sessions.forEach(session => {
            const div = document.createElement('div');
            div.className = 'history-item';

            const titleSpan = document.createElement('span');
            titleSpan.textContent = session.title;
            titleSpan.style.overflow = 'hidden';
            titleSpan.style.textOverflow = 'ellipsis';
            titleSpan.style.whiteSpace = 'nowrap';
            titleSpan.style.flex = '1';

            const deleteBtn = document.createElement('span');
            deleteBtn.className = 'delete-btn';
            deleteBtn.innerHTML = '×'; // Simple cross
            deleteBtn.title = "Delete Mission";

            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent switching
                if (confirm('Delete this mission?')) {
                    deleteSession(session.id);
                }
            });

            div.appendChild(titleSpan);
            div.appendChild(deleteBtn);

            if (session.id === currentSessionId) {
                div.classList.add('active');
                div.style.backgroundColor = '#282a2c';
                div.style.borderLeft = '3px solid #ffd700';
            }

            div.addEventListener('click', () => {
                switchSession(session.id);
            });
            historyList.appendChild(div);
        });
    }

    async function deleteSession(id) {
        // 1. Call Backend
        try {
            await fetch(`/api/history/${id}`, { method: 'DELETE' });
        } catch (e) {
            console.error("Failed to delete remote history", e);
        }

        // 2. Remove from Local Storage
        let sessions = JSON.parse(localStorage.getItem('gemini_sessions') || '[]');
        sessions = sessions.filter(s => s.id !== id);
        localStorage.setItem('gemini_sessions', JSON.stringify(sessions));

        // 3. UI Update
        if (currentSessionId === id) {
            createNewChat();
        } else {
            loadSidebar();
        }
    }

    async function switchSession(id) {
        if (currentSessionId === id && chatHistory.childElementCount > 1) return; // Already there

        currentSessionId = id;
        localStorage.setItem('gemini_current_session_id', id);

        // Update Sidebar UI
        loadSidebar();

        // Clear Chat UI
        chatHistory.innerHTML = '';

        // Add minimal loading or welcome
        // render the welcome message hidden initially
        chatHistory.appendChild(welcomeMessage);
        welcomeMessage.style.display = 'block';
        welcomeMessage.querySelector('p').textContent = "Loading mission data...";

        await loadChatHistory(id);
    }

    // --- Chat Logic ---

    // Auto-resize textarea
    messageInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') this.style.height = 'auto';
    });

    // Handle Enter key
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewChat);
    }

    async function loadChatHistory(id) {
        try {
            const res = await fetch(`/api/history/${id}`);
            if (res.ok) {
                const history = await res.json();

                welcomeMessage.querySelector('p').textContent = "Awaiting input."; // Reset text

                if (history.length > 0) {
                    welcomeMessage.style.display = 'none';
                    history.forEach(msg => {
                        const text = msg.parts ? msg.parts[0] : "";
                        appendMessage(msg.role, text, false);
                    });
                } else {
                    // History is empty (maybe server restarted)
                    // Keep welcome message visible but maybe indicate no history found?
                    // For now, standard welcome is fine.
                    welcomeMessage.style.display = 'block';
                }
                scrollToBottom();
            }
        } catch (e) {
            console.error("Failed to load history", e);
            welcomeMessage.querySelector('p').textContent = "Connection failed.";
        }
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;

        // Save session title if this is the first message
        const chatContainer = chatHistory.querySelectorAll('.message');
        if (chatContainer.length === 0) {
            // Generate a simplified title from first message
            const title = message.substring(0, 30) + (message.length > 30 ? '...' : '');
            saveSessionToSidebar(currentSessionId, title);
        }

        messageInput.value = '';
        messageInput.style.height = 'auto';
        if (welcomeMessage) welcomeMessage.style.display = 'none';

        appendMessage('user', message);
        const modelMsgId = 'msg-' + Date.now();
        const modelContentDiv = appendMessage('model', 'Thinking...', true, modelMsgId);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: currentSessionId,
                    message: message
                })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Network response was not ok');
            }
            if (!response.body) throw new Error('No readable stream');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedText = "";
            let isFirstChunk = true;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                accumulatedText += chunk;

                if (isFirstChunk) {
                    modelContentDiv.innerHTML = "";
                    isFirstChunk = false;
                }
                modelContentDiv.innerHTML = marked.parse(accumulatedText);
                modelContentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
                scrollToBottom();
            }

        } catch (error) {
            console.error(error);
            modelContentDiv.innerHTML = `<span style="color: #ff8a80;">Error: ${error.message}</span>`;
        }
    }

    function appendMessage(role, text, isStreaming = false, elementId = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;

        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        // Simple Cog Icon for model, U for user
        avatarDiv.innerHTML = role === 'user' ? 'U' : '<svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,13L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.04 4.95,18.95L7.44,17.95C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.68 16.04,18.34 16.56,17.95L19.05,18.95C19.27,19.04 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z" /></svg>';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content markdown-content';
        if (elementId) contentDiv.id = elementId;

        if (role === 'model' && isStreaming && text === 'Thinking...') {
            contentDiv.innerHTML = `<span class="typing-indicator">${text}</span>`;
        } else {
            contentDiv.innerHTML = role === 'model' ? marked.parse(text) : text.replace(/\n/g, '<br>');
        }

        if (role === 'model' && !isStreaming) {
            contentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
        }

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        chatHistory.appendChild(msgDiv);
        scrollToBottom();
        return contentDiv;
    }

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // Initialize
    initSession();
});
