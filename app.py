import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw, ImageEnhance
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
    page_title="PDF/Image to LaTeX Converter - Universal & Smart",
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

class UniversalImageExtractor:
    """Class tối ưu hóa để tách ảnh/bảng CHÍNH XÁC cho mọi loại đề"""
    
    def __init__(self):
        # Tham số cơ bản - được điều chỉnh để phù hợp với mọi loại đề
        self.min_area_ratio = 0.005     # Giảm xuống để catch các hình nhỏ
        self.min_area_abs = 1500        # Giảm threshold
        self.min_width = 60             # Flexible hơn
        self.min_height = 60            
        self.max_figures = 12           # Tăng để không miss figures
        self.padding = 12               # Optimized padding
        self.confidence_threshold = 45   # Giảm để bao gồm nhiều figures hơn
        
        # Tham số cho multi-format support
        self.question_patterns = [
            r'^[Cc]âu\s*\d+[\.\:\)]',           # Câu 1. / Câu 1:
            r'^\d+[\.\:\)]',                     # 1. / 1:
            r'^[Bb]ài\s*\d+[\.\:\)]',           # Bài 1. / Bài 1:
            r'^[A-Z]\d*[\.\:\)]',               # A1. / A:
            r'^[IVX]+[\.\:\)]',                 # I. / II:
            r'^\(\d+\)',                        # (1)
            r'^Question\s*\d+[\.\:]'            # Question 1.
        ]
        
        # Từ khóa insertion - mở rộng cho nhiều context
        self.insertion_triggers = {
            'high_priority': [
                'sau:', 'dưới đây:', 'bên dưới:', 'như sau:',
                'hình vẽ sau:', 'bảng sau:', 'biểu đồ sau:',
                'đồ thị sau:', 'sơ đồ sau:', 'minh họa sau:'
            ],
            'medium_priority': [
                'hình', 'bảng', 'đồ thị', 'biểu đồ', 'sơ đồ',
                'minh họa', 'figure', 'table', 'chart',
                'diagram', 'graph', 'illustration'
            ],
            'context_keywords': [
                'cho', 'xét', 'dựa vào', 'quan sát', 'xem',
                'theo', 'từ', 'trong', 'với', 'based on'
            ]
        }
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh/bảng với algorithm được cải thiện cho mọi loại đề"""
        if not CV2_AVAILABLE:
            return [], 0, 0
        
        # 1. Tiền xử lý ảnh thông minh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # 2. Multi-stage preprocessing cho better detection
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Enhance contrast và giảm noise
        gray = self._enhance_image_quality(gray)
        
        # 3. Smart content detection
        text_regions = self._detect_text_regions_improved(gray, img)
        figure_regions = self._detect_figure_regions_improved(gray, img)
        
        # 4. Advanced edge detection với multiple scales
        edges = self._multi_scale_edge_detection(gray)
        
        # 5. Remove text noise from edges
        clean_edges = cv2.bitwise_and(edges, cv2.bitwise_not(text_regions))
        
        # 6. Find and filter contours
        contours, _ = cv2.findContours(clean_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = self._analyze_contours(contours, w, h, img, gray)
        
        # 7. Intelligent filtering và classification
        candidates = self._intelligent_filtering(candidates, w, h)
        
        # 8. Smart cropping với context preservation
        final_figures = self._extract_with_smart_cropping(candidates, img, w, h)
        
        return final_figures, h, w
    
    def _enhance_image_quality(self, gray):
        """Cải thiện chất lượng ảnh cho detection tốt hơn"""
        # Gaussian blur nhẹ để giảm noise
        enhanced = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # CLAHE với tham số tối ưu
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(enhanced)
        
        # Morphological opening để clean noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, kernel)
        
        return enhanced
    
    def _detect_text_regions_improved(self, gray, img_color):
        """Improved text region detection"""
        text_mask = np.zeros(gray.shape, dtype=np.uint8)
        
        # 1. Color-based text detection (colored backgrounds)
        hsv = cv2.cvtColor(img_color, cv2.COLOR_RGB2HSV)
        
        # Detect colored backgrounds more precisely
        color_ranges = [
            ([100, 50, 50], [130, 255, 255]),  # Blue
            ([0, 50, 50], [10, 255, 255]),     # Red 1
            ([170, 50, 50], [180, 255, 255]),  # Red 2
            ([15, 50, 50], [35, 255, 255]),    # Yellow/Orange
            ([45, 50, 50], [75, 255, 255]),    # Green
        ]
        
        for lower, upper in color_ranges:
            mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            text_mask = cv2.bitwise_or(text_mask, mask)
        
        # 2. Morphology-based text line detection
        # Horizontal text lines
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        
        # Vertical text blocks (for some layouts)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        
        # Combine all text masks
        text_mask = cv2.bitwise_or(text_mask, h_lines)
        text_mask = cv2.bitwise_or(text_mask, v_lines)
        
        # Smooth the mask
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, kernel)
        
        return text_mask
    
    def _detect_figure_regions_improved(self, gray, img_color):
        """Detect potential figure regions"""
        figure_mask = np.zeros(gray.shape, dtype=np.uint8)
        
        # Look for regions with geometric content
        # 1. Detect lines (figures often have many lines)
        edges = cv2.Canny(gray, 30, 100)
        
        # 2. Hough lines to identify geometric content
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, minLineLength=10, maxLineGap=5)
        
        if lines is not None:
            line_img = np.zeros_like(gray)
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(line_img, (x1, y1), (x2, y2), 255, 2)
            
            # Dilate to create regions
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 10))
            figure_mask = cv2.dilate(line_img, kernel, iterations=2)
        
        return figure_mask
    
    def _multi_scale_edge_detection(self, gray):
        """Multi-scale edge detection for better figure detection"""
        edges_combined = np.zeros_like(gray)
        
        # Multiple scales for different figure types
        scales = [(50, 150), (30, 100), (20, 60)]
        
        for low, high in scales:
            edges = cv2.Canny(gray, low, high)
            edges_combined = cv2.bitwise_or(edges_combined, edges)
        
        # Morphological operations to connect broken edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges_combined = cv2.morphologyEx(edges_combined, cv2.MORPH_CLOSE, kernel)
        edges_combined = cv2.dilate(edges_combined, kernel, iterations=1)
        
        return edges_combined
    
    def _analyze_contours(self, contours, w, h, img, gray):
        """Analyze contours với improved metrics"""
        candidates = []
        
        for cnt in contours:
            # Basic geometric properties
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Skip if too small or too large
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.5):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            # More flexible aspect ratio for diverse figures
            if not (0.15 < aspect_ratio < 10.0):
                continue
            
            # Skip edge regions with smaller margin
            margin = 0.02
            if (x < margin*w or y < margin*h or 
                (x+ww) > (1-margin)*w or (y+hh) > (1-margin)*h):
                continue
            
            # Advanced shape analysis
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(cnt)
            
            if hull_area == 0 or contour_area < 100:
                continue
            
            solidity = float(contour_area) / hull_area
            extent = float(contour_area) / area
            
            # More lenient shape requirements
            if solidity < 0.25 or extent < 0.2:
                continue
            
            # ROI analysis
            roi = gray[y:y+hh, x:x+ww]
            roi_color = img[y:y+hh, x:x+ww]
            
            # Content analysis
            content_score = self._analyze_content_type(roi, roi_color)
            
            # Classification
            is_table = self._classify_as_table(roi, ww, hh, aspect_ratio)
            
            # Enhanced confidence calculation
            confidence = self._calculate_enhanced_confidence(
                area_ratio, aspect_ratio, solidity, extent, 
                content_score, ww, hh, w, h
            )
            
            if confidence >= self.confidence_threshold:
                candidates.append({
                    "area": area,
                    "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                    "is_table": is_table,
                    "confidence": confidence,
                    "aspect_ratio": aspect_ratio,
                    "solidity": solidity,
                    "extent": extent,
                    "content_score": content_score,
                    "bbox": (x, y, ww, hh),
                    "center_y": y + hh // 2,
                    "y_position": y,
                    "is_diagram": not is_table
                })
        
        return candidates
    
    def _analyze_content_type(self, roi, roi_color):
        """Analyze ROI content to determine figure likelihood"""
        if roi.shape[0] < 20 or roi.shape[1] < 20:
            return 0
        
        score = 0
        
        # 1. Edge density (figures have more edges)
        edges = cv2.Canny(roi, 50, 150)
        edge_density = np.sum(edges > 0) / (roi.shape[0] * roi.shape[1])
        
        if edge_density > 0.05:
            score += 30
        elif edge_density > 0.02:
            score += 20
        
        # 2. Line detection (geometric figures have lines)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=15, minLineLength=10, maxLineGap=3)
        line_count = len(lines) if lines is not None else 0
        
        if line_count > 5:
            score += 25
        elif line_count > 2:
            score += 15
        
        # 3. Color variation (figures often have more color variation than text)
        hsv_roi = cv2.cvtColor(roi_color, cv2.COLOR_RGB2HSV)
        color_std = np.std(hsv_roi[:,:,1])  # Saturation std
        
        if color_std > 25:
            score += 20
        elif color_std > 15:
            score += 10
        
        # 4. Texture analysis (figures have different texture than text)
        gray_roi = cv2.cvtColor(roi_color, cv2.COLOR_RGB2GRAY)
        texture_score = np.std(gray_roi)
        
        if texture_score > 30:
            score += 15
        
        return min(100, score)
    
    def _classify_as_table(self, roi, w, h, aspect_ratio):
        """Improved table classification"""
        # Basic table criteria
        if aspect_ratio < 1.3:  # Tables are usually wider
            return False
        
        # Look for grid structure
        edges = cv2.Canny(roi, 50, 150)
        
        # Horizontal lines (table rows)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//3, 1))
        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        h_contours = cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        
        # Vertical lines (table columns)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//3))
        v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)
        v_contours = cv2.findContours(v_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        
        # Table needs both horizontal and vertical structure
        return len(h_contours) >= 2 and len(v_contours) >= 2
    
    def _calculate_enhanced_confidence(self, area_ratio, aspect_ratio, solidity, extent, content_score, w, h, img_w, img_h):
        """Enhanced confidence calculation"""
        confidence = 0
        
        # Size score (balanced for various figure sizes)
        if 0.008 < area_ratio < 0.3:
            confidence += 35
        elif 0.005 < area_ratio < 0.4:
            confidence += 25
        else:
            confidence += 10
        
        # Aspect ratio score (more flexible)
        if 0.6 < aspect_ratio < 1.8:  # Near square (common for diagrams)
            confidence += 25
        elif 0.3 < aspect_ratio < 3.0:  # Moderate rectangle
            confidence += 20
        elif 0.15 < aspect_ratio < 6.0:  # Wide range
            confidence += 15
        else:
            confidence += 5
        
        # Shape quality
        if solidity > 0.5:
            confidence += 20
        elif solidity > 0.3:
            confidence += 15
        else:
            confidence += 5
        
        if extent > 0.4:
            confidence += 15
        elif extent > 0.25:
            confidence += 10
        
        # Content score contribution
        confidence += content_score * 0.2
        
        return min(100, confidence)
    
    def _intelligent_filtering(self, candidates, w, h):
        """Intelligent filtering to remove overlaps and false positives"""
        # Sort by confidence
        candidates = sorted(candidates, key=lambda x: x['confidence'], reverse=True)
        
        # Remove overlaps with smart IoU calculation
        filtered = []
        for candidate in candidates:
            is_duplicate = False
            
            for existing in filtered:
                iou = self._calculate_iou(candidate, existing)
                if iou > 0.15:  # Lower threshold to avoid removing nearby figures
                    # Keep the one with higher confidence
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered.append(candidate)
        
        # Limit number but don't be too restrictive
        filtered = filtered[:self.max_figures]
        
        # Sort by position for insertion
        filtered = sorted(filtered, key=lambda x: (x["y0"], x["x0"]))
        
        return filtered
    
    def _calculate_iou(self, box1, box2):
        """Calculate Intersection over Union"""
        x1_min, y1_min, x1_max, y1_max = box1['x0'], box1['y0'], box1['x1'], box1['y1']
        x2_min, y2_min, x2_max, y2_max = box2['x0'], box2['y0'], box2['x1'], box2['y1']
        
        # Calculate intersection area
        x_overlap = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
        y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
        intersection = x_overlap * y_overlap
        
        # Calculate union area
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _extract_with_smart_cropping(self, candidates, img, img_w, img_h):
        """Smart cropping với context preservation"""
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Smart padding calculation
            x, y, w, h = fig_data["bbox"]
            
            # Adaptive padding based on figure size
            padding_x = min(self.padding, w // 8, (img_w - (x + w)) // 2, x // 2)
            padding_y = min(self.padding, h // 8, (img_h - (y + h)) // 2, y // 2)
            
            # Calculate crop bounds
            x0 = max(0, x - padding_x)
            y0 = max(0, y - padding_y)
            x1 = min(img_w, x + w + padding_x)
            y1 = min(img_h, y + h + padding_y)
            
            # Extract and enhance crop
            crop = img[y0:y1, x0:x1]
            
            if crop.size == 0:
                continue
            
            # Post-process crop for better quality
            crop_enhanced = self._enhance_crop_quality(crop)
            
            # Convert to base64
            buf = io.BytesIO()
            Image.fromarray(crop_enhanced).save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            # Generate filename
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
                "content_score": fig_data["content_score"],
                "center_y": fig_data["center_y"],
                "y_position": fig_data["y_position"],
                "is_diagram": fig_data["is_diagram"]
            })
        
        return final_figures
    
    def _enhance_crop_quality(self, crop):
        """Enhance extracted crop quality"""
        # Convert to PIL for enhancement
        pil_crop = Image.fromarray(crop)
        
        # Slight sharpening
        enhancer = ImageEnhance.Sharpness(pil_crop)
        pil_crop = enhancer.enhance(1.1)
        
        # Slight contrast enhancement
        enhancer = ImageEnhance.Contrast(pil_crop)
        pil_crop = enhancer.enhance(1.05)
        
        return np.array(pil_crop)
    
    def insert_figures_into_text_universal(self, text, figures, img_h, img_w):
        """Universal insertion algorithm cho mọi loại đề"""
        if not figures:
            return text
        
        lines = text.split('\n')
        
        # Phân tích structure của text
        text_structure = self._analyze_universal_structure(lines)
        
        # Map figures to appropriate positions
        figure_placements = self._map_figures_universal(figures, text_structure, img_h)
        
        # Insert figures
        result_lines = self._insert_figures_smart(lines, figure_placements)
        
        return '\n'.join(result_lines)
    
    def _analyze_universal_structure(self, lines):
        """Analyze text structure for universal question formats"""
        structure = {
            'questions': [],
            'sections': [],
            'insertion_points': []
        }
        
        for i, line in enumerate(lines):
            line_content = line.strip()
            if not line_content:
                continue
            
            line_lower = line_content.lower()
            
            # Detect questions with multiple patterns
            is_question = False
            for pattern in self.question_patterns:
                if re.match(pattern, line_content, re.IGNORECASE):
                    is_question = True
                    break
            
            if is_question:
                structure['questions'].append({
                    'line': i,
                    'content': line_content,
                    'insertion_candidates': []
                })
            
            # Find high-priority insertion points
            for trigger in self.insertion_triggers['high_priority']:
                if trigger in line_lower:
                    structure['insertion_points'].append({
                        'line': i,
                        'priority': 100,
                        'trigger': trigger,
                        'content': line_content
                    })
            
            # Find medium-priority insertion points
            for trigger in self.insertion_triggers['medium_priority']:
                if trigger in line_lower:
                    # Check for context keywords to boost priority
                    priority = 60
                    for context in self.insertion_triggers['context_keywords']:
                        if context in line_lower:
                            priority += 20
                            break
                    
                    structure['insertion_points'].append({
                        'line': i,
                        'priority': priority,
                        'trigger': trigger,
                        'content': line_content
                    })
        
        # Add insertion candidates to questions
        for question in structure['questions']:
            q_line = question['line']
            # Look for insertion points near this question
            for point in structure['insertion_points']:
                if abs(point['line'] - q_line) <= 5:  # Within 5 lines
                    question['insertion_candidates'].append(point)
            
            # Sort by priority
            question['insertion_candidates'].sort(key=lambda x: x['priority'], reverse=True)
        
        return structure
    
    def _map_figures_universal(self, figures, text_structure, img_h):
        """Universal figure mapping algorithm"""
        # Sort figures by vertical position
        sorted_figures = sorted(figures, key=lambda f: f['y_position'])
        
        mappings = []
        
        for figure in sorted_figures:
            figure_y_ratio = figure['y_position'] / img_h
            best_insertion = None
            best_score = 0
            
            # Try to match with insertion points
            for point in text_structure['insertion_points']:
                # Calculate position-based score
                line_ratio = point['line'] / max(1, len(text_structure['insertion_points']))
                distance_score = max(0, 100 - abs(figure_y_ratio - line_ratio) * 200)
                
                # Combine with priority
                total_score = distance_score * 0.6 + point['priority'] * 0.4
                
                # Boost score for table/figure type matching
                if figure['is_table'] and 'bảng' in point['trigger']:
                    total_score += 20
                elif not figure['is_table'] and any(word in point['trigger'] for word in ['hình', 'đồ thị', 'biểu đồ']):
                    total_score += 20
                
                if total_score > best_score:
                    best_score = total_score
                    best_insertion = point
            
            # Fallback to questions if no good insertion point found
            if best_score < 40:
                for question in text_structure['questions']:
                    q_line_ratio = question['line'] / max(1, len(text_structure['questions']))
                    distance_score = max(0, 80 - abs(figure_y_ratio - q_line_ratio) * 150)
                    
                    if distance_score > best_score:
                        best_score = distance_score
                        best_insertion = {
                            'line': question['line'] + 1,  # Insert after question
                            'priority': 50,
                            'trigger': 'question_fallback'
                        }
            
            mappings.append({
                'figure': figure,
                'insertion_point': best_insertion,
                'score': best_score
            })
        
        # Sort by insertion line to maintain order
        mappings.sort(key=lambda x: x['insertion_point']['line'] if x['insertion_point'] else float('inf'))
        
        return mappings
    
    def _insert_figures_smart(self, lines, figure_placements):
        """Smart insertion maintaining text flow"""
        result_lines = lines[:]
        inserted_count = 0
        
        for placement in figure_placements:
            if placement['insertion_point'] is None:
                continue
            
            figure = placement['figure']
            insertion_line = placement['insertion_point']['line'] + inserted_count
            
            # Ensure we don't insert beyond text bounds
            if insertion_line > len(result_lines):
                insertion_line = len(result_lines)
            
            # Create tag
            tag = f"\n[BẢNG: {figure['name']}]\n" if figure['is_table'] else f"\n[HÌNH: {figure['name']}]\n"
            
            # Insert with proper spacing
            if insertion_line < len(result_lines):
                # Check if we need to add spacing
                if insertion_line > 0 and result_lines[insertion_line-1].strip():
                    if not result_lines[insertion_line-1].endswith(':'):
                        tag = tag
                
                result_lines.insert(insertion_line, tag.strip())
                inserted_count += 1
            else:
                result_lines.append(tag.strip())
                inserted_count += 1
        
        return result_lines
    
    def create_debug_image(self, image_bytes, figures):
        """Create debug visualization"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            bbox = fig['original_bbox']
            x, y, w, h = bbox
            
            # Draw bounding box
            thickness = 3
            draw.rectangle([x, y, x+w, y+h], outline=color, width=thickness)
            
            # Create detailed label
            type_label = "TBL" if fig['is_table'] else "IMG"
            label = f"{fig['name']}\n{type_label}: {fig['confidence']:.0f}%\nScore: {fig.get('content_score', 0):.0f}"
            
            # Draw background for text
            lines = label.split('\n')
            max_width = max(len(line) for line in lines) * 8
            text_height = len(lines) * 15
            draw.rectangle([x, y-text_height-5, x+max_width, y], fill=color, outline=color)
            
            # Draw text
            for j, line in enumerate(lines):
                draw.text((x+2, y-text_height+j*13), line, fill='white')
        
        return img_pil

