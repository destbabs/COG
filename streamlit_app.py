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

# Sidebar for session management
with st.sidebar:
    st.header("Chat Sessions")
    
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.cache_data.clear() # Clear cache for new session
        st.rerun()
    
    st.divider()
    
    # List existing sessions with titles
    # We use a helper to run the async method
    def get_sessions():
        return asyncio.run(history_service.get_all_sessions())
    
    sessions = get_sessions()
    
    for session in sessions:
        cols = st.columns([0.8, 0.2])
        is_active = session["id"] == st.session_state.session_id
        
        button_label = f"{'⭐ ' if is_active else ''}{session['title']}"
        
        if cols[0].button(button_label, key=f"btn_{session['id']}", use_container_width=True):
            if session["id"] != st.session_state.session_id:
                st.session_state.session_id = session["id"]
                st.cache_data.clear()
                st.rerun()
                
        if is_active:
            if cols[1].button("🗑️", key=f"del_{session['id']}"):
                asyncio.run(history_service.delete_history(session["id"]))
                st.session_state.session_id = str(uuid.uuid4())
                st.cache_data.clear()
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

# Load History
@st.cache_data(show_spinner=False)
def load_chat_history(session_id, refresh_trigger):
    # We use asyncio.run because history_service is async
    return asyncio.run(history_service.get_history(session_id))

if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

history = load_chat_history(st.session_state.session_id, st.session_state.refresh_counter)

# Display Messages
if history:
    for msg in history:
        with st.chat_message(msg["role"]):
            st.write(msg["parts"][0])
            if "model" in msg:
                st.markdown(f'<div class="model-tag">Responded by: {msg["model"]}</div>', unsafe_allow_html=True)
else:
    st.info("Start a new conversation by typing below!")

# Chat Input
if prompt := st.chat_input("Challenge me..."):
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)
    
    # Generate Assistant Response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # Use a dict to store state as nonlocal won't work correctly at top level in Streamlit
        chat_state = {"full_response": "", "used_model": None}
        
        # Handle async execution in streamlit
        try:
            async def run_chat():
                api_key = st.session_state.get("custom_api_key")
                async for chunk, model_name in gemini_service.get_streaming_response(prompt, history, api_key=api_key):
                    chat_state["full_response"] += chunk
                    chat_state["used_model"] = model_name
                    response_placeholder.markdown(chat_state["full_response"] + "▌")
                
                response_placeholder.markdown(chat_state["full_response"])
                
                # Save to history (only if it's not a system error message)
                if chat_state["used_model"] != "System" and chat_state["full_response"]:
                    await history_service.add_message(st.session_state.session_id, "user", prompt)
                    await history_service.add_message(
                        st.session_state.session_id, 
                        "model", 
                        chat_state["full_response"], 
                        model_name=chat_state["used_model"]
                    )
                    return True # Success
                return False

            # Use simple asyncio.run for the streaming task
            success = asyncio.run(run_chat())

            if chat_state["used_model"] and chat_state["used_model"] != "System":
                st.markdown(f'<div class="model-tag">Responded by: {chat_state["used_model"]}</div>', unsafe_allow_html=True)
                
                # Increment refresh counter to update history view
                st.session_state.refresh_counter += 1
                
                # Check if this was the first user message (to update sidebar title)
                user_msgs = [m for m in history if m["role"] == "user"]
                if len(user_msgs) == 0:
                    st.rerun() # Hard rerun to refresh sidebar
                else:
                    # Soft refresh: historical messages will now include the new one 
                    # because refresh_counter changed the cache key.
                    # We need one rerun to trigger the reload_chat_history call at the top.
                    st.rerun()
            elif chat_state["used_model"] == "System":
                st.error(chat_state["full_response"])

        except Exception as e:
            st.error(f"Critical Application Error: {e}")
