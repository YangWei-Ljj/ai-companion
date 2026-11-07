"""统一业务异常树。

所有业务错误都继承 ``AppError``，携带 code / http_status；
全局 exception handler 把它们渲染成标准错误 JSON。
未知异常兜底 500，绝不向前端泄漏堆栈。
"""
from __future__ import annotations


class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    message: str = "内部错误"
    http_status: int = 500

    def __init__(self, message: str | None = None, code: str | None = None,
                 http_status: int | None = None):
        if message:
            self.message = message
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status
        super().__init__(self.message)


class AuthRequiredError(AppError):
    code = "AUTH_REQUIRED"
    message = "未登录或缺少 token"
    http_status = 401


class AuthInvalidError(AppError):
    code = "AUTH_INVALID"
    message = "用户名或密码错误"
    http_status = 401


class TokenInvalidError(AppError):
    code = "TOKEN_INVALID"
    message = "token 无效或已过期"
    http_status = 401


class ConflictError(AppError):
    code = "CONFLICT"
    message = "资源已存在"
    http_status = 409


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    message = "无权访问该资源"
    http_status = 403


class NotFoundError(AppError):
    code = "NOT_FOUND"
    message = "资源不存在"
    http_status = 404


class ValidationFailedError(AppError):
    code = "VALIDATION_ERROR"
    message = "请求参数不合法"
    http_status = 422


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    message = "请求过于频繁，请稍后再试"
    http_status = 429


class LLMUpstreamError(AppError):
    code = "LLM_UPSTREAM_ERROR"
    message = "模型服务暂时不可用"
    http_status = 502


class PayloadTooLargeError(AppError):
    code = "FILE_TOO_LARGE"
    message = "文件过大"
    http_status = 413


class UnsupportedTypeError(AppError):
    code = "UNSUPPORTED_TYPE"
    message = "不支持的文件类型"
    http_status = 415


class JobExecutionError(AppError):
    code = "JOB_EXECUTION_ERROR"
    message = "后台任务执行失败"
    http_status = 500
