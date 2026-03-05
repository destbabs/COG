import os
from typing import AsyncGenerator, Dict, List

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Make path portable
current_dir = os.path.dirname(os.path.abspath(__file__))
prompt_path = os.path.join(current_dir, "system_prompt.txt")

with open(prompt_path, "r", encoding="utf-8") as f:
    system_prompt = f.read()


class GeminiService:
    def __init__(self):
        self.system_prompt = system_prompt

        self.model_name = "gemini-3.1-flash-lite-preview"

    def _get_client(self, api_key: str = None):
        # 1. Use provided key from session state
        if api_key:
            return genai.Client(api_key=api_key)
            
        # 2. Fallback to Environment Variable
        final_key = os.getenv("GOOGLE_API_KEY")
        
        # 3. Fallback to Streamlit Secrets (if running in Streamlit)
        if not final_key:
            try:
                import streamlit as st
                if "GOOGLE_API_KEY" in st.secrets:
                    final_key = st.secrets["GOOGLE_API_KEY"]
            except (ImportError, Exception):
                pass
                
        if not final_key:
            return None
        return genai.Client(api_key=final_key)

    async def get_streaming_response(
        self, message: str, history: List[Dict[str, str]], api_key: str = None
    ) -> AsyncGenerator[tuple[str, str], None]:
        """
        Sends message to Gemini and yields (chunk, model_name).
        Simple, single-model implementation with custom API key support.
        """

        formatted_history = []
        for item in history:
            parts = []
            for p in item.get("parts", []):
                if isinstance(p, str):
                    parts.append(types.Part.from_text(text=p))
                elif isinstance(p, dict):
                    text_val = p.get("text", "")
                    parts.append(types.Part.from_text(text=text_val))

            formatted_history.append(types.Content(role=item["role"], parts=parts))

        client = self._get_client(api_key)
        if not client:
            yield "⚠️ Google API Key not found. Please provide one in the settings or .env file.", "System"
            return

        try:
            print(f"Attempting response with model: {self.model_name}")
            chat = client.aio.chats.create(
                model=self.model_name,
                history=formatted_history,
                config=types.GenerateContentConfig(system_instruction=self.system_prompt),
            )

            async for chunk in await chat.send_message_stream(message):
                if chunk.text:
                    yield chunk.text, self.model_name
            
            print(f"Successfully responded with {self.model_name}")

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            print(error_msg)
            yield error_msg, "System"


gemini_service = GeminiService()
