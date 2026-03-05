import json
import os
from typing import List, Dict
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

STORAGE_DIR = "app/storage"
# Try load from env first
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Fallback to Streamlit Secrets for cloud deployment
if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        import streamlit as st
        if "SUPABASE_URL" in st.secrets:
            SUPABASE_URL = st.secrets["SUPABASE_URL"]
        if "SUPABASE_KEY" in st.secrets:
            SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    except (ImportError, Exception):
        pass

class HistoryService:
    def __init__(self):
        # Ensure storage directory exists
        if not os.path.exists(STORAGE_DIR):
            os.makedirs(STORAGE_DIR)
        
        self.supabase: Client = None
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                print(f"Failed to initialize Supabase: {e}")

    def _get_file_path(self, session_id: str) -> str:
        return os.path.join(STORAGE_DIR, f"{session_id}.json")

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        # 1. Try Supabase first
        if self.supabase:
            try:
                response = self.supabase.table("chat_history").select("messages").eq("session_id", session_id).execute()
                if response.data:
                    return response.data[0]["messages"]
            except Exception as e:
                print(f"Supabase fetch error: {e}")

        # 2. Fallback to local
        file_path = self._get_file_path(session_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    async def add_message(self, session_id: str, role: str, text: str, model_name: str = None):
        history = await self.get_history(session_id)
        
        message_obj = {
            "role": role,
            "parts": [text] 
        }
        
        if model_name:
            message_obj["model"] = model_name
            
        history.append(message_obj)
        
        # 1. Save to local JSON (Mirror)
        file_path = self._get_file_path(session_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        # 2. Save to Supabase
        if self.supabase:
            try:
                self.supabase.table("chat_history").upsert({
                    "session_id": session_id,
                    "messages": history
                }).execute()
            except Exception as e:
                print(f"Supabase save error: {e}")

    async def get_all_sessions(self) -> List[Dict[str, str]]:
        sessions = {}
        
        # 1. Get from Supabase
        if self.supabase:
            try:
                response = self.supabase.table("chat_history").select("session_id, messages").execute()
                for item in response.data:
                    sid = item["session_id"]
                    history = item["messages"]
                    title = self._get_title_from_history(history)
                    sessions[sid] = {"id": sid, "title": title}
            except Exception as e:
                print(f"Supabase list error: {e}")

        # 2. Merge with local (local might have chats not yet in DB)
        if os.path.exists(STORAGE_DIR):
            for filename in os.listdir(STORAGE_DIR):
                if filename.endswith(".json"):
                    sid = filename.replace(".json", "")
                    if sid not in sessions:
                        history = await self.get_history(sid)
                        title = self._get_title_from_history(history)
                        sessions[sid] = {"id": sid, "title": title}
        
        return sorted(list(sessions.values()), key=lambda x: x["id"], reverse=True)

    def _get_title_from_history(self, history: List[Dict]) -> str:
        for msg in history:
            if msg["role"] == "user":
                text = msg["parts"][0]
                return text[:30] + "..." if len(text) > 30 else text
        return "New Chat"

    async def delete_history(self, session_id: str) -> bool:
        success_local = False
        success_db = False
        
        # 1. Delete Local
        file_path = self._get_file_path(session_id)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                success_local = True
            except OSError:
                pass

        # 2. Delete from Supabase
        if self.supabase:
            try:
                self.supabase.table("chat_history").delete().eq("session_id", session_id).execute()
                success_db = True
            except Exception as e:
                print(f"Supabase delete error: {e}")
                
        return success_local or success_db

history_service = HistoryService()
