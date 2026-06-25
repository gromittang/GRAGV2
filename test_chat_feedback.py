"""Test Chat feedback UI with Playwright."""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8812"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Navigate to Chat page
    page.goto(f"{BASE}/#/chat")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Check the page loaded
    title = page.locator("h1").first.text_content()
    print(f"Page title: {title}")

    # Find textarea and type a question
    textarea = page.locator("textarea").first
    if textarea.is_visible():
        textarea.fill("仓库管理系统的拣货流程是怎样的")
        print("Filled question in textarea")
    else:
        print("ERROR: textarea not found")
        page.screenshot(path="/tmp/chat_no_textarea.png", full_page=True)
        browser.close()
        exit(1)

    # Find and click the send button
    send_btn = page.locator("button").filter(has_text="发送").first
    if send_btn.is_visible():
        send_btn.click()
        print("Clicked send button")
    else:
        # Try the ChatInput component's button
        all_buttons = page.locator("button").all()
        print(f"Found {len(all_buttons)} buttons, looking for send...")
        for btn in all_buttons:
            try:
                txt = btn.text_content()
                if txt:
                    print(f"  Button: {txt[:30]}")
            except:
                pass
        send_btn = page.locator("button").filter(has=page.locator("[icon='lucide:send']")).first
        if send_btn.is_visible():
            send_btn.click()
            print("Clicked send (icon button)")
        else:
            # Try clicking the last button in the input area
            btns = page.locator("button").all()
            if len(btns) >= 2:
                btns[-1].click()
                print(f"Clicked last button: {btns[-1].text_content()[:30] if btns[-1].text_content() else 'no text'}")

    # Wait for AI response (streaming)
    print("Waiting for AI response...")
    page.wait_for_timeout(15000)  # Wait up to 15s for generation

    # Take screenshot after response
    page.screenshot(path="/tmp/chat_after_response.png", full_page=True)

    # Look for feedback thumbs-up button (lucide:thumbs-up icon)
    thumbs_up = page.locator("[icon='lucide:thumbs-up']").first
    thumbs_down = page.locator("[icon='lucide:thumbs-down']").first

    if thumbs_up.is_visible():
        print("Thumbs up button found - clicking it")
        thumbs_up.click()
        page.wait_for_timeout(500)

        # Check if the detailed feedback form expanded
        source_toggle = page.locator("text=来源准确").first
        if source_toggle.is_visible():
            print("Feedback detail form expanded correctly")

            # Find and click submit button
            submit_btn = page.locator("button").filter(has_text="提交").first
            if submit_btn.is_visible():
                submit_btn.click()
                page.wait_for_timeout(1000)

                # Check for "已反馈" confirmation
                feedback_done = page.locator("text=已反馈").first
                if feedback_done.is_visible():
                    print("Feedback submitted successfully!")
                else:
                    print("ERROR: '已反馈' not visible after submit")
            else:
                print("ERROR: Submit button not found")
        else:
            print("ERROR: Detail form did not expand")
    elif thumbs_down.is_visible():
        print("Thumbs down button found")
    else:
        print("WARNING: No feedback buttons found - checking for other indicators")
        # Check if there's any assistant message (answer might still be streaming)
        assistant_msgs = page.locator(".message-md-content")
        count = assistant_msgs.count()
        print(f"  Assistant message bubbles: {count}")
        if count == 0:
            print("  No assistant response received - may need longer wait or knowledge base empty")

    page.screenshot(path="/tmp/chat_feedback_final.png", full_page=True)
    browser.close()
    print("\nTest complete.")
