"""DMS LLM Chat API - Tool-calling agent with document intelligence."""

import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dms_models import get_dms_session, DmsDocument, Folder, DocType, ChatHistory
from dms_auth import get_current_user_id
from llm_provider import get_llm_provider
from chat_tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("materialhub.routers.v2_chat")

router = APIRouter(prefix="/api/v2/chat", tags=["dms-chat"])

MAX_TOOL_ROUNDS = 5  # prevent infinite loops


class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    folder_id: Optional[int] = None


# ============================================================
# System Prompt
# ============================================================

def _build_system_prompt(folder_id: int | None) -> str:
    """Build system prompt with brief context overview (not full doc dump)."""
    parts = []

    with get_dms_session() as session:
        # Brief overview
        doc_count = session.query(DmsDocument).filter(
            DmsDocument.status.in_(["active", "draft"])
        ).count()
        folder_count = session.query(Folder).count()

        type_stats = []
        for dt in session.query(DocType).all():
            cnt = session.query(DmsDocument).filter(
                DmsDocument.doc_type_id == dt.id,
                DmsDocument.status.in_(["active", "draft"])
            ).count()
            if cnt > 0:
                type_stats.append(f"{dt.name}: {cnt}")

        parts.append(f"System has {folder_count} folders, {doc_count} documents.")
        if type_stats:
            parts.append(f"By type: {', '.join(type_stats)}")

        if folder_id:
            folder = session.query(Folder).filter(Folder.id == folder_id).first()
            if folder:
                parts.append(f"User is currently viewing folder: {folder.path}")

    overview = "\n".join(parts)

    return f"""You are the MaterialHub intelligent assistant. You help users manage and query their document library (business licenses, qualification certificates, contracts, personnel credentials, audit reports, etc).

You have access to tools to search, list, read, and analyze documents. USE THEM proactively:
- When the user asks about specific documents or data, use search_documents or list_documents first to find relevant docs
- When you need detailed info about a document, use get_document_detail
- When the user asks about content INSIDE a document (financial data, contract terms, certificate details), use read_document_content to read the full OCR text
- For overview/statistics questions, use get_statistics

IMPORTANT RULES:
- Always use tools to retrieve data before answering. Do NOT guess or fabricate document content.
- If a tool returns no data or an error, tell the user honestly.
- When citing document info, mention the document title and ID so the user can verify.
- Answer concisely in Chinese.
- You may call multiple tools if needed to gather complete information.

Current system overview:
{overview}"""


# ============================================================
# Agent Loop - runs tool calls iteratively
# ============================================================

def _build_tool_result_message(tool_call_id: str, name: str, result: str, provider_name: str) -> dict:
    """Build a tool result message in the appropriate format."""
    if provider_name == "anthropic":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result,
                }
            ]
        }
    else:
        # OpenAI format (DeepSeek, OpenRouter)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        }


def _get_provider_name() -> str:
    """Get the current provider name from settings."""
    import os
    try:
        from dms_models import get_setting
        val = get_setting("llm_provider")
        if val:
            return val.lower()
    except Exception:
        pass
    return os.getenv("LLM_PROVIDER", "deepseek").lower()


def run_agent_loop(user_messages: list[dict], folder_id: int | None,
                   on_tool_use: callable = None) -> str:
    """
    Run the agent loop with tool calling.

    Args:
        user_messages: conversation history from the user
        folder_id: current folder context
        on_tool_use: callback(tool_name, tool_args) for streaming status updates

    Returns:
        Final text response from the LLM
    """
    provider = get_llm_provider()
    provider_name = _get_provider_name()
    system_prompt = _build_system_prompt(folder_id)

    # Build initial messages
    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in user_messages:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})

    for round_num in range(MAX_TOOL_ROUNDS):
        logger.info(f"Agent loop round {round_num + 1}/{MAX_TOOL_ROUNDS}")

        try:
            response = provider.chat_with_tools(
                llm_messages, TOOL_DEFINITIONS,
                temperature=0.3, max_tokens=4000
            )
        except NotImplementedError:
            # Provider doesn't support tool calling - fallback to plain chat
            logger.warning("Provider doesn't support tool calling, falling back to plain chat")
            return _fallback_plain_chat(provider, llm_messages, folder_id)

        if not response.has_tool_calls:
            # LLM gave a final text response
            return response.content or ""

        # Process tool calls
        if response.raw_message:
            llm_messages.append(response.raw_message)

        for tc in response.tool_calls:
            logger.info(f"Tool call: {tc.name}({tc.arguments})")
            if on_tool_use:
                on_tool_use(tc.name, tc.arguments)

            result = execute_tool(tc.name, tc.arguments)
            logger.info(f"Tool result: {result[:200]}...")

            tool_msg = _build_tool_result_message(tc.id, tc.name, result, provider_name)
            llm_messages.append(tool_msg)

    # Hit max rounds - ask LLM to summarize what it has
    llm_messages.append({
        "role": "user",
        "content": "Please provide your final answer based on the information gathered so far."
    })
    try:
        final = provider.chat(llm_messages, temperature=0.3, max_tokens=2000)
        return final
    except Exception as e:
        logger.error(f"Final summary failed: {e}")
        return "I gathered some information but encountered an error generating the final response."