# GeminiAPI class (unchanged)
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

# PDFProcessor class (unchanged)
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

# SimpleWordExporter class (unchanged)
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
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Universal & Smart</h1>', unsafe_allow_html=True)
    
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
            enable_extraction = st.checkbox("Bật tách ảnh/bảng", value=True)
            
            if enable_extraction:
                min_area = st.slider("Diện tích tối thiểu (%)", 0.3, 2.0, 0.5, 0.1) / 100
                max_figures = st.slider("Số ảnh tối đa", 1, 20, 12, 1)
                min_size = st.slider("Kích thước tối thiểu (px)", 40, 120, 60, 10)
                padding = st.slider("Padding xung quanh (px)", 5, 25, 12, 2)
                confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 80, 45, 5)
                show_debug = st.checkbox("Hiển thị ảnh debug", value=True)
        else:
            enable_extraction = False
            st.warning("⚠️ OpenCV không khả dụng. Tính năng tách ảnh bị tắt.")
        
        st.markdown("---")
        st.markdown("""
        ### ✅ **Universal Version:**
        - 🎯 **Multi-format support** - Tất cả loại đề
        - 🧠 **Smart detection** - AI-powered figure detection
        - 📍 **Precise insertion** - Context-aware positioning  
        - ✂️ **Smart cropping** - Beautiful figure extraction
        - 🔍 **Enhanced quality** - Better image processing
        
        ### 🚀 Improvements:
        - ✅ Hỗ trợ đa định dạng câu hỏi
        - ✅ Insertion thông minh hơn
        - ✅ Cắt ảnh đẹp với padding adaptive
        - ✅ Confidence scoring cải tiến
        - ✅ Content-aware classification
        
        ### 📝 Hoạt động với:
        ```
        Câu 1: / 1. / Bài 1: / A1:
        Question 1: / (1) / I.
        + Multi-trigger insertion
        + Context-aware positioning
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
            image_extractor = UniversalImageExtractor()
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
                                    
                                    st.write(f"🖼️ Trang {page_num}: Tách được {len(figures)} figures (enhanced)")
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt cho Gemini - Enhanced cho universal format
                            prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng CHÍNH XÁC.

🎯 ĐỊNH DẠNG LINH HOẠT - Hỗ trợ mọi kiểu đề:

1. **Trắc nghiệm 4 phương án:**
   - Sử dụng A), B), C), D) cho đáp án 4 lựa chọn
   
2. **Trắc nghiệm đúng sai:**
   - Sử dụng a), b), c), d) cho đáp án đúng/sai
   
3. **Câu hỏi tự luận:**
   - Giữ nguyên format câu hỏi gốc

4. **Định dạng câu hỏi linh hoạt:**
   - Câu X: / X. / Bài X: / (X) / Question X: / A.X:
   - Giữ CHÍNH XÁC format gốc

5. **Công thức toán học:**
   - Sử dụng ${...}$ cho inline: ${x^2 + y^2}$  
   - Sử dụng $${...}$$ cho display: $${\\frac{a+b}{c}}$$

⚠️ YÊU CẦU CHẤT LƯỢNG:
- Giữ CHÍNH XÁC thứ tự và cấu trúc
- Bao gồm TẤT CẢ text, số, công thức
- Không thay đổi format câu hỏi gốc
- Chú ý context cho hình ảnh/bảng
- Text thuần túy + công thức LaTeX
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                if latex_result:
                                    # Chèn ảnh vào văn bản với UNIVERSAL algorithm
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                        latex_result = image_extractor.insert_figures_into_text_universal(
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
                            st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} figures (universal algorithm)")
                            
                            # Debug images
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug - Universal Figure Detection")
                                
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
                                                st.write(f"🏷️ Loại: {'📊 Bảng' if fig['is_table'] else '📐 Hình'}")
                                                st.write(f"🎯 Confidence: {fig['confidence']:.1f}%")
                                                st.write(f"📊 Content Score: {fig.get('content_score', 0):.1f}")
                                                st.write(f"📍 Vị trí Y: {fig['y_position']}px")
                        
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
                                
                                st.write(f"🖼️ {uploaded_image.name}: Tách được {len(figures)} figures (enhanced)")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt_text = """
Chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng CHÍNH XÁC.

🎯 ĐỊNH DẠNG LINH HOẠT - Hỗ trợ mọi kiểu đề:

1. **Trắc nghiệm 4 phương án:**
   - Sử dụng A), B), C), D) cho đáp án 4 lựa chọn
   
