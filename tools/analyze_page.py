"""
页面分析工具
用于分析AI工具网页结构，帮助确定正确的CSS选择器
"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path


async def analyze_page(url: str, auth_state_path: str = "./auth_state/state.json"):
    """
    分析AI工具页面结构
    
    Args:
        url: AI工具网址
        auth_state_path: 认证状态文件路径
    """
    print(f"正在分析页面: {url}")
    print("=" * 60)
    
    playwright = await async_playwright().start()
    
    # 启动浏览器（非无头模式，方便查看）
    browser = await playwright.chromium.launch(headless=False)
    
    # 加载认证状态
    context_options = {"viewport": {"width": 1920, "height": 1080}}
    if Path(auth_state_path).exists():
        context_options["storage_state"] = auth_state_path
        print(f"已加载认证状态: {auth_state_path}")
    
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    
    try:
        # 导航到页面
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)  # 等待页面完全加载
        
        print("\n=== 页面分析结果 ===\n")
        
        # 分析可能的输入框
        print("【可能的输入框】")
        input_selectors = [
            "textarea",
            "input[type='text']",
            "[contenteditable='true']",
            "[role='textbox']",
        ]
        
        for selector in input_selectors:
            elements = await page.locator(selector).all()
            for i, el in enumerate(elements):
                try:
                    visible = await el.is_visible()
                    if visible:
                        # 获取元素属性
                        tag = await el.evaluate("el => el.tagName")
                        classes = await el.evaluate("el => el.className")
                        id_attr = await el.evaluate("el => el.id")
                        placeholder = await el.evaluate("el => el.placeholder || ''")
                        data_testid = await el.evaluate("el => el.dataset.testid || ''")
                        
                        print(f"  [{i+1}] {tag}")
                        if id_attr:
                            print(f"      ID: {id_attr}")
                        if classes:
                            print(f"      Class: {classes}")
                        if placeholder:
                            print(f"      Placeholder: {placeholder}")
                        if data_testid:
                            print(f"      data-testid: {data_testid}")
                        print()
                except:
                    pass
        
        # 分析可能的按钮
        print("\n【可能的发送按钮】")
        button_selectors = [
            "button",
            "[role='button']",
            "input[type='submit']",
        ]
        
        for selector in button_selectors:
            elements = await page.locator(selector).all()
            for i, el in enumerate(elements):
                try:
                    visible = await el.is_visible()
                    if visible:
                        text = await el.inner_text()
                        classes = await el.evaluate("el => el.className")
                        aria_label = await el.evaluate("el => el.getAttribute('aria-label') || ''")
                        data_testid = await el.evaluate("el => el.dataset.testid || ''")
                        
                        # 过滤可能是发送按钮的
                        keywords = ['send', 'submit', '送信', '発送', '发送', 'Send', '提交']
                        if any(kw in (text + classes + aria_label).lower() for kw in ['send', 'submit', '送', '发']):
                            print(f"  [{i+1}] Button")
                            print(f"      Text: {text}")
                            if classes:
                                print(f"      Class: {classes}")
                            if aria_label:
                                print(f"      aria-label: {aria_label}")
                            if data_testid:
                                print(f"      data-testid: {data_testid}")
                            print()
                except:
                    pass
        
        # 分析可能的响应区域
        print("\n【可能的响应区域】")
        response_selectors = [
            "div[class*='message']",
            "div[class*='response']",
            "div[class*='answer']",
            "div[class*='markdown']",
            "div[class*='content']",
        ]
        
        for selector in response_selectors:
            try:
                elements = await page.locator(selector).all()
                if elements:
                    print(f"  选择器 '{selector}' 找到 {len(elements)} 个元素")
            except:
                pass
        
        # 保存页面HTML（用于离线分析）
        html_content = await page.content()
        html_file = Path("./page_analysis.html")
        html_file.write_text(html_content, encoding="utf-8")
        print(f"\n页面HTML已保存到: {html_file.absolute()}")
        
        # 提供交互式检查
        print("\n" + "=" * 60)
        print("浏览器保持打开状态，您可以:")
        print("1. 使用开发者工具 (F12) 检查元素")
        print("2. 手动测试选择器")
        print("3. 按 Enter 键关闭浏览器")
        print("=" * 60)
        input()
        
    finally:
        await browser.close()
        await playwright.stop()


async def test_selectors(url: str, selectors: dict, auth_state_path: str = "./auth_state/state.json"):
    """
    测试选择器是否能正确找到元素
    
    Args:
        url: AI工具网址
        selectors: 选择器字典
        auth_state_path: 认证状态文件路径
    """
    print(f"测试选择器配置...")
    print("=" * 60)
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    
    context_options = {"viewport": {"width": 1920, "height": 1080}}
    if Path(auth_state_path).exists():
        context_options["storage_state"] = auth_state_path
    
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        results = {}
        
        for name, selector in selectors.items():
            try:
                elements = await page.locator(selector).all()
                visible_count = 0
                for el in elements:
                    if await el.is_visible():
                        visible_count += 1
                
                status = "✓" if visible_count > 0 else "✗"
                results[name] = visible_count
                print(f"{status} {name}: 找到 {visible_count} 个可见元素")
                print(f"    选择器: {selector}")
            except Exception as e:
                results[name] = 0
                print(f"✗ {name}: 错误 - {e}")
        
        print("\n" + "=" * 60)
        print("测试完成！")
        
        if all(v > 0 for v in results.values()):
            print("所有选择器都能找到元素 ✓")
        else:
            print("部分选择器需要调整 ✗")
            print("请使用浏览器开发者工具检查页面结构")
        
        input("\n按 Enter 键关闭浏览器...")
        
    finally:
        await browser.close()
        await playwright.stop()


def main():
    """主函数"""
    import sys
    
    url = "https://taa.xxx.co.jp"  # 默认URL
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("用法:")
            print("  python analyze_page.py              # 分析页面结构")
            print("  python analyze_page.py --test       # 测试当前选择器配置")
            print("  python analyze_page.py <url>        # 分析指定URL")
            return
        elif sys.argv[1] == "--test":
            # 测试选择器
            selectors = {
                "input": "textarea[data-testid='chat-input'], textarea.chat-input, textarea",
                "send_button": "button[data-testid='send-button'], button.send-button",
                "response": "div.response-content, div.markdown, div.message-content",
                "loading": "div.loading, div[class*='typing']",
            }
            asyncio.run(test_selectors(url, selectors))
            return
        else:
            url = sys.argv[1]
    
    asyncio.run(analyze_page(url))


if __name__ == "__main__":
    main()
