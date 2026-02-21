"""API Key 加密/解密工具（Fernet 对称加密）"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet

from config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """获取 Fernet 实例，密钥从环境变量或配置派生"""
    global _fernet
    if _fernet is None:
        settings = get_settings()
        # 从数据库密码 + 固定盐派生加密密钥（生产环境应使用独立密钥）
        secret = (settings.db_password or "default-secret") + "-werewolf-encryption"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt_key(plain_key: str) -> str:
    """加密 API Key"""
    return _get_fernet().encrypt(plain_key.encode()).decode()


def decrypt_key(encrypted_key: str) -> str:
    """解密 API Key"""
    return _get_fernet().decrypt(encrypted_key.encode()).decode()
