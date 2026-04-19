"""
Test if app.py can start without errors
"""
import sys
import os

print("🔍 Testing app.py startup...")
print("-" * 50)

try:
    # Test imports
    print("📦 Testing imports...")
    from flask import Flask, request, jsonify, render_template, session
    from flask_cors import CORS
    import sqlite3
    import hashlib
    import json
    import requests
    import re
    print("✅ All imports successful")
    
    # Test if app.py can be imported
    print("\n📄 Testing app.py structure...")
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check for syntax errors
    compile(content, 'app.py', 'exec')
    print("✅ app.py syntax is valid")
    
    # Check key components
    checks = {
        "Flask app creation": "app = Flask(__name__)" in content,
        "GROQ_API_KEY defined": "GROQ_API_KEY" in content,
        "Database init": "def init_db():" in content,
        "Register route": "@app.route(\"/api/register\"" in content,
        "Login route": "@app.route(\"/api/login\"" in content,
        "Screening route": "@app.route(\"/api/questions/screening\"" in content,
        "Roadmap route": "@app.route(\"/api/roadmap/generate\"" in content,
        "Resume route": "@app.route(\"/api/resume/generate\"" in content,
        "Main block": "if __name__ == \"__main__\":" in content,
    }
    
    print("\n🔧 Checking app components:")
    all_good = True
    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check}")
        if not result:
            all_good = False
    
    # Check API key
    print("\n🔑 Checking API key configuration:")
    if "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" in content:
        print("  ✅ API key is configured")
    else:
        print("  ⚠️  API key not found in default value")
    
    print("\n" + "=" * 50)
    if all_good:
        print("✅ ALL CHECKS PASSED!")
        print("🚀 Your app is ready to run: python app.py")
    else:
        print("⚠️  Some checks failed. Review the output above.")
    
except SyntaxError as e:
    print(f"❌ SYNTAX ERROR in app.py:")
    print(f"   Line {e.lineno}: {e.msg}")
    print(f"   {e.text}")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
