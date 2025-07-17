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
import cv2
import numpy as np

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

class ImageExtractor:
    """
    Class để tách ảnh/bảng từ ảnh gốc và chèn vào đúng vị trí trong văn bản
    """
    
    def __init__(self):
        self.min_area_ratio = 0.008    # Diện tích tối thiểu (% của ảnh gốc)
        self.min_area_abs = 2500       # Diện tích tối thiểu (pixel)
        self.min_width = 70            # Chiều rộng tối thiểu
        self.min_height = 70           # Chiều cao tối thiểu
        self.max_figures = 8           # Số lượng ảnh tối đa
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng từ ảnh gốc"""
        # 1. Đọc ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # 2. Tiền xử lý ảnh
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # 3. Tăng cường độ tương phản
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # 4. Tạo ảnh nhị phân
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, 
            cv2.THRESH_BINARY_INV, 25, 10
        )
        
        # 5. Làm dày các đường viền
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=1)
        
        # 6. Tìm các contour
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 7. Lọc và phân loại các vùng
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc theo kích thước
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.6):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            if not (0.2 < aspect_ratio < 8.0):
                continue
            
            # Loại bỏ vùng ở rìa
            if (x < 0.03*w or y < 0.03*h or 
                (x+ww) > 0.97*w or (y+hh) > 0.97*h):
                continue
            
            # Kiểm tra độ đặc
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area == 0:
                continue
            solidity = float(area) / hull_area
            if solidity < 0.4:
                continue
            
            # Phân loại bảng vs hình
            is_table = (ww > 0.25*w and hh > 0.05*h and 
                       aspect_ratio > 2.0 and aspect_ratio < 10.0)
            
            candidates.append({
                "area": area,
                "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                "is_table": is_table,
                "bbox": (x, y, ww, hh)
            })
        
        # 8. Sắp xếp và lọc
        candidates = sorted(candidates, key=lambda f: f['area'], reverse=True)
        candidates = self._filter_nested_boxes(candidates)
        candidates = candidates[:self.max_figures]
        candidates = sorted(candidates, key=lambda box: (box["y0"], box["x0"]))
        
        # 9. Tạo danh sách ảnh kết quả
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Cắt ảnh
            crop = img[fig_data["y0"]:fig_data["y1"], fig_data["x0"]:fig_data["x1"]]
            
            # Chuyển thành base64
            buf = io.BytesIO()
            Image.fromarray(crop).save(buf, format="JPEG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            # Đặt tên file
            if fig_data["is_table"]:
                name = f"table-{table_idx+1}.jpeg"
                table_idx += 1
            else:
                name = f"img-{img_idx+1}.jpeg"
                img_idx += 1
            
            final_figures.append({
                "name": name,
                "base64": b64,
                "is_table": fig_data["is_table"],
                "bbox": fig_data["bbox"]
            })
        
        return final_figures, h, w
    
    def _filter_nested_boxes(self, candidates):
        """Loại bỏ các box nằm bên trong box khác"""
        filtered = []
        for i, box in enumerate(candidates):
            x0, y0, x1, y1 = box['x0'], box['y0'], box['x1'], box['y1']
            is_nested = False
            
            for j, other in enumerate(candidates):
                if i == j:
                    continue
                ox0, oy0, ox1, oy1 = other['x0'], other['y0'], other['x1'], other['y1']
                
                if x0 >= ox0 and y0 >= oy0 and x1 <= ox1 and y1 <= oy1:
                    is_nested = True
                    break
            
            if not is_nested:
                filtered.append(box)
        
        return filtered
    
    def insert_figures_into_text(self, text, figures, img_h, img_w):
        """Chèn ảnh/bảng vào đúng vị trí trong văn bản"""
        lines = self._preprocess_text_lines(text)
        
        figures_sorted = sorted(
            [fig for fig in figures if fig.get('bbox')],
            key=lambda f: (f['bbox'][1], f['bbox'][0])
        )
        
        processed_lines = []
        used_figures = set()
        fig_idx = 0
        
        for i, line in enumerate(lines):
            processed_lines.append(line)
            
            inserted = self._try_insert_figure(
                line, figures_sorted, used_figures, 
                processed_lines, fig_idx
            )
            
            if inserted:
                fig_idx = inserted
        
        # Chèn các ảnh còn lại vào câu hỏi
        processed_lines = self._insert_remaining_figures(
            processed_lines, figures_sorted, used_figures, fig_idx
        )
        
        return '\n'.join(processed_lines)
    
    def _preprocess_text_lines(self, text):
        """Tiền xử lý văn bản thành các dòng"""
        lines = []
        buffer = ""
        
        for line in text.split('\n'):
            stripped_line = line.strip()
            if stripped_line:
                buffer = buffer + " " + stripped_line if buffer else stripped_line
            else:
                if buffer:
                    lines.append(buffer)
                    buffer = ""
                lines.append('')
        
        if buffer:
            lines.append(buffer)
        
        return lines
    
    def _try_insert_figure(self, line, figures_sorted, used_figures, processed_lines, fig_idx):
        """Thử chèn ảnh/bảng dựa trên từ khóa"""
        lower_line = line.lower()
        
        # Từ khóa cho bảng
        table_keywords = [
            "bảng", "bảng giá trị", "bảng biến thiên", 
            "bảng tần số", "bảng số liệu", "table"
        ]
        
        # Từ khóa cho hình
        image_keywords = [
            "hình vẽ", "hình bên", "(hình", "xem hình", 
            "đồ thị", "biểu đồ", "minh họa", "hình", "figure", "chart"
        ]
        
        # Kiểm tra và chèn bảng
        if (any(keyword in lower_line for keyword in table_keywords) or 
            (line.strip().startswith("|") and "|" in line)):
            
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[BẢNG: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        # Kiểm tra và chèn hình
        elif any(keyword in lower_line for keyword in image_keywords):
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if not fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[HÌNH: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        return fig_idx
    
    def _insert_remaining_figures(self, processed_lines, figures_sorted, used_figures, fig_idx):
        """Chèn các ảnh còn lại vào đầu các câu hỏi"""
        for i, line in enumerate(processed_lines):
            if re.match(r"^(Câu|Question|Problem)\s*\d+[\.\:]", line) and fig_idx < len(figures_sorted):
                next_line = processed_lines[i+1] if i+1 < len(processed_lines) else ""
                
                if (not re.match(r"\[HÌNH:.*\]", next_line) and 
                    not re.match(r"\[BẢNG:.*\]", next_line)):
                    
                    while (fig_idx < len(figures_sorted) and 
                           figures_sorted[fig_idx]['name'] in used_figures):
                        fig_idx += 1
                    
                    if fig_idx < len(figures_sorted):
                        fig = figures_sorted[fig_idx]
                        tag = (f"\n[BẢNG: {fig['name']}]\n" if fig['is_table'] 
                               else f"\n[HÌNH: {fig['name']}]\n")
                        processed_lines.insert(i+1, tag)
                        used_figures.add(fig['name'])
                        fig_idx += 1
        
        return processed_lines

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
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        """Tạo file Word với equations từ LaTeX và ảnh đã tách"""
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
            
            # Xử lý tag ảnh/bảng đã tách
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                WordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                WordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            # Skip comments
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                continue
            
            if not line:
                continue
            
            # Xử lý các công thức LaTeX
            if '

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
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter + Auto Image Extract</h1>', unsafe_allow_html=True)
    
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
        
        # Cài đặt tách ảnh
        st.subheader("🖼️ Tách ảnh tự động")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng tự động", value=True, 
                                       help="Tự động tách và chèn ảnh/bảng vào đúng vị trí")
        
        if enable_extraction:
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.8, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 15, 8, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 150, 70, 10)
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng mới:
        - ✅ Tự động tách ảnh/bảng
        - ✅ Chèn đúng vị trí dựa trên từ khóa
        - ✅ Phân biệt hình minh họa và bảng số liệu
        
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
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX + Auto Extract", "🖼️ Image to LaTeX + Auto Extract"])
    
    # Khởi tạo API và ImageExtractor
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction:
            image_extractor = ImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX + Tách ảnh tự động")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học và hình ảnh"
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
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF + Tách ảnh", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh/bảng nếu được bật
                            extracted_figures = []
                            if enable_extraction:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    st.write(f"🖼️ Trang {page_num}: Tách được {len(figures)} ảnh/bảng")
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Tạo prompt cho Gemini
                            prompt = f"""
