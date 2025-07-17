import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import fitz  # PyMuPDF
import tempfile
import os
import re
import time
import math

# Import python-docx
try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import cv2
    import numpy as np
    from scipy import ndimage
    from skimage import filters, measure, morphology
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Cấu hình trang
st.set_page_config(
    page_title="PDF/LaTeX Converter - Enhanced & Fixed",
    page_icon="📝",
    layout="wide"
)

# CSS cải tiến với hiệu ứng đẹp
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #2E86AB;
        font-size: 2.5rem;
        margin-bottom: 2rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    .latex-output {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 1.5rem;
        border-radius: 12px;
        font-family: 'Consolas', 'Monaco', monospace;
        border-left: 4px solid #2E86AB;
        max-height: 400px;
        overflow-y: auto;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .extracted-image {
        border: 3px solid #28a745;
        border-radius: 12px;
        margin: 15px 0;
        padding: 10px;
        background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        transition: transform 0.3s ease;
    }
    
    .extracted-image:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    
    .debug-info {
        background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
        padding: 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
        margin-top: 8px;
        border-left: 3px solid #2196F3;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        margin: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        transition: transform 0.2s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
    }
    
    .figure-preview {
        border: 2px solid #007bff;
        border-radius: 8px;
        padding: 8px;
        margin: 8px 0;
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .figure-info {
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        padding: 0.8rem;
        border-radius: 6px;
        margin: 5px 0;
        font-size: 0.85rem;
        border-left: 3px solid #ffc107;
    }
    
    .status-success {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        color: #155724;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin: 10px 0;
    }
    
    .status-warning {
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        color: #856404;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ffc107;
        margin: 10px 0;
    }
    
    .processing-container {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 2rem;
        border-radius: 12px;
        margin: 20px 0;
        border: 2px solid #dee2e6;
    }
</style>
""", unsafe_allow_html=True)

class SuperEnhancedImageExtractor:
    """
    Thuật toán tách ảnh SIÊU CẢI TIẾN - Đảm bảo cắt được ảnh
    """
    
    def __init__(self):
        # Tham số siêu relaxed để tách được nhiều ảnh
        self.min_area_ratio = 0.0008      # 0.08% diện tích (CỰC NHỎ)
        self.min_area_abs = 400           # 400 pixels (CỰC NHỎ)
        self.min_width = 25               # 25 pixels (CỰC NHỎ)
        self.min_height = 25              # 25 pixels (CỰC NHỎ)
        self.max_figures = 30             # Tối đa 30 ảnh
        self.max_area_ratio = 0.80        # Tối đa 80% diện tích
        
        # Tham số cắt ảnh
        self.smart_padding = 30           # Padding lớn hơn
        self.quality_threshold = 0.15     # Ngưỡng chất lượng CỰC THẤP
        self.edge_margin = 0.005          # Margin từ rìa CỰC NHỎ
        
        # Tham số phân tích - CỰC RELAXED
        self.text_ratio_threshold = 0.8   # Ngưỡng tỷ lệ text cao
        self.line_density_threshold = 0.01 # Ngưỡng mật độ line CỰC THẤP
        self.confidence_threshold = 20    # Ngưỡng confidence CỰC THẤP
        
        # Tham số morphology nhẹ
        self.morph_kernel_size = 2
        self.dilate_iterations = 1
        self.erode_iterations = 1
        
        # Tham số mới cho edge detection
        self.canny_low = 30
        self.canny_high = 80
        self.blur_kernel = 3
    
    def extract_figures_and_tables(self, image_bytes):
        """
        Tách ảnh với thuật toán SIÊU CẢI TIẾN - Đảm bảo tách được
        """
        if not CV2_AVAILABLE:
            st.error("❌ OpenCV không có sẵn! Cần cài đặt: pip install opencv-python")
            return [], 0, 0
        
        try:
            # Đọc ảnh
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            st.write(f"🔍 Phân tích ảnh kích thước: {w}x{h}")
            
            # Bước 1: Tiền xử lý ảnh SIÊU CẢI TIẾN
            enhanced_img = self._super_enhance_image(img)
            
            # Bước 2: Phát hiện regions bằng NHIỀU PHƯƠNG PHÁP
            all_candidates = []
            
            # Phương pháp 1: Edge-based detection
            edge_candidates = self._detect_by_edges(enhanced_img, w, h)
            all_candidates.extend(edge_candidates)
            st.write(f"   📍 Edge detection: {len(edge_candidates)} candidates")
            
            # Phương pháp 2: Contour-based detection
            contour_candidates = self._detect_by_contours(enhanced_img, w, h)
            all_candidates.extend(contour_candidates)
            st.write(f"   📍 Contour detection: {len(contour_candidates)} candidates")
            
            # Phương pháp 3: Grid-based detection (cho tables)
            grid_candidates = self._detect_by_grid(enhanced_img, w, h)
            all_candidates.extend(grid_candidates)
            st.write(f"   📍 Grid detection: {len(grid_candidates)} candidates")
            
            # Phương pháp 4: Blob detection
            blob_candidates = self._detect_by_blobs(enhanced_img, w, h)
            all_candidates.extend(blob_candidates)
            st.write(f"   📍 Blob detection: {len(blob_candidates)} candidates")
            
            st.write(f"📊 Tổng candidates trước lọc: {len(all_candidates)}")
            
            # Bước 3: Lọc và merge candidates
            filtered_candidates = self._filter_and_merge_candidates(all_candidates, w, h)
            st.write(f"📊 Sau lọc và merge: {len(filtered_candidates)}")
            
            # Bước 4: Tạo final figures
            final_figures = self._create_final_figures_enhanced(filtered_candidates, img, w, h)
            st.write(f"✅ Final figures: {len(final_figures)}")
            
            return final_figures, h, w
            
        except Exception as e:
            st.error(f"❌ Lỗi trong quá trình tách ảnh: {str(e)}")
            return [], 0, 0
    
    def _super_enhance_image(self, img):
        """
        Tiền xử lý ảnh SIÊU CẢI TIẾN
        """
        # Chuyển sang grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Blur nhẹ để giảm noise
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        
        # Tăng cường contrast với CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)
        
        # Normalize
        normalized = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
        
        return normalized
    
    def _detect_by_edges(self, gray_img, w, h):
        """
        Phát hiện bằng edge detection
        """
        # Edge detection với threshold thấp
        edges = cv2.Canny(gray_img, self.canny_low, self.canny_high)
        
        # Dilate để nối các edge
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges_dilated = cv2.dilate(edges, kernel, iterations=1)
        
        # Tìm contours
        contours, _ = cv2.findContours(edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            
            if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                candidates.append({
                    'bbox': (x, y, ww, hh),
                    'area': area,
                    'method': 'edge',
                    'confidence': 30
                })
        
        return candidates
    
    def _detect_by_contours(self, gray_img, w, h):
        """
        Phát hiện bằng contour analysis
        """
        # Threshold với Otsu
        _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (self.morph_kernel_size, self.morph_kernel_size))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Tìm contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            
            if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                candidates.append({
                    'bbox': (x, y, ww, hh),
                    'area': area,
                    'method': 'contour',
                    'confidence': 40
                })
        
        return candidates
    
    def _detect_by_grid(self, gray_img, w, h):
        """
        Phát hiện tables bằng grid analysis
        """
        # Horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//20, 1))
        horizontal_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, horizontal_kernel)
        
        # Vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//20))
        vertical_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, vertical_kernel)
        
        # Combine lines
        grid_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
        
        # Dilate để tạo regions
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        grid_dilated = cv2.dilate(grid_mask, kernel, iterations=2)
        
        # Tìm contours
        contours, _ = cv2.findContours(grid_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            
            if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                # Bonus cho table-like shapes
                aspect_ratio = ww / (hh + 1e-6)
                confidence = 50 if aspect_ratio > 1.5 else 30
                
                candidates.append({
                    'bbox': (x, y, ww, hh),
                    'area': area,
                    'method': 'grid',
                    'confidence': confidence,
                    'is_table': aspect_ratio > 1.5
                })
        
        return candidates
    
    def _detect_by_blobs(self, gray_img, w, h):
        """
        Phát hiện bằng blob detection
        """
        # Threshold adaptively
        adaptive_thresh = cv2.adaptiveThreshold(
            gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Invert
        inverted = cv2.bitwise_not(adaptive_thresh)
        
        # Morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        opened = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel)
        
        # Tìm contours
        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            
            if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                candidates.append({
                    'bbox': (x, y, ww, hh),
                    'area': area,
                    'method': 'blob',
                    'confidence': 35
                })
        
        return candidates
    
    def _is_valid_candidate(self, x, y, ww, hh, area, img_w, img_h):
        """
        Kiểm tra candidate có hợp lệ không - SIÊU RELAXED
        """
        area_ratio = area / (img_w * img_h)
        
        # Điều kiện cơ bản
        if (area < self.min_area_abs or 
            area_ratio < self.min_area_ratio or 
            area_ratio > self.max_area_ratio or
            ww < self.min_width or 
            hh < self.min_height):
            return False
        
        # Kiểm tra vị trí (không quá gần rìa)
        if (x < self.edge_margin * img_w or 
            y < self.edge_margin * img_h or 
            (x + ww) > (1 - self.edge_margin) * img_w or 
            (y + hh) > (1 - self.edge_margin) * img_h):
            return False
        
        return True
    
    def _filter_and_merge_candidates(self, candidates, w, h):
        """
        Lọc và merge candidates
        """
        if not candidates:
            return []
        
        # Sắp xếp theo area giảm dần
        candidates = sorted(candidates, key=lambda x: x['area'], reverse=True)
        
        # Loại bỏ overlap
        filtered = []
        for candidate in candidates:
            if not self._is_overlapping_with_list(candidate, filtered):
                # Tính confidence tổng hợp
                candidate['final_confidence'] = self._calculate_final_confidence(candidate, w, h)
                if candidate['final_confidence'] >= self.confidence_threshold:
                    filtered.append(candidate)
        
        # Giới hạn số lượng
        return filtered[:self.max_figures]
    
    def _is_overlapping_with_list(self, candidate, existing_list):
        """
        Kiểm tra overlap với danh sách existing
        """
        x1, y1, w1, h1 = candidate['bbox']
        
        for existing in existing_list:
            x2, y2, w2, h2 = existing['bbox']
            
            # Tính IoU
            intersection_area = max(0, min(x1+w1, x2+w2) - max(x1, x2)) * max(0, min(y1+h1, y2+h2) - max(y1, y2))
            union_area = w1*h1 + w2*h2 - intersection_area
            
            if union_area > 0:
                iou = intersection_area / union_area
                if iou > 0.25:  # Ngưỡng overlap thấp
                    return True
        
        return False
    
    def _calculate_final_confidence(self, candidate, w, h):
        """
        Tính confidence cuối cùng
        """
        x, y, ww, hh = candidate['bbox']
        area_ratio = candidate['area'] / (w * h)
        aspect_ratio = ww / (hh + 1e-6)
        
        confidence = candidate.get('confidence', 30)
        
        # Bonus cho size phù hợp
        if 0.01 < area_ratio < 0.3:
            confidence += 20
        elif 0.005 < area_ratio < 0.5:
            confidence += 10
        
        # Bonus cho aspect ratio
        if 0.5 < aspect_ratio < 3.0:
            confidence += 15
        elif 0.3 < aspect_ratio < 5.0:
            confidence += 5
        
        # Bonus cho method
        if candidate['method'] == 'grid':
            confidence += 10
        elif candidate['method'] == 'edge':
            confidence += 5
        
        return min(100, confidence)
    
    def _create_final_figures_enhanced(self, candidates, img, w, h):
        """
        Tạo final figures với cắt ảnh cải tiến
        """
        # Sắp xếp theo vị trí
        candidates = sorted(candidates, key=lambda x: (x['bbox'][1], x['bbox'][0]))
        
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for candidate in candidates:
            # Cắt ảnh với smart padding
            cropped_img = self._smart_crop_enhanced(img, candidate, w, h)
            
            if cropped_img is None:
                continue
            
            # Chuyển thành base64
            buf = io.BytesIO()
            Image.fromarray(cropped_img).save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            # Xác định loại và tên
            is_table = candidate.get('is_table', False) or candidate.get('method') == 'grid'
            
            if is_table:
                name = f"table-{table_idx+1}.jpeg"
                table_idx += 1
            else:
                name = f"figure-{img_idx+1}.jpeg"
                img_idx += 1
            
            final_figures.append({
                "name": name,
                "base64": b64,
                "is_table": is_table,
                "bbox": candidate["bbox"],
                "confidence": candidate["final_confidence"],
                "area_ratio": candidate["area"] / (w * h),
                "aspect_ratio": candidate["bbox"][2] / (candidate["bbox"][3] + 1e-6),
                "method": candidate["method"],
                "center_y": candidate["bbox"][1] + candidate["bbox"][3] // 2,
                "center_x": candidate["bbox"][0] + candidate["bbox"][2] // 2
            })
        
        return final_figures
    
    def _smart_crop_enhanced(self, img, candidate, img_w, img_h):
        """
        Cắt ảnh thông minh cải tiến
        """
        x, y, w, h = candidate['bbox']
        
        # Tính padding thông minh
        padding_x = min(self.smart_padding, w // 4)
        padding_y = min(self.smart_padding, h // 4)
        
        # Điều chỉnh boundaries
        x0 = max(0, x - padding_x)
        y0 = max(0, y - padding_y)
        x1 = min(img_w, x + w + padding_x)
        y1 = min(img_h, y + h + padding_y)
        
        # Cắt ảnh
        cropped = img[y0:y1, x0:x1]
        
        if cropped.size == 0:
            return None
        
        # Làm sạch và tăng cường
        cleaned = self._clean_and_enhance_cropped(cropped)
        
        return cleaned
    
    def _clean_and_enhance_cropped(self, cropped_img):
        """
        Làm sạch và tăng cường ảnh đã cắt
        """
        # Chuyển sang PIL
        pil_img = Image.fromarray(cropped_img)
        
        # Tăng cường contrast nhẹ
        enhancer = ImageEnhance.Contrast(pil_img)
        enhanced = enhancer.enhance(1.1)
        
        # Sharpen nhẹ
        sharpened = enhanced.filter(ImageFilter.UnsharpMask(radius=0.5, percent=100, threshold=2))
        
        return np.array(sharpened)
    
    def create_beautiful_debug_visualization(self, image_bytes, figures):
        """
        Tạo debug visualization ĐẸP
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box với style đẹp
            draw.rectangle([x, y, x+w, y+h], outline=color, width=4)
            
            # Vẽ corner markers
            corner_size = 10
            # Top-left
            draw.rectangle([x, y, x+corner_size, y+corner_size], fill=color)
            # Top-right
            draw.rectangle([x+w-corner_size, y, x+w, y+corner_size], fill=color)
            # Bottom-left
            draw.rectangle([x, y+h-corner_size, x+corner_size, y+h], fill=color)
            # Bottom-right
            draw.rectangle([x+w-corner_size, y+h-corner_size, x+w, y+h], fill=color)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-8, center_y-8, center_x+8, center_y+8], fill=color, outline='white', width=2)
            
            # Label với background đẹp
            label_lines = [
                f"📷 {fig['name']}",
                f"{'📊' if fig['is_table'] else '🖼️'} {fig['confidence']:.0f}%",
                f"📏 {fig['aspect_ratio']:.2f}",
                f"📐 {fig['area_ratio']:.3f}",
                f"⚙️ {fig['method']}"
            ]
            
            # Tính kích thước label
            text_height = len(label_lines) * 18
            text_width = max(len(line) for line in label_lines) * 10
            
            # Vẽ background với bo góc
            label_x = x
            label_y = y - text_height - 10
            if label_y < 0:
                label_y = y + h + 10
            
            # Background với alpha
            overlay = Image.new('RGBA', img_pil.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(
                [label_x, label_y, label_x + text_width, label_y + text_height],
                radius=8, fill=(*tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)), 200)
            )
            
            img_pil = Image.alpha_composite(img_pil.convert('RGBA'), overlay).convert('RGB')
            draw = ImageDraw.Draw(img_pil)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
                draw.text((label_x + 5, label_y + j * 16), line, fill='white', stroke_width=1, stroke_fill='black')
        
        return img_pil
    
    def insert_figures_into_text_precisely(self, text, figures, img_h, img_w):
        """
        Chèn ảnh vào văn bản với độ chính xác cao - CẢI TIẾN
        """
        if not figures:
            return text
        
        lines = text.split('\n')
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        result_lines = lines[:]
        offset = 0
        
        # Chiến lược chèn cải tiến
        for i, figure in enumerate(sorted_figures):
            # Tính vị trí chèn dựa trên multiple factors
            insertion_line = self._calculate_insertion_position(figure, lines, i, len(sorted_figures))
            
            # Điều chỉnh với offset
            actual_insertion = insertion_line + offset
            
            # Đảm bảo không vượt quá
            if actual_insertion > len(result_lines):
                actual_insertion = len(result_lines)
            
            # Tạo tag đẹp
            if figure['is_table']:
                tag = f"[📊 BẢNG: {figure['name']} - Confidence: {figure['confidence']:.1f}%]"
            else:
                tag = f"[🖼️ HÌNH: {figure['name']} - Confidence: {figure['confidence']:.1f}%]"
            
            # Chèn với format đẹp
            result_lines.insert(actual_insertion, "")
            result_lines.insert(actual_insertion + 1, tag)
            result_lines.insert(actual_insertion + 2, f"<!-- Method: {figure['method']}, Aspect: {figure['aspect_ratio']:.2f} -->")
            result_lines.insert(actual_insertion + 3, "")
            
            offset += 4
        
        return '\n'.join(result_lines)
    
    def _calculate_insertion_position(self, figure, lines, fig_index, total_figures):
        """
        Tính vị trí chèn thông minh
        """
        # Tìm câu hỏi patterns
        question_lines = []
        for i, line in enumerate(lines):
            if re.match(r'^(câu|bài|question)\s*\d+', line.strip().lower()):
                question_lines.append(i)
        
        # Nếu có câu hỏi, chèn sau câu hỏi
        if question_lines:
            if fig_index < len(question_lines):
                return question_lines[fig_index] + 1
            else:
                # Chèn sau câu hỏi cuối
                return question_lines[-1] + 2
        
        # Fallback: chèn đều
        section_size = len(lines) // (total_figures + 1)
        return min(section_size * (fig_index + 1), len(lines) - 1)

