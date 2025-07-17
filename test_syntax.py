#!/usr/bin/env python3
"""
Test script to verify all imports work correctly and syntax is valid
"""

def test_syntax():
    """Test Python syntax of main files"""
    import ast
    import os
    
    files_to_test = ['app.py', 'app_fixed.py', 'app_simple.py']
    syntax_results = {}
    
    for filename in files_to_test:
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                ast.parse(content, filename=filename)
                print(f"✅ {filename} - Syntax OK")
                syntax_results[filename] = True
            except SyntaxError as e:
                print(f"❌ {filename} - SyntaxError: Line {e.lineno}: {e.msg}")
                syntax_results[filename] = False
            except Exception as e:
                print(f"❌ {filename} - Error: {str(e)}")
                syntax_results[filename] = False
    
    return syntax_results

def test_imports():
    """Test all required imports"""
    try:
        # Core libraries
        import streamlit as st
        print("✅ streamlit")
        
        import requests
        print("✅ requests")
        
        # Built-in modules
        import base64
        import io
        import json
        import tempfile
        import os
        import re
        import time
        from typing import List, Tuple
        print("✅ built-in modules")
        
        # PIL
        from PIL import Image
        print("✅ Pillow (PIL)")
        
        # PyMuPDF
        import fitz
        print("✅ PyMuPDF (fitz)")
        
        # python-docx
        from docx import Document
        print("✅ python-docx")
        
        print("\n🎉 All imports successful!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_functionality():
    """Test basic functionality"""
    try:
        # Test PIL
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        print("✅ PIL Image creation")
        
        # Test docx
        from docx import Document
        doc = Document()
        doc.add_heading('Test', 0)
        print("✅ python-docx Document creation")
        
        # Test requests
        import requests
        if hasattr(requests, 'post'):
            print("✅ requests.post available")
        
        # Test fitz (PyMuPDF)
        import fitz
        if hasattr(fitz, 'open'):
            print("✅ fitz.open available")
        
        # Test time module
        import time
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ time.strftime working: {timestamp}")
        
        print("\n🎉 All functionality tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False

def check_requirements():
    """Check if requirements.txt is clean"""
    import os
    
    if not os.path.exists('requirements.txt'):
        print("⚠️  requirements.txt not found")
        return False
    
    with open('requirements.txt', 'r') as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    expected_packages = [
        'streamlit',
        'requests', 
        'Pillow',
        'PyMuPDF',
        'python-docx'
    ]
    
    found_packages = []
    for line in lines:
        package = line.split('>=')[0].split('==')[0].split('<')[0]
        found_packages.append(package)
    
    missing = []
    for pkg in expected_packages:
        if not any(pkg in found for found in found_packages):
            missing.append(pkg)
    
    if missing:
        print(f"❌ Missing packages in requirements.txt: {missing}")
        return False
    
    if len(lines) > 7:  # Should be around 5 packages
        print(f"⚠️  requirements.txt has many packages ({len(lines)}), consider cleaning")
    
    print("✅ requirements.txt looks good")
    return True

def main():
    print("🔍 Testing PDF/LaTeX Converter Dependencies & Syntax...\n")
    
    # Test syntax first
    print("1️⃣ Testing Python syntax:")
    print("-" * 30)
    syntax_results = test_syntax()
    
    # Test imports
    print("\n2️⃣ Testing imports:")
    print("-" * 20)
    import_success = test_imports()
    
    # Test functionality  
    print("\n3️⃣ Testing functionality:")
    print("-" * 25)
    functionality_success = test_functionality()
    
    # Check requirements
    print("\n4️⃣ Checking requirements:")
    print("-" * 25)
    requirements_success = check_requirements()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 FINAL RESULTS:")
    print("=" * 50)
    
    # Syntax results
    working_apps = [f for f, result in syntax_results.items() if result]
    broken_apps = [f for f, result in syntax_results.items() if not result]
    
    if working_apps:
        print(f"✅ Working app files: {', '.join(working_apps)}")
    if broken_apps:
        print(f"❌ Broken app files: {', '.join(broken_apps)}")
    
    print(f"✅ Imports: {'PASS' if import_success else 'FAIL'}")
    print(f"✅ Functionality: {'PASS' if functionality_success else 'FAIL'}")
    print(f"✅ Requirements: {'PASS' if requirements_success else 'FAIL'}")
    
    # Recommendations
    print("\n🎯 RECOMMENDATIONS:")
    print("-" * 20)
    
    if 'app_fixed.py' in working_apps:
        print("🚀 BEST: Use app_fixed.py (no syntax errors)")
        print("   Run: cp app_fixed.py app.py")
    elif 'app_simple.py' in working_apps:
        print("⚡ GOOD: Use app_simple.py (simplified but working)")
        print("   Run: cp app_simple.py app.py") 
    elif 'app.py' in working_apps:
        print("✅ OK: app.py syntax is valid")
    else:
        print("❌ NO WORKING APP FILES - Check syntax errors")
    
    if not import_success:
        print("🔧 Install dependencies: pip install -r requirements.txt")
    
    if not requirements_success:
        print("📝 Fix requirements.txt with clean dependencies")
    
    # Overall result
    overall_success = (
        len(working_apps) > 0 and 
        import_success and 
        functionality_success and 
        requirements_success
    )
    
    if overall_success:
        print("\n✅ ALL TESTS PASSED - Ready for deployment!")
        print("🚀 You can now deploy to Streamlit Cloud!")
        exit(0)
    else:
        print("\n❌ SOME TESTS FAILED - Fix issues before deploying")
        print("🔧 Run ./fix_deploy.sh for automatic fixes")
        exit(1)

if __name__ == "__main__":
    main()