2. **Trắc nghiệm đúng sai:**
   - Sử dụng a), b), c), d) cho đáp án đúng/sai
   
3. **Định dạng câu hỏi linh hoạt:**
   - Câu X: / X. / Bài X: / (X) / Question X:
   - Giữ CHÍNH XÁC format gốc

4. **Công thức toán học:**
   - ${x^2 + y^2}$ cho inline
   - $${\\frac{a+b}{c}}$$ cho display

⚠️ YÊU CẦU:
- Giữ CHÍNH XÁC format gốc
- Text thuần túy + công thức LaTeX
- Bao gồm TẤT CẢ nội dung
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt_text
                            )
                            if latex_result:
                                if enable_extraction and extracted_figures and CV2_AVAILABLE:
                                    latex_result = image_extractor.insert_figures_into_text_universal(
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
                        st.info(f"🖼️ Tổng cộng đã tách: {len(all_extracted_figures)} figures (universal algorithm)")
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug - Universal Figure Detection")
                            
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
                                            st.write(f"🏷️ Loại: {'📊 Bảng' if fig['is_table'] else '📐 Hình'}")
                                            st.write(f"🎯 Confidence: {fig['confidence']:.1f}%")
                                            st.write(f"📊 Content Score: {fig.get('content_score', 0):.1f}")
                                            st.write(f"📍 Vị trí Y: {fig['y_position']}px")
                    
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
        <p>🎯 <strong>UNIVERSAL & SMART VERSION:</strong> Hỗ trợ mọi loại đề + Chèn thông minh</p>
        <p>🧠 <strong>AI-Powered Detection:</strong> Content-aware figure classification</p>
        <p>✂️ <strong>Smart Cropping:</strong> Adaptive padding + Enhanced quality</p>
        <p>📍 <strong>Universal Insertion:</strong> Multi-format question support</p>
        <p>🔧 <strong>Enhanced Processing:</strong> Better algorithms cho mọi context</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
