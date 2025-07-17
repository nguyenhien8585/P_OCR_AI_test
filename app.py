import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw
import fitz  # PyMuPDF
from docx import Document
import tempfile
import os
import re
import time

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Cấu hình trang
st.set_page_config(
    page_title="PDF/Image to LaTeX Converter - Fixed",
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
    .extracted-image {
        border: 2px solid #2E86AB;
        border-radius: 8px;
        margin: 10px 0;
        padding: 5px;
        background: #f8f9fa;
    }
    .image-info {
        background-color: #e8f4f8;
        padding: 8px;
        border-radius: 4px;
        margin: 5px 0;
        font-size: 0.9em;
    }
    .confidence-high {
        color: #28a745;
        font-weight: bold;
    }
    .confidence-medium {
        color: #ffc107;
        font-weight: bold;
    }
    .confidence-low {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

class SimpleImageExtractor:
    """Class đơn giản để tách ảnh/bảng"""
    
    def __init__(self):
        self.min_area_ratio = 0.005
        self.min_area_abs = 2000
        self.min_width = 60
        self.min_height = 60
        self.max_figures = 10
        self.padding = 5
        self.confidence_threshold = 60
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng đơn giản"""
        if not CV2_AVAILABLE:
            return [], 0, 0
        
        # Đọc ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # Tiền xử lý đơn giản
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Tăng cường độ tương phản
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # Tạo ảnh nhị phân
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Tìm contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc cơ bản
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.6):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            if not (0.2 < aspect_ratio < 10.0):
                continue
            
            # Loại bỏ vùng ở rìa
            if (x < 0.02*w or y < 0.02*h or 
                (x+ww) > 0.98*w or (y+hh) > 0.98*h):
                continue
            
            # Phân loại đơn giản
            is_table = (ww > 0.3 * w and aspect_ratio > 1.5)
            
            # Tính confidence đơn giản
            confidence = min(100, area_ratio * 1000 + aspect_ratio * 10 + 50)
            
            if confidence >= self.confidence_threshold:
                candidates.append({
                    "area": area,
                    "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                    "is_table": is_table,
                    "confidence": confidence,
                    "aspect_ratio": aspect_ratio,
                    "bbox": (x, y, ww, hh)
                })
        
        # Sắp xếp và lọc
        candidates = sorted(candidates, key=lambda f: f['confidence'], reverse=True)
        candidates = self._filter_overlapping(candidates)
        candidates = candidates[:self.max_figures]
        candidates = sorted(candidates, key=lambda box: (box["y0"], box["x0"]))
        
        # Tạo ảnh kết quả
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Cắt ảnh với padding
            x0 = max(0, fig_data["x0"] - self.padding)
            y0 = max(0, fig_data["y0"] - self.padding)
            x1 = min(w, fig_data["x1"] + self.padding)
            y1 = min(h, fig_data["y1"] + self.padding)
            
            crop = img[y0:y1, x0:x1]
            
            if crop.size == 0:
                continue
            
            # Chuyển thành base64
            buf = io.BytesIO()
            Image.fromarray(crop).save(buf, format="JPEG", quality=95)
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
                "bbox": (x0, y0, x1-x0, y1-y0),
                "original_bbox": fig_data["bbox"],
                "confidence": fig_data["confidence"],
                "aspect_ratio": fig_data["aspect_ratio"],
                "area": fig_data["area"]
            })
        
        return final_figures, h, w
    
    def _filter_overlapping(self, candidates):
        """Lọc overlap đơn giản"""
        filtered = []
        for candidate in candidates:
            is_overlap = False
            x0, y0, x1, y1 = candidate['x0'], candidate['y0'], candidate['x1'], candidate['y1']
            
            for other in filtered:
                ox0, oy0, ox1, oy1 = other['x0'], other['y0'], other['x1'], other['y1']
                
                # Tính overlap
                overlap_x = max(0, min(x1, ox1) - max(x0, ox0))
                overlap_y = max(0, min(y1, oy1) - max(y0, oy0))
                overlap_area = overlap_x * overlap_y
                
                area1 = (x1-x0) * (y1-y0)
                area2 = (ox1-ox0) * (oy1-oy0)
                
                if overlap_area > 0.3 * min(area1, area2):
                    is_overlap = True
                    break
            
            if not is_overlap:
                filtered.append(candidate)
        
        return filtered
    
    def create_debug_image(self, image_bytes, figures):
        """Tạo ảnh debug"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            bbox = fig['original_bbox']
            x, y, w, h = bbox
            
            # Vẽ khung
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ label
            label = f"{fig['name']} ({fig['confidence']:.0f}%)"
            draw.text((x, y-20), label, fill=color)
        
        return img_pil
    
    def insert_figures_into_text(self, text, figures, img_h, img_w):
        """Chèn ảnh vào văn bản"""
        lines = text.split('\n')
        processed_lines = []
        used_figures = set()
        fig_idx = 0
        
        # Từ khóa
        table_keywords = ["bảng", "table", "theo bảng", "bảng sau"]
        image_keywords = ["hình", "figure", "đồ thị", "biểu đồ", "theo hình"]
        
        for line in lines:
            processed_lines.append(line)
            lower_line = line.lower()
            
            # Kiểm tra từ khóa bảng
            if any(keyword in lower_line for keyword in table_keywords):
                for j in range(fig_idx, len(figures)):
                    fig = figures[j]
                    if fig['is_table'] and fig['name'] not in used_figures:
                        processed_lines.append(f"\n[BẢNG: {fig['name']}]\n")
                        used_figures.add(fig['name'])
                        fig_idx = j + 1
                        break
            
            # Kiểm tra từ khóa hình
            elif any(keyword in lower_line for keyword in image_keywords):
                for j in range(fig_idx, len(figures)):
                    fig = figures[j]
                    if not fig['is_table'] and fig['name'] not in used_figures:
                        processed_lines.append(f"\n[HÌNH: {fig['name']}]\n")
                        used_figures.add(fig['name'])
                        fig_idx = j + 1
                        break
        
        # Chèn ảnh còn lại vào đầu câu hỏi
        question_patterns = [r"^(Câu|Question)\s*\d+", r"^\d+[\.\)]\s*"]
        
        for i, line in enumerate(processed_lines):
            if any(re.match(pattern, line.strip()) for pattern in question_patterns):
                if fig_idx < len(figures):
                    next_line = processed_lines[i+1] if i+1 < len(processed_lines) else ""
                    if not re.match(r"\[(HÌNH|BẢNG):.*\]", next_line.strip()):
                        while fig_idx < len(figures) and figures[fig_idx]['name'] in used_figures:
                            fig_idx += 1
                        
                        if fig_idx < len(figures):
                            fig = figures[fig_idx]
                            tag = f"\n[BẢNG: {fig['name']}]\n" if fig['is_table'] else f"\n[HÌNH: {fig['name']}]\n"
                            processed_lines.insert(i+1, tag)
                            used_figures.add(fig['name'])
                            fig_idx += 1
        
        return '\n'.join(processed_lines)

class GeminiAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    def encode_image(self, image_data: bytes) -> str:
        return base64.b64encode(image_data).decode('utf-8')
    
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        
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
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        images = []
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            mat = fitz.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class WordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu đã chuyển đổi từ PDF/Ảnh', 0)
        title.alignment = 1
        
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter")
        doc.add_paragraph(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks
            if line.startswith('```') or line.endswith('```'):
                continue
            
            # Xử lý tag ảnh/bảng
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
            
            # Xử lý công thức toán học
            dollar_pattern = r'\$\{([^}]+)\}\$'
            if re.search(dollar_pattern, line):
                p = doc.add_paragraph()
                
                # Tách và xử lý từng phần
                parts = re.split(dollar_pattern, line)
                for i, part in enumerate(parts):
                    if i % 2 == 0:  # Text thường
                        if part.strip():
                            p.add_run(part)
                    else:  # Công thức
                        eq_run = p.add_run(f" [{part}] ")
                        eq_run.font.italic = True
                        eq_run.font.bold = True
            else:
                doc.add_paragraph(line)
        
        # Thêm ảnh gốc nếu có
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
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        if not extracted_figures:
            doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")

def validate_api_key(api_key: str) -> bool:
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Fixed</h1>', unsafe_allow_html=True)
    
    # Sidebar
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
        if CV2_AVAILABLE:
            st.subheader("🖼️ Tách ảnh tự động")
            enable_extraction = st.checkbox("Bật tách ảnh/bảng tự động", value=True)
            
            if enable_extraction:
                min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.5, 0.1) / 100
                max_figures = st.slider("Số ảnh tối đa", 1, 15, 10, 1)
                min_size = st.slider("Kích thước tối thiểu (px)", 30, 150, 60, 10)
                confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 60, 5)
                show_debug = st.checkbox("Hiển thị ảnh debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file và chờ xử lý
        
        ### 📝 Định dạng output:
        **Công thức:** `${x^2 + y^2}$`
        
        **Trắc nghiệm 4 phương án:**
        ```
        Câu X: [nội dung]
        A. [Đáp án]
        B. [Đáp án]  
        C. [Đáp án]
        D. [Đáp án]
        ```
        
        **Trắc nghiệm đúng sai:**
        ```
        Câu X: [nội dung]
        a) [Đáp án]
        b) [Đáp án]
        c) [Đáp án]
        d) [Đáp án]
        ```
        
        ### 🔑 Lấy API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX"])
    
    # Khởi tạo
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction and CV2_AVAILABLE:
            image_extractor = SimpleImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.confidence_threshold = confidence_threshold
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader("Chọn file PDF", type=['pdf'])
        
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
                        
                        for img, page_num in pdf_images[:2]:
                            st.write(f"**Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 2:
                            st.info(f"... và {len(pdf_images) - 2} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                            
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh nếu được bật
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_image(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🖼️ Trang {page_num}: Tách được {len(figures)} ảnh/bảng")
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cho Gemini
                            prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng chuẩn.

QUAN TRỌNG - CHỈ XUẤT RA VĂN BẢN THUẦN TÚY:

ĐỊNH DẠNG BẮT BUỘC:

1. Trắc nghiệm 4 phương án:
Câu X: [nội dung câu hỏi]
A. [đáp án A]
B. [đáp án B]  
C. [đáp án C]
D. [đáp án D]

2. Trắc nghiệm đúng sai:
Câu X: [nội dung câu hỏi nếu có]
a) [đáp án a]
b) [đáp án b]  
c) [đáp án c]
d) [đáp án d]

3. Trả lời ngắn/Tự luận:
Câu X: [nội dung câu hỏi]

4. Công thức toán học:
- CHỈ sử dụng: ${x^2 + y^2}$ cho công thức
- VÍ DỤ: ${ABCD}$, ${A'C' \\perp BD}$, ${\\frac{a+b}{c-d}}$
- KHÔNG dùng markdown hay latex blocks

5. Ký hiệu đặc biệt:
- Vuông góc: ${\\perp}$ hoặc ⊥
- Song song: ${\\parallel}$ hoặc //
- Độ: ° hoặc ${^\\circ}$

LƯU Ý:
- KHÔNG xuất markdown hay latex blocks
- CHỈ văn bản thuần túy với công thức ${...}$
- Giữ chính xác thứ tự và cấu trúc
- Bao gồm tất cả text và công thức
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn ảnh vào văn bản
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
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
                        st.text_area("📝 Kết quả (định dạng chuẩn):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê
                        if enable_extraction and CV2_AVAILABLE:
                            st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} ảnh/bảng")
                            
                            # Debug images
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug - Ảnh đã phát hiện")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    st.write(f"**Trang {page_num}:**")
                                    st.image(debug_img, caption=f"Phát hiện {len(figures)} vùng", use_column_width=True)
                                    
                                    if figures:
                                        cols = st.columns(min(len(figures), 3))
                                        for idx, fig in enumerate(figures):
                                            with cols[idx % 3]:
                                                img_data = base64.b64decode(fig['base64'])
                                                img_pil = Image.open(io.BytesIO(img_data))
                                                
                                                st.image(img_pil, caption=fig['name'], use_column_width=True)
                                                st.write(f"**{fig['name']}**")
                                                st.write(f"Loại: {'Bảng' if fig['is_table'] else 'Hình'}")
                                                st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                st.write(f"Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px")
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
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
    
    # Tab Image (tương tự)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True
        )
        
        if uploaded_images:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                total_size = sum(img.size for img in uploaded_images)
                st.info(f"📁 Số ảnh: {len(uploaded_images)}")
                st.info(f"📏 Tổng kích thước: {format_file_size(total_size)}")
                
                for i, uploaded_image in enumerate(uploaded_images[:2]):
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                
                if len(uploaded_images) > 2:
                    st.info(f"... và {len(uploaded_images) - 2} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    all_debug_images = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)}...")
                        
                        image_bytes = uploaded_image.getvalue()
                        image_pil = Image.open(uploaded_image)
                        all_original_images.append(image_pil)
                        
                        # Tách ảnh
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_image(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🖼️ {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng chuẩn.

Sử dụng định dạng ${...}$ cho công thức toán học.
Không dùng markdown hay latex blocks.
Giữ chính xác thứ tự và cấu trúc nội dung.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
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
                    st.text_area("📝 Kết quả (định dạng chuẩn):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug
                    if enable_extraction and CV2_AVAILABLE:
                        st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} ảnh/bảng")
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug - Ảnh đã phát hiện")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                st.write(f"**{img_name}:**")
                                st.image(debug_img, caption=f"Phát hiện {len(figures)} vùng", use_column_width=True)
                                
                                if figures:
                                    cols = st.columns(min(len(figures), 3))
                                    for idx, fig in enumerate(figures):
                                        with cols[idx % 3]:
                                            img_data = base64.b64decode(fig['base64'])
                                            img_pil = Image.open(io.BytesIO(img_data))
                                            
                                            st.image(img_pil, caption=fig['name'], use_column_width=True)
                                            st.write(f"**{fig['name']}**")
                                            st.write(f"Loại: {'Bảng' if fig['is_table'] else 'Hình'}")
                                            st.write(f"Confidence: {fig['confidence']:.1f}%")
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word", key="create_word_images"):
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
        <p>🎯 Hỗ trợ chuyển đổi PDF và ảnh sang LaTeX với độ chính xác cao</p>
        <p>📝 Định dạng chuẩn: Công thức ${...}$, Trắc nghiệm đúng format</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
