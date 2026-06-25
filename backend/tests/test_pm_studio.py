"""
PM Studio LangGraph 架构测试脚本
测试流程: 创建会话 → 多轮对话 → 确认推进 → 回退 → PRD导出
"""
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
TEST_PROBLEM = "优化仓库的订单拣货流程，当前拣货员每天走超过15公里，效率低且容易出错"
SCREENSHOT_DIR = "D:/WMSRAGV2/backend/test_screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []

def log(step, status, detail=""):
    tag = "PASS" if status else "FAIL"
    msg = f"[{tag}] {step}"
    if detail:
        msg += f" -- {detail}"
    print(msg)
    results.append({"step": step, "status": status, "detail": detail})


def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(30000)

        # Capture browser console for diagnostics
        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: console_logs.append(f"[PAGE_ERROR] {err.message}"))

        # ===================================================================
        # TEST 1: Navigate to PM Studio page
        # ===================================================================
        step = "1. Navigate to PM Studio page"
        try:
            page.goto(f"{BASE_URL}/pm-studio", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/01_initial_page.png", full_page=True)
            log(step, True)
        except Exception as e:
            log(step, False, str(e))
            browser.close()
            return

        # ===================================================================
        # TEST 2: Create a new session
        # ===================================================================
        step = "2. Create new session"
        try:
            # Look for textarea on the new-session form
            textarea = page.locator("textarea").first
            textarea.wait_for(state="visible", timeout=10000)
            textarea.fill(TEST_PROBLEM)
            page.wait_for_timeout(500)

            # Click start button
            start_btn = page.locator("button:has-text('开始分析')")
            start_btn.click()
            page.wait_for_timeout(500)
            log(step, True, f"Submitted: {TEST_PROBLEM[:40]}...")
        except Exception as e:
            log(step, False, str(e))
            page.screenshot(path=f"{SCREENSHOT_DIR}/02_create_fail.png")
            browser.close()
            return

        # Wait for SSE response to arrive (Phase 1 first answer)
        page.wait_for_timeout(10000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/02_phase1_response.png", full_page=True)

        # Check if chat view is now visible
        try:
            chat_textarea = page.locator("textarea[placeholder*='输入你的问题']")
            if chat_textarea.is_visible():
                log("2b. Phase 1 chat view appeared", True)
            else:
                log("2b. Phase 1 chat view appeared", False, "chat textarea not found")
                # Check what's on the page
                page.screenshot(path=f"{SCREENSHOT_DIR}/02b_whats_on_page.png", full_page=True)
        except Exception as e:
            log("2b. Phase 1 chat view appeared", False, str(e))

        # ===================================================================
        # TEST 3: Multi-round conversation in Phase 1
        # ===================================================================
        step = "3. Phase 1 round 2 chat"
        try:
            chat_textarea = page.locator("textarea[placeholder*='输入你的问题']")
            chat_textarea.fill("请详细说明拣货流程中的主要瓶颈是什么？")
            chat_btn = page.locator("button:has-text('对话')")
            chat_btn.click()
            log(step, True)
        except Exception as e:
            log(step, False, str(e))

        page.wait_for_timeout(10000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/03_phase1_round2.png", full_page=True)

        # Round 3
        step = "3b. Phase 1 round 3 chat"
        try:
            chat_textarea = page.locator("textarea[placeholder*='输入你的问题']")
            chat_textarea.fill("另外，请考虑自动化设备引入的可行性")
            chat_btn = page.locator("button:has-text('对话')")
            chat_btn.click()
            log(step, True)
        except Exception as e:
            log(step, False, str(e))

        page.wait_for_timeout(10000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/03b_phase1_round3.png", full_page=True)

        # ===================================================================
        # TEST 4: Confirm Phase 1 → Phase 2 (Analysis)
        # ===================================================================
        step = "4. Confirm Phase 1 → Phase 2 (Analysis)"
        try:
            confirm_btn = page.locator("button:has-text('确认并进入下一阶段')")
            if confirm_btn.is_visible():
                confirm_btn.click()
                log(step, True, "Clicked confirm")
            else:
                log(step, False, "Confirm button not visible")
                page.screenshot(path=f"{SCREENSHOT_DIR}/04_confirm_not_found.png")
        except Exception as e:
            log(step, False, str(e))
            page.screenshot(path=f"{SCREENSHOT_DIR}/04_confirm_fail.png")

        # Wait for confirm SSE (structured output + Phase 2 generation)
        page.wait_for_timeout(15000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/04_phase2_generated.png", full_page=True)

        # ===================================================================
        # TEST 5: Check Phase 2 content
        # ===================================================================
        step = "5. Verify Phase 2 (Analysis) content"
        try:
            page_text = page.locator("body").inner_text()
            # Phase label check
            has_label = "方案分析" in page_text
            log(step, has_label, f"Page has analysis label: {has_label}")
        except Exception as e:
            log(step, False, str(e))

        # ===================================================================
        # TEST 6: Chat in Phase 2
        # ===================================================================
        step = "6. Phase 2 chat"
        try:
            # Wait a generous amount for confirm SSE to complete
            page.wait_for_timeout(25000)
            chat_textarea = page.locator("textarea[placeholder*='输入你的问题']")
            chat_textarea.wait_for(state="visible", timeout=10000)
            chat_textarea.fill("请对比自动化分拣和人工优化两种方案的成本")
            page.wait_for_timeout(500)
            chat_btn = page.locator("button:has-text('对话')")
            if chat_btn.is_disabled():
                log(step, False, "Button still disabled after 25s wait (loading stuck)")
                page.screenshot(path=f"{SCREENSHOT_DIR}/06_disabled.png", full_page=True)
            else:
                chat_btn.click()
                log(step, True)
        except Exception as e:
            log(step, False, str(e))
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_fail.png", full_page=True)

        page.wait_for_timeout(10000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/06_phase2_chat.png", full_page=True)

        # ===================================================================
        # TEST 7: Rollback test - go back to Phase 1
        # ===================================================================
        step = "7. Rollback to Phase 1"
        try:
            back_btn = page.locator("button:has-text('返回上一步')")
            if back_btn.is_visible():
                back_btn.click()
                log(step, True, "Clicked rollback")
                page.wait_for_timeout(10000)
                page.screenshot(path=f"{SCREENSHOT_DIR}/07_rollback_result.png", full_page=True)
            else:
                log(step, False, "Rollback button not visible (may be at first phase)")
                page.screenshot(path=f"{SCREENSHOT_DIR}/07_no_rollback.png")
        except Exception as e:
            log(step, False, str(e))

        # ===================================================================
        # TEST 8: Full flow through all phases
        # ===================================================================
        # 8a: Confirm current phase → Phase 2
        step = "8a. Confirm → Phase 2"
        try:
            confirm_btn = page.locator("button:has-text('确认并进入下一阶段')")
            if confirm_btn.is_visible():
                confirm_btn.click()
                log(step, True)
            else:
                log(step, False, "Button not visible")
        except Exception as e:
            log(step, False, str(e))
        page.wait_for_timeout(15000)

        # 8b: Confirm Phase 2 → Phase 3 (Detail)
        step = "8b. Confirm Phase 2 → Phase 3 (Detail)"
        try:
            confirm_btn = page.locator("button:has-text('确认并进入下一阶段')")
            if confirm_btn.is_visible():
                confirm_btn.click()
                log(step, True)
            else:
                log(step, False, "Button not visible")
        except Exception as e:
            log(step, False, str(e))
        page.wait_for_timeout(15000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/08b_phase3.png", full_page=True)

        # 8c: Confirm Phase 3 → Phase 4 (PRD)
        step = "8c. Confirm Phase 3 → Phase 4 (PRD)"
        try:
            # Text changes to "生成PRD" in last non-prd phase (detail→prd transfer)
            prd_btn = page.locator("button:has-text('生成PRD')")
            confirm_btn = page.locator("button:has-text('确认并进入下一阶段')")
            if prd_btn.is_visible():
                prd_btn.click()
                log(step, True, "Clicked generate PRD")
            elif confirm_btn.is_visible():
                confirm_btn.click()
                log(step, True, "Clicked confirm (generate PRD variant)")
            else:
                log(step, False, "Neither button visible")
        except Exception as e:
            log(step, False, str(e))
        page.wait_for_timeout(15000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/08c_phase4.png", full_page=True)

        # 8d: Final confirm → Export PRD
        step = "8d. Final confirm → Export PRD"
        try:
            prd_btn = page.locator("button:has-text('生成PRD')")
            if prd_btn.is_visible():
                page.on("dialog", lambda dialog: dialog.accept())
                prd_btn.click()
                page.wait_for_timeout(3000)
                log(step, True, "PRD export triggered")
            else:
                log(step, False, "PRD button not visible")
        except Exception as e:
            log(step, False, str(e))
        page.screenshot(path=f"{SCREENSHOT_DIR}/08d_export.png", full_page=True)

        # ===================================================================
        # TEST 9: History list
        # ===================================================================
        step = "9. Session history list"
        try:
            page.goto(f"{BASE_URL}/pm-studio", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            history_btn = page.locator("button:has-text('历史方案')")
            if history_btn.is_visible():
                history_btn.click()
                page.wait_for_timeout(2000)
                page.screenshot(path=f"{SCREENSHOT_DIR}/09_history_modal.png")
                log(step, True, "History modal opened")
            else:
                log(step, False, "History button not visible")
        except Exception as e:
            log(step, False, str(e))

        browser.close()

    # ===================================================================
    # Report
    # ===================================================================
    # Show relevant console logs
    error_logs = [l for l in console_logs if 'error' in l.lower() or 'fail' in l.lower() or 'confirm' in l.lower() or 'loading' in l.lower()]
    if error_logs:
        print("\n--- Browser Console (errors/warnings) ---")
        for l in error_logs[-20:]:
            print(f"  {l[:300]}")

    passed = sum(1 for r in results if r["status"])
    failed = sum(1 for r in results if not r["status"])
    total = len(results)

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print("=" * 60)
    for r in results:
        tag = "PASS" if r["status"] else "FAIL"
        print(f"  [{tag}] {r['step']}")
        if r["detail"]:
            print(f"         {r['detail']}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
