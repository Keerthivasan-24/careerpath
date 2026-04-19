"""
Test HTML/JavaScript for common errors
"""
import re

print("🔍 Testing templates/index.html...")
print("-" * 50)

try:
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("✅ HTML file loaded successfully")
    
    # Check for common issues
    checks = {
        "HTML structure": content.startswith("<!DOCTYPE html>"),
        "Closing html tag": "</html>" in content,
        "Script tag present": "<script>" in content,
        "No 'Ollama' references": "Ollama" not in content and "ollama" not in content,
        "Groq references present": "Groq" in content,
        "State object defined": "const S = {" in content,
        "goTo function": "function goTo(" in content,
        "doRegister function": "function doRegister(" in content,
        "doLogin function": "function doLogin(" in content,
        "startScreening function": "function startScreening(" in content,
        "renderQ function": "function renderQ(" in content,
        "S.sCurrent used correctly": "S.sCurrent" in content,
    }
    
    print("\n🔧 Checking HTML/JS components:")
    all_good = True
    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check}")
        if not result:
            all_good = False
    
    # Check for potential JS errors
    print("\n🐛 Checking for common JS errors:")
    
    # Check for undefined variables
    if "S.sCurren" in content and "S.sCurrent" not in content:
        print("  ❌ Found 'S.sCurren' (incomplete variable)")
        all_good = False
    else:
        print("  ✅ No incomplete variable names")
    
    # Check for unclosed brackets
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces == close_braces:
        print(f"  ✅ Balanced braces ({open_braces} pairs)")
    else:
        print(f"  ⚠️  Unbalanced braces: {open_braces} open, {close_braces} close")
    
    open_brackets = content.count('[')
    close_brackets = content.count(']')
    if open_brackets == close_brackets:
        print(f"  ✅ Balanced brackets ({open_brackets} pairs)")
    else:
        print(f"  ⚠️  Unbalanced brackets: {open_brackets} open, {close_brackets} close")
    
    open_parens = content.count('(')
    close_parens = content.count(')')
    if open_parens == close_parens:
        print(f"  ✅ Balanced parentheses ({open_parens} pairs)")
    else:
        print(f"  ⚠️  Unbalanced parentheses: {open_parens} open, {close_parens} close")
    
    # Check for API endpoints
    print("\n🌐 Checking API endpoint references:")
    endpoints = [
        "/api/register",
        "/api/login",
        "/api/questions/screening",
        "/api/roadmap/generate",
        "/api/questions/progress",
        "/api/resume/generate"
    ]
    
    for endpoint in endpoints:
        if endpoint in content:
            print(f"  ✅ {endpoint}")
        else:
            print(f"  ❌ {endpoint} NOT FOUND")
            all_good = False
    
    print("\n" + "=" * 50)
    if all_good:
        print("✅ ALL HTML/JS CHECKS PASSED!")
        print("🎨 Frontend is ready!")
    else:
        print("⚠️  Some checks failed. Review the output above.")
    
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
