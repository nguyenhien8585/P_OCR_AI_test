"""
Utility functions for PDF/Image to LaTeX converter
"""

import re
import base64
from typing import List, Tuple, Optional
import streamlit as st
from PIL import Image
import io
import time

def clean_latex_content(latex_text: str) -> str:
    """
    Làm sạch và chuẩn hóa nội dung LaTeX
    """
    if not latex_text:
        return ""
    
    # Loại bỏ các ký tự không mong muốn
    cleaned = latex_text.strip()
    
    # Chuẩn hóa các công thức LaTeX
    # Thay thế các pattern không đúng format
    cleaned = re.sub(r'\$\s*\$', '', cleaned)  # Loại bỏ $$ rỗng
    cleaned = re.sub(r'\$\$\s*\$\$', '', cleaned)  # Loại bỏ $$$$ rỗng
    
    # Đảm bảo có khoảng trắng sau dấu chấm câu
    cleaned = re.sub(r'\.(?=[a-zA-Z])', '. ', cleaned)
    
    # Chuẩn hóa line breaks
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    
    return cleaned

def validate_api_key(api_key: str) -> bool:
    """
    Kiểm tra tính hợp lệ của API key
    """
    if not api_key:
        return False
    
    # Kiểm tra độ dài tối thiểu (Gemini API key thường dài khoảng 39 ký tự)
    if len(api_key) < 20:
        return False
    
    # Kiểm tra format cơ bản (chỉ chứa ký tự alphanum và dấu gạch ngang, underscore)
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        return False
    
    return True

def format_file_size(size_bytes: int) -> str:
    """
    Chuyển đổi kích thước file sang định dạng human-readable
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def validate_image_file(uploaded_file) -> Tuple[bool, str]:
    """
    Kiểm tra tính hợp lệ của file ảnh
    """
    if not uploaded_file:
        return False, "Không có file được upload"
    
    # Kiểm tra kích thước file (giới hạn 10MB)
    if uploaded_file.size > 10 * 1024 * 1024:
        return False, f"File quá lớn: {format_file_size(uploaded_file.size)}. Giới hạn: 10MB"
    
    # Kiểm tra định dạng file
    allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/bmp', 'image/tiff']
    if uploaded_file.type not in allowed_types:
        return False, f"Định dạng file không được hỗ trợ: {uploaded_file.type}"
    
    try:
        # Thử mở file để kiểm tra tính hợp lệ
        Image.open(uploaded_file)
        return True, "OK"
    except Exception as e:
        return False, f"File ảnh bị lỗi: {str(e)}"

def validate_pdf_file(uploaded_file) -> Tuple[bool, str]:
    """
    Kiểm tra tính hợp lệ của file PDF
    """
    if not uploaded_file:
        return False, "Không có file được upload"
    
    # Kiểm tra kích thước file (giới hạn 50MB)
    if uploaded_file.size > 50 * 1024 * 1024:
        return False, f"File quá lớn: {format_file_size(uploaded_file.size)}. Giới hạn: 50MB"
    
    # Kiểm tra định dạng file
    if uploaded_file.type != 'application/pdf':
        return False, f"Không phải file PDF: {uploaded_file.type}"
    
    # Kiểm tra magic bytes của PDF
    file_header = uploaded_file.read(4)
    uploaded_file.seek(0)  # Reset file pointer
    
    if file_header != b'%PDF':
        return False, "File không phải định dạng PDF hợp lệ"
    
    return True, "OK"

def create_download_link(file_content: bytes, filename: str, mime_type: str) -> str:
    """
    Tạo link download cho file
    """
    b64_content = base64.b64encode(file_content).decode()
    return f'<a href="data:{mime_type};base64,{b64_content}" download="{filename}">📥 Tải {filename}</a>'

def extract_latex_equations(text: str) -> List[str]:
    """
    Trích xuất các công thức LaTeX từ text
    """
    # Pattern cho inline math: $...$
    inline_pattern = r'\$([^$]+)\$'
    
    # Pattern cho display math: $$...$$
    display_pattern = r'\$\$([^$]+)\$\$'
    
    inline_equations = re.findall(inline_pattern, text)
    display_equations = re.findall(display_pattern, text)
    
    all_equations = []
    all_equations.extend([f"${eq}$" for eq in inline_equations])
    all_equations.extend([f"$${eq}$$" for eq in display_equations])
    
    return all_equations

def count_math_content(text: str) -> dict:
    """
    Đếm số lượng công thức toán học trong text
    """
    equations = extract_latex_equations(text)
    
    inline_count = len([eq for eq in equations if eq.startswith('$') and not eq.startswith('$$')])
    display_count = len([eq for eq in equations if eq.startswith('$$')])
    
    return {
        'total_equations': len(equations),
        'inline_equations': inline_count,
        'display_equations': display_count,
        'text_length': len(text),
        'has_math': len(equations) > 0
    }

def show_processing_stats(stats: dict):
    """
    Hiển thị thống kê quá trình xử lý
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("📊 Tổng công thức", stats.get('total_equations', 0))
    
    with col2:
        st.metric("📝 Inline equations", stats.get('inline_equations', 0))
    
    with col3:
        st.metric("📋 Display equations", stats.get('display_equations', 0))

def create_latex_preview(latex_content: str, max_length: int = 1000) -> str:
    """
    Tạo preview cho nội dung LaTeX
    """
    if len(latex_content) <= max_length:
        return latex_content
    
    preview = latex_content[:max_length]
    # Cắt tại dấu xuống dòng gần nhất
    last_newline = preview.rfind('\n')
    if last_newline > max_length - 100:  # Nếu newline gần cuối
        preview = preview[:last_newline]
    
    return preview + f"\n\n... (còn {len(latex_content) - len(preview)} ký tự)"

