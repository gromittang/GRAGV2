"""
检查知识库页面实际HTML结构
"""
from playwright.sync_api import sync_playwright

def inspect_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto('http://localhost:5173/knowledge')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)

        # 获取统计卡片区域的HTML
        stats_section = page.locator('.grid.grid-cols-2.md\\:grid-cols-4.mb-10')
        if stats_section.count() > 0:
            html = stats_section.evaluate('el => el.outerHTML')
            print("=== StatsBento区域HTML ===")
            print(html[:2000])  # 打印前2000字符

            # 检查每个卡片
            cards = stats_section.locator('> div').all()
            print(f"\n=== 找到 {len(cards)} 个卡片 ===")
            for i, card in enumerate(cards):
                # 获取inline style
                inline_style = card.evaluate('el => el.getAttribute("style")')
                computed_bg = card.evaluate('el => window.getComputedStyle(el).backgroundColor')
                print(f"卡片{i+1}: style属性='{inline_style}', computed背景='{computed_bg}'")
        else:
            print("未找到StatsBento区域")
            # 尝试其他选择器
            all_divs = page.locator('div').all()
            print(f"页面共有 {len(all_divs)} 个div元素")

            # 搜索包含"知识库"文字的区域
            kb_text = page.locator('text=/知识库|文档|片段|字符/')
            print(f"包含关键词的元素: {kb_text.count()}")

        browser.close()

if __name__ == '__main__':
    inspect_page()