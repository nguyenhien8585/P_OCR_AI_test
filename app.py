import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw, ImageFont
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
    page_title="PDF/Image to LaTeX Converter - Enhanced",
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
    }
    .image-info {
        background-color: #e8f4f8;
        padding: 8px;
        border-radius: 4px;
        margin: 5px 0;
        font-size: 0.9em;
    }
</style>
""", unsafe_allow_html=True)

class AdvancedImageExtractor:
    """
    Class cải tiến để tách ảnh/bảng từ ảnh gốc với độ chính xác cao
    """
    
    def __init__(self):
        self.min_area_ratio = 0.005    # Diện tích tối thiểu (% của ảnh gốc)
        self.min_area_abs = 1500       # Diện tích tối thiểu (pixel)
        self.min_width = 50            # Chiều rộng tối thiểu
        self.min_height = 50           # Chiều cao tối thiểu
        self.max_figures = 10          # Số lượng ảnh tối đa
        self.padding = 5               # Padding xung quanh ảnh cắt
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng từ ảnh gốc với thuật toán cải tiến"""
        # 1. Đọc ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # 2. Tiền xử lý ảnh nhiều bước
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Khử nhiễu
        gray = cv2.medianBlur(gray, 3)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Tăng cường độ tương phản adaptive
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # 3. Phát hiện cạnh với nhiều phương pháp
        # Phương pháp 1: Adaptive threshold
        thresh1 = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Phương pháp 2: Canny edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Phương pháp 3: Morphological operations
        kernel_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        thresh2 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel_rect)
        
        # Kết hợp các phương pháp
        combined = cv2.bitwise_or(thresh2, edges)
        
        # 4. Làm dày các đường viền
        kernel = np.ones((2, 2), np.uint8)
        combined = cv2.dilate(combined, kernel, iterations=1)
        
        # 5. Tìm các contour với hierarchy
        contours, hierarchy = cv2.findContours(
            combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        # 6. Lọc và phân loại các vùng với nhiều tiêu chí
        candidates = []
        for i, cnt in enumerate(contours):
            # Tính toán bounding box
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc theo kích thước cơ bản
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.7):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            # Lọc aspect ratio hợp lý
            if not (0.1 < aspect_ratio < 15.0):
                continue
            
            # Loại bỏ vùng ở rìa ảnh
            margin = 0.02
            if (x < margin*w or y < margin*h or 
                (x+ww) > (1-margin)*w or (y+hh) > (1-margin)*h):
                continue
            
            # Tính các đặc trưng hình học
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(cnt)
            
            if hull_area == 0:
                continue
                
            solidity = float(contour_area) / hull_area
            if solidity < 0.3:  # Loại bỏ shape quá phức tạp
                continue
            
            # Tính extent (tỷ lệ fill bounding box)
            extent = float(contour_area) / area
            if extent < 0.2:  # Loại bỏ shape quá thưa
                continue
            
            # Phân loại bảng vs hình dựa trên nhiều tiêu chí
            is_table = self._classify_as_table(x, y, ww, hh, w, h, cnt, gray)
            
            # Tính toán điểm confidence
            confidence = self._calculate_confidence(
                area_ratio, aspect_ratio, solidity, extent, ww, hh, w, h
            )
            
            candidates.append({
                "area": area,
                "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                "width": ww, "height": hh,
                "is_table": is_table,
                "confidence": confidence,
                "aspect_ratio": aspect_ratio,
                "solidity": solidity,
                "extent": extent,
                "bbox": (x, y, ww, hh),
                "contour": cnt
            })
        
        # 7. Sắp xếp theo confidence và area
        candidates = sorted(candidates, key=lambda f: f['confidence'], reverse=True)
        candidates = self._filter_overlapping_boxes(candidates)
        candidates = candidates[:self.max_figures]
        
        # 8. Sắp xếp lại theo vị trí (top-to-bottom, left-to-right)
        candidates = sorted(candidates, key=lambda box: (box["y0"], box["x0"]))
        
        # 9. Tạo danh sách ảnh kết quả với padding
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
    
    def _classify_as_table(self, x, y, w, h, img_w, img_h, contour, gray_img):
        """Phân loại xem vùng này là bảng hay hình ảnh"""
        aspect_ratio = w / (h + 1e-6)
        
        # Kiểm tra tỷ lệ và kích thước cho bảng
        size_score = 0
        if w > 0.3 * img_w:  # Bảng thường rộng
            size_score += 2
        if h > 0.1 * img_h and h < 0.6 * img_h:  # Chiều cao vừa phải
            size_score += 1
        
        # Kiểm tra aspect ratio
        ratio_score = 0
        if 2.0 < aspect_ratio < 8.0:  # Bảng thường dài hơn cao
            ratio_score += 2
        elif 1.2 < aspect_ratio < 12.0:
            ratio_score += 1
        
        # Kiểm tra đường kẻ ngang trong vùng
        roi = gray_img[y:y+h, x:x+w]
        horizontal_lines = self._detect_horizontal_lines(roi)
        line_score = min(horizontal_lines * 0.5, 2)
        
        total_score = size_score + ratio_score + line_score
        return total_score >= 3
    
    def _detect_horizontal_lines(self, roi):
        """Phát hiện đường kẻ ngang trong vùng (dấu hiệu của bảng)"""
        if roi.shape[0] < 10 or roi.shape[1] < 10:
            return 0
        
        # Tạo kernel dài ngang để detect đường kẻ ngang
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (roi.shape[1]//3, 1))
        thresh = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # Đếm số đường kẻ
        lines = cv2.HoughLinesP(horizontal_lines, 1, np.pi/180, 
                               threshold=roi.shape[1]//4, minLineLength=roi.shape[1]//3)
        
        return len(lines) if lines is not None else 0
    
    def _calculate_confidence(self, area_ratio, aspect_ratio, solidity, extent, w, h, img_w, img_h):
        """Tính điểm confidence cho việc cắt ảnh"""
        confidence = 0
        
        # Điểm dựa trên kích thước
        if 0.01 < area_ratio < 0.5:
            confidence += 30
        elif 0.005 < area_ratio < 0.01:
            confidence += 20
        
        # Điểm dựa trên aspect ratio
        if 0.5 < aspect_ratio < 3.0:
            confidence += 25
        elif 0.2 < aspect_ratio < 8.0:
            confidence += 15
        
        # Điểm dựa trên solidity (độ đặc)
        if solidity > 0.8:
            confidence += 20
        elif solidity > 0.6:
            confidence += 15
        
        # Điểm dựa trên extent
        if extent > 0.6:
            confidence += 15
        elif extent > 0.4:
            confidence += 10
        
        # Điểm dựa trên vị trí (ưu tiên vùng trung tâm)
        center_x, center_y = w//2, h//2
        if 0.2 * img_w < center_x < 0.8 * img_w and 0.2 * img_h < center_y < 0.8 * img_h:
            confidence += 10
        
        return confidence
    
    def _filter_overlapping_boxes(self, candidates):
        """Loại bỏ các box trùng lặp"""
        filtered = []
        
        for i, box in enumerate(candidates):
            is_duplicate = False
            x0, y0, x1, y1 = box['x0'], box['y0'], box['x1'], box['y1']
            
            for j, other in enumerate(filtered):
                ox0, oy0, ox1, oy1 = other['x0'], other['y0'], other['x1'], other['y1']
                
                # Tính IoU (Intersection over Union)
                intersection_area = max(0, min(x1, ox1) - max(x0, ox0)) * max(0, min(y1, oy1) - max(y0, oy0))
                union_area = (x1-x0)*(y1-y0) + (ox1-ox0)*(oy1-oy0) - intersection_area
                
                if union_area > 0:
                    iou = intersection_area / union_area
                    if iou > 0.3:  # Nếu overlap > 30%
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                filtered.append(box)
        
        return filtered
    
    def create_debug_image(self, image_bytes, figures):
        """Tạo ảnh debug hiển thị các vùng đã cắt"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray']
        
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
        """Chèn ảnh/bảng vào đúng vị trí trong văn bản với logic cải thiện"""
        lines = self._preprocess_text_lines(text)
        
        figures_sorted = sorted(
            [fig for fig in figures if fig.get('bbox')],
            key=lambda f: (f['bbox'][1], f['bbox'][0])  # Sort by y, then x
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
            
            if isinstance(inserted, int):
                fig_idx = inserted
        
        # Chèn các ảnh còn lại
        processed_lines = self._insert_remaining_figures(
            processed_lines, figures_sorted, used_figures, fig_idx
        )
        
        return '\n'.join(processed_lines)
    
    def _preprocess_text_lines(self, text):
        """Tiền xử lý văn bản thành các dòng"""
        lines = []
        current_line = ""
        
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped:
                if current_line:
                    current_line += " " + stripped
                else:
                    current_line = stripped
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                if lines:  # Chỉ thêm dòng trống nếu đã có content
                    lines.append('')
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def _try_insert_figure(self, line, figures_sorted, used_figures, processed_lines, fig_idx):
        """Thử chèn ảnh/bảng dựa trên từ khóa cải thiện"""
        lower_line = line.lower()
        
        # Từ khóa cho bảng (mở rộng)
        table_keywords = [
            "bảng", "bảng giá trị", "bảng biến thiên", "bảng tần số", 
            "bảng số liệu", "table", "cho bảng", "theo bảng", "bảng sau",
            "quan sát bảng", "từ bảng", "dựa vào bảng"
        ]
        
        # Từ khóa cho hình (mở rộng)  
        image_keywords = [
            "hình vẽ", "hình bên", "(hình", "xem hình", "đồ thị", 
            "biểu đồ", "minh họa", "hình", "figure", "chart", "graph",
            "cho hình", "theo hình", "hình sau", "quan sát hình",
            "từ hình", "dựa vào hình", "sơ đồ"
        ]
        
        # Kiểm tra bảng trước
        if any(keyword in lower_line for keyword in table_keywords):
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[BẢNG: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        # Kiểm tra hình ảnh
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
        """Chèn các ảnh còn lại vào đầu câu hỏi"""
        # Pattern để nhận diện câu hỏi
        question_patterns = [
            r"^(Câu|Question|Problem)\s*\d+",
            r"^\d+[\.\)]\s*",
            r"^[A-D][\.\)]\s*",
            r"^[a-d][\.\)]\s*"
        ]
        
        for i, line in enumerate(processed_lines):
            # Kiểm tra xem có phải đầu câu hỏi không
            is_question = any(re.match(pattern, line.strip()) for pattern in question_patterns)
            
            if is_question and fig_idx < len(figures_sorted):
                # Kiểm tra dòng tiếp theo đã có ảnh chưa
                next_line = processed_lines[i+1] if i+1 < len(processed_lines) else ""
                has_image = re.match(r"\[(HÌNH|BẢNG):.*\]", next_line.strip())
                
                if not has_image:
                    # Tìm ảnh chưa sử dụng
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
            mat = fitz.Matrix(2.5, 2.5)  # Tăng độ phân giải
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
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter Enhanced")
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
            if '$$' in line or '$' in line:
                p = doc.add_paragraph()
                
                # Xử lý display equations ($$...$$) trước
                while '$$' in line:
                    start_idx = line.find('$$')
                    if start_idx != -1:
                        end_idx = line.find('$$', start_idx + 2)
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
                while '$' in line:
                    start_idx = line.find('$')
                    if start_idx != -1:
                        end_idx = line.find('$', start_idx + 1)
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
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Enhanced</h1>', unsafe_allow_html=True)
    
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
        
        # Cài đặt tách ảnh nâng cao
        st.subheader("🖼️ Tách ảnh nâng cao")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng tự động", value=True, 
                                       help="Tự động tách và chèn ảnh/bảng vào đúng vị trí")
        
        if enable_extraction:
            st.write("**Cài đặt nâng cao:**")
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 3.0, 0.5, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 20, 10, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 200, 50, 10)
            padding = st.slider("Padding xung quanh (px)", 0, 20, 5, 1)
            
            show_debug = st.checkbox("Hiển thị ảnh debug", value=True,
                                   help="Hiển thị ảnh với các vùng đã phát hiện")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng nâng cao:
        - ✅ Thuật toán cắt ảnh cải tiến
        - ✅ Hiển thị ảnh cắt với kích thước lớn
        - ✅ Định dạng chuẩn cho câu hỏi
        - ✅ Debug mode với confidence score
        
        ### 📝 Định dạng hỗ trợ:
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
        st.info("💡 Bạn có thể lấy API key miễn phí tại Google AI Studio")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX + Enhanced Extract", "🖼️ Image to LaTeX + Enhanced Extract"])
    
    # Khởi tạo API và ImageExtractor
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction:
            image_extractor = AdvancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.padding = padding
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX + Tách ảnh nâng cao")
        
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
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF + Tách ảnh nâng cao", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
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
                                    
                                    # Tạo ảnh debug
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_image(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🖼️ Trang {page_num}: Tách được {len(figures)} ảnh/bảng")
                                    
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Tạo prompt cải tiến cho Gemini
                            prompt = f"""
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh trang {page_num} thành định dạng LaTeX chính xác với cấu trúc chuẩn.

YÊU CẦU ĐỊNH DẠNG:

1. **Trắc nghiệm 4 phương án:**
```
Câu X: [nội dung câu hỏi]
A. [đáp án A]
B. [đáp án B]  
C. [đáp án C]
D. [đáp án D]
```

2. **Trắc nghiệm đúng sai:**
```
a) [nội dung đáp án a]
b) [nội dung đáp án b]
c) [nội dung đáp án c]
d) [nội dung đáp án d]
```

3. **Trả lời ngắn/Tự luận:**
```
Câu X: [nội dung câu hỏi]
```

4. **Công thức toán học:**
- Inline: ${{x^2 + y^2}}$
- Display: $${{\\int_0^1 x dx = \\frac{{1}}{{2}}}}$$

5. **Hình ảnh và bảng:**
{'- Khi thấy hình ảnh/đồ thị: sử dụng từ khóa "xem hình", "theo hình", "hình sau"' if enable_extraction else ''}
{'- Khi thấy bảng: sử dụng từ khóa "bảng sau", "theo bảng", "quan sát bảng"' if enable_extraction else ''}

YÊU CẦU KHÁC:
- Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text và công thức toán học
- Sử dụng ký hiệu LaTeX chuẩn
- Đảm bảo định dạng đúng cho từng loại câu hỏi
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
                        st.text_area("📝 Kết quả LaTeX (định dạng chuẩn):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị thống kê
                        if enable_extraction:
                            st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} ảnh/bảng")
                            
                            # Hiển thị ảnh debug và ảnh đã cắt
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug - Ảnh đã phát hiện và cắt")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    st.write(f"**Trang {page_num} - Vùng phát hiện:**")
                                    st.image(debug_img, caption=f"Đã phát hiện {len(figures)} vùng", use_column_width=True)
                                    
                                    # Hiển thị từng ảnh đã cắt với thông tin chi tiết
                                    if figures:
                                        cols = st.columns(min(len(figures), 3))
                                        for idx, fig in enumerate(figures):
                                            with cols[idx % 3]:
                                                # Decode và hiển thị ảnh cắt
                                                img_data = base64.b64decode(fig['base64'])
                                                img_pil = Image.open(io.BytesIO(img_data))
                                                
                                                st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                                st.image(img_pil, caption=fig['name'], use_column_width=True)
                                                
                                                # Thông tin chi tiết
                                                st.markdown(f'''
                                                <div class="image-info">
                                                <strong>{fig['name']}</strong><br>
                                                Loại: {"Bảng" if fig['is_table'] else "Hình ảnh"}<br>
                                                Confidence: {fig['confidence']:.1f}%<br>
                                                Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                                Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px
                                                </div>
                                                ''', unsafe_allow_html=True)
                                                st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn + ảnh)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_enhanced_latex.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word (Enhanced)",
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
                                
                                st.success("✅ File Word với định dạng chuẩn đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh (tương tự như PDF tab)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX + Tách ảnh nâng cao")
        
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
                
                for i, uploaded_image in enumerate(uploaded_images[:2]):
                    st.write(f"**Ảnh {i+1}: {uploaded_image.name}**")
                    image = Image.open(uploaded_image)
                    st.image(image, use_column_width=True)
                
                if len(uploaded_images) > 2:
                    st.info(f"... và {len(uploaded_images) - 2} ảnh khác")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi ảnh + Tách ảnh nâng cao", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    all_debug_images = []
                    
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
                                
                                # Tạo ảnh debug
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_image(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🖼️ {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành định dạng LaTeX chính xác với cấu trúc chuẩn.

YÊU CẦU ĐỊNH DẠNG:

1. **Trắc nghiệm 4 phương án:**
```
Câu X: [nội dung câu hỏi]
A. [đáp án A]
B. [đáp án B]  
C. [đáp án C]
D. [đáp án D]
```

2. **Trắc nghiệm đúng sai:**
```
a) [nội dung đáp án a]
b) [nội dung đáp án b]
c) [nội dung đáp án c]
d) [nội dung đáp án d]
```

3. **Trả lời ngắn/Tự luận:**
```
Câu X: [nội dung câu hỏi]
```

4. **Công thức toán học:**
- Inline: ${x^2 + y^2}$
- Display: $${\\int_0^1 x dx = \\frac{1}{2}}$$

YÊU CẦU KHÁC:
- Giữ CHÍNH XÁC thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text và công thức toán học
- Sử dụng ký hiệu LaTeX chuẩn
- Đảm bảo định dạng đúng cho từng loại câu hỏi
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
                    st.text_area("📝 Kết quả LaTeX (định dạng chuẩn):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Hiển thị thống kê và ảnh debug
                    if enable_extraction:
                        st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} ảnh/bảng")
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug - Ảnh đã phát hiện và cắt")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                st.write(f"**{img_name} - Vùng phát hiện:**")
                                st.image(debug_img, caption=f"Đã phát hiện {len(figures)} vùng", use_column_width=True)
                                
                                if figures:
                                    cols = st.columns(min(len(figures), 3))
                                    for idx, fig in enumerate(figures):
                                        with cols[idx % 3]:
                                            img_data = base64.b64decode(fig['base64'])
                                            img_pil = Image.open(io.BytesIO(img_data))
                                            
                                            st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                            st.image(img_pil, caption=fig['name'], use_column_width=True)
                                            
                                            st.markdown(f'''
                                            <div class="image-info">
                                            <strong>{fig['name']}</strong><br>
                                            Loại: {"Bảng" if fig['is_table'] else "Hình ảnh"}<br>
                                            Confidence: {fig['confidence']:.1f}%<br>
                                            Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                            Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px
                                            </div>
                                            ''', unsafe_allow_html=True)
                                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn + ảnh)", key="create_word_images"):
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
                                    label="📥 Tải file Word (Enhanced)",
                                    data=word_buffer.getvalue(),
                                    file_name="images_enhanced_latex.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word với định dạng chuẩn đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>✨ <strong>Enhanced Version:</strong> Thuật toán cắt ảnh cải tiến + Định dạng chuẩn!</p>
        <p>🎯 Hỗ trợ đầy đủ: Trắc nghiệm 4 phương án, Đúng/Sai, Tự luận + AI tách ảnh thông minh</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