def generate_filename(original_name: str, suffix: str = "converted") -> str:
    """
    Tạo tên file output
    """
    if '.' in original_name:
        name, ext = original_name.rsplit('.', 1)
        return f"{name}_{suffix}.docx"
    else:
        return f"{original_name}_{suffix}.docx"

def log_conversion_stats(input_type: str, file_count: int, success: bool):
    """
    Log thống kê conversion (có thể mở rộng để lưu vào database)
    """
    status = "SUCCESS" if success else "FAILED"
    st.write(f"📊 Conversion Stats: {input_type} | Files: {file_count} | Status: {status}")

class ConversionHistory:
    """
    Class để quản lý lịch sử conversion trong session
    """
    
    @staticmethod
    def add_to_history(input_type: str, filename: str, success: bool, latex_length: int = 0):
        """Thêm vào lịch sử conversion"""
        if 'conversion_history' not in st.session_state:
            st.session_state.conversion_history = []
        
        entry = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'input_type': input_type,
            'filename': filename,
            'success': success,
            'latex_length': latex_length
        }
        
        st.session_state.conversion_history.append(entry)
        st.session_state.conversion_time = entry['timestamp']
        
        # Giới hạn lịch sử chỉ 10 entries gần nhất
        if len(st.session_state.conversion_history) > 10:
            st.session_state.conversion_history = st.session_state.conversion_history[-10:]
    
    @staticmethod
    def show_history():
        """Hiển thị lịch sử conversion"""
        if 'conversion_history' not in st.session_state or not st.session_state.conversion_history:
            st.info("Chưa có lịch sử conversion nào")
            return
        
        st.subheader("📊 Lịch sử conversion")
        
        for i, entry in enumerate(reversed(st.session_state.conversion_history)):
            status_icon = "✅" if entry['success'] else "❌"
            type_icon = "📄" if entry['input_type'] == 'PDF' else "🖼️"
            
            st.write(f"{status_icon} {type_icon} **{entry['filename']}** - {entry['latex_length']} chars LaTeX")
            st.caption(f"⏰ {entry['timestamp']}")
    
    @staticmethod
    def clear_history():
        """Xóa lịch sử"""
        if 'conversion_history' in st.session_state:
            del st.session_state.conversion_history
        if 'conversion_time' in st.session_state:
            del st.session_state.conversion_time
        st.success("Đã xóa lịch sử conversion")

def show_tips_and_tricks():
    """
    Hiển thị tips và tricks cho người dùng
    """
    with st.expander("💡 Tips & Tricks"):
        st.markdown("""
        ### 📋 Để có kết quả tốt nhất:
        
        **Cho PDF:**
        - Sử dụng PDF có chất lượng cao, không bị mờ
        - Tránh PDF được scan với độ phân giải thấp
        - PDF không nên có nhiều hình ảnh phức tạp
        
        **Cho ảnh:**
        - Độ phân giải tối thiểu 300 DPI
        - Ảnh có độ tương phản tốt
        - Công thức rõ ràng, không bị mờ
        - Tránh ảnh có background phức tạp
        
        **Định dạng LaTeX:**
        - Inline equations: `$x^2 + y^2 = z^2$`
        - Display equations: `$$\\int_0^1 x dx = \\frac{1}{2}$$`
        - Matrix: `$$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$$`
        
        **Khắc phục sự cố:**
        - Nếu API lỗi, kiểm tra lại API key
        - File quá lớn? Chia nhỏ hoặc nén ảnh
        - Kết quả không chính xác? Thử cắt ảnh nhỏ hơn
        """)

def create_sample_prompts() -> dict:
    """
    Tạo các prompt mẫu cho các loại nội dung khác nhau
    """
    return {
        'math_equations': """
        Chuyển đổi tất cả công thức toán học trong ảnh thành LaTeX format.
        Sử dụng ${...}$ cho inline equations và $${...}$$ cho display equations.
        Giữ nguyên cấu trúc và thứ tự của nội dung.
        """,
        
        'physics_formulas': """
        Chuyển đổi các công thức vật lý thành LaTeX format.
        Chú ý các ký hiệu đặc biệt như vector, tensor, đạo hàm riêng.
        Sử dụng notation chuẩn cho các đại lượng vật lý.
        """,
        
        'chemistry_equations': """
        Chuyển đổi các phương trình hóa học và công thức thành LaTeX.
        Sử dụng ký hiệu chuẩn cho các nguyên tố và phản ứng.
        Chú ý các chỉ số trên và dưới.
        """,
        
        'statistics_formulas': """
        Chuyển đổi các công thức thống kê thành LaTeX format.
        Chú ý các ký hiệu như sigma, mu, probability notation.
        Giữ đúng format cho distributions và test statistics.
        """
    }

# Error handling decorators
def handle_api_errors(func):
    """
    Decorator để xử lý lỗi API
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            if "API key" in error_msg:
                st.error("❌ Lỗi API Key. Vui lòng kiểm tra lại API key!")
            elif "timeout" in error_msg.lower():
                st.error("⏰ Timeout. Vui lòng thử lại sau ít phút.")
            elif "rate limit" in error_msg.lower():
                st.error("🚫 Đã vượt quá giới hạn API. Vui lòng đợi và thử lại.")
            else:
                st.error(f"❌ Lỗi: {error_msg}")
            return None
    return wrapper
