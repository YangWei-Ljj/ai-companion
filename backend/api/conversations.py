"""会话路由：CRUD / 消息列表 / SSE 流式聊天 / 文件上传。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi import File, UploadFile
from starlette.concurrency import iterate_in_threadpool

from backend.core import security
from backend.core.config import settings
from backend.core.deps import rate_limited
from backend.core.exceptions import (
    LLMUpstreamError,
    PayloadTooLargeError,
    UnsupportedTypeError,
    ValidationFailedError,
)
from backend.core.logging import request_id_var, user_id_var
from backend.infrastructure import llm
from backend.infrastructure.audit import write_audit
from backend.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageStreamRequest,
)
from backend.service import conversation_service, message_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _sse(event: dict) -> str:
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"data: {body}\n\n"


@router.post("")
def create_conversation(body: ConversationCreate, request: Request,
                        user: dict = Depends(rate_limited)):
    conv = conversation_service.create_conversation(
        user["id"], title=body.title, persona_id=body.persona_id,
        nick_name=body.nick_name, nature=body.nature,
    )
    write_audit(request_id=request_id_var.get(), user_id=user["id"],
                action="conversation.create", resource_type="conversation",
                resource_id=conv["id"])
    return conv


@router.get("")
def list_conversations(user: dict = Depends(rate_limited)):
    return conversation_service.list_conversations(user["id"])


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, request: Request,
                     user: dict = Depends(rate_limited)):
    try:
        return conversation_service.get_conversation_for_user(user["id"], conversation_id)
    except Exception:
        # 越权访问：记录 denied 审计后再抛出
        write_audit(request_id=request_id_var.get(), user_id=user["id"],
                    action="conversation.access", resource_type="conversation",
                    resource_id=conversation_id, result="denied")
        raise


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: str, body: ConversationUpdate,
                        user: dict = Depends(rate_limited)):
    return conversation_service.update_conversation(
        user["id"], conversation_id, body.model_dump(exclude_unset=True)
    )


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request,
                        user: dict = Depends(rate_limited)):
    conversation_service.delete_conversation(user["id"], conversation_id)
    write_audit(request_id=request_id_var.get(), user_id=user["id"],
                action="conversation.delete", resource_type="conversation",
                resource_id=conversation_id)
    return {"deleted": True}


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: str, user: dict = Depends(rate_limited)):
    conversation_service.get_conversation_for_user(user["id"], conversation_id)  # 归属校验
    return message_service.list_messages(conversation_id)


@router.post("/{conversation_id}/messages/stream")
async def stream_message(conversation_id: str, body: MessageStreamRequest,
                         request: Request, user: dict = Depends(rate_limited)):
    content = body.content.strip()
    if not content:
        raise ValidationFailedError("消息内容不能为空")
    # 归属校验（不存在→404，他人→403 并审计）
    try:
        conv = conversation_service.get_conversation_for_user(
            user["id"], conversation_id)
    except Exception:
        write_audit(request_id=request_id_var.get(), user_id=user["id"],
                    action="message.send", resource_type="conversation",
                    resource_id=conversation_id, result="denied")
        raise

    # 先落库用户消息
    message_service.add_message(conversation_id, "user", content)
    write_audit(request_id=request_id_var.get(), user_id=user["id"],
                action="message.send", resource_type="conversation",
                resource_id=conversation_id)

    system_prompt = llm.build_system_prompt(conv["nick_name"], conv["nature"])
    history = message_service.build_llm_history(conversation_id)

    async def event_gen():
        full = ""
        try:
            async for delta in iterate_in_threadpool(
                llm.stream_chat(system_prompt, history)
            ):
                if delta:
                    full += delta
                    yield _sse({"type": "delta", "text": delta})
        except llm.LLMError as exc:
            message_service.add_message(
                conversation_id, "assistant", f"（调用失败）{exc}"
            )
            yield _sse({"type": "error", "message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            message_service.add_message(
                conversation_id, "assistant", f"（内部错误）{exc}"
            )
            yield _sse({"type": "error", "message": "内部错误，请稍后重试"})
            return

        assistant_text = full or "（模型未返回内容，请稍后重试）"
        assistant_id = message_service.add_message(
            conversation_id, "assistant", assistant_text
        )
        yield _sse({"type": "done", "message_id": assistant_id, "text": assistant_text})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{conversation_id}/files")
async def upload_file(conversation_id: str, request: Request,
                      file: UploadFile = File(...),
                      user: dict = Depends(rate_limited)):
    conversation_service.get_conversation_for_user(user["id"], conversation_id)
    name = file.filename or ""
    if not name.lower().endswith(tuple(settings.ALLOWED_UPLOAD_EXT)):
        raise UnsupportedTypeError(
            f"仅支持 {', '.join(settings.ALLOWED_UPLOAD_EXT)} 格式")
    raw = await file.read()
    if len(raw) > settings.MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError(
            f"文件过大，上限 {settings.MAX_UPLOAD_BYTES // 1024 // 1024}MB")
    text = None
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValidationFailedError("文件编码无法识别，请另存为 UTF-8 后再上传")
    mid = message_service.add_message(
        conversation_id, "file", f"【文件 {name} 内容】\n{text}")
    write_audit(request_id=request_id_var.get(), user_id=user["id"],
                action="file.upload", resource_type="message", resource_id=mid,
                detail={"name": name})
    return {"message_id": mid, "name": name, "chars": len(text)}
