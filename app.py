import streamlit as st
import requests
import base64
import io
import json
from PIL import Image
import fitz  # PyMuPDF
from docx import Document
import tempfile
import os
from typing import List, Tuple
import re

# Import utility functions
try:
    from utils import (
        clean_latex_content, validate_api_key, format_file_size,
        validate_image_file, validate_pdf_file, extract_latex_equations,
        count_math_content, show_processing_stats, create_latex_preview,
        generate_filename, ConversionHistory, show_tips_and_tricks,
        handle_api_errors
    )
except ImportError:
    # Fallback nếu utils.py không có
    import time
    def clean_latex_content(text): return text.strip()
    def validate_api_key(key): return len(key) > 10 if key else False
    def format_file_size(size): return f"{size/1024:.1f} KB"
    def validate_image_file(f): return (True, "OK") if f else (False, "No file")
    def validate_pdf_file(f): return (True, "OK") if f else (False, "No file")
    def extract_latex_equations(text): return []
    def count_math_content(text): return {'total_equations': 0}
    def show_processing_stats(stats): pass
    def create_latex_preview(text, max_len=1000): return text[:max_len]
    def generate_filename(name, suffix="converted"): return f"{name}_{suffix}.docx"
    class ConversionHistory:
        @staticmethod
        def add_to_history(input_type, filename, success, latex_length=0):
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
        @staticmethod
        def show_history(): 
            if 'conversion_history' in st.session_state:
                st.write("📊 Lịch sử:", len(st.session_state.conversion_history), "items")
        @staticmethod
        def clear_history():
            if 'conversion_history' in st.session_state:
                del st.session_state.conversion_history
    def show_tips_and_tricks(): pass
    def handle_api_errors(func): return func

# Cấu hình trang
st.set_page_config(
    page_title="PDF/Image to LaTeX Converter",
    page_icon="📝",
    layout="wide"
)

