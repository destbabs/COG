from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.history_service import history_service
from app.services.gemini_service import gemini_service
import json

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str
    message: str

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # Load history
        history = await history_service.get_history(request.session_id)
        
        # Prepare generator for streaming
        async def response_generator():
            full_response = ""
            used_model = None
            try:
                # Stream the response from Gemini
                async for chunk, model_name in gemini_service.get_streaming_response(
                    request.message, history
                ):
                    full_response += chunk
                    used_model = model_name
                    yield chunk
                
                # Save to history only on success (and if it's not a system error)
                if used_model != "System" and full_response:
                    await history_service.add_message(request.session_id, "user", request.message)
                    await history_service.add_message(request.session_id, "model", full_response, model_name=used_model)
                
            except Exception as e:
                # Log the specific error
                print(f"Streaming Error: {e}")
                # Yield an error message clearly
                yield f"\n\n**Error details:** {str(e)}\n\n*Please check your GOOGLE_API_KEY and Ensure the API is enabled.*"

        return StreamingResponse(response_generator(), media_type="text/plain")

    except Exception as e:
        # Log error in production
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Check system status."""
    return {"status": "ok", "storage": "In-Memory"}

@router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    """Optional endpoint if we want to load history on page refresh"""
    return await history_service.get_history(session_id)

@router.delete("/history/{session_id}")
async def delete_chat_history(session_id: str):
    success = await history_service.delete_history(session_id)
    if not success:
        # It's okay if it doesn't exist, just return success or 404
        # For UI purposes, returning OK is often easier if we just want it gone
        pass 
    return {"status": "success", "message": "History deleted"}
