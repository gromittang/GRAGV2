"""
配置模块测试
"""
import pytest
import os

# 设置测试环境
os.environ["DEEPSEEK_API_KEY"] = "test_key"


def test_settings_load():
    """测试配置加载"""
    from app.config import get_settings
    settings = get_settings()
    assert settings.app_name == "知识库系统"
    assert settings.llm_provider in ["deepseek", "openai", "anthropic"]


def test_industry_settings():
    """测试行业配置"""
    from app.core.settings import get_industry_settings, INDUSTRIES

    # 测试默认行业
    general = get_industry_settings("general")
    assert general.chunk_size == 500
    assert general.use_bm25 == True

    # 测试 WMS 行业
    wms = get_industry_settings("wms")
    assert wms.chunk_size == 800
    assert "仓库" in wms.system_prompt


def test_all_industries():
    """测试获取所有行业"""
    from app.core.settings import get_all_industries

    industries = get_all_industries()
    assert "general" in industries
    assert "wms" in industries
    assert len(industries) >= 5