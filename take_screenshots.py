#!/usr/bin/env python3
"""
Screenshot capture script for Exam Portal
This script will capture screenshots of different pages
"""

import os
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_driver():
    """Setup Chrome driver with headless options"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"Chrome driver not available: {e}")
        return None

def take_screenshot(driver, url, filename, wait_for_element=None):
    """Take a screenshot of a specific URL"""
    try:
        print(f"Capturing {filename}...")
        driver.get(url)
        
        if wait_for_element:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_element))
            )
        
        time.sleep(2)  # Wait for page to load completely
        
        # Create screenshots directory
        os.makedirs("screenshots", exist_ok=True)
        
        # Take screenshot
        screenshot_path = f"screenshots/{filename}"
        driver.save_screenshot(screenshot_path)
        print(f"✅ Screenshot saved: {screenshot_path}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to capture {filename}: {e}")
        return False

def main():
    """Main function to capture all screenshots"""
    base_url = "http://localhost:8000"
    
    # Setup driver
    driver = setup_driver()
    if not driver:
        print("❌ Could not setup Chrome driver. Please install Chrome and chromedriver.")
        return
    
    try:
        # List of pages to capture
        pages = [
            {
                "url": f"{base_url}/",
                "filename": "01_homepage.png",
                "wait_for": "body"
            },
            {
                "url": f"{base_url}/student/login/",
                "filename": "02_student_login.png",
                "wait_for": "form"
            },
            {
                "url": f"{base_url}/faculty/login/",
                "filename": "03_faculty_login.png",
                "wait_for": "form"
            },
            {
                "url": f"{base_url}/student/register/",
                "filename": "04_student_register.png",
                "wait_for": "form"
            },
            {
                "url": f"{base_url}/faculty/register/",
                "filename": "05_faculty_register.png",
                "wait_for": "form"
            }
        ]
        
        print("🚀 Starting screenshot capture...")
        print(f"📱 Server URL: {base_url}")
        print("=" * 50)
        
        success_count = 0
        total_count = len(pages)
        
        for page in pages:
            if take_screenshot(driver, page["url"], page["filename"], page["wait_for"]):
                success_count += 1
        
        print("=" * 50)
        print(f"📊 Screenshot capture complete!")
        print(f"✅ Successfully captured: {success_count}/{total_count} screenshots")
        
        if success_count > 0:
            print(f"📁 Screenshots saved in: ./screenshots/")
            print("🎉 You can now use these screenshots in your README!")
        
    except Exception as e:
        print(f"❌ Error during screenshot capture: {e}")
    
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
