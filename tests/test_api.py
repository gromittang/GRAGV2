"""
API 测试
"""
import pytest
import os

# 设置测试环境
os.environ["DEEPSEEK_API_KEY"] = "test_key"


def test_import_main():
    """测试导入主模块"""
    try:
        from app.main import app
        assert app.title == "知识库系统"
    except ImportError as e:
        pytest.skip(f"导入失败（依赖未安装）: {e}")


def test_import_config():
    """测试导入配置"""
    from app.config import get_settings
    settings = get_settings()
    assert settings is not None


def test_import_models():
    """测试导入数据模型"""
    from app.models.document import Knowledge, Document, Paragraph
    assert Knowledge.__tablename__ == 'knowledge'
    assert Document.__tablename__ == 'document'
    assert Paragraph.__tablename__ == 'paragraph'