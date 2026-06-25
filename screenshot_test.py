"""
前端UI截图测试 - 可视化验证
"""
from playwright.sync_api import sync_playwright
import os

def take_screenshots():
    """截取各页面截图用于可视化验证"""
    print("\n=== 截取前端UI截图 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 知识库页面
        print("截取知识库页面...")
        page.goto('http://localhost:5173/knowledge')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)  # 等待动画完成
        page.screenshot(path='D:/WMSRAGV2/screenshots/knowledge_page.png', full_page=True)

        # 检查统计卡片
        cards = page.locator('.grid.grid-cols-2.md\\:grid-cols-4.mb-10 > div').all()
        print(f"  统计卡片数量: {len(cards)}")
        for i, card in enumerate(cards):
            bg = card.evaluate('el => window.getComputedStyle(el).backgroundColor')
            text = card.evaluate('el => window.getComputedStyle(el).color')
            print(f"  卡片{i+1}: 背景={bg}, 文字={text}")

        # 智能问答页面
        print("截取智能问答页面...")
        page.goto('http://localhost:5173/chat')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        page.screenshot(path='D:/WMSRAGV2/screenshots/chat_page.png', full_page=True)

        # PM工作室页面
        print("截取PM工作室页面...")
        page.goto('http://localhost:5173/pm-studio')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        page.screenshot(path='D:/WMSRAGV2/screenshots/pm_studio_page.png', full_page=True)

        # 数据查询页面
        print("截取数据查询页面...")
        page.goto('http://localhost:5173/query')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        page.screenshot(path='D:/WMSRAGV2/screenshots/query_page.png', full_page=True)

        browser.close()
        print("\n截图保存到 D:/WMSRAGV2/screenshots/ 目录")

if __name__ == '__main__':
    # 创建截图目录
    os.makedirs('D:/WMSRAGV2/screenshots', exist_ok=True)
    take_screenshots()