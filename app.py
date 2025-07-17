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
import re
import time

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
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    def encode_image(self, image_data: bytes) -> str:
        """Mã hóa ảnh thành base64"""
        return base64.b64encode(image_data).decode('utf-8')
    
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str:
        """Chuyển đổi nội dung sang LaTeX sử dụng Gemini API"""
        headers = {"Content-Type": "application/json"}
        
        # Tạo payload cho API
        if content_type.startswith('image/'):
            mime_type = content_type
        else:
            mime_type = "image/png"
        
        encoded_content = self.encode_image(content_data)
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
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
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers=headers,
                json=payload,
                timeout=90
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    return content.strip()
                else:
                    raise Exception("API không trả về kết quả hợp lệ")
            elif response.status_code == 401:
                raise Exception("API key không hợp lệ hoặc đã hết hạn")
            elif response.status_code == 429:
                raise Exception("Đã vượt quá giới hạn rate limit")
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
    def extract_images_and_text(pdf_file):
        """Trích xuất ảnh và chuyển đổi trang PDF thành ảnh"""
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        images = []
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class WordExporter:
    @staticmethod
    def create_word_document(latex_content: str, images=None) -> io.BytesIO:
        """Tạo file Word với equations từ LaTeX"""
        doc = Document()
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu đã chuyển đổi từ PDF/Ảnh', 0)
        title.alignment = 1
        
        # Thêm thông tin
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter")
        doc.add_paragraph(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        # Xử lý nội dung LaTeX
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip comments
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                continue
            
            if not line:
                continue
            
            # Xử lý các công thức LaTeX
            if '$' in line:
                p = doc.add_paragraph()
                
                # Xử lý display equations ($$...$$) trước
                while '$$' in line:
                    start_idx = line.find('$$')
                    if start_idx != -1:
                        end_idx = line.find('$$', start_idx + 2)
                        if end_idx != -1:
                            # Thêm text trước equation
                            if start_idx > 0:
                                p.add_run(line[:start_idx])
                            
                            # Thêm equation
                            equation = line[start_idx+2:end_idx]
                            eq_run = p.add_run(f"\n[EQUATION: {equation}]\n")
                            eq_run.font.bold = True
                            
                            # Cập nhật line
                            line = line[end_idx+2:]
                        else:
                            break
                    else:
                        break
                
                # Xử lý inline equations ($...$)
                while '$' in line:
                    start_idx = line.find('$')
                    if start_idx != -1:
                        end_idx = line.find('$', start_idx + 1)
                        if end_idx != -1:
                            # Thêm text trước equation
                            if start_idx > 0:
                                p.add_run(line[:start_idx])
                            
                            # Thêm equation
                            equation = line[start_idx+1:end_idx]
                            eq_run = p.add_run(f"[{equation}]")
                            eq_run.font.italic = True
                            
                            # Cập nhật line
                            line = line[end_idx+1:]
                        else:
                            break
                    else:
                        break
                
                # Thêm text còn lại
                if line.strip():
                    p.add_run(line)
            else:
                # Không có công thức LaTeX
                doc.add_paragraph(line)
        
        # Thêm ảnh nếu có
        if images:
            doc.add_page_break()
            doc.add_heading('Hình ảnh minh họa', level=1)
            
            for i, img in enumerate(images):
                try:
                    doc.add_heading(f'Hình {i+1}', level=2)
                    
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    
                    # Lưu ảnh tạm thời
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        img.save(tmp.name, 'PNG')
                        try:
                            doc.add_picture(tmp.name, width=doc.sections[0].page_width * 0.8)
                        except Exception:
                            doc.add_paragraph(f"[Hình ảnh {i+1} - Không thể hiển thị]")
                        os.unlink(tmp.name)
                except Exception:
                    doc.add_paragraph(f"[Lỗi hiển thị hình {i+1}]")
        
        # Lưu document vào buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer

def validate_api_key(api_key: str) -> bool:
    """Kiểm tra tính hợp lệ của API key"""
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    """Chuyển đổi kích thước file sang định dạng human-readable"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        api_key = st.text_input(
            "Gemini API Key", 
            type="password", 
            help="Nhập API key từ Google AI Studio",
            placeholder="Paste your API key here..."
        )
        
        if api_key:
            if validate_api_key(api_key):
                st.success("✅ API key hợp lệ")
            else:
                st.error("❌ API key không hợp lệ")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🔑 Lấy API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại Google AI Studio")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX"])
    
    # Khởi tạo API
    try:
        gemini_api = GeminiAPI(api_key)
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo API: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học"
        )
        
        if uploaded_pdf:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                with st.spinner("🔄 Đang xử lý PDF..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang")
                        
                        # Hiển thị preview
                        for img, page_num in pdf_images[:3]:
                            st.write(f"**Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 3:
                            st.info(f"... và {len(pdf_images) - 3} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tạo prompt cho Gemini
                            prompt = """
Hãy chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.

YÊU CẦU:
1. Sử dụng ${...}$ cho công thức inline
2. Sử dụng $${...}$$ cho công thức display
3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
4. Bao gồm TẤT CẢ text và công thức toán học
5. Sử dụng ký hiệu LaTeX chuẩn

ĐỊNH DẠNG OUTPUT:
- Text: viết bình thường
- Inline: ${x^2 + y^2}$
- Display: $${\\int_0^1 x dx = \\frac{1}{2}}$$
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        status_text.text("✅ Hoàn thành chuyển đổi!")
                        
                        # Hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    st.session_state.pdf_images
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_converted.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.pdf_latex_content,
                                    file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học"
        )
        
        if uploaded_images:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                total_size = sum(img.size for img in uploaded_images)
                st.info(f"📁 Số ảnh: {len(uploaded_images)}")
                st.info(f"📏 Tổng kích thước: {format_file_size(total_size)}")
                
                for i, uploaded_image in enumerate(uploaded_images[:3]):
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                
                if len(uploaded_images) > 3:
                    st.info(f"... và {len(uploaded_images) - 3} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh", key="convert_images"):
                    all_latex_content = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}: {uploaded_image.name}")
                        
                        image_bytes = uploaded_image.getvalue()
                        
                        prompt = """
Chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.

YÊU CẦU:
1. Sử dụng ${...}$ cho công thức inline
2. Sử dụng $${...}$$ cho công thức display  
3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
4. Bao gồm TẤT CẢ text và công thức toán học
5. Sử dụng ký hiệu LaTeX chuẩn
"""
                        
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
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý {uploaded_image.name}: {str(e)}")
                        
                        progress_bar.progress((i + 1) / len(uploaded_images))
                    
                    status_text.text("✅ Hoàn thành chuyển đổi!")
                    
                    # Hiển thị kết quả
                    combined_latex = "\n".join(all_latex_content)
                    
                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = [Image.open(img) for img in uploaded_images]
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    st.session_state.image_list
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word",
                                    data=word_buffer.getvalue(),
                                    file_name="images_converted.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
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