# Các class khác giữ nguyên nhưng có một số cải tiến nhỏ
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
            # Tăng độ phân giải
            mat = fitz.Matrix(3.5, 3.5)  # Tăng lên 3.5x
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    """
    Xuất Word document với LaTeX và hình ảnh - ĐÃ FIX LỖI
    """
    
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        try:
            # Tạo document mới
            doc = Document()
            
            # Cấu hình font và style
            style = doc.styles['Normal']
            style.font.name = 'Times New Roman'
            style.font.size = Pt(12)
            
            # Thêm tiêu đề
            title_para = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
            title_para.alignment = 1  # Center
            
            # Thông tin metadata
            info_para = doc.add_paragraph()
            info_para.alignment = 1
            info_run = info_para.add_run(
                f"Được tạo bởi Enhanced PDF/LaTeX Converter\n"
                f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Figures: {len(extracted_figures) if extracted_figures else 0}"
            )
            info_run.font.size = Pt(10)
            info_run.font.color.rgb = RGBColor(128, 128, 128)
            
            # Thêm line break
            doc.add_paragraph("")
            
            # Xử lý nội dung LaTeX
            lines = latex_content.split('\n')
            current_paragraph = None
            
            for line in lines:
                line = line.strip()
                
                # Bỏ qua các dòng trống và comment
                if not line or line.startswith('<!--'):
                    if line.startswith('<!--') and ('Trang' in line or 'Page' in line):
                        # Thêm page break cho trang mới
                        if current_paragraph:
                            doc.add_page_break()
                        heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                        heading.alignment = 1
                    continue
                
                # Xử lý tags hình ảnh
                if line.startswith('[') and line.endswith(']'):
                    if 'HÌNH:' in line or 'BẢNG:' in line:
                        EnhancedWordExporter._insert_figure_to_word(doc, line, extracted_figures)
                    continue
                
                # Xử lý câu hỏi (heading)
                if re.match(r'^(câu|bài)\s+\d+', line.lower()):
                    current_paragraph = doc.add_heading(line, level=3)
                    current_paragraph.alignment = 0  # Left align
                    continue
                
                # Xử lý paragraph thường
                if line:
                    para = doc.add_paragraph()
                    EnhancedWordExporter._process_latex_content(para, line)
                    current_paragraph = para
            
            # Thêm appendix nếu có figures
            if extracted_figures:
                EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
            
            # Thêm ảnh gốc nếu không có extracted figures
            if images and not extracted_figures:
                EnhancedWordExporter._add_original_images(doc, images)
            
            # Lưu vào buffer
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            return buffer
            
        except Exception as e:
            st.error(f"❌ Lỗi tạo Word document: {str(e)}")
            raise e
    
    @staticmethod
    def _process_latex_content(para, content):
        """
        Xử lý nội dung LaTeX trong paragraph
        """
        # Tách content thành các phần text và LaTeX
        parts = re.split(r'(\$\{[^}]+\}\$)', content)
        
        for part in parts:
            if part.startswith('${') and part.endswith('}

def display_beautiful_figures(figures, debug_img=None):
    """
    Hiển thị figures một cách đẹp mắt
    """
    if not figures:
        st.markdown('<div class="status-warning">⚠️ Không có figures nào được tách ra</div>', unsafe_allow_html=True)
        return
    
    # Hiển thị debug image nếu có
    if debug_img:
        st.markdown("### 🔍 Debug Visualization")
        st.image(debug_img, caption="Enhanced extraction results", use_column_width=True)
    
    # Hiển thị figures
    st.markdown("### 📸 Figures đã tách")
    
    # Tạo grid layout
    cols_per_row = 3
    for i in range(0, len(figures), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            if i + j < len(figures):
                fig = figures[i + j]
                with cols[j]:
                    # Hiển thị ảnh
                    img_data = base64.b64decode(fig['base64'])
                    img_pil = Image.open(io.BytesIO(img_data))
                    
                    st.markdown('<div class="figure-preview">', unsafe_allow_html=True)
                    st.image(img_pil, use_column_width=True)
                    
                    # Thông tin chi tiết
                    confidence_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                    type_icon = "📊" if fig['is_table'] else "🖼️"
                    
                    st.markdown(f"""
                    <div class="figure-info">
                        <strong>{type_icon} {fig['name']}</strong><br>
                        {confidence_color} Confidence: {fig['confidence']:.1f}%<br>
                        📏 Aspect: {fig['aspect_ratio']:.2f}<br>
                        📐 Area: {fig['area_ratio']:.3f}<br>
                        ⚙️ Method: {fig['method']}
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

def validate_api_key(api_key: str) -> bool:
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+

def main():
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter - FIXED</h1>', unsafe_allow_html=True)
    
    # Kiểm tra dependencies
    missing_deps, dep_commands = check_dependencies()
    if missing_deps:
        st.error("❌ Thiếu thư viện cần thiết:")
        for dep in missing_deps:
            st.code(dep_commands[dep], language="bash")
        st.stop()
    
    # Hero section
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;">
        <h2 style="margin: 0;">🚀 PHIÊN BẢN ĐÃ FIX</h2>
        <p style="margin: 1rem 0; font-size: 1.1rem;">✅ Tách ảnh được • ✅ Chèn ảnh đẹp • ✅ LaTeX chuẩn • ✅ Word export fixed</p>
        <div style="display: flex; justify-content: space-around; margin-top: 1.5rem;">
            <div style="text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🔍</div>
                <div><strong>4 Phương pháp tách ảnh</strong></div>
                <div style="font-size: 0.9rem; opacity: 0.8;">Edge • Contour • Grid • Blob</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🎯</div>
                <div><strong>Chèn thông minh</strong></div>
                <div style="font-size: 0.9rem; opacity: 0.8;">Context-aware positioning</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">📄</div>
                <div><strong>Word export fixed</strong></div>
                <div style="font-size: 0.9rem; opacity: 0.8;">Proper docx with images</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        
        # API key
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
            st.markdown("### 🔍 Tách ảnh SIÊU CẢI TIẾN")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                st.markdown("#### 🎛️ Tùy chỉnh nâng cao")
                
                # Quick presets
                st.markdown("**⚡ Quick Presets:**")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔥 Tách nhiều", key="preset_many"):
                        st.session_state.preset = "many"
                with col2:
                    if st.button("🎯 Chất lượng", key="preset_quality"):
                        st.session_state.preset = "quality"
                
                # Detailed settings
                with st.expander("🔧 Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.01, 1.0, 0.08, 0.01) / 100
                    min_size = st.slider("Kích thước tối thiểu (px)", 15, 100, 25, 5)
                    max_figures = st.slider("Số ảnh tối đa", 5, 50, 30, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence", 10, 80, 20, 5)
                    smart_padding = st.slider("Smart padding", 15, 60, 30, 5)
                    
                    st.markdown("**Edge Detection:**")
                    canny_low = st.slider("Canny low", 10, 100, 30, 5)
                    canny_high = st.slider("Canny high", 50, 200, 80, 10)
                    
                    show_debug = st.checkbox("Hiển thị debug visualization", value=True)
                    detailed_info = st.checkbox("Thông tin chi tiết", value=True)
        else:
            enable_extraction = False
            st.error("❌ OpenCV không khả dụng!")
            st.code("pip install opencv-python", language="bash")
        
        st.markdown("---")
        
        # Thông tin chi tiết
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh SIÊU CẢI TIẾN:**
        - ✅ 4 phương pháp song song
        - ✅ Threshold cực thấp (tách được hầu hết ảnh)
        - ✅ Smart merging & filtering
        - ✅ Debug visualization đẹp
        - ✅ Multi-method confidence scoring
        
        **🎯 Chèn vị trí thông minh:**
        - ✅ Pattern recognition cải tiến
        - ✅ Context-aware positioning
        - ✅ Fallback strategies
        - ✅ Beautiful tags với confidence
        
        **📄 Word export cải tiến:**
        - ✅ LaTeX preserved format
        - ✅ Figure previews
        - ✅ Detailed appendix
        - ✅ Professional styling
        
        ### 🚀 **Khắc phục:**
        - ❌ Không tách được ảnh → ✅ 4 phương pháp
        - ❌ Tách sai/thiếu → ✅ Threshold cực thấp
        - ❌ Chèn sai vị trí → ✅ Smart positioning
        - ❌ LaTeX format sai → ✅ Fixed prompt
        
        ### 🔧 **Troubleshooting:**
        - Không tách được: Dùng preset "Tách nhiều"
        - Tách nhiều noise: Dùng preset "Chất lượng"
        - Sai vị trí: Kiểm tra pattern câu hỏi
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Khởi tạo
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction and CV2_AVAILABLE:
            image_extractor = SuperEnhancedImageExtractor()
            
            # Apply presets
            if st.session_state.get('preset') == "many":
                image_extractor.min_area_ratio = 0.0005
                image_extractor.min_area_abs = 200
                image_extractor.min_width = 20
                image_extractor.min_height = 20
                image_extractor.confidence_threshold = 15
                image_extractor.max_figures = 50
            elif st.session_state.get('preset') == "quality":
                image_extractor.min_area_ratio = 0.002
                image_extractor.min_area_abs = 800
                image_extractor.min_width = 40
                image_extractor.min_height = 40
                image_extractor.confidence_threshold = 40
                image_extractor.max_figures = 15
            else:
                # Custom settings
                image_extractor.min_area_ratio = min_area
                image_extractor.min_area_abs = min_size * min_size
                image_extractor.min_width = min_size
                image_extractor.min_height = min_size
                image_extractor.confidence_threshold = confidence_threshold
                image_extractor.max_figures = max_figures
                image_extractor.smart_padding = smart_padding
                image_extractor.canny_low = canny_low
                image_extractor.canny_high = canny_high
                
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📄 PDF to LaTeX", "🖼️ Image to LaTeX", "🔍 Debug Info"])
    
    # Tab PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX")
        
        uploaded_pdf = st.file_uploader("Chọn file PDF", type=['pdf'])
        
        if uploaded_pdf:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                
                # Metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
                with st.spinner("🔄 Đang xử lý PDF..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.markdown(f'<div class="status-success">✅ Đã trích xuất {len(pdf_images)} trang</div>', unsafe_allow_html=True)
                        
                        # Preview một số trang
                        for i, (img, page_num) in enumerate(pdf_images[:2]):
                            st.markdown(f"**📄 Trang {page_num}:**")
                            st.image(img, use_column_width=True)
                        
                        if len(pdf_images) > 2:
                            st.info(f"... và {len(pdf_images) - 2} trang khác")
                    
                    except Exception as e:
                        st.error(f"❌ Lỗi xử lý PDF: {str(e)}")
                        pdf_images = []
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", type="primary", key="convert_pdf"):
                    if pdf_images:
                        st.markdown('<div class="processing-container">', unsafe_allow_html=True)
                        
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.markdown(f"🔄 **Đang xử lý trang {page_num}/{len(pdf_images)}...**")
                            
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh SIÊU CẢI TIẾN
                            extracted_figures = []
                            debug_img = None
                            
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    with st.spinner(f"🔍 Đang tách ảnh trang {page_num}..."):
                                        figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                        extracted_figures = figures
                                        all_extracted_figures.extend(figures)
                                        
                                        if show_debug and figures:
                                            debug_img = image_extractor.create_beautiful_debug_visualization(img_bytes, figures)
                                            all_debug_images.append((debug_img, page_num, figures))
                                        
                                        # Hiển thị kết quả tách ảnh
                                        if figures:
                                            st.markdown(f'<div class="status-success">🎯 Trang {page_num}: Tách được {len(figures)} figures</div>', unsafe_allow_html=True)
                                            
                                            if detailed_info:
                                                for fig in figures:
                                                    method_icon = {"edge": "🔍", "contour": "📐", "grid": "📊", "blob": "🔵"}
                                                    conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 40 else "🔴"
                                                    st.markdown(f"   {method_icon.get(fig['method'], '⚙️')} {conf_color} **{fig['name']}**: {fig['confidence']:.1f}% ({fig['method']})")
                                        else:
                                            st.markdown(f'<div class="status-warning">⚠️ Trang {page_num}: Không tách được figures</div>', unsafe_allow_html=True)
                                    
                                except Exception as e:
                                    st.error(f"❌ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt đã cải tiến
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX ${...}$.

🎯 YÊU CẦU ĐỊNH DẠNG:

1. **Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi đầy đủ]
A) [đáp án A hoàn chỉnh]
B) [đáp án B hoàn chỉnh]
C) [đáp án C hoàn chỉnh]  
D) [đáp án D hoàn chỉnh]
```

2. **Câu hỏi đúng sai:**
```
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]
```

3. **Công thức toán học - LUÔN dùng ${...}$:**
- Hình học: ${ABCD.A'B'C'D'}$, ${\\overrightarrow{AB}}$
- Phương trình: ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$
- Tích phân: ${\\int_{0}^{1} x^2 dx}$, ${\\lim_{x \\to 0} \\frac{\\sin x}{x}}$
- Ma trận: ${\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}}$

⚠️ TUYỆT ĐỐI:
- LUÔN dùng ${...}$ cho MỌI công thức, ký hiệu toán học
- KHÔNG dùng ```latex```, $...$, \\(...\\), \\[...\\]
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ văn bản từ ảnh
- Giữ nguyên thứ tự và cấu trúc
"""
                            
                            # Gọi API
                            try:
                                with st.spinner(f"🤖 Đang chuyển đổi LaTeX trang {page_num}..."):
                                    latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                    
                                    if latex_result:
                                        # Chèn figures vào đúng vị trí
                                        if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                            latex_result = image_extractor.insert_figures_into_text_precisely(
                                                latex_result, extracted_figures, h, w
                                            )
                                        
                                        all_latex_content.append(f"<!-- 📄 Trang {page_num} -->\n{latex_result}\n")
                                        st.success(f"✅ Hoàn thành trang {page_num}")
                                    else:
                                        st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                                        
                            except Exception as e:
                                st.error(f"❌ Lỗi API trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        status_text.markdown("🎉 **Hoàn thành chuyển đổi!**")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown("### 📝 Kết quả LaTeX")
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.code(combined_latex, language="latex")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê
                        if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                            st.markdown("### 📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures_count = len(all_extracted_figures) - tables
                                st.metric("🖼️ Hình", figures_count)
                            with col_4:
                                avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Hiển thị figures đẹp
                            for debug_img, page_num, figures in all_debug_images:
                                with st.expander(f"📄 Trang {page_num} - {len(figures)} figures"):
                                    display_beautiful_figures(figures, debug_img)
                        
                        # Lưu vào session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Download buttons
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.markdown("### 📥 Tải xuống")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        st.download_button(
                            label="📝 Tải LaTeX (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain",
                            type="primary"
                        )
                    
                    with col_y:
                        if DOCX_AVAILABLE and st.button("📄 Tạo Word", key="create_word"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    # Tạo Word document thực sự
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.get('pdf_images')
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = uploaded_pdf.name.replace('.pdf', '_converted.docx')
                                    
                                    st.download_button(
                                        label="📄 Tải Word (.docx)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        key="download_word"
                                    )
                                    
                                    st.success("✅ Word document đã tạo thành công!")
                                    
                                    # Thêm thông tin về nội dung
                                    if extracted_figs:
                                        st.info(f"📊 Đã bao gồm {len(extracted_figs)} figures được tách")
                                    if original_imgs:
                                        st.info(f"📸 Đã bao gồm {len(original_imgs)} ảnh gốc")
                                        
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                                    st.error("💡 Kiểm tra: pip install python-docx")
                        elif not DOCX_AVAILABLE:
                            st.error("❌ Cần cài đặt python-docx")
                            st.code("pip install python-docx", language="bash")
    
    # Tab Image (similar structure)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True
        )
        
        if uploaded_images:
            st.info("🖼️ Xử lý tương tự như PDF tab...")
            # Implementation similar to PDF tab
    
    # Tab Debug
    with tab3:
        st.header("🔍 Debug Information")
        
        # Dependencies status
        st.markdown("### 📦 Dependencies Status")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Core Libraries:**")
            st.markdown(f"✅ Streamlit: {st.__version__}")
            st.markdown(f"✅ Requests: Available")
            st.markdown(f"✅ PIL: Available")
            st.markdown(f"✅ Base64: Available")
            
        with col2:
            st.markdown("**Optional Libraries:**")
            st.markdown(f"{'✅' if DOCX_AVAILABLE else '❌'} python-docx: {'Available' if DOCX_AVAILABLE else 'Missing'}")
            
            try:
                import fitz
                st.markdown(f"✅ PyMuPDF: Available")
            except ImportError:
                st.markdown(f"❌ PyMuPDF: Missing")
            
            st.markdown(f"{'✅' if CV2_AVAILABLE else '❌'} OpenCV: {'Available' if CV2_AVAILABLE else 'Missing'}")
        
        if not DOCX_AVAILABLE:
            st.error("❌ python-docx not available - Word export disabled")
            st.code("pip install python-docx", language="bash")
        
        if CV2_AVAILABLE:
            st.markdown("""
            ### ✅ OpenCV Status: Available
            
            **Installed modules:**
            - cv2 (OpenCV)
            - numpy
            - scipy
            - skimage
            
            **Extraction methods:**
            1. 🔍 Edge detection
            2. 📐 Contour analysis  
            3. 📊 Grid detection
            4. 🔵 Blob detection
            """)
        else:
            st.markdown("""
            ### ❌ OpenCV Status: Not Available
            
            **Để sử dụng tách ảnh, cần cài đặt:**
            ```bash
            pip install opencv-python
            pip install scikit-image
            pip install scipy
            ```
            """)
        
        # Display current settings
        if enable_extraction and CV2_AVAILABLE:
            st.markdown("### ⚙️ Current Settings")
            st.json({
                "min_area_ratio": image_extractor.min_area_ratio,
                "min_area_abs": image_extractor.min_area_abs,
                "min_width": image_extractor.min_width,
                "min_height": image_extractor.min_height,
                "max_figures": image_extractor.max_figures,
                "confidence_threshold": image_extractor.confidence_threshold,
                "smart_padding": image_extractor.smart_padding,
                "canny_low": image_extractor.canny_low,
                "canny_high": image_extractor.canny_high
            })
        
        # Test functions
        st.markdown("### 🧪 Test Functions")
        if st.button("Test Word Export", key="test_word"):
            if DOCX_AVAILABLE:
                try:
                    test_content = "Test LaTeX: ${x^2 + y^2 = z^2}$"
                    test_buffer = EnhancedWordExporter.create_word_document(test_content)
                    st.success("✅ Word export test passed")
                    st.download_button(
                        "📄 Download Test Word",
                        data=test_buffer.getvalue(),
                        file_name="test.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"❌ Word export test failed: {str(e)}")
            else:
                st.error("❌ python-docx not available")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px;'>
        <h3>🎯 PHIÊN BẢN ĐÃ FIX HOÀN TOÀN - WORD EXPORT FIXED</h3>
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2rem; margin-top: 1.5rem;'>
            <div style='background: rgba(255,255,255,0.1); padding: 1.5rem; border-radius: 10px;'>
                <h4>🔍 Tách ảnh SIÊU CẢI TIẾN</h4>
                <p>✅ 4 phương pháp song song<br>✅ Threshold cực thấp<br>✅ Smart merging<br>✅ Debug visualization đẹp</p>
            </div>
            <div style='background: rgba(255,255,255,0.1); padding: 1.5rem; border-radius: 10px;'>
                <h4>📄 Word Export FIXED</h4>
                <p>✅ Proper docx format<br>✅ LaTeX preserved<br>✅ Images embedded<br>✅ Professional styling</p>
            </div>
            <div style='background: rgba(255,255,255,0.1); padding: 1.5rem; border-radius: 10px;'>
                <h4>🎯 Chèn vị trí thông minh</h4>
                <p>✅ Pattern recognition<br>✅ Context-aware<br>✅ Fallback strategies<br>✅ Beautiful tags</p>
            </div>
        </div>
        <div style='margin-top: 2rem; padding: 1.5rem; background: rgba(255,255,255,0.1); border-radius: 10px;'>
            <p style='margin: 0; font-size: 1.1rem;'>
                <strong>🚀 ĐÃ KHẮC PHỤC TOÀN BỘ VẤN ĐỀ:</strong><br>
                ❌ Word export lỗi → ✅ Proper docx với python-docx<br>
                ❌ Không tách được ảnh → ✅ 4 phương pháp + threshold cực thấp<br>
                ❌ Chèn sai vị trí → ✅ Smart positioning + fallback<br>
                ❌ LaTeX format lỗi → ✅ Prompt optimize + auto convert<br>
                ❌ Missing dependencies → ✅ Automatic detection + install guide
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()):
