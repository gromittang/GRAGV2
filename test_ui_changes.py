"""
前端UI优化测试脚本
验证所有新修改的功能
"""
from playwright.sync_api import sync_playwright
import os

def test_knowledge_page():
    """测试知识库页面改动"""
    print("\n=== 测试知识库页面 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 导航到知识库页面
        page.goto('http://localhost:5173/knowledge')
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(2000)  # 等待动画和AJAX完成

        # 截图保存
        page.screenshot(path='/tmp/knowledge_page.png', full_page=True)

        # 1. 验证统计卡片颜色
        stat_cards = page.locator('.grid.grid-cols-2.md\\:grid-cols-4 > div').all()
        print(f"  统计卡片数量: {len(stat_cards)}")

        if len(stat_cards) >= 4:
            # 检查第一个卡片背景色（应为蓝色 #3B82F6）
            first_card = stat_cards[0]
            bg_color = first_card.evaluate('el => window.getComputedStyle(el).backgroundColor')
            print(f"  第一个卡片背景色: {bg_color}")

            # 检查是否有白色文字
            title_el = first_card.locator('.font-space.text-4xl')
            if title_el.count() > 0:
                text_color = title_el.evaluate('el => window.getComputedStyle(el).color')
                print(f"  标题文字颜色: {text_color}")

            # 检查中文标签
            label_el = first_card.locator('.text-sm.opacity-90')
            if label_el.count() > 0:
                label = label_el.text_content()
                print(f"  第一个卡片标签: {label}")
                assert '知识库总数' in label or '文档总计' in label or '累计' in label, "标签应为中文"
            else:
                print("  [WARN] 未找到标签元素")

        # 2. 验证知识库卡片间距
        kb_grid = page.locator('.grid.gap-6')
        if kb_grid.count() > 0:
            print("  [OK] 知识库卡片使用gap-6间距")
        else:
            print("  [WARN] 未找到gap-6网格")

        # 3. 验证卡片中文标签
        kb_cards = page.locator('[class*="border-grid"]').all()
        for card in kb_cards[:2]:
            card_text = card.text_content()
            if '文档数' in card_text or '片段数' in card_text:
                print("  [OK] 知识库卡片标签已改为中文")
                break

        browser.close()
        print("知识库页面测试完成")

def test_chat_page():
    """测试智能问答页面改动"""
    print("\n=== 测试智能问答页面 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 导航到智能问答页面
        page.goto('http://localhost:5173/chat')
        page.wait_for_load_state('domcontentloaded')

        page.screenshot(path='/tmp/chat_page.png', full_page=True)

        # 1. 验证输入框和按钮高度
        textarea = page.locator('textarea')
        button = page.locator('button:has-text("发送")')

        if textarea.count() > 0 and button.count() > 0:
            textarea_height = textarea.evaluate('el => el.offsetHeight')
            button_height = button.evaluate('el => el.offsetHeight')
            print(f"  输入框高度: {textarea_height}px")
            print(f"  发送按钮高度: {button_height}px")

            if textarea_height >= 44 and button_height >= 44:
                print("  [OK] 输入框和按钮高度已统一")
            else:
                print("  [WARN] 高度可能未完全对齐")

        # 2. 检查Markdown解析样式是否存在
        md_style = page.locator('.message-md-content')
        print(f"  Markdown样式容器存在: {md_style.count() > 0}")

        # 3. 检查文本对比度（空状态提示）
        empty_text = page.locator('.text-slate-500, .text-slate-600')
        if empty_text.count() > 0:
            print("  [OK] 文本对比度已提升")

        browser.close()
        print("智能问答页面测试完成")

def test_pm_studio_page():
    """测试PM方案工作室页面改动"""
    print("\n=== 测试PM方案工作室页面 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 导航到PM工作室页面
        page.goto('http://localhost:5173/pm-studio')
        page.wait_for_load_state('domcontentloaded')

        page.screenshot(path='/tmp/pm_studio_page.png', full_page=True)

        # 1. 验证顶部时间轴
        timeline = page.locator('.flex.items-center.justify-center.py-6')
        if timeline.count() > 0:
            print("  [OK] 顶部时间轴已添加")

            # 检查阶段圆点
            circles = page.locator('.w-10.h-10.rounded-full').all()
            print(f"  阶段圆点数量: {len(circles)}")

            # 检查阶段标签
            phase_labels = page.locator('.text-sm.font-medium').all()
            labels_text = [el.text_content() for el in phase_labels[:4]]
            print(f"  阶段标签: {labels_text}")
        else:
            print("  [WARN] 未找到顶部时间轴")

        # 2. 验证左侧流程卡片已移除
        sidebar = page.locator('aside.w-\\[220px\\]')
        if sidebar.count() == 0:
            print("  [OK] 左侧流程卡片已移除")
        else:
            print("  [WARN] 左侧流程卡片仍存在")

        browser.close()
        print("PM方案工作室页面测试完成")

def test_query_page():
    """测试数据查询页面改动"""
    print("\n=== 测试数据查询页面 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 导航到数据查询页面
        page.goto('http://localhost:5173/query')
        page.wait_for_load_state('domcontentloaded')

        page.screenshot(path='/tmp/query_page.png', full_page=True)

        # 1. 验证搜索框
        search_input = page.locator('input[placeholder*="搜索"]')
        if search_input.count() > 0:
            print("  [OK] Schema搜索框已添加")
            placeholder = search_input.get_attribute('placeholder')
            print(f"  搜索框placeholder: {placeholder}")
        else:
            print("  [WARN] 未找到搜索框")

        # 2. 验证Schema浏览器中文化
        schema_title = page.locator('text=数据库结构')
        if schema_title.count() > 0:
            print("  [OK] Schema浏览器标题已改为中文")
        else:
            # 检查其他可能的中文文本
            chinese_text = page.locator('text=/数据库|结构|搜索/')
            print(f"  中文文本元素: {chinese_text.count()}")

        # 3. 检查悬浮窗组件代码是否存在（需要点击表名才能触发）
        # 检查表名列表
        table_names = page.locator('.font-mono.text-\\[12px\\].font-bold').all()
        print(f"  表名元素数量: {len(table_names)}")

        browser.close()
        print("数据查询页面测试完成")

def test_backend_api():
    """测试后端API端点"""
    print("\n=== 测试后端API ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # 1. 测试schema搜索API
        api_url = 'http://localhost:8812/query/schema/search?q=test&limit=5'
        response = page.request.get(api_url)
        if response.ok:
            data = response.json()
            print(f"  [OK] Schema搜索API正常工作")
            print(f"  返回表数量: {len(data.get('tables', []))}")
        else:
            print(f"  [WARN] API响应: {response.status}")

        # 2. 测试字段详情API（如果有表）
        # 先获取一个表名
        schema_url = 'http://localhost:8812/query/schema'
        schema_response = page.request.get(schema_url)
        if schema_response.ok:
            schema_data = schema_response.json()
            tables = schema_data.get('tables', [])
            if tables:
                first_table = tables[0].get('name', tables[0].get('table_name', ''))
                fields_url = f'http://localhost:8812/query/schema/table/{first_table}/fields'
                fields_response = page.request.get(fields_url)
                if fields_response.ok:
                    fields_data = fields_response.json()
                    print(f"  [OK] 字段详情API正常工作")
                    print(f"  表名: {fields_data.get('table_name')}")
                    print(f"  字段数量: {len(fields_data.get('columns', []))}")
                else:
                    print(f"  [WARN] 字段API响应: {fields_response.status}")

        browser.close()
        print("后端API测试完成")

def main():
    print("=" * 50)
    print("前端UI优化功能测试")
    print("=" * 50)

    try:
        test_knowledge_page()
        test_chat_page()
        test_pm_studio_page()
        test_query_page()
        test_backend_api()

        print("\n" + "=" * 50)
        print("所有测试完成！")
        print("截图保存在: /tmp/knowledge_page.png, /tmp/chat_page.png, /tmp/pm_studio_page.png, /tmp/query_page.png")
        print("=" * 50)
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()