Hãy chuyển đổi tất cả nội dung trong ảnh trang {page_num} thành định dạng LaTeX chính xác.

YÊU CẦU:
1. Sử dụng ${{...}}$ cho công thức inline
2. Sử dụng ${{...}}$ cho công thức display
3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
4. Bao gồm TẤT CẢ text và công thức toán học
5. Sử dụng ký hiệu LaTeX chuẩn

{'6. Khi gặp hình ảnh/bảng, sử dụng từ khóa như "xem hình", "bảng sau", "biểu đồ", "đồ thị"' if enable_extraction else ''}

ĐỊNH DẠNG OUTPUT:
- Text: viết bình thường
- Inline: ${{x^2 + y^2}}$
- Display: ${{\\int_0^1 x dx = \\frac{{1}}{{2}}}}$
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    # Chèn ảnh vào văn bản nếu có tách ảnh
                                    if enable_extraction and extracted_figures:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, h, w
                                        )
                                    
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
                        st.text_area("📝 Kết quả LaTeX (với ảnh đã tách):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị thống kê
                        if enable_extraction:
                            st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} ảnh/bảng")
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (với ảnh tự động)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_latex_with_images.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word (có ảnh tự động chèn)",
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
                                
                                st.success("✅ File Word với ảnh tự động đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX + Tách ảnh tự động")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học và hình minh họa"
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
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh + Tách ảnh", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}: {uploaded_image.name}")
                        
                        image_bytes = uploaded_image.getvalue()
                        image_pil = Image.open(uploaded_image)
                        all_original_images.append(image_pil)
                        
                        # Tách ảnh/bảng nếu được bật
                        extracted_figures = []
                        if enable_extraction:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                st.write(f"🖼️ {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt = """
Chuyển đổi tất cả nội dung trong ảnh thành định dạng LaTeX chính xác.

YÊU CẦU:
1. Sử dụng ${...}$ cho công thức inline
2. Sử dụng ${...}$ cho công thức display  
3. Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
4. Bao gồm TẤT CẢ text và công thức toán học
5. Sử dụng ký hiệu LaTeX chuẩn
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                # Chèn ảnh vào văn bản nếu có tách ảnh
                                if enable_extraction and extracted_figures:
                                    latex_result = image_extractor.insert_figures_into_text(
                                        latex_result, extracted_figures, h, w
                                    )
                                
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
                    st.text_area("📝 Kết quả LaTeX (với ảnh đã tách):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Hiển thị thống kê
                    if enable_extraction:
                        st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} ảnh/bảng")
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (với ảnh tự động)", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                extracted_figs = st.session_state.get('image_extracted_figures')
                                original_imgs = st.session_state.image_list
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word (có ảnh tự động chèn)",
                                    data=word_buffer.getvalue(),
                                    file_name="images_latex_with_extracted.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word với ảnh tự động đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>✨ <strong>Tính năng mới:</strong> Tự động tách ảnh/bảng và chèn đúng vị trí!</p>
        <p>🎯 Hỗ trợ chuyển đổi PDF và ảnh sang LaTeX với độ chính xác cao + AI tách ảnh thông minh</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main() in line:
                p = doc.add_paragraph()
                
                # Xử lý display equations ($...$) trước
                while '$' in line:
                    start_idx = line.find('$')
                    if start_idx != -1:
                        end_idx = line.find('$', start_idx + 2)
                        if end_idx != -1:
                            if start_idx > 0:
                                p.add_run(line[:start_idx])
                            
                            equation = line[start_idx+2:end_idx]
                            eq_run = p.add_run(f"\n[EQUATION: {equation}]\n")
                            eq_run.font.bold = True
                            
                            line = line[end_idx+2:]
                        else:
                            break
                    else:
                        break
                
                # Xử lý inline equations ($...$)
                while '

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
    main() in line:
                    start_idx = line.find('

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
    main())
                    if start_idx != -1:
                        end_idx = line.find('

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
    main(), start_idx + 1)
                        if end_idx != -1:
                            if start_idx > 0:
                                p.add_run(line[:start_idx])
                            
                            equation = line[start_idx+1:end_idx]
                            eq_run = p.add_run(f"[{equation}]")
                            eq_run.font.italic = True
                            
                            line = line[end_idx+1:]
                        else:
                            break
                    else:
                        break
                
                if line.strip():
                    p.add_run(line)
            else:
                doc.add_paragraph(line)
        
        # Thêm ảnh gốc nếu có (fallback)
        if images and not extracted_figures:
            doc.add_page_break()
            doc.add_heading('Hình ảnh gốc', level=1)
            
            for i, img in enumerate(images):
                try:
                    doc.add_heading(f'Hình {i+1}', level=2)
                    
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    
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
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """Chèn ảnh đã tách vào Word document"""
        if not extracted_figures:
            doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        # Tìm ảnh trong danh sách đã tách
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Thêm heading
            doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            
            # Decode base64 và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.7
                    doc.add_picture(tmp.name, width=max_width)
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")

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
