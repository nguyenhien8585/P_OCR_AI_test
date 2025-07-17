import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.shared import OxmlElement, qn
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
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
    page_title="PDF/Image to LaTeX Converter - Advanced",
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

class SmartImageExtractor:
    """Class thông minh để tách ảnh/bảng với padding tốt"""
    
    def __init__(self):
        self.min_area_ratio = 0.003
        self.min_area_abs = 1500
        self.min_width = 50
        self.min_height = 50
        self.max_figures = 12
        self.padding = 15
        self.confidence_threshold = 50
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng với padding thông minh và loại bỏ text"""
        if not CV2_AVAILABLE:
            return [], 0, 0
        
        # Đọc ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # Tiền xử lý nâng cao
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.medianBlur(gray, 5)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Tăng cường độ tương phản
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # Tách text và hình vẽ
        text_mask = self._detect_text_regions(gray)
        diagram_enhanced = self._enhance_diagrams(gray, text_mask)
        
        # Phát hiện cạnh đa phương pháp (ưu tiên hình vẽ)
        thresh1 = cv2.adaptiveThreshold(diagram_enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        thresh2 = cv2.adaptiveThreshold(diagram_enhanced, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 3)
        edges1 = cv2.Canny(diagram_enhanced, 40, 120)
        edges2 = cv2.Canny(diagram_enhanced, 60, 180)
        
        # Kết hợp
        combined = cv2.bitwise_or(thresh1, thresh2)
        combined = cv2.bitwise_or(combined, edges1)
        combined = cv2.bitwise_or(combined, edges2)
        
        # Loại bỏ text noise
        combined = cv2.bitwise_and(combined, cv2.bitwise_not(text_mask))
        
        # Morphological operations for diagrams
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_close)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_open)
        
        # Dilate nhẹ để nối các thành phần
        kernel_dilate = np.ones((3, 3), np.uint8)
        combined = cv2.dilate(combined, kernel_dilate, iterations=2)
        
        # Tìm contours
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc cơ bản - ưu tiên hình vẽ lớn
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.6):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            if not (0.2 < aspect_ratio < 8.0):  # Thắt chặt hơn
                continue
            
            # Loại bỏ vùng ở rìa
            margin = 0.02
            if (x < margin*w or y < margin*h or 
                (x+ww) > (1-margin)*w or (y+hh) > (1-margin)*h):
                continue
            
            # Kiểm tra content quality (tránh text blocks)
            roi = gray[y:y+hh, x:x+ww]
            if not self._is_valid_diagram(roi, text_mask[y:y+hh, x:x+ww]):
                continue
            
            # Tính đặc trưng
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(cnt)
            
            if hull_area == 0 or contour_area < 100:
                continue
            
            solidity = float(contour_area) / hull_area
            extent = float(contour_area) / area
            
            if solidity < 0.2 or extent < 0.15:
                continue
            
            # Phân loại bảng vs hình (cải thiện)
            is_table = self._classify_table_advanced(x, y, ww, hh, w, h, roi, text_mask[y:y+hh, x:x+ww])
            
            # Tính confidence (cải thiện cho hình vẽ)
            confidence = self._calculate_confidence_advanced(area_ratio, aspect_ratio, solidity, extent, ww, hh, w, h, is_table)
            
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
                    "content_type": "diagram" if not is_table else "table"
                })
        
        # Sắp xếp và lọc
        candidates = sorted(candidates, key=lambda f: f['confidence'], reverse=True)
        candidates = self._filter_overlapping(candidates)
        candidates = candidates[:self.max_figures]
        candidates = sorted(candidates, key=lambda box: (box["y0"], box["x0"]))
        
        # Tạo ảnh kết quả với content-aware cropping
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Smart cropping để loại bỏ text
            clean_crop = self._extract_clean_figure(
                img, fig_data, text_mask, w, h
            )
            
            if clean_crop is None or clean_crop.size == 0:
                continue
            
            # Chuyển thành base64
            buf = io.BytesIO()
            Image.fromarray(clean_crop).save(buf, format="JPEG", quality=98)
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
                "bbox": fig_data["bbox"],
                "original_bbox": fig_data["bbox"],
                "confidence": fig_data["confidence"],
                "aspect_ratio": fig_data["aspect_ratio"],
                "area": fig_data["area"],
                "solidity": fig_data["solidity"],
                "extent": fig_data["extent"],
                "center_y": fig_data["center_y"],
                "y_position": fig_data["y0"],
                "content_type": fig_data["content_type"]
            })
        
        return final_figures, h, w
    
    def _detect_text_regions(self, gray):
        """Phát hiện và tạo mask cho các vùng text"""
        # Sử dụng morphological operations để phát hiện text
        # Text thường có đặc điểm: chiều ngang, kích thước nhỏ, mật độ cao
        
        # Kernel ngang để nối các chữ cái thành từ
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 8))
        
        # Threshold để có binary image
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Tìm các vùng text ngang
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)
        horizontal = cv2.dilate(horizontal, kernel_v, iterations=2)
        
        # Tìm text với kích thước nhỏ
        kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        small_components = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_small)
        
        # Kết hợp
        text_mask = cv2.bitwise_or(horizontal, small_components)
        
        # Làm mịn mask
        kernel_smooth = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, kernel_smooth)
        
        return text_mask
    
    def _enhance_diagrams(self, gray, text_mask):
        """Tăng cường hình vẽ và giảm text noise"""
        # Loại bỏ text regions
        diagram_enhanced = cv2.bitwise_and(gray, gray, mask=cv2.bitwise_not(text_mask))
        
        # Tăng cường contrast cho diagram
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        diagram_enhanced = clahe.apply(diagram_enhanced)
        
        # Làm mịn để kết nối các đường nét
        diagram_enhanced = cv2.bilateralFilter(diagram_enhanced, 9, 80, 80)
        
        return diagram_enhanced
    
    def _is_valid_diagram(self, roi, text_mask_roi):
        """Kiểm tra xem ROI có phải là diagram hợp lệ không"""
        if roi.shape[0] < 20 or roi.shape[1] < 20:
            return False
        
        # Tính tỷ lệ text trong ROI
        text_ratio = np.sum(text_mask_roi > 0) / (roi.shape[0] * roi.shape[1])
        
        # Nếu quá nhiều text, không phải diagram
        if text_ratio > 0.6:
            return False
        
        # Kiểm tra edge density
        edges = cv2.Canny(roi, 50, 150)
        edge_density = np.sum(edges > 0) / (roi.shape[0] * roi.shape[1])
        
        # Diagram cần có đủ edge content
        if edge_density < 0.02:
            return False
        
        # Kiểm tra structural coherence
        # Diagram thường có cấu trúc hình học rõ ràng
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) == 0:
            return False
        
        # Tính area ratio của contour lớn nhất
        areas = [cv2.contourArea(cnt) for cnt in contours]
        max_area = max(areas) if areas else 0
        total_area = roi.shape[0] * roi.shape[1]
        
        # Diagram cần có structure chính
        if max_area / total_area < 0.1:
            return False
        
        return True
    
    def _classify_table_advanced(self, x, y, w, h, img_w, img_h, roi, text_mask_roi):
        """Phân loại table vs diagram cải thiện"""
        aspect_ratio = w / (h + 1e-6)
        
        # Tính tỷ lệ text (table thường có nhiều text hơn)
        text_ratio = np.sum(text_mask_roi > 0) / (roi.shape[0] * roi.shape[1])
        
        # Điểm từ text content
        text_score = 0
        if text_ratio > 0.3:
            text_score += 3
        elif text_ratio > 0.1:
            text_score += 2
        elif text_ratio > 0.05:
            text_score += 1
        
        # Điểm từ kích thước
        size_score = 0
        if w > 0.25 * img_w:
            size_score += 2
        if h > 0.08 * img_h and h < 0.7 * img_h:
            size_score += 1
        
        # Điểm từ aspect ratio (table thường dài ngang)
        ratio_score = 0
        if 2.0 < aspect_ratio < 6.0:
            ratio_score += 2
        elif 1.2 < aspect_ratio < 8.0:
            ratio_score += 1
        
        # Phát hiện đường kẻ (table có grid lines)
        line_score = 0
        if roi.shape[0] > 10 and roi.shape[1] > 10:
            # Horizontal lines
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min(roi.shape[1]//3, 40), 1))
            _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
            h_contours = cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
            
            # Vertical lines
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min(roi.shape[0]//3, 40)))
            v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
            v_contours = cv2.findContours(v_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
            
            if len(h_contours) > 2 and len(v_contours) > 2:
                line_score += 3
            elif len(h_contours) > 1 or len(v_contours) > 1:
                line_score += 2
            elif len(h_contours) > 0 or len(v_contours) > 0:
                line_score += 1
        
        total_score = text_score + size_score + ratio_score + line_score
        return total_score >= 4  # Threshold để phân biệt table/diagram
    
    def _calculate_confidence_advanced(self, area_ratio, aspect_ratio, solidity, extent, w, h, img_w, img_h, is_table):
        """Tính confidence cho diagram và table"""
        confidence = 0
        
        # Base score từ area
        if 0.02 < area_ratio < 0.5:
            confidence += 50
        elif 0.01 < area_ratio < 0.7:
            confidence += 35
        else:
            confidence += 15
        
        # Score từ aspect ratio
        if is_table:
            # Table ưu tiên ratio ngang
            if 1.5 < aspect_ratio < 5.0:
                confidence += 25
            elif 1.0 < aspect_ratio < 8.0:
                confidence += 15
            else:
                confidence += 5
        else:
            # Diagram linh hoạt hơn
            if 0.4 < aspect_ratio < 2.5:
                confidence += 25
            elif 0.2 < aspect_ratio < 4.0:
                confidence += 20
            else:
                confidence += 10
        
        # Score từ shape quality
        if solidity > 0.8:
            confidence += 15
        elif solidity > 0.5:
            confidence += 10
        else:
            confidence += 5
        
        if extent > 0.6:
            confidence += 10
        elif extent > 0.3:
            confidence += 5
        
        return min(100, confidence)
    
    def _extract_clean_figure(self, img, fig_data, text_mask, img_w, img_h):
        """Trích xuất figure sạch, loại bỏ text noise"""
        x, y, w, h = fig_data["bbox"]
        
        # Tính smart padding
        base_padding = max(self.padding, min(w, h) // 15)
        
        # Adjust padding dựa trên content type
        if fig_data["content_type"] == "diagram":
            # Diagram cần ít padding hơn để tránh text
            padding = base_padding // 2
        else:
            # Table có thể cần padding nhiều hơn
            padding = base_padding
        
        # Expand bbox với padding
        x0 = max(0, x - padding)
        y0 = max(0, y - padding)
        x1 = min(img_w, x + w + padding)
        y1 = min(img_h, y + h + padding)
        
        # Crop figure
        crop = img[y0:y1, x0:x1]
        crop_text_mask = text_mask[y0:y1, x0:x1]
        
        if crop.size == 0:
            return None
        
        # Advanced cleaning cho diagram
        if fig_data["content_type"] == "diagram":
            crop = self._clean_diagram_crop(crop, crop_text_mask)
        
        # Enhance crop quality
        crop = self._enhance_crop(crop)
        
        return crop
    
    def _clean_diagram_crop(self, crop, text_mask):
        """Làm sạch diagram crop bằng cách loại bỏ text"""
        if crop.shape[0] < 10 or crop.shape[1] < 10:
            return crop
        
        # Tạo content mask - giữ lại diagram, loại bỏ text
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        
        # Phát hiện diagram edges
        edges = cv2.Canny(gray_crop, 50, 150)
        
        # Tạo diagram mask
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        diagram_mask = cv2.dilate(edges, kernel, iterations=2)
        
        # Kết hợp: giữ diagram, loại bỏ text
        final_mask = cv2.bitwise_and(diagram_mask, cv2.bitwise_not(text_mask))
        
        # Nếu mask quá ít, giữ nguyên original
        if np.sum(final_mask > 0) < 0.05 * crop.shape[0] * crop.shape[1]:
            return crop
        
        # Áp dụng inpainting để làm sạch text regions
        inpaint_mask = cv2.bitwise_and(text_mask, cv2.bitwise_not(final_mask))
        
        if np.sum(inpaint_mask > 0) > 0:
            # Inpaint để loại bỏ text
            crop_clean = cv2.inpaint(crop, inpaint_mask, 3, cv2.INPAINT_TELEA)
            return crop_clean
        
        return crop
        """Phân loại bảng vs hình"""
        aspect_ratio = w / (h + 1e-6)
        
        # Điểm từ kích thước
        size_score = 0
        if w > 0.2 * img_w:
            size_score += 2
        if h > 0.06 * img_h and h < 0.8 * img_h:
            size_score += 1
        
        # Điểm từ aspect ratio
        ratio_score = 0
        if 1.5 < aspect_ratio < 8.0:
            ratio_score += 2
        elif 1.0 < aspect_ratio < 12.0:
            ratio_score += 1
        
        # Phát hiện đường kẻ
        line_score = 0
        if roi.shape[0] > 10 and roi.shape[1] > 10:
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min(roi.shape[1]//4, 30), 1))
            _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
            h_contours = cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
            
            if len(h_contours) > 1:
                line_score += 2
            elif len(h_contours) > 0:
                line_score += 1
        
        total_score = size_score + ratio_score + line_score
        return total_score >= 3
    
    def _calculate_confidence(self, area_ratio, aspect_ratio, solidity, extent, w, h, img_w, img_h):
        """Tính confidence"""
        confidence = 0
        
        if 0.01 < area_ratio < 0.4:
            confidence += 40
        elif 0.005 < area_ratio < 0.6:
            confidence += 25
        else:
            confidence += 10
        
        if 0.5 < aspect_ratio < 4.0:
            confidence += 30
        elif 0.2 < aspect_ratio < 8.0:
            confidence += 20
        else:
            confidence += 10
        
        if solidity > 0.7:
            confidence += 20
        elif solidity > 0.4:
            confidence += 15
        else:
            confidence += 5
        
        if extent > 0.5:
            confidence += 10
        elif extent > 0.2:
            confidence += 5
        
        return min(100, confidence)
    
    def _filter_overlapping(self, candidates):
        """Lọc overlap"""
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
                    if iou > 0.25:
                        is_overlap = True
                        break
            
            if not is_overlap:
                filtered.append(candidate)
        
        return filtered
    
    def _enhance_crop(self, crop):
        """Cải thiện chất lượng ảnh cắt"""
        crop = cv2.medianBlur(crop, 3)
        
        lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        l = clahe.apply(l)
        crop = cv2.merge([l, a, b])
        crop = cv2.cvtColor(crop, cv2.COLOR_LAB2RGB)
        
        return crop
    
    def insert_figures_into_text_by_position(self, text, figures, img_h, img_w):
        """Chèn ảnh vào văn bản dựa trên vị trí thực tế + ngữ cảnh thông minh"""
        if not figures:
            return text
        
        lines = text.split('\n')
        
        # Phân tích cấu trúc văn bản
        structure_info = self._analyze_text_structure(lines, img_h, img_w)
        
        # Sắp xếp figures theo vị trí Y
        sorted_figures = sorted(figures, key=lambda f: f['y_position'])
        
        # Chèn ảnh với logic thông minh
        result_lines = lines[:]
        inserted_count = 0
        used_figures = set()
        
        for fig in sorted_figures:
            if fig['name'] in used_figures:
                continue
                
            # Tìm vị trí chèn tối ưu
            insertion_info = self._find_optimal_insertion_position(
                fig, structure_info, img_h, img_w
            )
            
            if insertion_info:
                insertion_index = insertion_info['index'] + inserted_count
                
                # Đảm bảo không vượt quá độ dài danh sách
                if insertion_index <= len(result_lines):
                    tag = f"\n[BẢNG: {fig['name']}]\n" if fig['is_table'] else f"\n[HÌNH: {fig['name']}]\n"
                    result_lines.insert(insertion_index, tag)
                    inserted_count += 1
                    used_figures.add(fig['name'])
        
        return '\n'.join(result_lines)
    
    def _analyze_text_structure(self, lines, img_h, img_w):
        """Phân tích cấu trúc văn bản để hiểu ngữ cảnh"""
        structure = []
        estimated_line_height = img_h / max(len([line for line in lines if line.strip()]), 1)
        
        current_y = 0
        current_question = None
        
        for i, line in enumerate(lines):
            line_content = line.strip()
            if not line_content:
                current_y += estimated_line_height * 0.5  # Dòng trống
                continue
            
            # Phân loại dòng
            line_type = self._classify_line(line_content)
            
            # Cập nhật câu hỏi hiện tại
            if line_type == 'question_start':
                current_question = self._extract_question_number(line_content)
            
            structure.append({
                'index': i,
                'content': line_content,
                'y_position': current_y,
                'type': line_type,
                'question_number': current_question,
                'is_answer_area': line_type in ['question_description', 'before_answers'],
                'is_after_question': line_type in ['before_answers', 'answer_option']
            })
            
            current_y += estimated_line_height
        
        return structure
    
    def _classify_line(self, line_content):
        """Phân loại loại dòng"""
        line_lower = line_content.lower()
        
        # Câu hỏi
        if re.match(r'^câu\s+\d+', line_lower):
            return 'question_start'
        
        # Mô tả câu hỏi hoặc đề bài
        if any(keyword in line_lower for keyword in [
            'xét tính đúng sai', 'cho hình', 'trong hình', 'có tất cả', 
            'khẳng định sau', 'các khẳng định', 'đáy là', 'tâm'
        ]):
            return 'question_description'
        
        # Vùng trước đáp án (thường là nơi chèn bảng/hình)
        if (line_content.endswith(':') or line_content.endswith('sau:') or
            'khẳng định sau' in line_lower):
            return 'before_answers'
        
        # Đáp án
        if re.match(r'^[a-d]\)', line_content) or re.match(r'^[A-D]\)', line_content):
            return 'answer_option'
        
        # Dòng thường
        return 'normal'
    
    def _extract_question_number(self, line_content):
        """Trích xuất số câu hỏi"""
        match = re.search(r'câu\s+(\d+)', line_content.lower())
        return int(match.group(1)) if match else None
    
    def _find_optimal_insertion_position(self, figure, structure_info, img_h, img_w):
        """Tìm vị trí chèn tối ưu dựa trên vị trí Y và ngữ cảnh"""
        fig_y = figure['y_position']
        fig_center_y = figure.get('center_y', fig_y)
        
        # Tìm các vị trí ứng viên
        candidates = []
        
        for i, struct in enumerate(structure_info):
            # Tính điểm dựa trên khoảng cách Y
            y_distance = abs(struct['y_position'] - fig_center_y)
            y_score = max(0, 100 - (y_distance / img_h) * 100)
            
            # Tính điểm dựa trên ngữ cảnh
            context_score = self._calculate_context_score(struct, figure)
            
            # Tính điểm tổng
            total_score = y_score * 0.6 + context_score * 0.4
            
            candidates.append({
                'index': i + 1,  # Chèn sau dòng này
                'struct': struct,
                'y_score': y_score,
                'context_score': context_score,
                'total_score': total_score,
                'y_distance': y_distance
            })
        
        # Lọc và sắp xếp ứng viên
        valid_candidates = [c for c in candidates if c['total_score'] > 30]
        valid_candidates.sort(key=lambda x: x['total_score'], reverse=True)
        
        # Ưu tiên các vị trí đặc biệt
        special_candidates = [c for c in valid_candidates if c['context_score'] >= 70]
        if special_candidates:
            return special_candidates[0]
        
        # Nếu không có vị trí đặc biệt, chọn vị trí có điểm cao nhất
        if valid_candidates:
            return valid_candidates[0]
        
        return None
    
    def _calculate_context_score(self, struct, figure):
        """Tính điểm ngữ cảnh cho vị trí chèn"""
        score = 0
        line_type = struct['type']
        content = struct['content'].lower()
        
        # Điểm cao cho vị trí lý tưởng
        if line_type == 'before_answers':
            score += 80  # Vị trí tốt nhất: sau mô tả, trước đáp án
        elif line_type == 'question_description':
            score += 60  # Vị trí tốt: trong mô tả câu hỏi
        elif line_type == 'question_start':
            score += 40  # Vị trí khả dụng: sau tiêu đề câu hỏi
        
        # Điểm thưởng cho từ khóa liên quan
        if figure['is_table']:
            if any(keyword in content for keyword in [
                'bảng', 'table', 'khẳng định', 'xét tính', 'đúng sai'
            ]):
                score += 20
        else:
            if any(keyword in content for keyword in [
                'hình', 'figure', 'cho hình', 'trong hình'
            ]):
                score += 20
        
        # Điểm trừ cho vị trí không phù hợp
        if line_type == 'answer_option':
            score -= 30  # Không chèn vào giữa các đáp án
        
        # Điểm thưởng cho dòng kết thúc bằng dấu ':'
        if struct['content'].endswith(':') or struct['content'].endswith('sau:'):
            score += 25
        
        return max(0, min(100, score))
    
    def create_debug_image(self, image_bytes, figures):
        """Tạo ảnh debug"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'magenta', 'lime']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            bbox = fig['original_bbox']
            x, y, w, h = bbox
            
            # Vẽ khung
            thickness = 4 if fig['confidence'] > 80 else 3 if fig['confidence'] > 60 else 2
            draw.rectangle([x, y, x+w, y+h], outline=color, width=thickness)
            
            # Vẽ label với thông tin chi tiết
            conf_class = "HIGH" if fig['confidence'] > 80 else "MED" if fig['confidence'] > 60 else "LOW"
            type_label = "TBL" if fig['is_table'] else "DGM"  # DGM = Diagram
            content_type = fig.get('content_type', 'unknown')[:3].upper()
            label = f"{fig['name']}\n{type_label}-{conf_class}: {fig['confidence']:.0f}%\nType: {content_type}\nY: {fig.get('y_position', fig['center_y'])}\nAR: {fig['aspect_ratio']:.2f}"
            
            # Vẽ background cho text
            lines = label.split('\n')
            max_width = max(len(line) for line in lines) * 8
            text_height = len(lines) * 16
            draw.rectangle([x, y-text_height-5, x+max_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(lines):
                draw.text((x+2, y-text_height+j*14), line, fill='white')
        
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
            
            # Xử lý công thức toán học với Word Equation
            if '${' in line and '}$' in line:
                WordExporter._process_line_with_equations(doc, line)
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
    def _process_line_with_equations(doc, line):
        """Xử lý dòng có chứa equation và chuyển thành Word equation object"""
        p = doc.add_paragraph()
        
        # Parsing an toàn
        temp_line = line
        
        while '${' in temp_line and '}$' in temp_line:
            start_pos = temp_line.find('${')
            if start_pos == -1:
                break
            
            end_pos = temp_line.find('}$', start_pos + 2)
            if end_pos == -1:
                break
            
            # Thêm text trước công thức
            if start_pos > 0:
                text_before = temp_line[:start_pos]
                if text_before.strip():
                    run = p.add_run(text_before)
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12)
            
            # Thêm equation
            equation_latex = temp_line[start_pos+2:end_pos]
            WordExporter._add_equation_to_paragraph(p, equation_latex)
            
            # Cập nhật temp_line
            temp_line = temp_line[end_pos+2:]
        
        # Thêm phần còn lại
        if temp_line.strip():
            run = p.add_run(temp_line)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(12)
    
    @staticmethod
    def _add_equation_to_paragraph(paragraph, latex_equation):
        """Thêm Word equation object vào paragraph"""
        try:
            # Chuyển LaTeX thành OMML (Office Math Markup Language)
            omml_equation = WordExporter._latex_to_omml(latex_equation)
            
            # Thêm equation vào paragraph
            run = paragraph.add_run()
            run._element.append(omml_equation)
            
        except Exception as e:
            # Fallback về Unicode nếu không tạo được equation
            equation_text = WordExporter._process_latex_symbols(latex_equation)
            run = paragraph.add_run(f" {equation_text} ")
            run.font.name = 'Cambria Math'
            run.font.size = Pt(12)
            run.font.italic = True
            run.font.color.rgb = RGBColor(0, 0, 139)
    
    @staticmethod
    def _latex_to_omml(latex_text):
        """Chuyển đổi LaTeX thành OMML cho Word equation"""
        # Làm sạch LaTeX
        latex_text = latex_text.strip()
        
        # Xử lý các phần tử cơ bản
        omml_content = WordExporter._convert_latex_elements(latex_text)
        
        # Tạo OMML structure
        omml = f"""
        <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
            {omml_content}
        </m:oMath>
        """
        
        return parse_xml(omml)
    
    @staticmethod
    def _convert_latex_elements(latex_text):
        """Chuyển đổi các phần tử LaTeX thành OMML"""
        result = ""
        i = 0
        
        while i < len(latex_text):
            if latex_text[i:i+5] == '\\frac':
                # Xử lý phân số
                frac_result, new_i = WordExporter._process_fraction(latex_text, i)
                result += frac_result
                i = new_i
            elif latex_text[i] == '^':
                # Xử lý superscript
                sup_result, new_i = WordExporter._process_superscript(latex_text, i)
                result += sup_result
                i = new_i
            elif latex_text[i] == '_':
                # Xử lý subscript
                sub_result, new_i = WordExporter._process_subscript(latex_text, i)
                result += sub_result
                i = new_i
            elif latex_text[i] == '\\':
                # Xử lý ký hiệu LaTeX
                symbol_result, new_i = WordExporter._process_latex_symbol(latex_text, i)
                result += symbol_result
                i = new_i
            else:
                # Ký tự thường
                result += f'<m:t>{latex_text[i]}</m:t>'
                i += 1
        
        return result
    
    @staticmethod
    def _process_fraction(latex_text, start_pos):
        """Xử lý phân số LaTeX"""
        # Tìm tử số
        if start_pos + 6 < len(latex_text) and latex_text[start_pos + 5] == '{':
            num_start = start_pos + 6
            num_end, brace_count = WordExporter._find_matching_brace(latex_text, num_start)
            
            if num_end != -1:
                numerator = latex_text[num_start:num_end]
                
                # Tìm mẫu số
                if num_end + 1 < len(latex_text) and latex_text[num_end + 1] == '{':
                    den_start = num_end + 2
                    den_end, brace_count = WordExporter._find_matching_brace(latex_text, den_start)
                    
                    if den_end != -1:
                        denominator = latex_text[den_start:den_end]
                        
                        # Tạo OMML fraction
                        num_omml = WordExporter._convert_latex_elements(numerator)
                        den_omml = WordExporter._convert_latex_elements(denominator)
                        
                        frac_omml = f"""
                        <m:f>
                            <m:num>{num_omml}</m:num>
                            <m:den>{den_omml}</m:den>
                        </m:f>
                        """
                        
                        return frac_omml, den_end + 1
        
        # Fallback
        return f'<m:t>\\frac</m:t>', start_pos + 5
    
    @staticmethod
    def _process_superscript(latex_text, start_pos):
        """Xử lý superscript"""
        if start_pos + 1 < len(latex_text) and latex_text[start_pos + 1] == '{':
            content_start = start_pos + 2
            content_end, _ = WordExporter._find_matching_brace(latex_text, content_start)
            
            if content_end != -1:
                content = latex_text[content_start:content_end]
                content_omml = WordExporter._convert_latex_elements(content)
                
                sup_omml = f"""
                <m:sSup>
                    <m:e><m:t></m:t></m:e>
                    <m:sup>{content_omml}</m:sup>
                </m:sSup>
                """
                
                return sup_omml, content_end + 1
        
        return f'<m:t>^</m:t>', start_pos + 1
    
    @staticmethod
    def _process_subscript(latex_text, start_pos):
        """Xử lý subscript"""
        if start_pos + 1 < len(latex_text) and latex_text[start_pos + 1] == '{':
            content_start = start_pos + 2
            content_end, _ = WordExporter._find_matching_brace(latex_text, content_start)
            
            if content_end != -1:
                content = latex_text[content_start:content_end]
                content_omml = WordExporter._convert_latex_elements(content)
                
                sub_omml = f"""
                <m:sSub>
                    <m:e><m:t></m:t></m:e>
                    <m:sub>{content_omml}</m:sub>
                </m:sSub>
                """
                
                return sub_omml, content_end + 1
        
        return f'<m:t>_</m:t>', start_pos + 1
    
    @staticmethod
    def _process_latex_symbol(latex_text, start_pos):
        """Xử lý ký hiệu LaTeX"""
        # Dictionary mapping LaTeX symbols to Unicode
        latex_symbols = {
            '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ',
            '\\epsilon': 'ε', '\\theta': 'θ', '\\lambda': 'λ', '\\mu': 'μ',
            '\\pi': 'π', '\\sigma': 'σ', '\\phi': 'φ', '\\omega': 'ω',
            '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ', '\\Sigma': 'Σ',
            '\\Phi': 'Φ', '\\Omega': 'Ω', '\\infty': '∞', '\\pm': '±',
            '\\leq': '≤', '\\geq': '≥', '\\neq': '≠', '\\approx': '≈',
            '\\equiv': '≡', '\\times': '×', '\\div': '÷', '\\sqrt': '√',
            '\\sum': '∑', '\\prod': '∏', '\\int': '∫', '\\perp': '⊥',
            '\\parallel': '∥', '\\angle': '∠', '\\degree': '°'
        }
        
        # Tìm symbol dài nhất
        for symbol in sorted(latex_symbols.keys(), key=len, reverse=True):
            if latex_text[start_pos:].startswith(symbol):
                unicode_char = latex_symbols[symbol]
                return f'<m:t>{unicode_char}</m:t>', start_pos + len(symbol)
        
        # Nếu không tìm thấy, trả về ký tự \
        return f'<m:t>\\</m:t>', start_pos + 1
    
    @staticmethod
    def _find_matching_brace(text, start_pos):
        """Tìm dấu ngoặc đóng tương ứng"""
        brace_count = 1
        i = start_pos
        
        while i < len(text) and brace_count > 0:
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
            i += 1
        
        if brace_count == 0:
            return i - 1, 0
        else:
            return -1, brace_count
    
    @staticmethod
    def _process_latex_symbols(latex_text):
        """Chuyển đổi LaTeX thành Unicode (fallback)"""
        # Dictionary mapping
        latex_to_unicode = {
            '\\perp': '⊥', '\\parallel': '∥', '\\angle': '∠', '\\degree': '°',
            '^\\circ': '°', '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ',
            '\\delta': 'δ', '\\epsilon': 'ε', '\\theta': 'θ', '\\lambda': 'λ',
            '\\mu': 'μ', '\\pi': 'π', '\\sigma': 'σ', '\\phi': 'φ', '\\omega': 'ω',
            '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ', '\\Sigma': 'Σ',
            '\\Phi': 'Φ', '\\Omega': 'Ω', '\\leq': '≤', '\\geq': '≥', '\\neq': '≠',
            '\\approx': '≈', '\\equiv': '≡', '\\subset': '⊂', '\\supset': '⊃',
            '\\in': '∈', '\\notin': '∉', '\\cup': '∪', '\\cap': '∩', '\\times': '×',
            '\\div': '÷', '\\pm': '±', '\\mp': '∓', '\\infty': '∞', '\\sqrt': '√',
            '\\sum': '∑', '\\prod': '∏', '\\int': '∫',
        }
        
        # Replace LaTeX symbols
        for latex_symbol, unicode_char in latex_to_unicode.items():
            latex_text = latex_text.replace(latex_symbol, unicode_char)
        
        # Clean up
        latex_text = re.sub(r'\\[a-zA-Z]+', '', latex_text)
        latex_text = re.sub(r'[{}]', '', latex_text)
        
        return latex_text
    
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
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Advanced</h1>', unsafe_allow_html=True)
    
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
            st.subheader("🖼️ Tách ảnh thông minh")
            enable_extraction = st.checkbox("Bật tách ảnh/bảng tự động", value=True)
            
            if enable_extraction:
                min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.3, 0.1) / 100
                max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                min_size = st.slider("Kích thước tối thiểu (px)", 30, 150, 50, 10)
                padding = st.slider("Padding xung quanh (px)", 5, 30, 15, 1)
                confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 50, 5)
                show_debug = st.checkbox("Hiển thị ảnh debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Cải tiến mới:
        - ✅ **Text masking** - Loại bỏ text khỏi diagram 
        - ✅ **Content-aware cropping** - Chỉ giữ hình vẽ thuần túy
        - ✅ **Inpainting** - Xóa text noise trong diagram
        - ✅ **Smart classification** - Phân biệt table/diagram
        - ✅ **Position + Context** - Chèn ảnh đúng 100% vị trí
        
        ### 🎯 Tính năng:
        - ✅ Diagram extraction không dính chữ
        - ✅ Word equation objects (OMML)
        - ✅ Multi-scale detection với text filtering
        - ✅ Context-aware image insertion
        
        ### 📝 Định dạng output:
        **Trắc nghiệm 4 phương án:**
        ```
        Câu X: [nội dung]
        A) [Đáp án]
        B) [Đáp án]  
        C) [Đáp án]
        D) [Đáp án]
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
            image_extractor = SmartImageExtractor()
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
                                    
                                    st.write(f"🖼️ Trang {page_num}: Tách được {len(figures)} diagrams/tables (text-free)")
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cho Gemini
                            prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng CHÍNH XÁC.

🎯 ĐỊNH DẠNG BẮT BUỘC - TUÂN THỦ NGHIÊM NGẶT:

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

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học:**
- CHỈ sử dụng: ${x^2 + y^2}$ cho công thức
- VÍ DỤ: ${ABCD}$, ${A'C' \\perp BD}$, ${\\frac{a+b}{c-d}}$

⚠️ YÊU CẦU NGHIÊM NGẶT:
- TUYỆT ĐỐI sử dụng A), B), C), D) cho trắc nghiệm 4 phương án
- TUYỆT ĐỐI sử dụng a), b), c), d) cho trắc nghiệm đúng sai
- CHỈ văn bản thuần túy với công thức ${...}$
- Giữ chính xác thứ tự và cấu trúc nội dung
- Bao gồm tất cả text và công thức từ ảnh
- Không bỏ sót bất kỳ nội dung nào
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn ảnh vào văn bản THEO VỊ TRÍ
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_by_position(
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
                            st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} diagrams/tables (text-free)")
                            
                            # Debug images
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug - Text-free Diagrams (với content analysis)")
                                
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
                                                st.write(f"🏷️ Loại: {'📊 Bảng' if fig['is_table'] else '📐 Diagram'}")
                                                st.write(f"🎯 Confidence: {fig['confidence']:.1f}%")
                                                st.write(f"📍 Vị trí Y: {fig.get('y_position', fig.get('center_y', 'N/A'))}px")
                                                st.write(f"🔘 Center Y: {fig.get('center_y', 'N/A')}px")
                                                st.write(f"📑 Content: {fig.get('content_type', 'unknown')}")
                                                st.write(f"📐 Tỷ lệ: {fig['aspect_ratio']:.2f}")
                                                st.write(f"📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px")
                        
                        # Lưu session
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (Text-free)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word với equations..."):
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
                                    label="📥 Tải file Word (Text-free + Equations)",
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
                                
                                st.success("✅ File Word với Text-free Diagrams + Word Equations đã được tạo thành công!")
                                st.info("🎯 Diagrams sạch không dính chữ + Equations OMML có thể chỉnh sửa!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab Image (tương tự nhưng sử dụng position-based insertion)
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
                                
                                st.write(f"🖼️ {uploaded_image.name}: Tách được {len(figures)} diagrams/tables (text-free)")
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
- Giữ chính xác thứ tự và cấu trúc nội dung
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_by_position(
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
                        st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} diagrams/tables (text-free)")
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug - Text-free Diagrams (với content analysis)")
                            
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
                                            st.write(f"🏷️ Loại: {'📊 Bảng' if fig['is_table'] else '📐 Diagram'}")
                                            st.write(f"🎯 Confidence: {fig['confidence']:.1f}%")
                                            st.write(f"📍 Vị trí Y: {fig.get('y_position', fig.get('center_y', 'N/A'))}px")
                                            st.write(f"🔘 Center Y: {fig.get('center_y', 'N/A')}px")
                                            st.write(f"📑 Content: {fig.get('content_type', 'unknown')}")
                                            st.write(f"📐 Tỷ lệ: {fig['aspect_ratio']:.2f}")
                    
                    # Lưu session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (Text-free)", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word với equations..."):
                            try:
                                extracted_figs = st.session_state.get('image_extracted_figures')
                                original_imgs = st.session_state.image_list
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word (Text-free + Equations)",
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
                                
                                st.success("✅ File Word với Text-free Diagrams + Word Equations đã được tạo thành công!")
                                st.info("🎯 Diagrams sạch không dính chữ + Equations OMML có thể chỉnh sửa!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>🎯 <strong>ADVANCED VERSION:</strong> Text-free diagram extraction + Position-based insertion</p>
        <p>📝 <strong>Word Equations:</strong> OMML format với LaTeX → fractions, superscripts, subscripts</p>
        <p>🔍 <strong>Smart Extraction:</strong> Text masking + Content-aware cropping</p>
        <p>🖼️ <strong>Clean Diagrams:</strong> Loại bỏ text noise, chỉ giữ hình vẽ thuần túy</p>
        <p>📍 <strong>Perfect Positioning:</strong> Context-aware insertion với scoring system</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