# CSS tùy chỉnh
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #2E86AB;
        font-size: 2.5rem;
        margin-bottom: 2rem;
    }
    .tab-content {
        padding: 2rem;
        border-radius: 10px;
        background-color: #f8f9fa;
        margin: 1rem 0;
    }
    .latex-output {
        background-color: #f4f4f4;
        padding: 1rem;
        border-radius: 5px;
        font-family: 'Courier New', monospace;
        border-left: 4px solid #2E86AB;
    }
    .success-message {
        color: #28a745;
        font-weight: bold;
    }
    .error-message {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

class GeminiAPI:
    def __init__(self, api_key: str):
        if not validate_api_key(api_key):
            raise ValueError("API key không hợp lệ")
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    def encode_image(self, image_data: bytes) -> str:
        """Mã hóa ảnh thành base64"""
        return base64.b64encode(image_data).decode('utf-8')
    
    @handle_api_errors
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str:
        """Chuyển đổi nội dung sang LaTeX sử dụng Gemini API"""
        headers = {
            "Content-Type": "application/json"
        }
        
        # Validate input data
        if not content_data:
            raise ValueError("Không có dữ liệu để xử lý")
        
        if len(content_data) > 10 * 1024 * 1024:  # 10MB limit
            raise ValueError("File quá lớn. Giới hạn 10MB")
        
        # Tạo payload cho API
        if content_type.startswith('image/'):
            mime_type = content_type
            encoded_content = self.encode_image(content_data)
        else:
            mime_type = "image/png"  # Cho PDF đã convert thành ảnh
            encoded_content = self.encode_image(content_data)
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded_content
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 1,
                "topP": 0.8,
                "maxOutputTokens": 8192,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH", 
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers=headers,
                json=payload,
                timeout=90  # Tăng timeout lên 90s
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    # Clean và validate LaTeX output
                    cleaned_content = clean_latex_content(content)
                    return cleaned_content
                else:
                    raise Exception("API không trả về kết quả hợp lệ")
            elif response.status_code == 401:
                raise Exception("API key không hợp lệ hoặc đã hết hạn")
            elif response.status_code == 429:
                raise Exception("Đã vượt quá giới hạn rate limit")
            elif response.status_code == 400:
                raise Exception("Request không hợp lệ")
            else:
                raise Exception(f"API Error {response.status_code}: {response.text}")
        
        except requests.exceptions.Timeout:
            raise Exception("Request timeout - thử lại sau ít phút")
        except requests.exceptions.ConnectionError:
            raise Exception("Lỗi kết nối mạng")
        except Exception as e:
            raise Exception(str(e))

class PDFProcessor:
    @staticmethod
    def extract_images_and_text(pdf_file) -> List[Tuple[Image.Image, int]]:
        """Trích xuất ảnh và chuyển đổi trang PDF thành ảnh"""
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        images = []
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            
            # Chuyển đổi trang thành ảnh
            mat = fitz.Matrix(2.0, 2.0)  # Tăng độ phân giải
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class WordExporter:
    @staticmethod
    def create_word_document(latex_content: str, images: List[Image.Image] = None) -> io.BytesIO:
        """Tạo file Word với equations từ LaTeX"""
        doc = Document()
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu đã chuyển đổi từ PDF/Ảnh', 0)
        title.alignment = 1  # Center alignment
        
        # Thêm thông tin metadata
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter")
        doc.add_paragraph(f"Thời gian: {str(st.session_state.get('conversion_time', 'N/A'))}")
        doc.add_paragraph("")  # Empty line
        
        # Xử lý nội dung LaTeX
        lines = latex_content.split('\n')
        current_paragraph = None
        
        for line in lines:
            line = line.strip()
            
            # Skip comments
            if line.startswith('<!--') and line.endswith('-->'):
                # Add as heading for source file info
                if 'Trang' in line or 'Ảnh' in line:
                    doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                continue
            
            if not line:
                current_paragraph = None
                continue
            
            # Tìm các công thức LaTeX
            latex_patterns = re.findall(r'\$\$([^$]+)\$\$|\$([^$]+)\

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key và settings
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        api_key = st.text_input(
            "Gemini API Key", 
            type="password", 
            help="Nhập API key từ Google AI Studio",
            placeholder="Paste your API key here..."
        )
        
        # Validation API key real-time
        if api_key:
            if validate_api_key(api_key):
                st.success("✅ API key hợp lệ")
            else:
                st.error("❌ API key không hợp lệ")
                st.info("API key phải có ít nhất 20 ký tự và chỉ chứa chữ cái, số, dấu gạch ngang và underscore")
        
        st.markdown("---")
        
        # Settings
        st.subheader("🎛️ Tùy chọn")
        
        max_file_size = st.selectbox(
            "Giới hạn kích thước file",
            ["10MB", "20MB", "50MB"],
            index=1
        )
        
        output_format = st.selectbox(
            "Định dạng output",
            ["LaTeX ($...$)", "MathJax", "AsciiMath"],
            index=0
        )
        
        include_images = st.checkbox("Bao gồm hình ảnh trong Word", value=True)
        
        st.markdown("---")
        
        # Conversion History
        st.subheader("📊 Lịch sử")
        ConversionHistory.show_history()
        
        if st.button("🗑️ Xóa lịch sử"):
            ConversionHistory.clear_history()
            st.rerun()
        
        st.markdown("---")
        
        # Tips và hướng dẫn
        show_tips_and_tricks()
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại [Google AI Studio](https://makersuite.google.com/app/apikey)")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2, tab3 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX", "📋 Batch Processing"])
    
    # Khởi tạo API với error handling
    try:
        gemini_api = GeminiAPI(api_key)
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo API: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học"
        )
        
        if uploaded_pdf:
            # Validate PDF file
            is_valid, error_msg = validate_pdf_file(uploaded_pdf)
            if not is_valid:
                st.error(f"❌ {error_msg}")
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                
                # Hiển thị thông tin file
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                # Extract images từ PDF
                with st.spinner("🔄 Đang xử lý PDF..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang")
                        
                        # Hiển thị preview các trang
                        for img, page_num in pdf_images[:3]:  # Hiển thị tối đa 3 trang đầu
                            st.write(f"**Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 3:
                            st.info(f"... và {len(pdf_images) - 3} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        conversion_successful = True
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tạo prompt cho Gemini
                            prompt = f"""
                            Hãy chuyển đổi tất cả nội dung trong ảnh trang {page_num} thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text thường và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn (\\frac, \\sqrt, \\sum, \\int, ...)
                            6. Xử lý đúng các chỉ số trên/dưới, ma trận, hệ phương trình
                            7. Nếu có bảng, sử dụng tabular environment
                            8. Mô tả ngắn gọn các hình vẽ/biểu đồ nếu có
                            
                            ĐỊNH DẠNG OUTPUT MONG MUỐN:
                            - Text thường: viết bình thường
                            - Công thức inline: ${{x^2 + y^2 = z^2}}$
                            - Công thức display: ${{\\int_0^1 x dx = \\frac{{1}}{{2}}}}$
                            - Ma trận: ${{A = \\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            
                            Hãy đảm bảo LaTeX output có thể compile được và chính xác 100%.
                            """
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                                    conversion_successful = False
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                                conversion_successful = False
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        if conversion_successful:
                            status_text.text("✅ Hoàn thành chuyển đổi!")
                            
                            # Combine và hiển thị kết quả
                            combined_latex = "\n".join(all_latex_content)
                            
                            # Thống kê kết quả
                            stats = count_math_content(combined_latex)
                            show_processing_stats(stats)
                            
                            # Hiển thị preview
                            st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                            preview_content = create_latex_preview(combined_latex, 2000)
                            st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            # Lưu vào session state để tái sử dụng
                            st.session_state.pdf_latex_content = combined_latex
                            st.session_state.pdf_images = [img for img, _ in pdf_images]
                            
                            # Add to history
                            ConversionHistory.add_to_history(
                                "PDF", uploaded_pdf.name, True, len(combined_latex)
                            )
                            
                        else:
                            status_text.text("❌ Một số trang không thể xử lý")
                            ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                
                # Tạo file Word nếu đã có kết quả
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.pdf_images if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    images_to_include
                                )
                                
                                filename = generate_filename(uploaded_pdf.name, "latex_converted")
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX source
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.pdf_latex_content,
                                    file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab xử lý ảnh
    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học"
        )
        
        if uploaded_images:
            # Validate all images
            all_valid = True
            for uploaded_image in uploaded_images:
                is_valid, error_msg = validate_image_file(uploaded_image)
                if not is_valid:
                    st.error(f"❌ {uploaded_image.name}: {error_msg}")
                    all_valid = False
            
            if not all_valid:
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                total_size = sum(img.size for img in uploaded_images)
                st.info(f"📁 Số ảnh: {len(uploaded_images)}")
                st.info(f"📏 Tổng kích thước: {format_file_size(total_size)}")
                
                # Hiển thị preview
                for i, uploaded_image in enumerate(uploaded_images[:5]):  # Tối đa 5 ảnh
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                    st.caption(f"📏 {image.size[0]}x{image.size[1]} pixels")
                
                if len(uploaded_images) > 5:
                    st.info(f"... và {len(uploaded_images) - 5} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                # Tùy chọn xử lý
                processing_mode = st.radio(
                    "Chế độ xử lý:",
                    ["Tự động", "Tùy chỉnh prompt"],
                    help="Tự động: sử dụng prompt mặc định. Tùy chỉnh: bạn có thể chỉnh sửa prompt"
                )
                
                custom_prompt = ""
                if processing_mode == "Tùy chỉnh prompt":
                    custom_prompt = st.text_area(
                        "Prompt tùy chỉnh:",
                        value="""Chuyển đổi nội dung toán học thành LaTeX format chính xác.
Sử dụng ${...}$ cho inline và ${...}$ cho display equations.
Giữ nguyên cấu trúc và thứ tự nội dung.""",
                        height=100
                    )
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh", key="convert_images"):
                    all_latex_content = []
                    conversion_successful = True
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}: {uploaded_image.name}")
                        
                        # Đọc ảnh
                        image_bytes = uploaded_image.getvalue()
                        
                        # Tạo prompt
                        if processing_mode == "Tùy chỉnh prompt" and custom_prompt:
                            prompt = custom_prompt
                        else:
                            prompt = f"""
                            Chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)  
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn
                            6. Xử lý đúng ma trận, hệ phương trình, tích phân, đạo hàm
                            7. Nếu có biểu đồ/hình vẽ, mô tả ngắn gọn
                            8. Đảm bảo LaTeX có thể compile được
                            
                            ĐỊNH DẠNG OUTPUT:
                            - Text: viết bình thường
                            - Inline: ${{x^2 + 1}}$
                            - Display: ${{\\int_0^\\infty e^{{-x}} dx = 1}}$
                            - Ma trận: ${{\\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            """
                        
                        # Gọi API
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                all_latex_content.append(
                                    f"<!-- Ảnh {i+1}: {uploaded_image.name} -->\n{latex_result}\n"
                                )
                            else:
                                st.warning(f"⚠️ Không thể xử lý ảnh {uploaded_image.name}")
                                conversion_successful = False
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý {uploaded_image.name}: {str(e)}")
                            conversion_successful = False
                        
                        progress_bar.progress((i + 1) / len(uploaded_images))
                    
                    if conversion_successful:
                        status_text.text("✅ Hoàn thành chuyển đổi!")
                        
                        # Combine và hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        # Thống kê
                        stats = count_math_content(combined_latex)
                        show_processing_stats(stats)
                        
                        # Preview
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        preview_content = create_latex_preview(combined_latex, 2000)
                        st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session
                        st.session_state.image_latex_content = combined_latex
                        st.session_state.image_list = [Image.open(img) for img in uploaded_images]
                        
                        # Add to history
                        ConversionHistory.add_to_history(
                            "Images", f"{len(uploaded_images)} files", True, len(combined_latex)
                        )
                    else:
                        status_text.text("❌ Một số ảnh không thể xử lý")
                        ConversionHistory.add_to_history("Images", f"{len(uploaded_images)} files", False)
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.image_list if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    images_to_include
                                )
                                
                                filename = "images_latex_converted.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab Batch Processing
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📋 Xử lý hàng loạt")
        
        st.info("🚀 Tính năng này cho phép xử lý nhiều file PDF và ảnh cùng lúc")
        
        # Upload multiple files
        batch_files = st.file_uploader(
            "Chọn nhiều file (PDF và ảnh)",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload nhiều file PDF và ảnh để xử lý cùng lúc"
        )
        
        if batch_files:
            st.write(f"📁 Đã chọn {len(batch_files)} file(s)")
            
            # Phân loại files
            pdf_files = [f for f in batch_files if f.type == 'application/pdf']
            image_files = [f for f in batch_files if f.type.startswith('image/')]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📄 PDF files", len(pdf_files))
            with col2:
                st.metric("🖼️ Image files", len(image_files))
            
            # Hiển thị danh sách files
            with st.expander("📂 Danh sách files"):
                for i, file in enumerate(batch_files):
                    file_type = "📄" if file.type == 'application/pdf' else "🖼️"
                    st.write(f"{file_type} {file.name} ({format_file_size(file.size)})")
            
            # Batch processing options
            st.subheader("⚙️ Tùy chọn xử lý")
            
            col1, col2 = st.columns(2)
            with col1:
                merge_output = st.checkbox("Gộp tất cả thành 1 file Word", value=True)
                include_source_name = st.checkbox("Ghi rõ tên file gốc", value=True)
            
            with col2:
                skip_errors = st.checkbox("Bỏ qua files lỗi", value=True)
                max_concurrent = st.slider("Số file xử lý đồng thời", 1, 5, 2)
            
            if st.button("🚀 Bắt đầu xử lý hàng loạt", key="batch_process"):
                batch_results = []
                
                # Create main progress bar
                main_progress = st.progress(0)
                main_status = st.empty()
                
                for i, file in enumerate(batch_files):
                    main_status.text(f"Đang xử lý {i+1}/{len(batch_files)}: {file.name}")
                    
                    try:
                        if file.type == 'application/pdf':
                            # Process PDF
                            pdf_images = PDFProcessor.extract_images_and_text(file)
                            
                            file_latex_content = []
                            for img, page_num in pdf_images:
                                img_buffer = io.BytesIO()
                                img.save(img_buffer, format='PNG')
                                img_bytes = img_buffer.getvalue()
                                
                                prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                                Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                                
                                latex_result = gemini_api.convert_to_latex(
                                    img_bytes, "image/png", prompt
                                )
                                if latex_result:
                                    file_latex_content.append(latex_result)
                            
                            combined_content = "\n".join(file_latex_content)
                            
                        else:
                            # Process Image
                            image_bytes = file.getvalue()
                            prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                            Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                            
                            combined_content = gemini_api.convert_to_latex(
                                image_bytes, file.type, prompt
                            )
                        
                        if combined_content:
                            if include_source_name:
                                combined_content = f"<!-- Source: {file.name} -->\n{combined_content}"
                            
                            batch_results.append({
                                'filename': file.name,
                                'content': combined_content,
                                'success': True
                            })
                        else:
                            raise Exception("Không nhận được kết quả từ API")
                    
                    except Exception as e:
                        error_msg = f"Lỗi xử lý {file.name}: {str(e)}"
                        if skip_errors:
                            st.warning(f"⚠️ {error_msg}")
                            batch_results.append({
                                'filename': file.name,
                                'content': f"<!-- ERROR: {error_msg} -->",
                                'success': False
                            })
                        else:
                            st.error(f"❌ {error_msg}")
                            break
                    
                    main_progress.progress((i + 1) / len(batch_files))
                
                # Process results
                successful_files = [r for r in batch_results if r['success']]
                failed_files = [r for r in batch_results if not r['success']]
                
                main_status.text(f"✅ Hoàn thành: {len(successful_files)} thành công, {len(failed_files)} lỗi")
                
                if successful_files:
                    if merge_output:
                        # Merge all content
                        all_content = "\n\n".join([r['content'] for r in successful_files])
                        
                        # Show stats
                        stats = count_math_content(all_content)
                        show_processing_stats(stats)
                        
                        # Create Word file
                        st.subheader("📥 Tải kết quả")
                        
                        if st.button("📥 Tạo file Word gộp", key="create_batch_word"):
                            with st.spinner("🔄 Đang tạo file Word..."):
                                try:
                                    word_buffer = WordExporter.create_word_document(all_content)
                                    
                                    st.download_button(
                                        label="📥 Tải file Word gộp",
                                        data=word_buffer.getvalue(),
                                        file_name="batch_converted.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.download_button(
                                        label="📝 Tải LaTeX source",
                                        data=all_content,
                                        file_name="batch_converted.tex",
                                        mime="text/plain"
                                    )
                                    
                                    st.success("✅ File đã được tạo thành công!")
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo file: {str(e)}")
                    
                    else:
                        # Individual downloads
                        st.subheader("📥 Tải từng file")
                        for result in successful_files:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"✅ {result['filename']}")
                            with col2:
                                st.download_button(
                                    label="📥 Tải",
                                    data=result['content'],
                                    file_name=f"{result['filename']}.tex",
                                    mime="text/plain",
                                    key=f"download_{result['filename']}"
                                )
                
                # Add batch to history
                ConversionHistory.add_to_history(
                    "Batch", 
                    f"{len(batch_files)} files", 
                    len(successful_files) > 0,
                    sum(len(r['content']) for r in successful_files)
                )
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>Hỗ trợ chuyển đổi PDF và ảnh sang LaTeX với độ chính xác cao</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main(), line)
            
            if latex_patterns:
                # Tạo paragraph mới nếu cần
                if current_paragraph is None:
                    current_paragraph = doc.add_paragraph()
                
                # Xử lý line có chứa LaTeX
                remaining_text = line
                
                # Replace display math ($...$) first
                display_matches = re.finditer(r'\$\$([^$]+)\$\

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key và settings
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        api_key = st.text_input(
            "Gemini API Key", 
            type="password", 
            help="Nhập API key từ Google AI Studio",
            placeholder="Paste your API key here..."
        )
        
        # Validation API key real-time
        if api_key:
            if validate_api_key(api_key):
                st.success("✅ API key hợp lệ")
            else:
                st.error("❌ API key không hợp lệ")
                st.info("API key phải có ít nhất 20 ký tự và chỉ chứa chữ cái, số, dấu gạch ngang và underscore")
        
        st.markdown("---")
        
        # Settings
        st.subheader("🎛️ Tùy chọn")
        
        max_file_size = st.selectbox(
            "Giới hạn kích thước file",
            ["10MB", "20MB", "50MB"],
            index=1
        )
        
        output_format = st.selectbox(
            "Định dạng output",
            ["LaTeX ($...$)", "MathJax", "AsciiMath"],
            index=0
        )
        
        include_images = st.checkbox("Bao gồm hình ảnh trong Word", value=True)
        
        st.markdown("---")
        
        # Conversion History
        st.subheader("📊 Lịch sử")
        ConversionHistory.show_history()
        
        if st.button("🗑️ Xóa lịch sử"):
            ConversionHistory.clear_history()
            st.rerun()
        
        st.markdown("---")
        
        # Tips và hướng dẫn
        show_tips_and_tricks()
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại [Google AI Studio](https://makersuite.google.com/app/apikey)")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2, tab3 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX", "📋 Batch Processing"])
    
    # Khởi tạo API với error handling
    try:
        gemini_api = GeminiAPI(api_key)
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo API: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học"
        )
        
        if uploaded_pdf:
            # Validate PDF file
            is_valid, error_msg = validate_pdf_file(uploaded_pdf)
            if not is_valid:
                st.error(f"❌ {error_msg}")
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                
                # Hiển thị thông tin file
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                # Extract images từ PDF
                with st.spinner("🔄 Đang xử lý PDF..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang")
                        
                        # Hiển thị preview các trang
                        for img, page_num in pdf_images[:3]:  # Hiển thị tối đa 3 trang đầu
                            st.write(f"**Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 3:
                            st.info(f"... và {len(pdf_images) - 3} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        conversion_successful = True
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tạo prompt cho Gemini
                            prompt = f"""
                            Hãy chuyển đổi tất cả nội dung trong ảnh trang {page_num} thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text thường và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn (\\frac, \\sqrt, \\sum, \\int, ...)
                            6. Xử lý đúng các chỉ số trên/dưới, ma trận, hệ phương trình
                            7. Nếu có bảng, sử dụng tabular environment
                            8. Mô tả ngắn gọn các hình vẽ/biểu đồ nếu có
                            
                            ĐỊNH DẠNG OUTPUT MONG MUỐN:
                            - Text thường: viết bình thường
                            - Công thức inline: ${{x^2 + y^2 = z^2}}$
                            - Công thức display: ${{\\int_0^1 x dx = \\frac{{1}}{{2}}}}$
                            - Ma trận: ${{A = \\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            
                            Hãy đảm bảo LaTeX output có thể compile được và chính xác 100%.
                            """
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                                    conversion_successful = False
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                                conversion_successful = False
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        if conversion_successful:
                            status_text.text("✅ Hoàn thành chuyển đổi!")
                            
                            # Combine và hiển thị kết quả
                            combined_latex = "\n".join(all_latex_content)
                            
                            # Thống kê kết quả
                            stats = count_math_content(combined_latex)
                            show_processing_stats(stats)
                            
                            # Hiển thị preview
                            st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                            preview_content = create_latex_preview(combined_latex, 2000)
                            st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            # Lưu vào session state để tái sử dụng
                            st.session_state.pdf_latex_content = combined_latex
                            st.session_state.pdf_images = [img for img, _ in pdf_images]
                            
                            # Add to history
                            ConversionHistory.add_to_history(
                                "PDF", uploaded_pdf.name, True, len(combined_latex)
                            )
                            
                        else:
                            status_text.text("❌ Một số trang không thể xử lý")
                            ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                
                # Tạo file Word nếu đã có kết quả
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.pdf_images if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    images_to_include
                                )
                                
                                filename = generate_filename(uploaded_pdf.name, "latex_converted")
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX source
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.pdf_latex_content,
                                    file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab xử lý ảnh
    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học"
        )
        
        if uploaded_images:
            # Validate all images
            all_valid = True
            for uploaded_image in uploaded_images:
                is_valid, error_msg = validate_image_file(uploaded_image)
                if not is_valid:
                    st.error(f"❌ {uploaded_image.name}: {error_msg}")
                    all_valid = False
            
            if not all_valid:
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                total_size = sum(img.size for img in uploaded_images)
                st.info(f"📁 Số ảnh: {len(uploaded_images)}")
                st.info(f"📏 Tổng kích thước: {format_file_size(total_size)}")
                
                # Hiển thị preview
                for i, uploaded_image in enumerate(uploaded_images[:5]):  # Tối đa 5 ảnh
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                    st.caption(f"📏 {image.size[0]}x{image.size[1]} pixels")
                
                if len(uploaded_images) > 5:
                    st.info(f"... và {len(uploaded_images) - 5} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                # Tùy chọn xử lý
                processing_mode = st.radio(
                    "Chế độ xử lý:",
                    ["Tự động", "Tùy chỉnh prompt"],
                    help="Tự động: sử dụng prompt mặc định. Tùy chỉnh: bạn có thể chỉnh sửa prompt"
                )
                
                custom_prompt = ""
                if processing_mode == "Tùy chỉnh prompt":
                    custom_prompt = st.text_area(
                        "Prompt tùy chỉnh:",
                        value="""Chuyển đổi nội dung toán học thành LaTeX format chính xác.
Sử dụng ${...}$ cho inline và ${...}$ cho display equations.
Giữ nguyên cấu trúc và thứ tự nội dung.""",
                        height=100
                    )
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh", key="convert_images"):
                    all_latex_content = []
                    conversion_successful = True
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}: {uploaded_image.name}")
                        
                        # Đọc ảnh
                        image_bytes = uploaded_image.getvalue()
                        
                        # Tạo prompt
                        if processing_mode == "Tùy chỉnh prompt" and custom_prompt:
                            prompt = custom_prompt
                        else:
                            prompt = f"""
                            Chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)  
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn
                            6. Xử lý đúng ma trận, hệ phương trình, tích phân, đạo hàm
                            7. Nếu có biểu đồ/hình vẽ, mô tả ngắn gọn
                            8. Đảm bảo LaTeX có thể compile được
                            
                            ĐỊNH DẠNG OUTPUT:
                            - Text: viết bình thường
                            - Inline: ${{x^2 + 1}}$
                            - Display: ${{\\int_0^\\infty e^{{-x}} dx = 1}}$
                            - Ma trận: ${{\\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            """
                        
                        # Gọi API
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                all_latex_content.append(
                                    f"<!-- Ảnh {i+1}: {uploaded_image.name} -->\n{latex_result}\n"
                                )
                            else:
                                st.warning(f"⚠️ Không thể xử lý ảnh {uploaded_image.name}")
                                conversion_successful = False
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý {uploaded_image.name}: {str(e)}")
                            conversion_successful = False
                        
                        progress_bar.progress((i + 1) / len(uploaded_images))
                    
                    if conversion_successful:
                        status_text.text("✅ Hoàn thành chuyển đổi!")
                        
                        # Combine và hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        # Thống kê
                        stats = count_math_content(combined_latex)
                        show_processing_stats(stats)
                        
                        # Preview
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        preview_content = create_latex_preview(combined_latex, 2000)
                        st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session
                        st.session_state.image_latex_content = combined_latex
                        st.session_state.image_list = [Image.open(img) for img in uploaded_images]
                        
                        # Add to history
                        ConversionHistory.add_to_history(
                            "Images", f"{len(uploaded_images)} files", True, len(combined_latex)
                        )
                    else:
                        status_text.text("❌ Một số ảnh không thể xử lý")
                        ConversionHistory.add_to_history("Images", f"{len(uploaded_images)} files", False)
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.image_list if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    images_to_include
                                )
                                
                                filename = "images_latex_converted.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab Batch Processing
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📋 Xử lý hàng loạt")
        
        st.info("🚀 Tính năng này cho phép xử lý nhiều file PDF và ảnh cùng lúc")
        
        # Upload multiple files
        batch_files = st.file_uploader(
            "Chọn nhiều file (PDF và ảnh)",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload nhiều file PDF và ảnh để xử lý cùng lúc"
        )
        
        if batch_files:
            st.write(f"📁 Đã chọn {len(batch_files)} file(s)")
            
            # Phân loại files
            pdf_files = [f for f in batch_files if f.type == 'application/pdf']
            image_files = [f for f in batch_files if f.type.startswith('image/')]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📄 PDF files", len(pdf_files))
            with col2:
                st.metric("🖼️ Image files", len(image_files))
            
            # Hiển thị danh sách files
            with st.expander("📂 Danh sách files"):
                for i, file in enumerate(batch_files):
                    file_type = "📄" if file.type == 'application/pdf' else "🖼️"
                    st.write(f"{file_type} {file.name} ({format_file_size(file.size)})")
            
            # Batch processing options
            st.subheader("⚙️ Tùy chọn xử lý")
            
            col1, col2 = st.columns(2)
            with col1:
                merge_output = st.checkbox("Gộp tất cả thành 1 file Word", value=True)
                include_source_name = st.checkbox("Ghi rõ tên file gốc", value=True)
            
            with col2:
                skip_errors = st.checkbox("Bỏ qua files lỗi", value=True)
                max_concurrent = st.slider("Số file xử lý đồng thời", 1, 5, 2)
            
            if st.button("🚀 Bắt đầu xử lý hàng loạt", key="batch_process"):
                batch_results = []
                
                # Create main progress bar
                main_progress = st.progress(0)
                main_status = st.empty()
                
                for i, file in enumerate(batch_files):
                    main_status.text(f"Đang xử lý {i+1}/{len(batch_files)}: {file.name}")
                    
                    try:
                        if file.type == 'application/pdf':
                            # Process PDF
                            pdf_images = PDFProcessor.extract_images_and_text(file)
                            
                            file_latex_content = []
                            for img, page_num in pdf_images:
                                img_buffer = io.BytesIO()
                                img.save(img_buffer, format='PNG')
                                img_bytes = img_buffer.getvalue()
                                
                                prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                                Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                                
                                latex_result = gemini_api.convert_to_latex(
                                    img_bytes, "image/png", prompt
                                )
                                if latex_result:
                                    file_latex_content.append(latex_result)
                            
                            combined_content = "\n".join(file_latex_content)
                            
                        else:
                            # Process Image
                            image_bytes = file.getvalue()
                            prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                            Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                            
                            combined_content = gemini_api.convert_to_latex(
                                image_bytes, file.type, prompt
                            )
                        
                        if combined_content:
                            if include_source_name:
                                combined_content = f"<!-- Source: {file.name} -->\n{combined_content}"
                            
                            batch_results.append({
                                'filename': file.name,
                                'content': combined_content,
                                'success': True
                            })
                        else:
                            raise Exception("Không nhận được kết quả từ API")
                    
                    except Exception as e:
                        error_msg = f"Lỗi xử lý {file.name}: {str(e)}"
                        if skip_errors:
                            st.warning(f"⚠️ {error_msg}")
                            batch_results.append({
                                'filename': file.name,
                                'content': f"<!-- ERROR: {error_msg} -->",
                                'success': False
                            })
                        else:
                            st.error(f"❌ {error_msg}")
                            break
                    
                    main_progress.progress((i + 1) / len(batch_files))
                
                # Process results
                successful_files = [r for r in batch_results if r['success']]
                failed_files = [r for r in batch_results if not r['success']]
                
                main_status.text(f"✅ Hoàn thành: {len(successful_files)} thành công, {len(failed_files)} lỗi")
                
                if successful_files:
                    if merge_output:
                        # Merge all content
                        all_content = "\n\n".join([r['content'] for r in successful_files])
                        
                        # Show stats
                        stats = count_math_content(all_content)
                        show_processing_stats(stats)
                        
                        # Create Word file
                        st.subheader("📥 Tải kết quả")
                        
                        if st.button("📥 Tạo file Word gộp", key="create_batch_word"):
                            with st.spinner("🔄 Đang tạo file Word..."):
                                try:
                                    word_buffer = WordExporter.create_word_document(all_content)
                                    
                                    st.download_button(
                                        label="📥 Tải file Word gộp",
                                        data=word_buffer.getvalue(),
                                        file_name="batch_converted.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.download_button(
                                        label="📝 Tải LaTeX source",
                                        data=all_content,
                                        file_name="batch_converted.tex",
                                        mime="text/plain"
                                    )
                                    
                                    st.success("✅ File đã được tạo thành công!")
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo file: {str(e)}")
                    
                    else:
                        # Individual downloads
                        st.subheader("📥 Tải từng file")
                        for result in successful_files:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"✅ {result['filename']}")
                            with col2:
                                st.download_button(
                                    label="📥 Tải",
                                    data=result['content'],
                                    file_name=f"{result['filename']}.tex",
                                    mime="text/plain",
                                    key=f"download_{result['filename']}"
                                )
                
                # Add batch to history
                ConversionHistory.add_to_history(
                    "Batch", 
                    f"{len(batch_files)} files", 
                    len(successful_files) > 0,
                    sum(len(r['content']) for r in successful_files)
                )
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>Hỗ trợ chuyển đổi PDF và ảnh sang LaTeX với độ chính xác cao</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main(), remaining_text)
                for match in reversed(list(display_matches)):
                    before_text = remaining_text[:match.start()]
                    after_text = remaining_text[match.end():]
                    latex_expr = match.group(1)
                    
                    if before_text.strip():
                        current_paragraph.add_run(before_text)
                    
                    # Add equation placeholder
                    eq_run = current_paragraph.add_run(f"\n[EQUATION: {latex_expr}]\n")
                    eq_run.font.bold = True
                    eq_run.font.italic = True
                    
                    remaining_text = after_text
                
                # Replace inline math ($...$)
                inline_matches = re.finditer(r'\$([^$]+)\

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key và settings
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        api_key = st.text_input(
            "Gemini API Key", 
            type="password", 
            help="Nhập API key từ Google AI Studio",
            placeholder="Paste your API key here..."
        )
        
        # Validation API key real-time
        if api_key:
            if validate_api_key(api_key):
                st.success("✅ API key hợp lệ")
            else:
                st.error("❌ API key không hợp lệ")
                st.info("API key phải có ít nhất 20 ký tự và chỉ chứa chữ cái, số, dấu gạch ngang và underscore")
        
        st.markdown("---")
        
        # Settings
        st.subheader("🎛️ Tùy chọn")
        
        max_file_size = st.selectbox(
            "Giới hạn kích thước file",
            ["10MB", "20MB", "50MB"],
            index=1
        )
        
        output_format = st.selectbox(
            "Định dạng output",
            ["LaTeX ($...$)", "MathJax", "AsciiMath"],
            index=0
        )
        
        include_images = st.checkbox("Bao gồm hình ảnh trong Word", value=True)
        
        st.markdown("---")
        
        # Conversion History
        st.subheader("📊 Lịch sử")
        ConversionHistory.show_history()
        
        if st.button("🗑️ Xóa lịch sử"):
            ConversionHistory.clear_history()
            st.rerun()
        
        st.markdown("---")
        
        # Tips và hướng dẫn
        show_tips_and_tricks()
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại [Google AI Studio](https://makersuite.google.com/app/apikey)")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2, tab3 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX", "📋 Batch Processing"])
    
    # Khởi tạo API với error handling
    try:
        gemini_api = GeminiAPI(api_key)
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo API: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học"
        )
        
        if uploaded_pdf:
            # Validate PDF file
            is_valid, error_msg = validate_pdf_file(uploaded_pdf)
            if not is_valid:
                st.error(f"❌ {error_msg}")
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                
                # Hiển thị thông tin file
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                # Extract images từ PDF
                with st.spinner("🔄 Đang xử lý PDF..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang")
                        
                        # Hiển thị preview các trang
                        for img, page_num in pdf_images[:3]:  # Hiển thị tối đa 3 trang đầu
                            st.write(f"**Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 3:
                            st.info(f"... và {len(pdf_images) - 3} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        conversion_successful = True
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tạo prompt cho Gemini
                            prompt = f"""
                            Hãy chuyển đổi tất cả nội dung trong ảnh trang {page_num} thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text thường và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn (\\frac, \\sqrt, \\sum, \\int, ...)
                            6. Xử lý đúng các chỉ số trên/dưới, ma trận, hệ phương trình
                            7. Nếu có bảng, sử dụng tabular environment
                            8. Mô tả ngắn gọn các hình vẽ/biểu đồ nếu có
                            
                            ĐỊNH DẠNG OUTPUT MONG MUỐN:
                            - Text thường: viết bình thường
                            - Công thức inline: ${{x^2 + y^2 = z^2}}$
                            - Công thức display: ${{\\int_0^1 x dx = \\frac{{1}}{{2}}}}$
                            - Ma trận: ${{A = \\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            
                            Hãy đảm bảo LaTeX output có thể compile được và chính xác 100%.
                            """
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                                    conversion_successful = False
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                                conversion_successful = False
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        if conversion_successful:
                            status_text.text("✅ Hoàn thành chuyển đổi!")
                            
                            # Combine và hiển thị kết quả
                            combined_latex = "\n".join(all_latex_content)
                            
                            # Thống kê kết quả
                            stats = count_math_content(combined_latex)
                            show_processing_stats(stats)
                            
                            # Hiển thị preview
                            st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                            preview_content = create_latex_preview(combined_latex, 2000)
                            st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            # Lưu vào session state để tái sử dụng
                            st.session_state.pdf_latex_content = combined_latex
                            st.session_state.pdf_images = [img for img, _ in pdf_images]
                            
                            # Add to history
                            ConversionHistory.add_to_history(
                                "PDF", uploaded_pdf.name, True, len(combined_latex)
                            )
                            
                        else:
                            status_text.text("❌ Một số trang không thể xử lý")
                            ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                
                # Tạo file Word nếu đã có kết quả
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.pdf_images if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    images_to_include
                                )
                                
                                filename = generate_filename(uploaded_pdf.name, "latex_converted")
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX source
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.pdf_latex_content,
                                    file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab xử lý ảnh
    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học"
        )
        
        if uploaded_images:
            # Validate all images
            all_valid = True
            for uploaded_image in uploaded_images:
                is_valid, error_msg = validate_image_file(uploaded_image)
                if not is_valid:
                    st.error(f"❌ {uploaded_image.name}: {error_msg}")
                    all_valid = False
            
            if not all_valid:
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                total_size = sum(img.size for img in uploaded_images)
                st.info(f"📁 Số ảnh: {len(uploaded_images)}")
                st.info(f"📏 Tổng kích thước: {format_file_size(total_size)}")
                
                # Hiển thị preview
                for i, uploaded_image in enumerate(uploaded_images[:5]):  # Tối đa 5 ảnh
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                    st.caption(f"📏 {image.size[0]}x{image.size[1]} pixels")
                
                if len(uploaded_images) > 5:
                    st.info(f"... và {len(uploaded_images) - 5} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                # Tùy chọn xử lý
                processing_mode = st.radio(
                    "Chế độ xử lý:",
                    ["Tự động", "Tùy chỉnh prompt"],
                    help="Tự động: sử dụng prompt mặc định. Tùy chỉnh: bạn có thể chỉnh sửa prompt"
                )
                
                custom_prompt = ""
                if processing_mode == "Tùy chỉnh prompt":
                    custom_prompt = st.text_area(
                        "Prompt tùy chỉnh:",
                        value="""Chuyển đổi nội dung toán học thành LaTeX format chính xác.
Sử dụng ${...}$ cho inline và ${...}$ cho display equations.
Giữ nguyên cấu trúc và thứ tự nội dung.""",
                        height=100
                    )
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh", key="convert_images"):
                    all_latex_content = []
                    conversion_successful = True
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}: {uploaded_image.name}")
                        
                        # Đọc ảnh
                        image_bytes = uploaded_image.getvalue()
                        
                        # Tạo prompt
                        if processing_mode == "Tùy chỉnh prompt" and custom_prompt:
                            prompt = custom_prompt
                        else:
                            prompt = f"""
                            Chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)  
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn
                            6. Xử lý đúng ma trận, hệ phương trình, tích phân, đạo hàm
                            7. Nếu có biểu đồ/hình vẽ, mô tả ngắn gọn
                            8. Đảm bảo LaTeX có thể compile được
                            
                            ĐỊNH DẠNG OUTPUT:
                            - Text: viết bình thường
                            - Inline: ${{x^2 + 1}}$
                            - Display: ${{\\int_0^\\infty e^{{-x}} dx = 1}}$
                            - Ma trận: ${{\\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            """
                        
                        # Gọi API
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                all_latex_content.append(
                                    f"<!-- Ảnh {i+1}: {uploaded_image.name} -->\n{latex_result}\n"
                                )
                            else:
                                st.warning(f"⚠️ Không thể xử lý ảnh {uploaded_image.name}")
                                conversion_successful = False
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý {uploaded_image.name}: {str(e)}")
                            conversion_successful = False
                        
                        progress_bar.progress((i + 1) / len(uploaded_images))
                    
                    if conversion_successful:
                        status_text.text("✅ Hoàn thành chuyển đổi!")
                        
                        # Combine và hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        # Thống kê
                        stats = count_math_content(combined_latex)
                        show_processing_stats(stats)
                        
                        # Preview
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        preview_content = create_latex_preview(combined_latex, 2000)
                        st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session
                        st.session_state.image_latex_content = combined_latex
                        st.session_state.image_list = [Image.open(img) for img in uploaded_images]
                        
                        # Add to history
                        ConversionHistory.add_to_history(
                            "Images", f"{len(uploaded_images)} files", True, len(combined_latex)
                        )
                    else:
                        status_text.text("❌ Một số ảnh không thể xử lý")
                        ConversionHistory.add_to_history("Images", f"{len(uploaded_images)} files", False)
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.image_list if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    images_to_include
                                )
                                
                                filename = "images_latex_converted.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab Batch Processing
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📋 Xử lý hàng loạt")
        
        st.info("🚀 Tính năng này cho phép xử lý nhiều file PDF và ảnh cùng lúc")
        
        # Upload multiple files
        batch_files = st.file_uploader(
            "Chọn nhiều file (PDF và ảnh)",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload nhiều file PDF và ảnh để xử lý cùng lúc"
        )
        
        if batch_files:
            st.write(f"📁 Đã chọn {len(batch_files)} file(s)")
            
            # Phân loại files
            pdf_files = [f for f in batch_files if f.type == 'application/pdf']
            image_files = [f for f in batch_files if f.type.startswith('image/')]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📄 PDF files", len(pdf_files))
            with col2:
                st.metric("🖼️ Image files", len(image_files))
            
            # Hiển thị danh sách files
            with st.expander("📂 Danh sách files"):
                for i, file in enumerate(batch_files):
                    file_type = "📄" if file.type == 'application/pdf' else "🖼️"
                    st.write(f"{file_type} {file.name} ({format_file_size(file.size)})")
            
            # Batch processing options
            st.subheader("⚙️ Tùy chọn xử lý")
            
            col1, col2 = st.columns(2)
            with col1:
                merge_output = st.checkbox("Gộp tất cả thành 1 file Word", value=True)
                include_source_name = st.checkbox("Ghi rõ tên file gốc", value=True)
            
            with col2:
                skip_errors = st.checkbox("Bỏ qua files lỗi", value=True)
                max_concurrent = st.slider("Số file xử lý đồng thời", 1, 5, 2)
            
            if st.button("🚀 Bắt đầu xử lý hàng loạt", key="batch_process"):
                batch_results = []
                
                # Create main progress bar
                main_progress = st.progress(0)
                main_status = st.empty()
                
                for i, file in enumerate(batch_files):
                    main_status.text(f"Đang xử lý {i+1}/{len(batch_files)}: {file.name}")
                    
                    try:
                        if file.type == 'application/pdf':
                            # Process PDF
                            pdf_images = PDFProcessor.extract_images_and_text(file)
                            
                            file_latex_content = []
                            for img, page_num in pdf_images:
                                img_buffer = io.BytesIO()
                                img.save(img_buffer, format='PNG')
                                img_bytes = img_buffer.getvalue()
                                
                                prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                                Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                                
                                latex_result = gemini_api.convert_to_latex(
                                    img_bytes, "image/png", prompt
                                )
                                if latex_result:
                                    file_latex_content.append(latex_result)
                            
                            combined_content = "\n".join(file_latex_content)
                            
                        else:
                            # Process Image
                            image_bytes = file.getvalue()
                            prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                            Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                            
                            combined_content = gemini_api.convert_to_latex(
                                image_bytes, file.type, prompt
                            )
                        
                        if combined_content:
                            if include_source_name:
                                combined_content = f"<!-- Source: {file.name} -->\n{combined_content}"
                            
                            batch_results.append({
                                'filename': file.name,
                                'content': combined_content,
                                'success': True
                            })
                        else:
                            raise Exception("Không nhận được kết quả từ API")
                    
                    except Exception as e:
                        error_msg = f"Lỗi xử lý {file.name}: {str(e)}"
                        if skip_errors:
                            st.warning(f"⚠️ {error_msg}")
                            batch_results.append({
                                'filename': file.name,
                                'content': f"<!-- ERROR: {error_msg} -->",
                                'success': False
                            })
                        else:
                            st.error(f"❌ {error_msg}")
                            break
                    
                    main_progress.progress((i + 1) / len(batch_files))
                
                # Process results
                successful_files = [r for r in batch_results if r['success']]
                failed_files = [r for r in batch_results if not r['success']]
                
                main_status.text(f"✅ Hoàn thành: {len(successful_files)} thành công, {len(failed_files)} lỗi")
                
                if successful_files:
                    if merge_output:
                        # Merge all content
                        all_content = "\n\n".join([r['content'] for r in successful_files])
                        
                        # Show stats
                        stats = count_math_content(all_content)
                        show_processing_stats(stats)
                        
                        # Create Word file
                        st.subheader("📥 Tải kết quả")
                        
                        if st.button("📥 Tạo file Word gộp", key="create_batch_word"):
                            with st.spinner("🔄 Đang tạo file Word..."):
                                try:
                                    word_buffer = WordExporter.create_word_document(all_content)
                                    
                                    st.download_button(
                                        label="📥 Tải file Word gộp",
                                        data=word_buffer.getvalue(),
                                        file_name="batch_converted.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.download_button(
                                        label="📝 Tải LaTeX source",
                                        data=all_content,
                                        file_name="batch_converted.tex",
                                        mime="text/plain"
                                    )
                                    
                                    st.success("✅ File đã được tạo thành công!")
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo file: {str(e)}")
                    
                    else:
                        # Individual downloads
                        st.subheader("📥 Tải từng file")
                        for result in successful_files:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"✅ {result['filename']}")
                            with col2:
                                st.download_button(
                                    label="📥 Tải",
                                    data=result['content'],
                                    file_name=f"{result['filename']}.tex",
                                    mime="text/plain",
                                    key=f"download_{result['filename']}"
                                )
                
                # Add batch to history
                ConversionHistory.add_to_history(
                    "Batch", 
                    f"{len(batch_files)} files", 
                    len(successful_files) > 0,
                    sum(len(r['content']) for r in successful_files)
                )
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>Hỗ trợ chuyển đổi PDF và ảnh sang LaTeX với độ chính xác cao</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main(), remaining_text)
                for match in reversed(list(inline_matches)):
                    before_text = remaining_text[:match.start()]
                    after_text = remaining_text[match.end():]
                    latex_expr = match.group(1)
                    
                    if before_text.strip():
                        current_paragraph.add_run(before_text)
                    
                    # Add inline equation
                    eq_run = current_paragraph.add_run(f"[{latex_expr}]")
                    eq_run.font.italic = True
                    
                    remaining_text = after_text
                
                # Add any remaining text
                if remaining_text.strip():
                    current_paragraph.add_run(remaining_text)
                    
            else:
                # Nếu không có công thức LaTeX, thêm paragraph thường
                doc.add_paragraph(line)
                current_paragraph = None
        
        # Thêm ảnh nếu có
        if images:
            doc.add_page_break()
            doc.add_heading('Hình ảnh minh họa', level=1)
            
            for i, img in enumerate(images):
                try:
                    doc.add_heading(f'Hình {i+1}', level=2)
                    
                    # Resize image if too large
                    max_width = 6.0  # inches
                    img_width = max_width
                    
                    # Lưu ảnh tạm thời
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        # Convert to RGB if necessary
                        if img.mode in ('RGBA', 'LA', 'P'):
                            img = img.convert('RGB')
                        
                        img.save(tmp.name, 'PNG')
                        
                        try:
                            doc.add_picture(tmp.name, width=doc.sections[0].page_width * 0.8)
                        except Exception as e:
                            # If image can't be added, add a placeholder
                            doc.add_paragraph(f"[Hình ảnh {i+1} - Không thể hiển thị: {str(e)}]")
                        
                        os.unlink(tmp.name)
                        
                except Exception as e:
                    doc.add_paragraph(f"[Lỗi hiển thị hình {i+1}: {str(e)}]")
        
        # Thêm footer thông tin
        doc.add_page_break()
        doc.add_heading('Thông tin chuyển đổi', level=2)
        
        info_text = f"""
        Tài liệu này được tạo tự động từ PDF/Image to LaTeX Converter.
        
        Lưu ý:
        - Các công thức toán học được hiển thị dạng [equation] do giới hạn của python-docx
        - Để có equations thật, bạn có thể copy LaTeX code và paste vào Word với MathType
        - Hoặc sử dụng các editor hỗ trợ LaTeX như Overleaf, TeXShop
        
        LaTeX format được sử dụng:
        - Inline equations: ${{formula}}$
        - Display equations: ${{formula}}$
        """
        
        doc.add_paragraph(info_text)
        
        # Lưu document vào buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key và settings
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        api_key = st.text_input(
            "Gemini API Key", 
            type="password", 
            help="Nhập API key từ Google AI Studio",
            placeholder="Paste your API key here..."
        )
        
        # Validation API key real-time
        if api_key:
            if validate_api_key(api_key):
                st.success("✅ API key hợp lệ")
            else:
                st.error("❌ API key không hợp lệ")
                st.info("API key phải có ít nhất 20 ký tự và chỉ chứa chữ cái, số, dấu gạch ngang và underscore")
        
        st.markdown("---")
        
        # Settings
        st.subheader("🎛️ Tùy chọn")
        
        max_file_size = st.selectbox(
            "Giới hạn kích thước file",
            ["10MB", "20MB", "50MB"],
            index=1
        )
        
        output_format = st.selectbox(
            "Định dạng output",
            ["LaTeX ($...$)", "MathJax", "AsciiMath"],
            index=0
        )
        
        include_images = st.checkbox("Bao gồm hình ảnh trong Word", value=True)
        
        st.markdown("---")
        
        # Conversion History
        st.subheader("📊 Lịch sử")
        ConversionHistory.show_history()
        
        if st.button("🗑️ Xóa lịch sử"):
            ConversionHistory.clear_history()
            st.rerun()
        
        st.markdown("---")
        
        # Tips và hướng dẫn
        show_tips_and_tricks()
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại [Google AI Studio](https://makersuite.google.com/app/apikey)")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2, tab3 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX", "📋 Batch Processing"])
    
    # Khởi tạo API với error handling
    try:
        gemini_api = GeminiAPI(api_key)
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo API: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học"
        )
        
        if uploaded_pdf:
            # Validate PDF file
            is_valid, error_msg = validate_pdf_file(uploaded_pdf)
            if not is_valid:
                st.error(f"❌ {error_msg}")
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                
                # Hiển thị thông tin file
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                # Extract images từ PDF
                with st.spinner("🔄 Đang xử lý PDF..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang")
                        
                        # Hiển thị preview các trang
                        for img, page_num in pdf_images[:3]:  # Hiển thị tối đa 3 trang đầu
                            st.write(f"**Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 3:
                            st.info(f"... và {len(pdf_images) - 3} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        conversion_successful = True
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tạo prompt cho Gemini
                            prompt = f"""
                            Hãy chuyển đổi tất cả nội dung trong ảnh trang {page_num} thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text thường và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn (\\frac, \\sqrt, \\sum, \\int, ...)
                            6. Xử lý đúng các chỉ số trên/dưới, ma trận, hệ phương trình
                            7. Nếu có bảng, sử dụng tabular environment
                            8. Mô tả ngắn gọn các hình vẽ/biểu đồ nếu có
                            
                            ĐỊNH DẠNG OUTPUT MONG MUỐN:
                            - Text thường: viết bình thường
                            - Công thức inline: ${{x^2 + y^2 = z^2}}$
                            - Công thức display: ${{\\int_0^1 x dx = \\frac{{1}}{{2}}}}$
                            - Ma trận: ${{A = \\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            
                            Hãy đảm bảo LaTeX output có thể compile được và chính xác 100%.
                            """
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                                    conversion_successful = False
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                                conversion_successful = False
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        if conversion_successful:
                            status_text.text("✅ Hoàn thành chuyển đổi!")
                            
                            # Combine và hiển thị kết quả
                            combined_latex = "\n".join(all_latex_content)
                            
                            # Thống kê kết quả
                            stats = count_math_content(combined_latex)
                            show_processing_stats(stats)
                            
                            # Hiển thị preview
                            st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                            preview_content = create_latex_preview(combined_latex, 2000)
                            st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            # Lưu vào session state để tái sử dụng
                            st.session_state.pdf_latex_content = combined_latex
                            st.session_state.pdf_images = [img for img, _ in pdf_images]
                            
                            # Add to history
                            ConversionHistory.add_to_history(
                                "PDF", uploaded_pdf.name, True, len(combined_latex)
                            )
                            
                        else:
                            status_text.text("❌ Một số trang không thể xử lý")
                            ConversionHistory.add_to_history("PDF", uploaded_pdf.name, False)
                
                # Tạo file Word nếu đã có kết quả
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.pdf_images if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    images_to_include
                                )
                                
                                filename = generate_filename(uploaded_pdf.name, "latex_converted")
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX source
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.pdf_latex_content,
                                    file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab xử lý ảnh
    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học"
        )
        
        if uploaded_images:
            # Validate all images
            all_valid = True
            for uploaded_image in uploaded_images:
                is_valid, error_msg = validate_image_file(uploaded_image)
                if not is_valid:
                    st.error(f"❌ {uploaded_image.name}: {error_msg}")
                    all_valid = False
            
            if not all_valid:
                return
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                total_size = sum(img.size for img in uploaded_images)
                st.info(f"📁 Số ảnh: {len(uploaded_images)}")
                st.info(f"📏 Tổng kích thước: {format_file_size(total_size)}")
                
                # Hiển thị preview
                for i, uploaded_image in enumerate(uploaded_images[:5]):  # Tối đa 5 ảnh
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                    st.caption(f"📏 {image.size[0]}x{image.size[1]} pixels")
                
                if len(uploaded_images) > 5:
                    st.info(f"... và {len(uploaded_images) - 5} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                # Tùy chọn xử lý
                processing_mode = st.radio(
                    "Chế độ xử lý:",
                    ["Tự động", "Tùy chỉnh prompt"],
                    help="Tự động: sử dụng prompt mặc định. Tùy chỉnh: bạn có thể chỉnh sửa prompt"
                )
                
                custom_prompt = ""
                if processing_mode == "Tùy chỉnh prompt":
                    custom_prompt = st.text_area(
                        "Prompt tùy chỉnh:",
                        value="""Chuyển đổi nội dung toán học thành LaTeX format chính xác.
Sử dụng ${...}$ cho inline và ${...}$ cho display equations.
Giữ nguyên cấu trúc và thứ tự nội dung.""",
                        height=100
                    )
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh", key="convert_images"):
                    all_latex_content = []
                    conversion_successful = True
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}: {uploaded_image.name}")
                        
                        # Đọc ảnh
                        image_bytes = uploaded_image.getvalue()
                        
                        # Tạo prompt
                        if processing_mode == "Tùy chỉnh prompt" and custom_prompt:
                            prompt = custom_prompt
                        else:
                            prompt = f"""
                            Chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.
                            
                            YÊU CẦU QUAN TRỌNG:
                            1. Sử dụng ${{...}}$ cho công thức inline (trong dòng)
                            2. Sử dụng ${{...}}$ cho công thức display (riêng dòng)  
                            3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
                            4. Bao gồm TẤT CẢ text và công thức toán học
                            5. Sử dụng ký hiệu LaTeX chuẩn
                            6. Xử lý đúng ma trận, hệ phương trình, tích phân, đạo hàm
                            7. Nếu có biểu đồ/hình vẽ, mô tả ngắn gọn
                            8. Đảm bảo LaTeX có thể compile được
                            
                            ĐỊNH DẠNG OUTPUT:
                            - Text: viết bình thường
                            - Inline: ${{x^2 + 1}}$
                            - Display: ${{\\int_0^\\infty e^{{-x}} dx = 1}}$
                            - Ma trận: ${{\\begin{{pmatrix}} a & b \\\\ c & d \\end{{pmatrix}}}}$
                            """
                        
                        # Gọi API
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                all_latex_content.append(
                                    f"<!-- Ảnh {i+1}: {uploaded_image.name} -->\n{latex_result}\n"
                                )
                            else:
                                st.warning(f"⚠️ Không thể xử lý ảnh {uploaded_image.name}")
                                conversion_successful = False
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý {uploaded_image.name}: {str(e)}")
                            conversion_successful = False
                        
                        progress_bar.progress((i + 1) / len(uploaded_images))
                    
                    if conversion_successful:
                        status_text.text("✅ Hoàn thành chuyển đổi!")
                        
                        # Combine và hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        # Thống kê
                        stats = count_math_content(combined_latex)
                        show_processing_stats(stats)
                        
                        # Preview
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        preview_content = create_latex_preview(combined_latex, 2000)
                        st.text_area("📝 Kết quả LaTeX (Preview):", preview_content, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session
                        st.session_state.image_latex_content = combined_latex
                        st.session_state.image_list = [Image.open(img) for img in uploaded_images]
                        
                        # Add to history
                        ConversionHistory.add_to_history(
                            "Images", f"{len(uploaded_images)} files", True, len(combined_latex)
                        )
                    else:
                        status_text.text("❌ Một số ảnh không thể xử lý")
                        ConversionHistory.add_to_history("Images", f"{len(uploaded_images)} files", False)
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                images_to_include = st.session_state.image_list if include_images else None
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    images_to_include
                                )
                                
                                filename = "images_latex_converted.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                                
                                # Download LaTeX
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Tab Batch Processing
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.header("📋 Xử lý hàng loạt")
        
        st.info("🚀 Tính năng này cho phép xử lý nhiều file PDF và ảnh cùng lúc")
        
        # Upload multiple files
        batch_files = st.file_uploader(
            "Chọn nhiều file (PDF và ảnh)",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload nhiều file PDF và ảnh để xử lý cùng lúc"
        )
        
        if batch_files:
            st.write(f"📁 Đã chọn {len(batch_files)} file(s)")
            
            # Phân loại files
            pdf_files = [f for f in batch_files if f.type == 'application/pdf']
            image_files = [f for f in batch_files if f.type.startswith('image/')]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📄 PDF files", len(pdf_files))
            with col2:
                st.metric("🖼️ Image files", len(image_files))
            
            # Hiển thị danh sách files
            with st.expander("📂 Danh sách files"):
                for i, file in enumerate(batch_files):
                    file_type = "📄" if file.type == 'application/pdf' else "🖼️"
                    st.write(f"{file_type} {file.name} ({format_file_size(file.size)})")
            
            # Batch processing options
            st.subheader("⚙️ Tùy chọn xử lý")
            
            col1, col2 = st.columns(2)
            with col1:
                merge_output = st.checkbox("Gộp tất cả thành 1 file Word", value=True)
                include_source_name = st.checkbox("Ghi rõ tên file gốc", value=True)
            
            with col2:
                skip_errors = st.checkbox("Bỏ qua files lỗi", value=True)
                max_concurrent = st.slider("Số file xử lý đồng thời", 1, 5, 2)
            
            if st.button("🚀 Bắt đầu xử lý hàng loạt", key="batch_process"):
                batch_results = []
                
                # Create main progress bar
                main_progress = st.progress(0)
                main_status = st.empty()
                
                for i, file in enumerate(batch_files):
                    main_status.text(f"Đang xử lý {i+1}/{len(batch_files)}: {file.name}")
                    
                    try:
                        if file.type == 'application/pdf':
                            # Process PDF
                            pdf_images = PDFProcessor.extract_images_and_text(file)
                            
                            file_latex_content = []
                            for img, page_num in pdf_images:
                                img_buffer = io.BytesIO()
                                img.save(img_buffer, format='PNG')
                                img_bytes = img_buffer.getvalue()
                                
                                prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                                Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                                
                                latex_result = gemini_api.convert_to_latex(
                                    img_bytes, "image/png", prompt
                                )
                                if latex_result:
                                    file_latex_content.append(latex_result)
                            
                            combined_content = "\n".join(file_latex_content)
                            
                        else:
                            # Process Image
                            image_bytes = file.getvalue()
                            prompt = """Chuyển đổi nội dung thành LaTeX format chính xác.
                            Sử dụng ${...}$ cho inline và ${...}$ cho display equations."""
                            
                            combined_content = gemini_api.convert_to_latex(
                                image_bytes, file.type, prompt
                            )
                        
                        if combined_content:
                            if include_source_name:
                                combined_content = f"<!-- Source: {file.name} -->\n{combined_content}"
                            
                            batch_results.append({
                                'filename': file.name,
                                'content': combined_content,
                                'success': True
                            })
                        else:
                            raise Exception("Không nhận được kết quả từ API")
                    
                    except Exception as e:
                        error_msg = f"Lỗi xử lý {file.name}: {str(e)}"
                        if skip_errors:
                            st.warning(f"⚠️ {error_msg}")
                            batch_results.append({
                                'filename': file.name,
                                'content': f"<!-- ERROR: {error_msg} -->",
                                'success': False
                            })
                        else:
                            st.error(f"❌ {error_msg}")
                            break
                    
                    main_progress.progress((i + 1) / len(batch_files))
                
                # Process results
                successful_files = [r for r in batch_results if r['success']]
                failed_files = [r for r in batch_results if not r['success']]
                
                main_status.text(f"✅ Hoàn thành: {len(successful_files)} thành công, {len(failed_files)} lỗi")
                
                if successful_files:
                    if merge_output:
                        # Merge all content
                        all_content = "\n\n".join([r['content'] for r in successful_files])
                        
                        # Show stats
                        stats = count_math_content(all_content)
                        show_processing_stats(stats)
                        
                        # Create Word file
                        st.subheader("📥 Tải kết quả")
                        
                        if st.button("📥 Tạo file Word gộp", key="create_batch_word"):
                            with st.spinner("🔄 Đang tạo file Word..."):
                                try:
                                    word_buffer = WordExporter.create_word_document(all_content)
                                    
                                    st.download_button(
                                        label="📥 Tải file Word gộp",
                                        data=word_buffer.getvalue(),
                                        file_name="batch_converted.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.download_button(
                                        label="📝 Tải LaTeX source",
                                        data=all_content,
                                        file_name="batch_converted.tex",
                                        mime="text/plain"
                                    )
                                    
                                    st.success("✅ File đã được tạo thành công!")
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo file: {str(e)}")
                    
                    else:
                        # Individual downloads
                        st.subheader("📥 Tải từng file")
                        for result in successful_files:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"✅ {result['filename']}")
                            with col2:
                                st.download_button(
                                    label="📥 Tải",
                                    data=result['content'],
                                    file_name=f"{result['filename']}.tex",
                                    mime="text/plain",
                                    key=f"download_{result['filename']}"
                                )
                
                # Add batch to history
                ConversionHistory.add_to_history(
                    "Batch", 
                    f"{len(batch_files)} files", 
                    len(successful_files) > 0,
                    sum(len(r['content']) for r in successful_files)
                )
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>Hỗ trợ chuyển đổi PDF và ảnh sang LaTeX với độ chính xác cao</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