def _fallback_plain_chat(provider, messages: list, folder_id: int | None) -> str:
    """Fallback for providers without tool support - old context-stuffing approach."""
    # Enrich system prompt with full document list
    with get_dms_session() as session:
        all_docs = session.query(DmsDocument).filter(
            DmsDocument.status.in_(["active", "draft"])
        ).order_by(DmsDocument.updated_at.desc()).limit(100).all()

        doc_lines = []
        for doc in all_docs:
            line = f"- [{doc.id}] {doc.title}"
            if doc.doc_type:
                line += f" (type: {doc.doc_type.name})"
            if doc.folder:
                line += f" [folder: {doc.folder.path}]"
            if doc.expiry_date:
                line += f" [expires: {doc.expiry_date}]"
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                    summary = meta.get("summary", "")
                    if summary:
                        line += f"\n  {summary}"
                    ed = meta.get("extracted_data", {})
                    if isinstance(ed, dict) and ed:
                        kv = [f"{k}={v}" for k, v in ed.items() if v and isinstance(v, str)]
                        if kv:
                            line += f"\n  {'; '.join(kv[:8])}"
                except (json.JSONDecodeError, TypeError):
                    pass
            doc_lines.append(line)

    enriched_system = messages[0]["content"] + "\n\nFull document list:\n" + "\n".join(doc_lines)
    messages[0]["content"] = enriched_system

    return provider.chat(messages, temperature=0.3, max_tokens=2000)


# ============================================================
# API Endpoints
# ============================================================

TOOL_NAME_LABELS = {
    "search_documents": "searching documents",
    "get_document_detail": "reading document details",
    "read_document_content": "reading document content",
    "list_documents": "listing documents",
    "get_statistics": "calculating statistics",
}


@router.post("")
async def chat(req: ChatRequest, request: Request):
    """Chat with LLM agent (non-streaming)."""
    if not req.messages:
        return {"error": "messages cannot be empty"}

    try:
        user_messages = [{"role": m.role, "content": m.content} for m in req.messages]
        reply = run_agent_loop(user_messages, req.folder_id)
        return {"reply": reply}
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return {"error": f"LLM call failed: {str(e)}"}


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """Chat with LLM agent - streaming response with tool-use indicators."""
    if not req.messages:
        return {"error": "messages cannot be empty"}

    user_messages = [{"role": m.role, "content": m.content} for m in req.messages]

    async def generate():
        try:
            tool_events = []

            def on_tool_use(name, args):
                tool_events.append((name, args))

            reply = run_agent_loop(user_messages, req.folder_id, on_tool_use=on_tool_use)

            # First send tool-use events so frontend can show what the agent did
            if tool_events:
                tools_used = []
                for name, args in tool_events:
                    label = TOOL_NAME_LABELS.get(name, name)
                    tools_used.append({"tool": name, "label": label, "args": args})
                yield f"data: {json.dumps({'tools_used': tools_used}, ensure_ascii=False)}\n\n"

            # Then stream the final reply in chunks
            chunk_size = 4
            for i in range(0, len(reply), chunk_size):
                chunk = reply[i:i + chunk_size]
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================
# Chat History Persistence (multi-session)
# ============================================================

class SaveHistoryRequest(BaseModel):
    messages: List[ChatMessage]
    session_id: Optional[int] = None


@router.get("/history")
async def list_chat_sessions(request: Request):
    """List all chat sessions for the current user."""
    user_id = get_current_user_id(request) or 0
    with get_dms_session() as session:
        sessions = session.query(ChatHistory).filter(
            ChatHistory.user_id == user_id
        ).order_by(ChatHistory.updated_at.desc()).all()
        return {"sessions": [s.to_dict() for s in sessions]}


@router.get("/history/{session_id}")
async def get_chat_history(session_id: int, request: Request):
    """Load a specific chat session."""
    user_id = get_current_user_id(request) or 0
    with get_dms_session() as session:
        record = session.query(ChatHistory).filter(
            ChatHistory.id == session_id, ChatHistory.user_id == user_id
        ).first()
        if not record:
            return {"messages": [], "session_id": session_id}
        try:
            messages = json.loads(record.messages_json)
        except (json.JSONDecodeError, TypeError):
            messages = []
        return {"messages": messages, "session_id": record.id, "title": record.title}


@router.post("/history/new")
async def new_chat_session(request: Request):
    """Create a new empty chat session."""
    user_id = get_current_user_id(request) or 0
    with get_dms_session() as session:
        record = ChatHistory(user_id=user_id, messages_json="[]")
        session.add(record)
        session.flush()
        return {"session_id": record.id}


@router.put("/history")
async def save_chat_history(req: SaveHistoryRequest, request: Request):
    """Save chat history to a session. Creates new session if session_id not provided."""
    user_id = get_current_user_id(request) or 0
    messages_json = json.dumps(
        [{"role": m.role, "content": m.content} for m in req.messages],
        ensure_ascii=False,
    )

    # Auto-title: first user message, truncated
    title = None
    for m in req.messages:
        if m.role == "user" and m.content.strip():
            title = m.content.strip()[:40]
            break

    with get_dms_session() as session:
        if req.session_id:
            record = session.query(ChatHistory).filter(
                ChatHistory.id == req.session_id, ChatHistory.user_id == user_id
            ).first()
            if record:
                record.messages_json = messages_json
                if title and not record.title:
                    record.title = title
        else:
            record = ChatHistory(user_id=user_id, messages_json=messages_json, title=title)
            session.add(record)
            session.flush()
            req.session_id = record.id

    return {"ok": True, "session_id": req.session_id}


@router.delete("/history/{session_id}")
async def delete_chat_session(session_id: int, request: Request):
    """Delete a chat session."""
    user_id = get_current_user_id(request) or 0
    with get_dms_session() as session:
        session.query(ChatHistory).filter(
            ChatHistory.id == session_id, ChatHistory.user_id == user_id
        ).delete()
    return {"ok": True}
