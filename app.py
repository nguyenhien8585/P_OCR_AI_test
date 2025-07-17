import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt, RGBColor, Inches
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
    page_title="PDF/Image to LaTeX Converter - Simple & Reliable",
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
</style>
""", unsafe_allow_html=True)

class SimpleImageExtractor:
    """Class đơn giản và ổn định để tách ảnh/bảng"""
    
    def __init__(self):
        self.min_area_ratio = 0.005
        self.min_area_abs = 2000
        self.min_width = 60
        self.min_height = 60
        self.max_figures = 15
        self.padding = 20
        self.confidence_threshold = 40
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng với thuật toán đơn giản, ổn định"""
        if not CV2_AVAILABLE:
            return [], 0, 0
        
        # Đọc ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # Tiền xử lý đơn giản
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Làm mịn
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Phát hiện cạnh
        edges = cv2.Canny(gray, 50, 150)
        
        # Dilate để nối các thành phần
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)
        
        # Morphological closing để lấp khoảng trống
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 10))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_close)
        
        # Tìm contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc cơ bản
            if area < self.min_area_abs or area_ratio < self.min_area_ratio or area_ratio > 0.8:
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            if not (0.2 < aspect_ratio < 10.0):
                continue
            
            # Loại bỏ vùng ở rìa
            margin = 0.03
            if (x < margin*w or y < margin*h or 
                (x+ww) > (1-margin)*w or (y+hh) > (1-margin)*h):
                continue
            
            # Tính đặc trưng đơn giản
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(cnt)
            
            if hull_area == 0 or contour_area < 100:
                continue
            
            solidity = float(contour_area) / hull_area
            extent = float(contour_area) / area
            
            if solidity < 0.3 or extent < 0.2:
                continue
            
            # Phân loại đơn giản
            is_table = self._is_table_simple(ww, hh, aspect_ratio, w, h)
            
            # Tính confidence đơn giản
            confidence = self._calculate_confidence_simple(area_ratio, aspect_ratio, solidity, extent)
            
            if confidence >= self.confidence_threshold:
                candidates.append({
                    "area": area,
                    "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                    "is_table": is_table,
                    "confidence": confidence,
                    "aspect_ratio": aspect_ratio,
                    "solidity": solidity,
                    "extent": extent,
                    "bbox": (x, y, ww, hh),
                    "center_y": y + hh // 2,
                    "y_position": y
                })
        
        # Sắp xếp và lọc overlap
        candidates = sorted(candidates, key=lambda f: f['confidence'], reverse=True)
        candidates = self._filter_overlapping_simple(candidates)
        candidates = candidates[:self.max_figures]
        candidates = sorted(candidates, key=lambda box: (box["y0"], box["x0"]))
        
        # Tạo ảnh kết quả
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Padding đơn giản
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
                "area": fig_data["area"],
                "solidity": fig_data["solidity"],
                "extent": fig_data["extent"],
                "center_y": fig_data["center_y"],
                "y_position": fig_data["y_position"]
            })
        
        return final_figures, h, w
    
    def _is_table_simple(self, w, h, aspect_ratio, img_w, img_h):
        """Phân loại table/image đơn giản"""
        # Table thường có aspect ratio ngang và chiếm nhiều chiều rộng
        is_wide = aspect_ratio > 1.5
        is_substantial_width = w > 0.3 * img_w
        is_reasonable_height = 0.1 * img_h < h < 0.8 * img_h
        
        return is_wide and is_substantial_width and is_reasonable_height
    
    def _calculate_confidence_simple(self, area_ratio, aspect_ratio, solidity, extent):
        """Tính confidence đơn giản"""
        confidence = 0
        
        # Điểm từ area
        if 0.02 < area_ratio < 0.6:
            confidence += 50
        elif 0.01 < area_ratio < 0.8:
            confidence += 30
        else:
            confidence += 10
        
        # Điểm từ aspect ratio
        if 0.5 < aspect_ratio < 3.0:
            confidence += 25
        elif 0.3 < aspect_ratio < 5.0:
            confidence += 15
        else:
            confidence += 5
        
        # Điểm từ shape quality
        if solidity > 0.7:
            confidence += 15
        elif solidity > 0.5:
            confidence += 10
        else:
            confidence += 5
        
        if extent > 0.5:
            confidence += 10
        elif extent > 0.3:
            confidence += 5
        
        return min(100, confidence)
    
    def _filter_overlapping_simple(self, candidates):
        """Lọc overlap đơn giản"""
        filtered = []
        
        for candidate in candidates:
            is_overlap = False
            x0, y0, x1, y1 = candidate['x0'], candidate['y0'], candidate['x1'], candidate['y1']
            area1 = (x1-x0) * (y1-y0)
            
            for other in filtered:
                ox0, oy0, ox1, oy1 = other['x0'], other['y0'], other['x1'], other['y1']
                area2 = (ox1-ox0) * (oy1-oy0)
                
                # Tính IoU
                intersection_area = max(0, min(x1, ox1) - max(x0, ox0)) * max(0, min(y1, oy1) - max(y0, oy0))
                union_area = area1 + area2 - intersection_area
                
                if union_area > 0:
                    iou = intersection_area / union_area
                    if iou > 0.3:
                        is_overlap = True
                        break
            
            if not is_overlap:
                filtered.append(candidate)
        
        return filtered
    
    def insert_figures_into_text_smart(self, text, figures, img_h, img_w):
        """Chèn ảnh vào văn bản thông minh - kết hợp từ khóa + vị trí"""
        if not figures:
            return text
        
        lines = text.split('\n')
        result_lines = lines[:]
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['y_position'])
        
        # Phân tích cấu trúc câu hỏi
        question_blocks = self._identify_question_blocks(lines)
        
        # Chèn figures vào từng question block
        inserted_count = 0
        used_figures = set()
        
        for fig in sorted_figures:
            if fig['name'] in used_figures:
                continue
            
            # Tìm question block phù hợp
            best_position = self._find_best_insertion_position(fig, question_blocks, lines, img_h)
            
            if best_position is not None:
                insertion_index = best_position + inserted_count
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {fig['name']}]\n" if fig['is_table'] else f"\n[HÌNH: {fig['name']}]\n"
                    result_lines.insert(insertion_index, tag)
                    inserted_count += 1
                    used_figures.add(fig['name'])
        
        return '\n'.join(result_lines)
    
    def _identify_question_blocks(self, lines):
        """Nhận diện các khối câu hỏi"""
        blocks = []
        current_block = None
        
        for i, line in enumerate(lines):
            line_content = line.strip()
            
            # Bắt đầu câu hỏi mới
            if re.match(r'^câu\s+\d+', line_content.lower()):
                if current_block:
                    blocks.append(current_block)
                
                current_block = {
                    'question_line': i,
                    'question_number': self._extract_question_number(line_content),
                    'description_lines': [],
                    'answer_start': None,
                    'answer_lines': []
                }
            
            elif current_block:
                # Tìm điểm chèn tối ưu
                if any(keyword in line_content.lower() for keyword in [
                    'xét tính đúng sai', 'khẳng định sau:', 'sau:', 'cho hình', 'trong hình'
                ]):
                    current_block['description_lines'].append(i)
                
                # Nhận diện đáp án
                elif re.match(r'^[a-d]\)', line_content) or re.match(r'^[A-D]\)', line_content):
                    if current_block['answer_start'] is None:
                        current_block['answer_start'] = i
                    current_block['answer_lines'].append(i)
        
        if current_block:
            blocks.append(current_block)
        
        return blocks
    
    def _extract_question_number(self, line_content):
        """Trích xuất số câu hỏi"""
        match = re.search(r'câu\s+(\d+)', line_content.lower())
        return int(match.group(1)) if match else None
    
    def _find_best_insertion_position(self, figure, question_blocks, lines, img_h):
        """Tìm vị trí chèn tốt nhất"""
        fig_y = figure['y_position']
        
        best_score = 0
        best_position = None
        
        for block in question_blocks:
            # Tính điểm cho các vị trí trong block
            
            # Vị trí 1: Sau description lines (trước đáp án)
            if block['description_lines'] and block['answer_start']:
                for desc_line in block['description_lines']:
                    line_content = lines[desc_line].strip().lower()
                    
                    # Ưu tiên vị trí sau dòng có từ khóa đặc biệt
                    position_score = 50
                    
                    if 'khẳng định sau:' in line_content or line_content.endswith('sau:'):
                        position_score += 40
                    elif 'xét tính đúng sai' in line_content:
                        position_score += 30
                    elif 'cho hình' in line_content or 'trong hình' in line_content:
                        position_score += 25
                    
                    # Điểm từ vị trí Y
                    estimated_line_y = (desc_line / len(lines)) * img_h
                    y_distance = abs(estimated_line_y - fig_y) / img_h
                    y_score = max(0, 30 - y_distance * 30)
                    
                    total_score = position_score + y_score
                    
                    if total_score > best_score:
                        best_score = total_score
                        best_position = desc_line + 1
            
            # Vị trí 2: Sau question line (nếu không có description tốt)
            elif block['question_line'] and best_score < 40:
                estimated_line_y = (block['question_line'] / len(lines)) * img_h
                y_distance = abs(estimated_line_y - fig_y) / img_h
                total_score = 30 - y_distance * 20
                
                if total_score > best_score:
                    best_score = total_score
                    best_position = block['question_line'] + 1
        
        return best_position if best_score > 20 else None
    
    def create_debug_image(self, image_bytes, figures):
        """Tạo ảnh debug đơn giản"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            bbox = fig['original_bbox']
            x, y, w, h = bbox
            
            # Vẽ khung
            thickness = 3
            draw.rectangle([x, y, x+w, y+h], outline=color, width=thickness)
            
            # Vẽ label
            type_label = "TBL" if fig['is_table'] else "IMG"
            label = f"{fig['name']}\n{type_label}: {fig['confidence']:.0f}%\nY: {fig['y_position']}"
            
            # Vẽ text background
            lines = label.split('\n')
            max_width = max(len(line) for line in lines) * 8
            text_height = len(lines) * 15
            draw.rectangle([x, y-text_height-5, x+max_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(lines):
                draw.text((x+2, y-text_height+j*13), line, fill='white')
        
        return img_pil

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

class SimpleWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu đã chuyển đổi từ PDF/Ảnh', 0)
        title.alignment = 1
        
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter")
        doc.add_paragraph(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        # Xử lý nội dung đơn giản
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks
            if line.startswith('```') or line.endswith('```'):
                continue
            
            # Xử lý tag ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                SimpleWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                SimpleWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            # Skip comments
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                continue
            
            if not line:
                continue
            
            # Xử lý công thức đơn giản - chuyển về text
            if '${' in line and '}$' in line:
                # Xử lý equation đơn giản
                processed_line = SimpleWordExporter._process_simple_equations(line)
                p = doc.add_paragraph(processed_line)
                run = p.runs[0] if p.runs else p.add_run("")
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12)
            else:
                # Đoạn văn bình thường
                p = doc.add_paragraph(line)
                run = p.runs[0] if p.runs else p.add_run("")
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12)
        
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
    def _process_simple_equations(line):
        """Xử lý equations đơn giản - chuyển về text"""
        result = line
        
        # LaTeX to Unicode mapping đơn giản
        replacements = {
            '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ',
            '\\theta': 'θ', '\\lambda': 'λ', '\\mu': 'μ', '\\pi': 'π',
            '\\sigma': 'σ', '\\phi': 'φ', '\\omega': 'ω',
            '\\leq': '≤', '\\geq': '≥', '\\neq': '≠', '\\approx': '≈',
            '\\times': '×', '\\div': '÷', '\\pm': '±', '\\infty': '∞',
            '\\perp': '⊥', '\\parallel': '∥', '\\angle': '∠', '\\degree': '°'
        }
        
        # Xử lý các công thức đơn giản
        while '${' in result and '}$' in result:
            start = result.find('${')
            end = result.find('}$', start)
            
            if start != -1 and end != -1:
                equation = result[start+2:end]
                
                # Thay thế symbols
                for latex, unicode_char in replacements.items():
                    equation = equation.replace(latex, unicode_char)
                
                # Xử lý fractions đơn giản
                equation = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)', equation)
                
                # Xử lý superscript/subscript đơn giản
                equation = re.sub(r'\^\{([^}]+)\}', r'^(\1)', equation)
                equation = re.sub(r'_\{([^}]+)\}', r'_(\1)', equation)
                
                # Loại bỏ các command khác
                equation = re.sub(r'\\[a-zA-Z]+', '', equation)
                equation = equation.replace('{', '').replace('}', '')
                
                result = result[:start] + equation + result[end+2:]
            else:
                break
        
        return result
    
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
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Simple & Reliable</h1>', unsafe_allow_html=True)
    
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
            st.subheader("🖼️ Tách ảnh đơn giản")
            enable_extraction = st.checkbox("Bật tách ảnh/bảng tự động", value=True)
            
            if enable_extraction:
                min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.5, 0.1) / 100
                max_figures = st.slider("Số ảnh tối đa", 1, 20, 15, 1)
                min_size = st.slider("Kích thước tối thiểu (px)", 40, 150, 60, 10)
                padding = st.slider("Padding xung quanh (px)", 10, 50, 20, 5)
                confidence_threshold = st.slider("Ngưỡng confidence (%)", 20, 80, 40, 5)
                show_debug = st.checkbox("Hiển thị ảnh debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### ✅ **Phiên bản ổn định:**
        - ✅ **Thuật toán đơn giản** - Hoạt động ổn định 
        - ✅ **Tách ảnh reliable** - Không bị lỗi
        - ✅ **Chèn ảnh thông minh** - Keyword + Position
        - ✅ **Word export đơn giản** - Không phức tạp
        - ✅ **Format chuẩn** - A), B), C), D)
        
        ### 🎯 Tính năng:
        - ✅ Tách ảnh/bảng ổn định
        - ✅ Chèn đúng vị trí
        - ✅ Export Word bình thường
        - ✅ Debug visualization
        
        ### 📝 Format:
        ```
        Câu X: [nội dung]
        [HÌNH/BẢNG: name.jpeg] 
        A) [Đáp án]
        B) [Đáp án]  
        ```
        
        ### 🔑 API Key:
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
            image_extractor.padding = padding
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
                                    
                                    st.write(f"🖼️ Trang {page_num}: Tách được {len(figures)} hình/bảng")
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cho Gemini
                            prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng CHÍNH XÁC.

🎯 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - SỬ DỤNG A), B), C), D):**
Câu X: [nội dung câu hỏi đầy đủ]
A) [nội dung đáp án A đầy đủ]
B) [nội dung đáp án B đầy đủ]
C) [nội dung đáp án C đầy đủ]
D) [nội dung đáp án D đầy đủ]

2. **Trắc nghiệm đúng sai - SỬ DỤNG a), b), c), d):**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Công thức toán học:**
- CHỈ sử dụng: ${x^2 + y^2}$ cho công thức
- VÍ DỤ: ${ABCD}$, ${A'C' \\perp BD}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU:
- TUYỆT ĐỐI sử dụng A), B), C), D) cho trắc nghiệm 4 phương án
- TUYỆT ĐỐI sử dụng a), b), c), d) cho trắc nghiệm đúng sai
- CHỈ văn bản thuần túy với công thức ${...}$
- Giữ chính xác thứ tự và cấu trúc nội dung
- Bao gồm tất cả text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn ảnh vào văn bản THÔNG MINH
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_smart(
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
                        st.text_area("📝 Kết quả:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê
                        if enable_extraction and CV2_AVAILABLE:
                            st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} hình/bảng")
                            
                            # Debug images
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug - Hình ảnh đã tách")
                                
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
                                                st.write(f"🏷️ Loại: {'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                st.write(f"🎯 Confidence: {fig['confidence']:.1f}%")
                                                st.write(f"📍 Vị trí Y: {fig['y_position']}px")
                                                st.write(f"📐 Tỷ lệ: {fig['aspect_ratio']:.2f}")
                        
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
                                
                                word_buffer = SimpleWordExporter.create_word_document(
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
    
    # Tab Image
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
                                
                                st.write(f"🖼️ {uploaded_image.name}: Tách được {len(figures)} hình/bảng")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng CHÍNH XÁC.

🎯 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - SỬ DỤNG A), B), C), D):**
Câu X: [nội dung câu hỏi đầy đủ]
A) [nội dung đáp án A đầy đủ]
B) [nội dung đáp án B đầy đủ]
C) [nội dung đáp án C đầy đủ]
D) [nội dung đáp án D đầy đủ]

2. **Trắc nghiệm đúng sai - SỬ DỤNG a), b), c), d):**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Công thức toán học:**
- CHỈ sử dụng: ${x^2 + y^2}$ cho công thức
- VÍ DỤ: ${ABCD}$, ${A'C' \\perp BD}$

⚠️ YÊU CẦU:
- TUYỆT ĐỐI sử dụng A), B), C), D) cho trắc nghiệm 4 phương án
- TUYỆT ĐỐI sử dụng a), b), c), d) cho trắc nghiệm đúng sai
- CHỈ văn bản thuần túy với công thức ${...}$
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_smart(
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
                    st.text_area("📝 Kết quả:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug
                    if enable_extraction and CV2_AVAILABLE:
                        st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} hình/bảng")
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug - Hình ảnh đã tách")
                            
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
                                            st.write(f"🏷️ Loại: {'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                            st.write(f"🎯 Confidence: {fig['confidence']:.1f}%")
                                            st.write(f"📍 Vị trí Y: {fig['y_position']}px")
                                            st.write(f"📐 Tỷ lệ: {fig['aspect_ratio']:.2f}")
                    
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
                                
                                word_buffer = SimpleWordExporter.create_word_document(
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
        <p>🎯 <strong>SIMPLE & RELIABLE VERSION:</strong> Thuật toán đơn giản, ổn định</p>
        <p>📝 <strong>Smart Insertion:</strong> Kết hợp keyword detection + position analysis</p>
        <p>🔍 <strong>Stable Extraction:</strong> Hoạt động ổn định với mọi loại ảnh</p>
        <p>📄 <strong>Standard Word:</strong> Export bình thường, dễ chỉnh sửa</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
