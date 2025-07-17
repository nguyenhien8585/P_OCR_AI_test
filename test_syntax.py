#!/usr/bin/env python3
"""
Test script to validate Python syntax in app files
"""

import ast
import sys
import os

def test_syntax(filename):
    """Test Python syntax of a file"""
    print(f"🔍 Testing syntax: {filename}")
    
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return False
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse the AST
        ast.parse(content, filename=filename)
        print(f"✅ {filename} - Syntax OK")
        return True
        
    except SyntaxError as e:
        print(f"❌ {filename} - SyntaxError:")
        print(f"   Line {e.lineno}: {e.text.strip() if e.text else 'N/A'}")
        print(f"   Error: {e.msg}")
        return False
    except Exception as e:
        print(f"❌ {filename} - Error: {str(e)}")
        return False

def test_imports(filename):
    """Test if imports work"""
    print(f"🔍 Testing imports: {filename}")
    
    try:
        # Try to compile the file
        import py_compile
        py_compile.compile(filename, doraise=True)
        print(f"✅ {filename} - Imports OK")
        return True
    except Exception as e:
        print(f"❌ {filename} - Import Error: {str(e)}")
        return False

def check_common_issues(filename):
    """Check for common issues"""
    print(f"🔍 Checking common issues: {filename}")
    
    issues = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for st.time() usage
            if 'st.time()' in line:
                issues.append(f"Line {i}: Found 'st.time()' - should be 'time.strftime()'")
            
            # Check for unterminated regex
            if line.strip().endswith('\\') and ('r"' in line or "r'" in line):
                issues.append(f"Line {i}: Possible unterminated regex string")
            
            # Check for missing imports
            if 'time.strftime' in line and 'import time' not in content:
                issues.append(f"Line {i}: Uses time.strftime but 'import time' not found")
        
        if issues:
            print("⚠️  Common issues found:")
            for issue in issues:
                print(f"   {issue}")
            return False
        else:
            print("✅ No common issues found")
            return True
            
    except Exception as e:
        print(f"❌ Error checking issues: {str(e)}")
        return False

def main():
    """Main test function"""
    print("🧪 PDF/LaTeX Converter - Syntax & Import Validator")
    print("=" * 50)
    
    # Files to test
    test_files = ['app.py', 'app_fixed.py', 'app_simple.py', 'utils.py']
    
    results = {}
    
    for filename in test_files:
        if os.path.exists(filename):
            print(f"\n📄 Testing {filename}:")
            print("-" * 30)
            
            syntax_ok = test_syntax(filename)
            imports_ok = test_imports(filename)
            issues_ok = check_common_issues(filename)
            
            results[filename] = {
                'syntax': syntax_ok,
                'imports': imports_ok,
                'issues': issues_ok,
                'overall': syntax_ok and imports_ok and issues_ok
            }
        else:
            print(f"\n📄 {filename}: File not found (skipping)")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print("=" * 50)
    
    working_files = []
    broken_files = []
    
    for filename, result in results.items():
        status = "✅ WORKING" if result['overall'] else "❌ ISSUES"
        print(f"{status}: {filename}")
        
        if result['overall']:
            working_files.append(filename)
        else:
            broken_files.append(filename)
    
    print("\n🎯 RECOMMENDATIONS:")
    print("-" * 20)
    
    if working_files:
        print(f"✅ Use these files for deployment:")
        for f in working_files:
            print(f"   - {f}")
    
    if broken_files:
        print(f"❌ Fix these files before deploying:")
        for f in broken_files:
            print(f"   - {f}")
    
    if 'app_fixed.py' in working_files:
        print(f"\n🚀 BEST CHOICE: app_fixed.py")
        print("   Run: cp app_fixed.py app.py")
    elif 'app_simple.py' in working_files:
        print(f"\n⚡ FALLBACK: app_simple.py") 
        print("   Run: cp app_simple.py app.py")
    elif working_files:
        print(f"\n💡 AVAILABLE: {working_files[0]}")
    else:
        print(f"\n🚨 NO WORKING FILES FOUND!")
        print("   Please check syntax errors manually")
    
    # Exit code
    if working_files:
        print(f"\n✅ Ready for deployment!")
        sys.exit(0)
    else:
        print(f"\n❌ Please fix errors before deploying")
        sys.exit(1)

if __name__ == "__main__":
    main()
