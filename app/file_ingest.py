"""上传文件读取：类型白名单 + 大小限制 + 编码容错（UTF-8 / GBK）。"""
from __future__ import annotations

from . import config


class UploadError(Exception):
    pass


def read_text_file(uploaded_file) -> str:
    """Streamlit UploadedFile -> 纯文本。"""
    name = getattr(uploaded_file, "name", "file")
    if not name.lower().endswith(config.ALLOWED_UPLOAD_EXT):
        raise UploadError(f"仅支持 {', '.join(config.ALLOWED_UPLOAD_EXT)} 格式的文件")
    raw = uploaded_file.getvalue()
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise UploadError(f"文件过大（{len(raw)} 字节），上限 {config.MAX_UPLOAD_BYTES // 1024 // 1024}MB")
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UploadError("文件编码无法识别，请另存为 UTF-8 后再上传")
