import streamlit as st
import uuid
import asyncio
import os
from app.services.gemini_service import gemini_service
from app.services.history_service import history_service

# Page Config
st.set_page_config(page_title="COG - Cognitive Coach", page_icon="🧠", layout="wide")

# Custom CSS for better aesthetics
st.markdown("""
<style>
    .stChatMessage {
        border-radius: 15px;
        padding: 10px;
        margin-bottom: 10px;
    }
    .model-tag {
        font-size: 0.8rem;
        color: #888;
        font-style: italic;
    }
</style>
""", unsafe_allow_html=True)

st.title("🧠 COG: Cognitive Coach")
st.subheader("Your Intellectual Sparring Partner")

# Initialize Session State
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_loaded_session" not in st.session_state:
    st.session_state.last_loaded_session = None

# Sidebar for session management
with st.sidebar:
    st.header("Chat Sessions")
    
    # Supabase Connection Status
    if history_service.supabase:
        st.success("✅ Supabase Connected")
    else:
        st.warning("⚠️ Local Mode (Supabase not found)")

    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    
    # List existing sessions with titles
    def get_sessions():
        try:
            return asyncio.run(history_service.get_all_sessions())
        except Exception:
            return []
    
    sessions = get_sessions()
    
    for session in sessions:
        cols = st.columns([0.8, 0.2])
        is_active = session["id"] == st.session_state.session_id
        
        # Display active session clearly
        button_label = f"{'⭐ ' if is_active else ''}{session['title']}"
        
        if cols[0].button(button_label, key=f"btn_{session['id']}", use_container_width=True):
            if session["id"] != st.session_state.session_id:
                st.session_state.session_id = session["id"]
                st.session_state.messages = [] # Force reload
                st.rerun()
                
        if is_active:
            if cols[1].button("🗑️", key=f"del_{session['id']}"):
                try:
                    asyncio.run(history_service.delete_history(session["id"]))
                except Exception:
                    pass
                st.session_state.session_id = str(uuid.uuid4())
                st.session_state.messages = []
                st.rerun()

    st.divider()
    
    st.subheader("Settings")
    custom_key = st.text_input("Custom Google API Key", type="password", help="Overrides the default server key if provided.")
    if custom_key:
        st.session_state.custom_api_key = custom_key
    else:
        st.session_state.custom_api_key = None

    st.divider()
    st.info("COG doesn't give answers. It helps you find them.")

# Load History if session changed
if st.session_state.last_loaded_session != st.session_state.session_id or not st.session_state.messages:
    with st.spinner("Loading history..."):
        try:
            st.session_state.messages = asyncio.run(history_service.get_history(st.session_state.session_id))
            st.session_state.last_loaded_session = st.session_state.session_id
        except Exception as e:
            st.error(f"Error loading history: {e}")
            st.session_state.messages = []

history = st.session_state.messages

# Display Messages
if history:
    for msg in history:
        with st.chat_message(msg["role"]):
            text = msg["parts"][0] if isinstance(msg["parts"], list) else msg["parts"]
            st.write(text)
            if "model" in msg:
                st.markdown(f'<div class="model-tag">Responded by: {msg["model"]}</div>', unsafe_allow_html=True)
else:
    st.info("Start a new conversation by typing below!")

# Chat Input
if prompt := st.chat_input("Challenge me..."):
    # Append user message locally immediately
    st.session_state.messages.append({"role": "user", "parts": [prompt]})
    
    # Force a rerun to show the user message while generating
    st.rerun()

# If there is a last message from user and no response yet, generate it
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_prompt = st.session_state.messages[-1]["parts"][0]
    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        try:
            async def run_chat():
                _full_response = ""
                _used_model = None
                api_key = st.session_state.get("custom_api_key")
                # Use history EXCLUDING the last message we just added
                context = st.session_state.messages[:-1]
                
                async for chunk, model_name in gemini_service.get_streaming_response(last_prompt, context, api_key=api_key):
                    _full_response += chunk
                    _used_model = model_name
                    response_placeholder.markdown(_full_response + "▌")
                
                response_placeholder.markdown(_full_response)
                return _full_response, _used_model

            # Use simple asyncio.run for the streaming task
            full_response, used_model = asyncio.run(run_chat())

            if used_model and used_model != "System":
                # Add to local state
                st.session_state.messages.append({
                    "role": "model", 
                    "parts": [full_response], 
                    "model": used_model
                })
                
                # Persist to DB in background
                async def persist():
                    await history_service.add_message(st.session_state.session_id, "user", last_prompt)
                    await history_service.add_message(
                        st.session_state.session_id, 
                        "model", 
                        full_response, 
                        model_name=used_model
                    )
                
                asyncio.run(persist())
                st.rerun()
            elif used_model == "System":
                st.error(full_response)
                # Remove the failed user message so they can try again
                st.session_state.messages.pop()
        except Exception as e:
            st.error(f"Critical Application Error: {e}")
            if st.session_state.messages:
                st.session_state.messages.pop()
