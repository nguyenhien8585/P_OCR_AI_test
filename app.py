import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import tempfile
import os
import re
import time
import math

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
    page_title="PDF/LaTeX Converter - Enhanced & Precise",
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
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        font-family: 'Consolas', 'Monaco', monospace;
        border-left: 4px solid #2E86AB;
        max-height: 400px;
        overflow-y: auto;
    }
    .extracted-image {
        border: 2px solid #28a745;
        border-radius: 8px;
        margin: 10px 0;
        padding: 5px;
        background: #f8f9fa;
    }
    .debug-info {
        background-color: #e9ecef;
        padding: 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
        margin-top: 5px;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        margin: 5px;
    }
</style>
""", unsafe_allow_html=True)

class EnhancedImageExtractor:
    """
    Thuật toán tách ảnh cải tiến - chính xác, đẹp, thông minh
    """
    
    def __init__(self):
        # Tham số chính - RELAXED để tách được nhiều ảnh hơn
        self.min_area_ratio = 0.002      # 0.2% diện tích ảnh gốc (giảm từ 0.5%)
        self.min_area_abs = 800          # 800 pixels (giảm từ 1500)
        self.min_width = 40              # 40 pixels (giảm từ 60)
        self.min_height = 40             # 40 pixels (giảm từ 60)
        self.max_figures = 20            # Tối đa 20 ảnh (tăng từ 12)
        self.max_area_ratio = 0.60       # Tối đa 60% diện tích (tăng từ 45%)
        
        # Tham số cắt ảnh
        self.smart_padding = 25          # Padding thông minh (tăng từ 20)
        self.quality_threshold = 0.4     # Ngưỡng chất lượng (giảm từ 0.7)
        self.edge_margin = 0.01          # Margin từ rìa (giảm từ 2% xuống 1%)
        
        # Tham số phân tích - RELAXED
        self.text_ratio_threshold = 0.5  # Ngưỡng tỷ lệ text (tăng từ 0.3)
        self.line_density_threshold = 0.02  # Ngưỡng mật độ line (giảm từ 0.05)
        self.confidence_threshold = 45    # Ngưỡng confidence (giảm từ 75)
        
        # Tham số morphology
        self.morph_kernel_size = 3       # Giảm từ 5
        self.dilate_iterations = 1       # Giảm từ 2
        self.erode_iterations = 1
    
    def extract_figures_and_tables(self, image_bytes):
        """
        Tách ảnh/bảng với thuật toán cải tiến
        """
        if not CV2_AVAILABLE:
            return [], 0, 0
        
        # Đọc và tiền xử lý ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # Bước 1: Tăng cường chất lượng ảnh
        enhanced_img = self._enhance_image_quality(img)
        
        # Bước 2: Phát hiện và loại bỏ text regions
        text_mask = self._detect_text_regions_advanced(enhanced_img)
        
        # Bước 3: Phát hiện geometric shapes và diagrams
        figure_mask = self._detect_geometric_shapes(enhanced_img, text_mask)
        
        # Bước 4: Tìm contours và phân tích
        candidates = self._find_and_analyze_contours(figure_mask, enhanced_img, w, h)
        
        # Bước 5: Lọc và xếp hạng candidates
        filtered_candidates = self._filter_and_rank_candidates(candidates, w, h)
        
        # Bước 6: Tạo final figures với cắt thông minh
        final_figures = self._create_final_figures(filtered_candidates, img, w, h)
        
        return final_figures, h, w
    
    def _enhance_image_quality(self, img):
        """
        Tăng cường chất lượng ảnh trước khi xử lý
        """
        # Chuyển sang grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Giảm noise
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Tăng cường contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # Sharpen
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        
        return sharpened
    
    def _detect_text_regions_advanced(self, gray_img):
        """
        Phát hiện text regions để loại trừ - thuật toán cải tiến
        """
        # Phát hiện text bằng morphological operations
        # Horizontal text lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        horizontal_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, horizontal_kernel)
        
        # Vertical text lines (ít hơn)
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
        vertical_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, vertical_kernel)
        
        # Combine text indicators
        text_indicators = cv2.bitwise_or(horizontal_lines, vertical_lines)
        
        # Dilate để bao phủ text regions
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        text_mask = cv2.dilate(text_indicators, dilate_kernel, iterations=3)
        
        # Phát hiện text blocks bằng connected components
        _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Tìm text blocks
        text_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
        text_blocks = cv2.morphologyEx(binary, cv2.MORPH_OPEN, text_kernel)
        
        # Combine all text detection methods
        combined_text_mask = cv2.bitwise_or(text_mask, text_blocks)
        
        return combined_text_mask
    
    def _detect_geometric_shapes(self, gray_img, text_mask):
        """
        Phát hiện geometric shapes và diagrams
        """
        # Edge detection với multiple thresholds
        edges1 = cv2.Canny(gray_img, 50, 150)
        edges2 = cv2.Canny(gray_img, 30, 100)
        edges_combined = cv2.bitwise_or(edges1, edges2)
        
        # Loại bỏ text edges
        edges_clean = cv2.bitwise_and(edges_combined, cv2.bitwise_not(text_mask))
        
        # Morphological operations để nối các đường
        morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edges_clean = cv2.morphologyEx(edges_clean, cv2.MORPH_CLOSE, morph_kernel)
        
        # Dilate để tạo regions
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        figure_mask = cv2.dilate(edges_clean, dilate_kernel, iterations=2)
        
        return figure_mask
    
    def _find_and_analyze_contours(self, figure_mask, gray_img, w, h):
        """
        Tìm và phân tích contours
        """
        # Tìm contours
        contours, _ = cv2.findContours(figure_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            # Tính các thông số cơ bản
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc cơ bản
            if (area < self.min_area_abs or area_ratio < self.min_area_ratio or 
                area_ratio > self.max_area_ratio or ww < self.min_width or hh < self.min_height):
                continue
            
            # Kiểm tra vị trí (không quá gần rìa)
            if (x < self.edge_margin * w or y < self.edge_margin * h or 
                (x + ww) > (1 - self.edge_margin) * w or (y + hh) > (1 - self.edge_margin) * h):
                continue
            
            # Phân tích chất lượng hình học
            quality_score = self._analyze_geometric_quality(cnt, gray_img[y:y+hh, x:x+ww])
            
            if quality_score < self.quality_threshold:
                continue
            
            # Phân loại table vs figure
            is_table = self._classify_table_vs_figure(gray_img[y:y+hh, x:x+ww], ww, hh, aspect_ratio)
            
            # Tính confidence score
            confidence = self._calculate_confidence_score(area_ratio, aspect_ratio, quality_score, ww, hh, w, h)
            
            if confidence >= self.confidence_threshold:
                candidates.append({
                    "contour": cnt,
                    "bbox": (x, y, ww, hh),
                    "area": area,
                    "area_ratio": area_ratio,
                    "aspect_ratio": aspect_ratio,
                    "quality_score": quality_score,
                    "is_table": is_table,
                    "confidence": confidence,
                    "center_y": y + hh // 2,
                    "center_x": x + ww // 2
                })
        
        return candidates
    
    def _analyze_geometric_quality(self, contour, roi):
        """
        Phân tích chất lượng hình học của contour
        """
        # Tính hull và solidity
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        contour_area = cv2.contourArea(contour)
        
        if hull_area == 0:
            return 0.0
        
        solidity = float(contour_area) / hull_area
        
        # Tính extent
        x, y, w, h = cv2.boundingRect(contour)
        rect_area = w * h
        extent = float(contour_area) / rect_area if rect_area > 0 else 0
        
        # Phân tích edge density trong ROI
        edges = cv2.Canny(roi, 50, 150)
        edge_density = np.sum(edges > 0) / (roi.shape[0] * roi.shape[1])
        
        # Phân tích line structures
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, minLineLength=10, maxLineGap=5)
        line_count = len(lines) if lines is not None else 0
        line_density = line_count / max(w, h)
        
        # Tính quality score tổng hợp
        quality_score = (
            solidity * 0.3 +
            extent * 0.2 +
            min(edge_density * 20, 1.0) * 0.3 +
            min(line_density * 0.1, 1.0) * 0.2
        )
        
        return quality_score
    
    def _classify_table_vs_figure(self, roi, w, h, aspect_ratio):
        """
        Phân loại table vs figure cải tiến
        """
        # Tables thường có:
        # 1. Aspect ratio cao (rộng > cao)
        # 2. Grid structures
        # 3. Horizontal và vertical lines
        
        if aspect_ratio < 1.5:
            return False  # Không đủ rộng để là table
        
        # Phát hiện grid structures
        edges = cv2.Canny(roi, 50, 150)
        
        # Horizontal lines
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//3, 1))
        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        h_count = len(cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
        
        # Vertical lines
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//3))
        v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)
        v_count = len(cv2.findContours(v_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
        
        # Table cần có cả horizontal và vertical lines
        return h_count >= 2 and v_count >= 2 and aspect_ratio > 2.0
    
    def _calculate_confidence_score(self, area_ratio, aspect_ratio, quality_score, w, h, img_w, img_h):
        """
        Tính confidence score tổng hợp
        """
        confidence = 0
        
        # Score từ size (kích thước vừa phải)
        if 0.01 < area_ratio < 0.3:
            confidence += 40
        elif 0.005 < area_ratio < 0.4:
            confidence += 25
        else:
            confidence += 10
        
        # Score từ aspect ratio
        if 0.5 < aspect_ratio < 3.0:
            confidence += 30
        elif 0.3 < aspect_ratio < 5.0:
            confidence += 20
        else:
            confidence += 5
        
        # Score từ quality
        confidence += quality_score * 30
        
        return min(100, confidence)
    
    def _filter_and_rank_candidates(self, candidates, w, h):
        """
        Lọc và xếp hạng candidates
        """
        # Sắp xếp theo confidence
        candidates = sorted(candidates, key=lambda x: x['confidence'], reverse=True)
        
        # Loại bỏ overlap
        filtered = []
        for candidate in candidates:
            if not self._is_overlapping(candidate, filtered):
                filtered.append(candidate)
        
        # Giới hạn số lượng
        return filtered[:self.max_figures]
    
    def _is_overlapping(self, candidate, existing_candidates):
        """
        Kiểm tra overlap với IoU
        """
        x1, y1, w1, h1 = candidate['bbox']
        
        for existing in existing_candidates:
            x2, y2, w2, h2 = existing['bbox']
            
            # Tính IoU
            intersection_area = max(0, min(x1+w1, x2+w2) - max(x1, x2)) * max(0, min(y1+h1, y2+h2) - max(y1, y2))
            union_area = w1*h1 + w2*h2 - intersection_area
            
            if union_area > 0:
                iou = intersection_area / union_area
                if iou > 0.3:  # Ngưỡng overlap
                    return True
        
        return False
    
    def _create_final_figures(self, candidates, img, w, h):
        """
        Tạo final figures với cắt thông minh
        """
        # Sắp xếp theo vị trí (top to bottom, left to right)
        candidates = sorted(candidates, key=lambda x: (x['center_y'], x['center_x']))
        
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for candidate in candidates:
            # Cắt ảnh thông minh
            cropped_img = self._smart_crop_image(img, candidate, w, h)
            
            if cropped_img is None:
                continue
            
            # Chuyển thành base64
            buf = io.BytesIO()
            Image.fromarray(cropped_img).save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            # Đặt tên file
            if candidate["is_table"]:
                name = f"table-{table_idx+1}.jpeg"
                table_idx += 1
            else:
                name = f"figure-{img_idx+1}.jpeg"
                img_idx += 1
            
            final_figures.append({
                "name": name,
                "base64": b64,
                "is_table": candidate["is_table"],
                "bbox": candidate["bbox"],
                "confidence": candidate["confidence"],
                "area_ratio": candidate["area_ratio"],
                "aspect_ratio": candidate["aspect_ratio"],
                "quality_score": candidate["quality_score"],
                "center_y": candidate["center_y"],
                "center_x": candidate["center_x"]
            })
        
        return final_figures
    
    def _smart_crop_image(self, img, candidate, img_w, img_h):
        """
        Cắt ảnh thông minh với padding và làm sạch
        """
        x, y, w, h = candidate['bbox']
        
        # Tính padding thông minh
        padding_x = min(self.smart_padding, w // 6)
        padding_y = min(self.smart_padding, h // 6)
        
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
        cleaned = self._clean_cropped_image(cropped)
        
        return cleaned
    
    def _clean_cropped_image(self, cropped_img):
        """
        Làm sạch ảnh đã cắt
        """
        # Chuyển sang PIL để xử lý
        pil_img = Image.fromarray(cropped_img)
        
        # Tăng cường contrast
        enhancer = ImageEnhance.Contrast(pil_img)
        enhanced = enhancer.enhance(1.2)
        
        # Sharpen nhẹ
        sharpened = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
        
        return np.array(sharpened)
    
    def insert_figures_into_text_precisely(self, text, figures, img_h, img_w):
        """
        Chèn ảnh vào văn bản với độ chính xác cao
        """
        if not figures:
            return text
        
        lines = text.split('\n')
        
        # Phân tích cấu trúc văn bản
        text_structure = self._analyze_text_structure(lines)
        
        # Ánh xạ figures với positions
        figure_positions = self._map_figures_to_positions(figures, text_structure, img_h)
        
        # Chèn figures vào đúng vị trí
        result_lines = self._insert_figures_at_positions(lines, figure_positions)
        
        return '\n'.join(result_lines)
    
    def _analyze_text_structure(self, lines):
        """
        Phân tích cấu trúc văn bản chi tiết
        """
        structure = {
            'questions': [],
            'sections': [],
            'insertion_points': []
        }
        
        current_question = None
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Phát hiện câu hỏi
            question_match = re.match(r'^câu\s+(\d+)', line_stripped.lower())
            if question_match:
                if current_question:
                    structure['questions'].append(current_question)
                
                current_question = {
                    'number': int(question_match.group(1)),
                    'start_line': i,
                    'content_lines': [i],
                    'insertion_candidates': []
                }
            
            elif current_question and line_stripped:
                current_question['content_lines'].append(i)
                
                # Tìm insertion points
                insertion_priority = self._calculate_insertion_priority(line_stripped)
                if insertion_priority > 0:
                    current_question['insertion_candidates'].append({
                        'line': i,
                        'priority': insertion_priority,
                        'content': line_stripped
                    })
        
        if current_question:
            structure['questions'].append(current_question)
        
        return structure
    
    def _calculate_insertion_priority(self, line_content):
        """
        Tính priority cho insertion points - CẢI TIẾN cho văn bản toán học
        """
        line_lower = line_content.lower()
        priority = 0
        
        # Highest priority: câu hỏi trắc nghiệm/đúng sai
        if re.search(r'câu\s+\d+[\.\:]', line_lower):
            priority += 150  # Tăng priority cho câu hỏi
        
        # High priority: kết thúc với pattern đặc biệt
        if re.search(r'(sau|dưới đây|bên dưới|như hình|theo hình):?\s*
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text - CẢI TIẾN cho toán học
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        # Nếu không có cấu trúc câu hỏi rõ ràng, dùng strategy khác
        if not text_structure['questions']:
            # Chèn figures vào các dòng có priority cao
            for i, figure in enumerate(sorted_figures):
                # Tìm vị trí chèn dựa trên thứ tự
                insertion_line = min(3 + i * 5, 20)  # Chèn cách đều
                
                mappings.append({
                    'figure': figure,
                    'question': None,
                    'insertion_line': insertion_line,
                    'score': 50
                })
            
            return mappings
        
        # Logic gốc cho trường hợp có câu hỏi
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                # Tính score dựa trên vị trí và ngữ cảnh
                question_y_ratio = question['start_line'] / max(len(text_structure['questions']), 1)
                
                # Position score (càng gần càng tốt)
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 50
                
                # Content score (dựa trên insertion candidates)
                content_score = 0
                if question['insertion_candidates']:
                    max_priority = max(c['priority'] for c in question['insertion_candidates'])
                    content_score = min(50, max_priority)
                
                total_score = position_score + content_score
                
                if total_score > best_score:
                    best_score = total_score
                    best_question = question
                    
                    # Xác định vị trí chèn
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            # Chấp nhận match nếu đủ tốt
            if best_score > 20:  # Giảm threshold từ 30 xuống 20
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
            else:
                # Fallback: chèn theo thứ tự
                fallback_line = 2 + len(mappings) * 3
                mappings.append({
                    'figure': figure,
                    'question': None,
                    'insertion_line': fallback_line,
                    'score': 25
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] if x['insertion_line'] else float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions - CẢI TIẾN với fallback strategies
        """
        result_lines = lines[:]
        offset = 0
        
        # Sắp xếp theo insertion_line
        sorted_positions = sorted(figure_positions, key=lambda x: x['insertion_line'] or float('inf'))
        
        for mapping in sorted_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                # Đảm bảo không vượt quá số dòng
                if insertion_index > len(result_lines):
                    insertion_index = len(result_lines)
                
                # Tạo tag tùy theo loại figure
                if figure['is_table']:
                    tag = f"[BẢNG: {figure['name']}]"
                else:
                    tag = f"[HÌNH: {figure['name']}]"
                
                # Chèn với dòng trống để dễ đọc
                result_lines.insert(insertion_index, "")
                result_lines.insert(insertion_index + 1, tag)
                result_lines.insert(insertion_index + 2, "")
                
                offset += 3  # Tăng offset do chèn 3 dòng
        
        # Nếu không có figures nào được chèn, thử fallback
        if not any(mapping['insertion_line'] is not None for mapping in figure_positions):
            # Fallback: chèn figures vào đầu các câu hỏi
            for i, line in enumerate(result_lines):
                if re.match(r'^câu\s+\d+', line.strip().lower()):
                    # Tìm figure chưa chèn
                    for mapping in figure_positions:
                        if mapping.get('inserted') != True:
                            figure = mapping['figure']
                            tag = f"[BẢNG: {figure['name']}]" if figure['is_table'] else f"[HÌNH: {figure['name']}]"
                            
                            # Chèn sau câu hỏi
                            result_lines.insert(i + 1, "")
                            result_lines.insert(i + 2, tag)
                            result_lines.insert(i + 3, "")
                            
                            mapping['inserted'] = True
                            break
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$ và CHUYỂN ĐỔI ```latex```
        """
        # Trước tiên, chuyển đổi ```latex ... ``` thành ${...}$
        line = re.sub(r'```latex\s*\n(.*?)\n```', r'${\1}
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Relaxed thresholds cho nhiều ảnh hơn
        - ✅ Phát hiện hình học toán học
        - ✅ Quality assessment chi tiết
        - ✅ Debug info cho mỗi figure
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Ưu tiên câu hỏi toán học
        - ✅ Fallback strategies
        - ✅ Context-aware cho hình học
        
        **📄 Word xuất LaTeX:**
        - ✅ Tự động chuyển ```latex``` → ${...}$
        - ✅ Hỗ trợ $...$ → ${...}$
        - ✅ Cambria Math font
        - ✅ Debug appendix
        
        ### 💡 **Troubleshooting:**
        - **Không tách được ảnh**: Giảm confidence xuống 30-40%
        - **Tách nhầm text**: Tăng confidence lên 60-70%
        - **LaTeX sai format**: Prompt đã fix tự động
        - **Chèn sai vị trí**: Cải thiện từ khóa trong văn bản
        
        ### 🔑 API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
        
        # Thêm quick settings
        st.markdown("---")
        st.markdown("### ⚡ Quick Settings:")
        
        if st.button("🔥 Tách nhiều ảnh", key="quick_many"):
            st.session_state.quick_settings = "many"
            st.rerun()
        
        if st.button("🎯 Chất lượng cao", key="quick_quality"):
            st.session_state.quick_settings = "quality"
            st.rerun()
        
        if st.button("🔄 Mặc định", key="quick_default"):
            st.session_state.quick_settings = "default"
            st.rerun()
        
        # Apply quick settings
        if 'quick_settings' in st.session_state:
            if st.session_state.quick_settings == "many":
                min_area = 0.001  # 0.1%
                max_figures = 25
                confidence_threshold = 30
            elif st.session_state.quick_settings == "quality":
                min_area = 0.008  # 0.8%
                max_figures = 8
                confidence_threshold = 70
            else:  # default
                min_area = 0.002  # 0.2%
                max_figures = 20
                confidence_threshold = 45
    
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
            image_extractor = EnhancedImageExtractor()
            
            # Apply quick settings nếu có
            if 'quick_settings' in st.session_state:
                if st.session_state.quick_settings == "many":
                    image_extractor.min_area_ratio = 0.001
                    image_extractor.max_figures = 25
                    image_extractor.confidence_threshold = 30
                elif st.session_state.quick_settings == "quality":
                    image_extractor.min_area_ratio = 0.008
                    image_extractor.max_figures = 8
                    image_extractor.confidence_threshold = 70
                else:  # default or manual
                    image_extractor.min_area_ratio = min_area
                    image_extractor.max_figures = max_figures
                    image_extractor.confidence_threshold = confidence_threshold
            else:
                # Sử dụng giá trị từ slider
                image_extractor.min_area_ratio = min_area
                image_extractor.max_figures = max_figures
                image_extractor.confidence_threshold = confidence_threshold
                
            # Các tham số khác
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
            
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Fixed LaTeX Format & Image Extraction</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh được cải thiện</h4>
                <p>✅ Relaxed thresholds (30-45% confidence)<br>✅ Phát hiện hình học toán học<br>✅ Debug info chi tiết<br>✅ Fallback strategies</p>
            </div>
            <div>
                <h4>📝 LaTeX format đã fix</h4>
                <p>✅ Prompt cải tiến → ${...}$<br>✅ Không còn ```latex```<br>✅ Tự động chuyển đổi format<br>✅ Cambria Math trong Word</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí cải thiện</h4>
                <p>✅ Ưu tiên câu hỏi toán học<br>✅ Fallback cho văn bản không có câu hỏi<br>✅ Context-aware insertion<br>✅ Debug positioning</p>
            </div>
        </div>
        <div style='margin-top: 1rem; padding: 1rem; background: rgba(255,255,255,0.1); border-radius: 8px;'>
            <p style='margin: 0; font-size: 0.9rem;'>
                <strong>💡 Giải pháp cho vấn đề của bạn:</strong><br>
                🔧 LaTeX format: ```latex``` → ${...}$ (đã fix)<br>
                🔧 Tách ảnh: 0 ảnh → nhiều ảnh (relaxed thresholds)<br>
                🔧 Chèn vị trí: random → context-aware (improved logic)
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line, flags=re.DOTALL)
        line = re.sub(r'```latex\s*(.*?)```', r'${\1}
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line)
        
        # Chuyển đổi $...$ thành ${...}$
        line = re.sub(r'\$\$([^$]+)\$\
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, r'${\1}
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line)
        
        # Chuyển đổi \(...\) thành ${...}$
        line = re.sub(r'\\[(]\s*(.*?)\s*\\[)]', r'${\1}
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line)
        
        # Chuyển đổi \[...\] thành ${...}$
        line = re.sub(r'\\[\[]\s*(.*?)\s*\\[\]]', r'${\1}
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line)
        
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
) and part.endswith('
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.2, 0.05, key="min_area_slider") / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 25, 20, 1, key="max_figures_slider")
                    min_size = st.slider("Kích thước tối thiểu (px)", 20, 200, 40, 10, key="min_size_slider")
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 25, 5, key="padding_slider")
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 95, 45, 5, key="confidence_slider")
                    show_debug = st.checkbox("Hiển thị debug", value=True, key="debug_checkbox")
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    # Hiển thị thông tin debug chi tiết
                                    if figures:
                                        st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures")
                                        
                                        # Hiển thị thông tin từng figure
                                        for fig in figures:
                                            conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                            st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                    else:
                                        st.write(f"⚠️ Trang {page_num}: Không tách được figures nào")
                                        st.write("   💡 Thử giảm confidence threshold hoặc min area")
                                    
                                    st.write(f"   📊 Avg Confidence: {sum(f['confidence'] for f in figures) / len(figures):.1f}%" if figures else "   📊 No figures extracted")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                # Hiển thị thông tin debug chi tiết
                                if figures:
                                    st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                                    
                                    # Hiển thị thông tin từng figure
                                    for fig in figures:
                                        conf_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                                        st.write(f"   {conf_color} {fig['name']}: {fig['confidence']:.1f}% confidence, {'Table' if fig['is_table'] else 'Figure'}")
                                else:
                                    st.write(f"⚠️ {uploaded_image.name}: Không tách được figures nào")
                                    st.write("   💡 Thử giảm confidence threshold hoặc min area")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt cải tiến - FIX LaTeX format cho IMAGE
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
, line_lower):
            priority += 120
        
        # High priority: từ khóa toán học
        if re.search(r'(hình hộp|hình chóp|hình thoi|hình vuông|hình chữ nhật)', line_lower):
            priority += 100
        
        # Medium-high priority: từ khóa hình học
        if re.search(r'(đỉnh|cạnh|mặt|đáy|tâm|trung điểm)', line_lower):
            priority += 80
        
        # Medium priority: từ khóa chung
        if re.search(r'(hình vẽ|biểu đồ|đồ thị|bảng|sơ đồ)', line_lower):
            priority += 70
        
        # Medium priority: xét tính đúng sai
        if re.search(r'(xét tính đúng sai|khẳng định sau)', line_lower):
            priority += 60
        
        # Lower priority: các từ khóa khác
        if re.search(r'(xét|tính|tìm|xác định|chọn|cho)', line_lower):
            priority += 40
        
        # Basic priority: kết thúc bằng dấu :
        if line_lower.endswith(':'):
            priority += 30
        
        return priority
    
    def _map_figures_to_positions(self, figures, text_structure, img_h):
        """
        Ánh xạ figures với positions trong text
        """
        mappings = []
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        for figure in sorted_figures:
            figure_y_ratio = figure['center_y'] / img_h
            
            best_question = None
            best_insertion_line = None
            best_score = 0
            
            # Tìm câu hỏi phù hợp nhất
            for question in text_structure['questions']:
                question_y_ratio = question['start_line'] / len(text_structure['questions']) if text_structure['questions'] else 0
                
                # Tính score dựa trên vị trí
                position_score = 100 - abs(figure_y_ratio - question_y_ratio) * 100
                
                if position_score > best_score:
                    best_score = position_score
                    best_question = question
                    
                    # Tìm insertion point tốt nhất
                    if question['insertion_candidates']:
                        best_candidate = max(question['insertion_candidates'], key=lambda x: x['priority'])
                        best_insertion_line = best_candidate['line'] + 1
                    else:
                        best_insertion_line = question['start_line'] + 1
            
            if best_score > 30:  # Threshold
                mappings.append({
                    'figure': figure,
                    'question': best_question,
                    'insertion_line': best_insertion_line,
                    'score': best_score
                })
        
        return sorted(mappings, key=lambda x: x['insertion_line'] or float('inf'))
    
    def _insert_figures_at_positions(self, lines, figure_positions):
        """
        Chèn figures vào positions
        """
        result_lines = lines[:]
        offset = 0
        
        for mapping in figure_positions:
            if mapping['insertion_line'] is not None:
                insertion_index = mapping['insertion_line'] + offset
                figure = mapping['figure']
                
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {figure['name']}]" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]"
                    result_lines.insert(insertion_index, tag)
                    offset += 1
        
        return result_lines
    
    def create_debug_visualization(self, image_bytes, figures):
        """
        Tạo visualization debug cho figures
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'yellow', 'magenta']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            # Vẽ bounding box
            draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
            
            # Vẽ center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-5, center_y-5, center_x+5, center_y+5], fill=color)
            
            # Vẽ label với thông tin chi tiết
            label_lines = [
                f"{fig['name']}",
                f"{'TBL' if fig['is_table'] else 'FIG'}: {fig['confidence']:.0f}%",
                f"Q: {fig['quality_score']:.2f}",
                f"A: {fig['area_ratio']:.3f}",
                f"R: {fig['aspect_ratio']:.2f}"
            ]
            
            # Background cho text
            text_height = len(label_lines) * 15
            text_width = max(len(line) for line in label_lines) * 8
            draw.rectangle([x, y-text_height-5, x+text_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(label_lines):
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
            # Tăng độ phân giải để có chất lượng ảnh tốt hơn
            mat = fitz.Matrix(3.0, 3.0)  # Scale factor tăng lên
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        doc = Document()
        
        # Thiết lập font chính
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu LaTeX đã chuyển đổi', 0)
        title.alignment = 1
        
        # Thông tin metadata
        info_para = doc.add_paragraph()
        info_para.alignment = 1
        info_run = info_para.add_run(f"Được tạo bởi Enhanced PDF/LaTeX Converter\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        info_run.font.size = Pt(10)
        info_run.font.color.rgb = RGBColor(128, 128, 128)
        
        doc.add_paragraph("")
        
        # Xử lý nội dung
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua code blocks và comments
            if line.startswith('```') or line.endswith('```'):
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                if 'Trang' in line or 'Ảnh' in line:
                    heading = doc.add_heading(line.replace('<!--', '').replace('-->', '').strip(), level=2)
                    heading.alignment = 1
                continue
            
            # Xử lý tags ảnh/bảng
            if line.startswith('[HÌNH:') and line.endswith(']'):
                img_name = line.replace('[HÌNH:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Hình minh họa")
                continue
            elif line.startswith('[BẢNG:') and line.endswith(']'):
                img_name = line.replace('[BẢNG:', '').replace(']', '').strip()
                EnhancedWordExporter._insert_extracted_image(doc, img_name, extracted_figures, "Bảng số liệu")
                continue
            
            if not line:
                continue
            
            # Xử lý LaTeX equations - GIỮ NGUYÊN ${...}$
            if ('${' in line and '}$' in line) or ('$' in line):
                para = doc.add_paragraph()
                EnhancedWordExporter._process_latex_line(para, line)
            else:
                # Đoạn văn bình thường
                para = doc.add_paragraph(line)
                para.style = doc.styles['Normal']
        
        # Thêm ảnh gốc nếu cần
        if images and not extracted_figures:
            EnhancedWordExporter._add_original_images(doc, images)
        
        # Thêm appendix với extracted figures
        if extracted_figures:
            EnhancedWordExporter._add_figures_appendix(doc, extracted_figures)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    
    @staticmethod
    def _process_latex_line(para, line):
        """
        Xử lý dòng chứa LaTeX equations - GIỮ NGUYÊN ${...}$
        """
        # Tách line thành các phần text và math
        parts = re.split(r'(\$[^$]+\$)', line)
        
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Đây là công thức LaTeX - GIỮ NGUYÊN
                math_run = para.add_run(part)
                math_run.font.name = 'Cambria Math'
                math_run.font.size = Pt(12)
                math_run.font.color.rgb = RGBColor(0, 0, 139)  # Dark blue
            else:
                # Text bình thường
                text_run = para.add_run(part)
                text_run.font.name = 'Times New Roman'
                text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """
        Chèn ảnh đã tách với formatting đẹp
        """
        if not extracted_figures:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        target_figure = None
        for fig in extracted_figures:
            if fig['name'] == img_name:
                target_figure = fig
                break
        
        if not target_figure:
            para = doc.add_paragraph(f"[{caption_prefix}: {img_name} - Không tìm thấy]")
            return
        
        try:
            # Tạo heading cho ảnh
            heading = doc.add_heading(f"{caption_prefix}: {img_name}", level=3)
            heading.alignment = 1
            
            # Decode và chèn ảnh
            img_data = base64.b64decode(target_figure['base64'])
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Chuyển về RGB nếu cần
            if img_pil.mode in ('RGBA', 'LA', 'P'):
                img_pil = img_pil.convert('RGB')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_pil.save(tmp.name, 'PNG')
                try:
                    # Tính kích thước phù hợp
                    max_width = doc.sections[0].page_width * 0.8
                    doc.add_picture(tmp.name, width=max_width)
                    
                    # Thêm caption với thông tin chi tiết
                    caption_para = doc.add_paragraph()
                    caption_para.alignment = 1
                    caption_run = caption_para.add_run(
                        f"Confidence: {target_figure['confidence']:.1f}% | "
                        f"Quality: {target_figure['quality_score']:.2f} | "
                        f"Aspect Ratio: {target_figure['aspect_ratio']:.2f}"
                    )
                    caption_run.font.size = Pt(9)
                    caption_run.font.color.rgb = RGBColor(128, 128, 128)
                    
                except Exception:
                    doc.add_paragraph(f"[Không thể hiển thị {img_name}]")
                finally:
                    os.unlink(tmp.name)
        
        except Exception as e:
            doc.add_paragraph(f"[Lỗi hiển thị {img_name}: {str(e)}]")
    
    @staticmethod
    def _add_original_images(doc, images):
        """
        Thêm ảnh gốc với formatting đẹp
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Hình ảnh gốc', level=1)
        
        for i, img in enumerate(images):
            try:
                doc.add_heading(f'Hình gốc {i+1}', level=2)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    img.save(tmp.name, 'PNG')
                    try:
                        max_width = doc.sections[0].page_width * 0.9
                        doc.add_picture(tmp.name, width=max_width)
                    except Exception:
                        doc.add_paragraph(f"[Hình gốc {i+1} - Không thể hiển thị]")
                    finally:
                        os.unlink(tmp.name)
            except Exception:
                doc.add_paragraph(f"[Lỗi hiển thị hình gốc {i+1}]")
    
    @staticmethod
    def _add_figures_appendix(doc, extracted_figures):
        """
        Thêm phụ lục với thông tin chi tiết về figures
        """
        doc.add_page_break()
        doc.add_heading('Phụ lục: Thông tin chi tiết về hình ảnh đã tách', level=1)
        
        # Tạo bảng thống kê
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        
        # Header
        header_cells = table.rows[0].cells
        headers = ['Tên', 'Loại', 'Confidence', 'Quality', 'Aspect Ratio', 'Area Ratio']
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].font.bold = True
        
        # Dữ liệu
        for fig in extracted_figures:
            row_cells = table.add_row().cells
            row_cells[0].text = fig['name']
            row_cells[1].text = 'Bảng' if fig['is_table'] else 'Hình'
            row_cells[2].text = f"{fig['confidence']:.1f}%"
            row_cells[3].text = f"{fig['quality_score']:.2f}"
            row_cells[4].text = f"{fig['aspect_ratio']:.2f}"
            row_cells[5].text = f"{fig['area_ratio']:.3f}"

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
    st.markdown('<h1 class="main-header">📝 Enhanced PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
    
    # Hiển thị thông tin cải tiến
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0; text-align: center;">🎯 PHIÊN BẢN CâI TIẾN</h3>
        <div style="display: flex; justify-content: space-around; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🔍</div>
                <div style="font-size: 0.9rem;">Tách ảnh thông minh</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">🎯</div>
                <div style="font-size: 0.9rem;">Chèn đúng vị trí</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">📄</div>
                <div style="font-size: 0.9rem;">LaTeX trong Word</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
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
            st.subheader("🔍 Tách ảnh cải tiến")
            enable_extraction = st.checkbox("Bật tách ảnh thông minh", value=True)
            
            if enable_extraction:
                with st.expander("Cài đặt chi tiết"):
                    min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                    max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                    min_size = st.slider("Kích thước tối thiểu (px)", 40, 200, 60, 10)
                    smart_padding = st.slider("Smart padding (px)", 10, 50, 20, 5)
                    confidence_threshold = st.slider("Ngưỡng confidence (%)", 50, 95, 75, 5)
                    show_debug = st.checkbox("Hiển thị debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 🎯 **Cải tiến chính:**
        
        **🔍 Tách ảnh thông minh:**
        - ✅ Loại bỏ text regions
        - ✅ Phát hiện geometric shapes
        - ✅ Quality assessment
        - ✅ Smart cropping với padding
        - ✅ Confidence scoring
        
        **🎯 Chèn vị trí chính xác:**
        - ✅ Phân tích cấu trúc văn bản
        - ✅ Ánh xạ figure-question
        - ✅ Priority-based insertion
        - ✅ Context-aware positioning
        
        **📄 Word xuất LaTeX:**
        - ✅ Giữ nguyên ${...}$ format
        - ✅ Cambria Math font
        - ✅ Color coding
        - ✅ Appendix với thống kê
        
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
            image_extractor = EnhancedImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.smart_padding = smart_padding
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
                
                # Hiển thị metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_pdf.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_pdf.size)}</div>', unsafe_allow_html=True)
                
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
                            
                            # Tách ảnh cải tiến
                            extracted_figures = []
                            if enable_extraction and CV2_AVAILABLE:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    st.write(f"🔍 Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                    
                                    # Hiển thị thống kê
                                    if figures:
                                        avg_confidence = sum(f['confidence'] for f in figures) / len(figures)
                                        avg_quality = sum(f['quality_score'] for f in figures) / len(figures)
                                        st.write(f"   📊 Avg Confidence: {avg_confidence:.1f}% | Avg Quality: {avg_quality:.2f}")
                                
                                except Exception as e:
                                    st.warning(f"⚠️ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cải tiến - FIX LaTeX format
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với công thức LaTeX format ${...}$.

🎯 ĐỊNH DẠNG CHÍNH XÁC:

1. **Câu hỏi trắc nghiệm:**
Câu X: [nội dung câu hỏi hoàn chỉnh]
A) [đáp án A đầy đủ]
B) [đáp án B đầy đủ]
C) [đáp án C đầy đủ]
D) [đáp án D đầy đủ]

2. **Câu hỏi đúng sai:**
Câu X: [nội dung câu hỏi]
a) [khẳng định a đầy đủ]
b) [khẳng định b đầy đủ]
c) [khẳng định c đầy đủ]
d) [khẳng định d đầy đủ]

3. **Công thức toán học - LUÔN dùng ${...}$:**
VÍ DỤ ĐÚNG:
- Hình hộp: ${ABCD.A'B'C'D'}$
- Điều kiện vuông góc: ${A'C' \\perp BD}$
- Góc: ${(AD', B'C) = 90°}$
- Phương trình: ${x^2 + y^2 = z^2}$
- Phân số: ${\\frac{a+b}{c-d}}$
- Căn: ${\\sqrt{x^2 + y^2}}$
- Vector: ${\\vec{AB}}$

⚠️ YÊU CẦU TUYỆT ĐỐI:
- LUÔN LUÔN dùng ${...}$ cho mọi công thức, ký hiệu toán học
- KHÔNG BAO GIỜ dùng ```latex ... ``` hay $...$
- KHÔNG BAO GIỜ dùng \\( ... \\) hay \\[ ... \\]
- MỌI ký hiệu toán học đều phải nằm trong ${...}$
- Sử dụng A), B), C), D) cho trắc nghiệm
- Sử dụng a), b), c), d) cho đúng sai
- Bao gồm TẤT CẢ text và công thức từ ảnh
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn figures vào đúng vị trí
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
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
                        st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê tổng hợp
                        if enable_extraction and CV2_AVAILABLE:
                            st.subheader("📊 Thống kê tách ảnh")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("🔍 Tổng figures", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                                st.metric("🖼️ Hình", figures)
                            with col_4:
                                if all_extracted_figures:
                                    avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                                    st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                            
                            # Debug visualization
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Visualization")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    with st.expander(f"Trang {page_num} - {len(figures)} figures"):
                                        st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                                        
                                        # Hiển thị figures đã tách
                                        if figures:
                                            st.write("**Figures đã tách:**")
                                            cols = st.columns(min(len(figures), 3))
                                            for idx, fig in enumerate(figures):
                                                with cols[idx % 3]:
                                                    img_data = base64.b64decode(fig['base64'])
                                                    img_pil = Image.open(io.BytesIO(img_data))
                                                    st.image(img_pil, use_column_width=True)
                                                    
                                                    st.markdown(f'<div class="debug-info">', unsafe_allow_html=True)
                                                    st.write(f"**{fig['name']}**")
                                                    st.write(f"{'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}")
                                                    st.write(f"Confidence: {fig['confidence']:.1f}%")
                                                    st.write(f"Quality: {fig['quality_score']:.2f}")
                                                    st.write(f"Aspect: {fig['aspect_ratio']:.2f}")
                                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_pdf"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('pdf_extracted_figures')
                                    original_imgs = st.session_state.pdf_images
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.pdf_latex_content, 
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    filename = f"{uploaded_pdf.name.split('.')[0]}_latex.docx"
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.pdf_latex_content,
                            file_name=uploaded_pdf.name.replace('.pdf', '.tex'),
                            mime="text/plain"
                        )
    
    # Tab Image (tương tự như PDF tab nhưng cho ảnh)
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
                
                # Metrics
                total_size = sum(img.size for img in uploaded_images)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📸 {len(uploaded_images)} ảnh</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(total_size)}</div>', unsafe_allow_html=True)
                
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
                        
                        # Tách ảnh cải tiến
                        extracted_figures = []
                        if enable_extraction and CV2_AVAILABLE:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_visualization(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                st.write(f"🔍 {uploaded_image.name}: Tách được {len(figures)} figures")
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        # Prompt tương tự như PDF
                        prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản LaTeX format CHÍNH XÁC.

🎯 ĐỊNH DẠNG CHÍNH XÁC:
1. **Câu hỏi trắc nghiệm:** Câu X: [nội dung] A) [đáp án A] B) [đáp án B] C) [đáp án C] D) [đáp án D]
2. **Câu hỏi đúng sai:** Câu X: [nội dung] a) [khẳng định a] b) [khẳng định b] c) [khẳng định c] d) [khẳng định d]
3. **Công thức toán học - GIỮ NGUYÊN ${...}$:** ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU: TUYỆT ĐỐI giữ nguyên ${...}$ cho mọi công thức, sử dụng A), B), C), D) cho trắc nghiệm và a), b), c), d) cho đúng sai.
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
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
                    st.text_area("📝 Kết quả LaTeX:", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Thống kê và debug (tương tự như PDF)
                    if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                        st.subheader("📊 Thống kê tách ảnh")
                        
                        col_1, col_2, col_3, col_4 = st.columns(4)
                        with col_1:
                            st.metric("🔍 Tổng figures", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures = sum(1 for f in all_extracted_figures if not f['is_table'])
                            st.metric("🖼️ Hình", figures)
                        with col_4:
                            avg_conf = sum(f['confidence'] for f in all_extracted_figures) / len(all_extracted_figures)
                            st.metric("🎯 Avg Confidence", f"{avg_conf:.1f}%")
                        
                        # Debug visualization
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Visualization")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                with st.expander(f"{img_name} - {len(figures)} figures"):
                                    st.image(debug_img, caption=f"Enhanced extraction results", use_column_width=True)
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word với LaTeX
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    st.subheader("📄 Xuất file Word")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        if st.button("📥 Tạo Word với LaTeX ${...}$", key="create_word_images"):
                            with st.spinner("🔄 Đang tạo Word với LaTeX..."):
                                try:
                                    extracted_figs = st.session_state.get('image_extracted_figures')
                                    original_imgs = st.session_state.image_list
                                    
                                    word_buffer = EnhancedWordExporter.create_word_document(
                                        st.session_state.image_latex_content,
                                        extracted_figures=extracted_figs,
                                        images=original_imgs
                                    )
                                    
                                    st.download_button(
                                        label="📥 Tải Word (LaTeX preserved)",
                                        data=word_buffer.getvalue(),
                                        file_name="images_latex.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )
                                    
                                    st.success("✅ Word file với LaTeX ${...}$ đã tạo thành công!")
                                
                                except Exception as e:
                                    st.error(f"❌ Lỗi tạo Word: {str(e)}")
                    
                    with col_y:
                        st.download_button(
                            label="📝 Tải LaTeX source (.tex)",
                            data=st.session_state.image_latex_content,
                            file_name="images_converted.tex",
                            mime="text/plain"
                        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 10px;'>
        <h3>🎯 ENHANCED VERSION - Hoàn thiện 100%</h3>
        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
            <div>
                <h4>🔍 Tách ảnh thông minh</h4>
                <p>✅ Loại bỏ text regions<br>✅ Geometric shape detection<br>✅ Quality assessment<br>✅ Smart cropping</p>
            </div>
            <div>
                <h4>🎯 Chèn vị trí chính xác</h4>
                <p>✅ Text structure analysis<br>✅ Figure-question mapping<br>✅ Priority-based insertion<br>✅ Context-aware positioning</p>
            </div>
            <div>
                <h4>📄 LaTeX trong Word</h4>
                <p>✅ Giữ nguyên ${...}$ format<br>✅ Cambria Math font<br>✅ Color coding<br>✅ Detailed appendix</p>
            </div>
        </div>
        <p style='margin-top: 1rem; font-size: 0.9rem;'>
            📝 <strong>Kết quả:</strong> Tách ảnh chính xác + Chèn đúng vị trí + Word có LaTeX equations
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
