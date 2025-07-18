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
    page_title="PDF/LaTeX Converter - Balanced Text Filter",
    page_icon="📝",
    layout="wide"
)

# CSS cải tiến
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

class BalancedTextFilter:
    """
    Bộ lọc text CÂN BẰNG - Lọc text nhưng vẫn giữ được figures
    """
    
    def __init__(self):
        # Ngưỡng cân bằng - không quá nghiêm ngặt
        self.text_density_threshold = 0.7      # Tăng từ 0.4 lên 0.7 (dễ dàng hơn)
        self.min_visual_complexity = 0.2       # Giảm từ 0.5 xuống 0.2 (dễ dàng hơn)  
        self.min_diagram_score = 0.1           # Giảm từ 0.3 xuống 0.1 (dễ dàng hơn)
        self.min_figure_quality = 0.15         # Giảm từ 0.3 xuống 0.15 (dễ dàng hơn)
        
        # Thông số phân tích text nâng cao - không quá khó
        self.line_density_threshold = 0.25     # Tăng từ 0.15 lên 0.25 (ít loại bỏ hơn)
        self.char_pattern_threshold = 0.8      # Tăng từ 0.6 lên 0.8 (ít loại bỏ hơn)
        self.horizontal_structure_threshold = 0.8  # Tăng từ 0.7 lên 0.8
        self.whitespace_ratio_threshold = 0.45  # Tăng từ 0.3 lên 0.45
        
        # Aspect ratio filtering - rộng hơn
        self.text_aspect_ratio_min = 0.1       # Giảm từ 0.2 xuống 0.1
        self.text_aspect_ratio_max = 12.0      # Tăng từ 8.0 lên 12.0
        
        # Size filtering - giảm yêu cầu
        self.min_meaningful_size = 1000        # Giảm từ 2000 xuống 1000
        self.max_text_block_size = 0.75        # Tăng từ 0.6 lên 0.75
        
        # Advanced pattern detection
        self.enable_ocr_simulation = True      
        self.enable_histogram_analysis = True  
        self.enable_structure_analysis = True  
        
        # Debug mode
        self.debug_mode = False
        
    def analyze_and_filter_balanced(self, image_bytes, candidates):
        """
        Phân tích và lọc với độ cân bằng tốt hơn
        """
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            # Đọc ảnh
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            if self.debug_mode:
                st.write(f"🔍 Balanced Text Filter analyzing {len(candidates)} candidates")
            
            # Phân tích từng candidate với 5 phương pháp
            analyzed_candidates = []
            for i, candidate in enumerate(candidates):
                analysis = self._balanced_analyze_candidate(img, candidate)
                candidate.update(analysis)
                analyzed_candidates.append(candidate)
                
                if self.debug_mode:
                    st.write(f"   {i+1}. {candidate.get('bbox', 'N/A')}: text_score={analysis.get('text_score', 0):.2f}, is_text={analysis.get('is_text', False)}")
            
            # Lọc cân bằng
            filtered_candidates = self._balanced_filter(analyzed_candidates)
            
            if self.debug_mode:
                st.write(f"📊 Balanced filter result: {len(filtered_candidates)}/{len(candidates)}")
            
            return filtered_candidates
            
        except Exception as e:
            if self.debug_mode:
                st.error(f"❌ Balanced filter error: {str(e)}")
            return candidates  # Fallback
    
    def _balanced_analyze_candidate(self, img, candidate):
        """
        Phân tích cân bằng từng candidate
        """
        x, y, w, h = candidate['bbox']
        roi = img[y:y+h, x:x+w]
        
        if roi.size == 0:
            return {'is_text': False, 'text_score': 0.0}
        
        # Phương pháp 1: Advanced Text Density
        text_density = self._calculate_advanced_text_density(roi)
        
        # Phương pháp 2: Line Structure Analysis
        line_density = self._analyze_line_structure(roi)
        
        # Phương pháp 3: Character Pattern Detection
        char_pattern = self._detect_character_patterns(roi)
        
        # Phương pháp 4: Histogram Analysis
        histogram_score = self._analyze_histogram_for_text(roi)
        
        # Phương pháp 5: Geometric Structure Analysis
        geometric_score = self._analyze_geometric_structure(roi)
        
        # Phương pháp 6: Whitespace Analysis
        whitespace_ratio = self._calculate_whitespace_ratio(roi)
        
        # Phương pháp 7: OCR Simulation
        ocr_score = self._simulate_ocr_detection(roi)
        
        # Tính text score tổng hợp
        text_score = (
            text_density * 0.25 +
            line_density * 0.2 +
            char_pattern * 0.15 +
            histogram_score * 0.15 +
            ocr_score * 0.15 +
            whitespace_ratio * 0.1
        )
        
        # Aspect ratio analysis
        aspect_ratio = w / (h + 1e-6)
        is_text_aspect = (self.text_aspect_ratio_min <= aspect_ratio <= self.text_aspect_ratio_max)
        
        # Size analysis
        area = w * h
        is_text_size = area < self.min_meaningful_size
        
        # Final decision - CÂN BẰNG HỢP LÝ
        # Chỉ coi là text khi:
        # 1. Text score RẤT CAO (> 0.8) VÀ là text aspect ratio
        # 2. HOẶC có nhiều indicators text cùng lúc
        
        strong_text_indicators = 0
        if text_score > 0.75:
            strong_text_indicators += 1
        if line_density > 0.3:
            strong_text_indicators += 1
        if char_pattern > 0.85:
            strong_text_indicators += 1
        if whitespace_ratio > 0.5:
            strong_text_indicators += 1
        if is_text_aspect and text_score > 0.6:
            strong_text_indicators += 1
        
        # Chỉ coi là text khi có ÍT NHẤT 3 indicators mạnh
        is_text = strong_text_indicators >= 3
        
        return {
            'text_density': text_density,
            'line_density': line_density,
            'char_pattern': char_pattern,
            'histogram_score': histogram_score,
            'geometric_score': geometric_score,
            'whitespace_ratio': whitespace_ratio,
            'ocr_score': ocr_score,
            'text_score': text_score,
            'aspect_ratio': aspect_ratio,
            'is_text': is_text,
            'area': area,
            'strong_text_indicators': strong_text_indicators
        }
    
    def _calculate_advanced_text_density(self, roi):
        """
        Tính text density nâng cao
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Phương pháp 1: Morphological text detection
        text_kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, gray.shape[1]//10), 1))
        text_kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, gray.shape[0]//10)))
        
        text_h = cv2.morphologyEx(gray, cv2.MORPH_OPEN, text_kernel_h)
        text_v = cv2.morphologyEx(gray, cv2.MORPH_OPEN, text_kernel_v)
        
        text_regions = cv2.bitwise_or(text_h, text_v)
        text_pixels = np.sum(text_regions > 0)
        total_pixels = gray.shape[0] * gray.shape[1]
        
        morphological_density = text_pixels / total_pixels if total_pixels > 0 else 0
        
        # Phương pháp 2: Edge-based text detection
        edges = cv2.Canny(gray, 50, 150)
        horizontal_edges = cv2.morphologyEx(edges, cv2.MORPH_OPEN, text_kernel_h)
        edge_density = np.sum(horizontal_edges > 0) / total_pixels if total_pixels > 0 else 0
        
        # Kết hợp
        return max(morphological_density, edge_density)
    
    def _analyze_line_structure(self, roi):
        """
        Phân tích cấu trúc dòng
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Phát hiện horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, gray.shape[1]//5), 1))
        horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
        
        # Đếm số dòng
        contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        line_count = len(contours)
        
        # Tính mật độ dòng
        height = gray.shape[0]
        line_density = line_count / (height / 20) if height > 0 else 0  # Expect 1 line per 20 pixels
        
        return min(1.0, line_density)
    
    def _detect_character_patterns(self, roi):
        """
        Phát hiện mẫu ký tự
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Phát hiện small components (characters)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary = cv2.bitwise_not(binary)  # Invert for dark text on light background
        
        # Find small components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
        
        char_like_components = 0
        total_area = gray.shape[0] * gray.shape[1]
        
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            width = stats[i, cv2.CC_STAT_WIDTH]
            height = stats[i, cv2.CC_STAT_HEIGHT]
            
            # Character-like criteria
            if (50 < area < 1000 and  # Character size
                5 < width < 50 and    # Character width
                10 < height < 50 and  # Character height
                0.2 < width/height < 3.0):  # Character aspect ratio
                char_like_components += 1
        
        # Tính tỷ lệ character-like components
        char_density = char_like_components / (total_area / 500) if total_area > 0 else 0
        return min(1.0, char_density)
    
    def _analyze_histogram_for_text(self, roi):
        """
        Phân tích histogram để phát hiện text
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Tính histogram
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = hist.flatten()
        
        # Text thường có bimodal distribution (background + text)
        # Tìm peaks
        peaks = []
        for i in range(1, len(hist) - 1):
            if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > np.max(hist) * 0.1:
                peaks.append(i)
        
        # Text có xu hướng có 2 peaks chính
        if len(peaks) >= 2:
            # Kiểm tra khoảng cách giữa peaks
            peak_distances = []
            for i in range(len(peaks) - 1):
                peak_distances.append(abs(peaks[i+1] - peaks[i]))
            
            # Text có peaks cách nhau khá xa
            if max(peak_distances) > 100:
                return 0.8
        
        # Tính entropy
        hist_norm = hist / (np.sum(hist) + 1e-10)
        entropy = -np.sum(hist_norm * np.log2(hist_norm + 1e-10))
        
        # Text có entropy thấp hơn diagrams
        if entropy < 4.0:
            return 0.6
        
        return 0.2
    
    def _analyze_geometric_structure(self, roi):
        """
        Phân tích cấu trúc hình học
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Phát hiện lines
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30, minLineLength=20, maxLineGap=10)
        line_count = len(lines) if lines is not None else 0
        
        # Phát hiện circles
        circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1, minDist=20, param1=50, param2=30, minRadius=5, maxRadius=100)
        circle_count = len(circles[0]) if circles is not None else 0
        
        # Phát hiện contours phức tạp
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        complex_contours = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 500:  # Contours lớn
                hull = cv2.convexHull(contour)
                hull_area = cv2.contourArea(hull)
                if hull_area > 0:
                    solidity = area / hull_area
                    if solidity < 0.8:  # Complex shape
                        complex_contours += 1
        
        # Tính geometric score
        total_area = gray.shape[0] * gray.shape[1]
        geometric_score = (line_count * 0.1 + circle_count * 0.5 + complex_contours * 0.3) / (total_area / 1000)
        
        return min(1.0, geometric_score)
    
    def _calculate_whitespace_ratio(self, roi):
        """
        Tính tỷ lệ khoảng trắng
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Threshold để tìm vùng sáng (whitespace)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        white_pixels = np.sum(binary == 255)
        total_pixels = gray.shape[0] * gray.shape[1]
        
        whitespace_ratio = white_pixels / total_pixels if total_pixels > 0 else 0
        
        # Text có nhiều whitespace hơn diagrams
        return whitespace_ratio
    
    def _simulate_ocr_detection(self, roi):
        """
        Mô phỏng OCR để phát hiện text
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
        
        # Chuẩn bị ảnh cho OCR
        # Resize to standard height
        target_height = 32
        if gray.shape[0] > 0:
            scale = target_height / gray.shape[0]
            new_width = int(gray.shape[1] * scale)
            if new_width > 0:
                resized = cv2.resize(gray, (new_width, target_height))
            else:
                resized = gray
        else:
            resized = gray
        
        # Enhance for OCR
        enhanced = cv2.equalizeHist(resized)
        
        # Phát hiện text patterns
        # Horizontal projections (typical for text lines)
        h_projection = np.sum(enhanced < 128, axis=1)  # Dark pixels per row
        
        # Text có xu hướng có multiple peaks trong horizontal projection
        h_peaks = 0
        for i in range(1, len(h_projection) - 1):
            if h_projection[i] > h_projection[i-1] and h_projection[i] > h_projection[i+1]:
                if h_projection[i] > np.max(h_projection) * 0.3:
                    h_peaks += 1
        
        # Text score based on projection analysis
        if h_peaks >= 2:  # Multiple text lines
            return 0.9
        elif h_peaks == 1:  # Single text line
            return 0.7
        else:
            return 0.3
    
    def _balanced_filter(self, candidates):
        """
        Lọc cân bằng - ưu tiên giữ lại figures
        """
        filtered = []
        
        for candidate in candidates:
            # Chỉ loại bỏ khi RẤT CHẮC CHẮN là text
            if candidate.get('is_text', False):
                # Cho phép giữ lại nếu có geometric complexity cao
                geometric_score = candidate.get('geometric_score', 0)
                if geometric_score >= 0.3:  # Có elements phức tạp
                    candidate['override_reason'] = 'complex_geometry'
                    filtered.append(candidate)
                    continue
                
                # Cho phép giữ lại nếu kích thước lớn và có structure
                area = candidate.get('area', 0)
                if area > 5000 and geometric_score > 0.1:
                    candidate['override_reason'] = 'large_with_structure'
                    filtered.append(candidate)
                    continue
                
                # Loại bỏ text chắc chắn
                continue
            
            # Kiểm tra các điều kiện khác - dễ dàng hơn
            text_score = candidate.get('text_score', 0)
            if text_score > self.text_density_threshold:
                # Vẫn cho phép giữ nếu có diagram elements
                geometric_score = candidate.get('geometric_score', 0)
                if geometric_score >= self.min_diagram_score:
                    candidate['override_reason'] = 'has_diagram_elements'
                    filtered.append(candidate)
                continue
            
            # Kiểm tra size - giảm requirement
            area = candidate.get('area', 0)
            if area < self.min_meaningful_size:
                # Cho phép figures nhỏ nếu có complexity cao
                geometric_score = candidate.get('geometric_score', 0)
                if geometric_score >= 0.4:
                    candidate['override_reason'] = 'small_but_complex'
                    filtered.append(candidate)
                continue
            
            # Nếu pass hầu hết tests thì giữ lại
            filtered.append(candidate)
        
        return filtered

class ContentBasedFigureFilter:
    """
    Bộ lọc thông minh với Balanced Text Filter
    """
    
    def __init__(self):
        self.text_filter = BalancedTextFilter()
        self.enable_balanced_filter = True
        self.min_estimated_count = 1
        self.max_estimated_count = 12  # Tăng từ 8 lên 12
        
    def analyze_content_and_filter(self, image_bytes, candidates):
        """
        Phân tích với Balanced Text Filter
        """
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            # Ước tính số lượng
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            estimated_count = self._estimate_figure_count_conservative(img)
            
            # Balanced Text Filter
            if self.enable_balanced_filter:
                filtered_candidates = self.text_filter.analyze_and_filter_balanced(image_bytes, candidates)
                st.success(f"🧠 Balanced Text Filter: {len(filtered_candidates)}/{len(candidates)} figures (estimated: {estimated_count})")
            else:
                filtered_candidates = candidates
            
            # Giới hạn theo estimated count - nhưng cho phép nhiều hơn
            target_count = min(estimated_count + 2, self.max_estimated_count)  # +2 để đảm bảo
            if len(filtered_candidates) > target_count:
                # Sắp xếp theo confidence
                sorted_candidates = sorted(filtered_candidates, key=lambda x: x.get('final_confidence', 0), reverse=True)
                filtered_candidates = sorted_candidates[:target_count]
            
            return filtered_candidates
            
        except Exception as e:
            st.error(f"❌ Content filter error: {str(e)}")
            return candidates
    
    def _estimate_figure_count_conservative(self, img):
        """
        Ước tính conservative số lượng figures
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            # Phân tích layout đơn giản
            # Detect horizontal separators
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//20, 1))
            h_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, h_kernel)
            h_separators = len(cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
            
            # Estimate based on separators
            estimated = min(max(h_separators + 1, self.min_estimated_count), self.max_estimated_count)
            
            return estimated
            
        except Exception:
            return 4  # Default fallback

class SuperEnhancedImageExtractor:
    """
    Tách ảnh với Balanced Text Filter
    """
    
    def __init__(self):
        # Tham số cơ bản - giảm requirements
        self.min_area_ratio = 0.0005       # Giảm từ 0.001
        self.min_area_abs = 400            # Giảm từ 600
        self.min_width = 20                # Giảm từ 30
        self.min_height = 20               # Giảm từ 30
        self.max_figures = 25              # Tăng từ 20
        self.max_area_ratio = 0.80         # Tăng từ 0.70
        
        # Tham số cắt ảnh
        self.smart_padding = 30            # Tăng từ 25
        self.quality_threshold = 0.15      # Giảm từ 0.25
        self.edge_margin = 0.005           # Giảm từ 0.01
        
        # Tham số confidence
        self.confidence_threshold = 15     # Giảm từ 30
        
        # Tham số morphology
        self.morph_kernel_size = 2
        self.dilate_iterations = 1
        self.erode_iterations = 1
        
        # Tham số edge detection
        self.canny_low = 30                # Giảm từ 40
        self.canny_high = 80               # Giảm từ 100
        self.blur_kernel = 3
        
        # Content-Based Filter với Balanced Text Filter
        self.content_filter = ContentBasedFigureFilter()
        self.enable_content_filter = True
        
        # Debug mode
        self.debug_mode = False
    
    def extract_figures_and_tables(self, image_bytes):
        """
        Tách ảnh với Balanced Text Filter
        """
        if not CV2_AVAILABLE:
            return [], 0, 0
        
        try:
            # Đọc ảnh
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            # Tiền xử lý
            enhanced_img = self._enhance_image(img)
            
            # Tách ảnh bằng 4 phương pháp
            all_candidates = []
            
            # Edge-based
            edge_candidates = self._detect_by_edges(enhanced_img, w, h)
            all_candidates.extend(edge_candidates)
            
            # Contour-based
            contour_candidates = self._detect_by_contours(enhanced_img, w, h)
            all_candidates.extend(contour_candidates)
            
            # Grid-based
            grid_candidates = self._detect_by_grid(enhanced_img, w, h)
            all_candidates.extend(grid_candidates)
            
            # Blob detection
            blob_candidates = self._detect_by_blobs(enhanced_img, w, h)
            all_candidates.extend(blob_candidates)
            
            # Lọc và merge
            filtered_candidates = self._filter_and_merge_candidates(all_candidates, w, h)
            
            # Content-Based Filter với Balanced Text Filter
            if self.enable_content_filter:
                content_filtered = self.content_filter.analyze_content_and_filter(image_bytes, filtered_candidates)
                filtered_candidates = content_filtered
            
            # Tạo final figures
            final_figures = self._create_final_figures(filtered_candidates, img, w, h)
            
            return final_figures, h, w
            
        except Exception as e:
            st.error(f"❌ Extraction error: {str(e)}")
            return [], 0, 0
    
    def _enhance_image(self, img):
        """
        Tiền xử lý ảnh
        """
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)
        return cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
    
    def _detect_by_edges(self, gray_img, w, h):
        """
        Edge detection
        """
        edges = cv2.Canny(gray_img, self.canny_low, self.canny_high)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges_dilated = cv2.dilate(edges, kernel, iterations=1)
        
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
                    'confidence': 25  # Giảm từ 35
                })
        
        return candidates
    
    def _detect_by_contours(self, gray_img, w, h):
        """
        Contour detection
        """
        _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (self.morph_kernel_size, self.morph_kernel_size))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
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
                    'confidence': 30  # Giảm từ 40
                })
        
        return candidates
    
    def _detect_by_grid(self, gray_img, w, h):
        """
        Grid detection for tables
        """
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//20, 1))
        horizontal_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, horizontal_kernel)
        
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//20))
        vertical_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, vertical_kernel)
        
        grid_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        grid_dilated = cv2.dilate(grid_mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(grid_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            
            if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                aspect_ratio = ww / (hh + 1e-6)
                confidence = 50 if aspect_ratio > 1.5 else 30  # Giảm từ 60/40
                
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
        Blob detection
        """
        adaptive_thresh = cv2.adaptiveThreshold(
            gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        inverted = cv2.bitwise_not(adaptive_thresh)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        opened = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel)
        
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
                    'confidence': 28  # Giảm từ 38
                })
        
        return candidates
    
    def _is_valid_candidate(self, x, y, ww, hh, area, img_w, img_h):
        """
        Kiểm tra candidate có hợp lệ
        """
        area_ratio = area / (img_w * img_h)
        
        if (area < self.min_area_abs or 
            area_ratio < self.min_area_ratio or 
            area_ratio > self.max_area_ratio or
            ww < self.min_width or 
            hh < self.min_height):
            return False
        
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
        
        candidates = sorted(candidates, key=lambda x: x['area'], reverse=True)
        
        filtered = []
        for candidate in candidates:
            if not self._is_overlapping_with_list(candidate, filtered):
                candidate['final_confidence'] = self._calculate_final_confidence(candidate, w, h)
                if candidate['final_confidence'] >= self.confidence_threshold:
                    filtered.append(candidate)
        
        return filtered[:self.max_figures]
    
    def _is_overlapping_with_list(self, candidate, existing_list):
        """
        Kiểm tra overlap
        """
        x1, y1, w1, h1 = candidate['bbox']
        
        for existing in existing_list:
            x2, y2, w2, h2 = existing['bbox']
            
            intersection_area = max(0, min(x1+w1, x2+w2) - max(x1, x2)) * max(0, min(y1+h1, y2+h2) - max(y1, y2))
            union_area = w1*h1 + w2*h2 - intersection_area
            
            if union_area > 0:
                iou = intersection_area / union_area
                if iou > 0.25:  # Giảm threshold từ 0.3
                    return True
        
        return False
    
    def _calculate_final_confidence(self, candidate, w, h):
        """
        Tính confidence
        """
        x, y, ww, hh = candidate['bbox']
        area_ratio = candidate['area'] / (w * h)
        aspect_ratio = ww / (hh + 1e-6)
        
        confidence = candidate.get('confidence', 20)  # Giảm từ 30
        
        # Bonus cho size phù hợp
        if 0.015 < area_ratio < 0.5:  # Giảm min từ 0.02
            confidence += 20  # Giảm từ 25
        elif 0.005 < area_ratio < 0.7:  # Giảm min từ 0.01
            confidence += 10
        
        # Bonus cho aspect ratio
        if 0.4 < aspect_ratio < 4.0:  # Mở rộng range
            confidence += 15  # Giảm từ 20
        elif 0.2 < aspect_ratio < 6.0:  # Mở rộng range
            confidence += 8   # Giảm từ 10
        
        # Bonus cho method
        if candidate['method'] == 'grid':
            confidence += 12  # Giảm từ 15
        elif candidate['method'] == 'edge':
            confidence += 8   # Giảm từ 10
        
        return min(100, confidence)
    
    def _create_final_figures(self, candidates, img, w, h):
        """
        Tạo final figures
        """
        candidates = sorted(candidates, key=lambda x: (x['bbox'][1], x['bbox'][0]))
        
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for candidate in candidates:
            cropped_img = self._smart_crop(img, candidate, w, h)
            
            if cropped_img is None:
                continue
            
            buf = io.BytesIO()
            Image.fromarray(cropped_img).save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
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
                "center_x": candidate["bbox"][0] + candidate["bbox"][2] // 2,
                "override_reason": candidate.get("override_reason", None)
            })
        
        return final_figures
    
    def _smart_crop(self, img, candidate, img_w, img_h):
        """
        Cắt ảnh thông minh
        """
        x, y, w, h = candidate['bbox']
        
        padding_x = min(self.smart_padding, w // 4)
        padding_y = min(self.smart_padding, h // 4)
        
        x0 = max(0, x - padding_x)
        y0 = max(0, y - padding_y)
        x1 = min(img_w, x + w + padding_x)
        y1 = min(img_h, y + h + padding_y)
        
        cropped = img[y0:y1, x0:x1]
        
        if cropped.size == 0:
            return None
        
        return cropped
    
    def insert_figures_into_text_precisely(self, text, figures, img_h, img_w):
        """
        Chèn figures vào text
        """
        if not figures:
            return text
        
        lines = text.split('\n')
        sorted_figures = sorted(figures, key=lambda f: f['center_y'])
        
        result_lines = lines[:]
        offset = 0
        
        for i, figure in enumerate(sorted_figures):
            insertion_line = self._calculate_insertion_position(figure, lines, i, len(sorted_figures))
            actual_insertion = insertion_line + offset
            
            if actual_insertion > len(result_lines):
                actual_insertion = len(result_lines)
            
            if figure['is_table']:
                tag = f"[📊 BẢNG: {figure['name']}]"
            else:
                tag = f"[🖼️ HÌNH: {figure['name']}]"
            
            # Thêm thông tin override nếu có
            override_info = ""
            if figure.get('override_reason'):
                override_info = f" (kept: {figure['override_reason']})"
            
            result_lines.insert(actual_insertion, "")
            result_lines.insert(actual_insertion + 1, tag + override_info)
            result_lines.insert(actual_insertion + 2, "")
            
            offset += 3
        
        return '\n'.join(result_lines)
    
    def _calculate_insertion_position(self, figure, lines, fig_index, total_figures):
        """
        Tính vị trí chèn
        """
        question_lines = []
        for i, line in enumerate(lines):
            if re.match(r'^(câu|bài|question)\s*\d+', line.strip().lower()):
                question_lines.append(i)
        
        if question_lines:
            if fig_index < len(question_lines):
                return question_lines[fig_index] + 1
            else:
                return question_lines[-1] + 2
        
        section_size = len(lines) // (total_figures + 1)
        return min(section_size * (fig_index + 1), len(lines) - 1)
    
    def create_beautiful_debug_visualization(self, image_bytes, figures):
        """
        Tạo debug visualization
        """
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            x, y, w, h = fig['bbox']
            
            draw.rectangle([x, y, x+w, y+h], outline=color, width=4)
            
            # Corner markers
            corner_size = 10
            draw.rectangle([x, y, x+corner_size, y+corner_size], fill=color)
            draw.rectangle([x+w-corner_size, y, x+w, y+corner_size], fill=color)
            
            # Center point
            center_x, center_y = fig['center_x'], fig['center_y']
            draw.ellipse([center_x-8, center_y-8, center_x+8, center_y+8], fill=color)
            
            # Simple label with override info
            label = f"{fig['name']} ({fig['confidence']:.0f}%)"
            if fig.get('override_reason'):
                label += f" [{fig['override_reason']}]"
            draw.text((x + 5, y + 5), label, fill=color, stroke_width=2, stroke_fill='white')
        
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
            mat = fitz.Matrix(3.5, 3.5)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class EnhancedWordExporter:
    """
    Xuất Word document sạch sẽ với xử lý LaTeX math chính xác
    """
    
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        try:
            doc = Document()
            
            # Cấu hình font
            style = doc.styles['Normal']
            style.font.name = 'Times New Roman'
            style.font.size = Pt(12)
            
            # Xử lý nội dung LaTeX
            lines = latex_content.split('\n')
            
            for line in lines:
                line = line.strip()
                
                if not line or line.startswith('<!--'):
                    continue
                
                if line.startswith('```'):
                    continue
                
                # Xử lý tags hình ảnh
                if line.startswith('[') and line.endswith(']'):
                    if 'HÌNH:' in line or 'BẢNG:' in line:
                        EnhancedWordExporter._insert_figure_to_word(doc, line, extracted_figures)
                        continue
                
                # Xử lý câu hỏi - đặt màu đen và in đậm
                if re.match(r'^(câu|bài)\s+\d+', line.lower()):
                    heading = doc.add_heading(line, level=3)
                    # Đặt màu đen cho câu hỏi và in đậm
                    for run in heading.runs:
                        run.font.color.rgb = RGBColor(0, 0, 0)  # Màu đen
                        run.font.bold = True
                    continue
                
                # Xử lý paragraph thường
                if line:
                    para = doc.add_paragraph()
                    EnhancedWordExporter._process_latex_content(para, line)
            
            # Lưu vào buffer
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            return buffer
            
        except Exception as e:
            st.error(f"❌ Lỗi tạo Word: {str(e)}")
            raise e
    
    @staticmethod
    def _process_latex_content(para, content):
        """
        Xử lý nội dung LaTeX - chuyển ${...}$ thành dạng Word hiệu quả
        """
        # Tách content thành các phần: text thường và công thức ${...}$
        parts = re.split(r'(\$\{[^}]+\}\$)', content)
        
        for part in parts:
            if part.startswith('${') and part.endswith('}$'):
                # Đây là công thức LaTeX
                # Loại bỏ ${ và }$ để lấy nội dung bên trong
                formula_content = part[2:-2]
                
                # Chuyển đổi một số ký hiệu LaTeX cơ bản thành Unicode
                formula_content = EnhancedWordExporter._convert_latex_to_unicode(formula_content)
                
                # Thêm công thức vào paragraph với font khác biệt
                run = para.add_run(formula_content)
                run.font.name = 'Cambria Math'  # Font phù hợp cho toán học
                run.font.italic = True  # In nghiêng cho công thức
                
            elif part.strip():
                # Đây là text thường
                run = para.add_run(part)
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12)
    
    @staticmethod
    def _convert_latex_to_unicode(latex_content):
        """
        Chuyển đổi một số ký hiệu LaTeX sang Unicode
        """
        # Dictionary chuyển đổi LaTeX sang Unicode
        latex_to_unicode = {
            # Chữ Hy Lạp
            '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ',
            '\\epsilon': 'ε', '\\theta': 'θ', '\\lambda': 'λ', '\\mu': 'μ',
            '\\pi': 'π', '\\sigma': 'σ', '\\phi': 'φ', '\\omega': 'ω',
            '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ', '\\Pi': 'Π',
            '\\Sigma': 'Σ', '\\Phi': 'Φ', '\\Omega': 'Ω',
            
            # Ký hiệu toán học
            '\\infty': '∞', '\\pm': '±', '\\mp': '∓',
            '\\times': '×', '\\div': '÷', '\\cdot': '·',
            '\\leq': '≤', '\\geq': '≥', '\\neq': '≠',
            '\\approx': '≈', '\\equiv': '≡', '\\sim': '∼',
            '\\subset': '⊂', '\\supset': '⊃', '\\in': '∈',
            '\\notin': '∉', '\\cup': '∪', '\\cap': '∩',
            '\\sum': '∑', '\\prod': '∏', '\\int': '∫',
            '\\partial': '∂', '\\nabla': '∇',
            
            # Mũi tên
            '\\rightarrow': '→', '\\leftarrow': '←',
            '\\leftrightarrow': '↔', '\\Rightarrow': '⇒',
            '\\Leftarrow': '⇐', '\\Leftrightarrow': '⇔',
            
            # Xử lý phân số đơn giản
            '\\frac{1}{2}': '½', '\\frac{1}{3}': '⅓', '\\frac{2}{3}': '⅔',
            '\\frac{1}{4}': '¼', '\\frac{3}{4}': '¾', '\\frac{1}{8}': '⅛',
            
            # Lũy thừa đơn giản (sử dụng superscript Unicode)
            '^2': '²', '^3': '³', '^1': '¹',
            '^0': '⁰', '^4': '⁴', '^5': '⁵',
            '^6': '⁶', '^7': '⁷', '^8': '⁸', '^9': '⁹',
            
            # Chỉ số dưới đơn giản (sử dụng subscript Unicode)
            '_0': '₀', '_1': '₁', '_2': '₂', '_3': '₃',
            '_4': '₄', '_5': '₅', '_6': '₆', '_7': '₇',
            '_8': '₈', '_9': '₉',
        }
        
        # Thực hiện chuyển đổi
        result = latex_content
        for latex_symbol, unicode_symbol in latex_to_unicode.items():
            result = result.replace(latex_symbol, unicode_symbol)
        
        # Xử lý phân số phức tạp \\frac{a}{b} -> a/b
        frac_pattern = r'\\frac\{([^}]+)\}\{([^}]+)\}'
        result = re.sub(frac_pattern, r'(\1)/(\2)', result)
        
        # Xử lý căn bậc hai \\sqrt{x} -> √x
        sqrt_pattern = r'\\sqrt\{([^}]+)\}'
        result = re.sub(sqrt_pattern, r'√(\1)', result)
        
        # Xử lý lũy thừa phức tạp {x}^{y} -> x^y
        pow_pattern = r'\{([^}]+)\}\^\{([^}]+)\}'
        result = re.sub(pow_pattern, r'\1^(\2)', result)
        
        # Xử lý chỉ số dưới phức tạp {x}_{y} -> x_y
        sub_pattern = r'\{([^}]+)\}_\{([^}]+)\}'
        result = re.sub(sub_pattern, r'\1_(\2)', result)
        
        # Loại bỏ các dấu ngoặc nhọn còn lại
        result = result.replace('{', '').replace('}', '')
        
        return result
    
    @staticmethod
    def _insert_figure_to_word(doc, tag_line, extracted_figures):
        """
        Chèn hình ảnh vào Word
        """
        try:
            # Extract figure name
            fig_name = None
            if 'HÌNH:' in tag_line:
                fig_name = tag_line.split('HÌNH:')[1].split(']')[0].split('(')[0].strip()
            elif 'BẢNG:' in tag_line:
                fig_name = tag_line.split('BẢNG:')[1].split(']')[0].split('(')[0].strip()
            
            if not fig_name or not extracted_figures:
                return
            
            # Find matching figure
            target_figure = None
            for fig in extracted_figures:
                if fig['name'] == fig_name:
                    target_figure = fig
                    break
            
            if target_figure:
                # Decode và chèn ảnh
                try:
                    img_data = base64.b64decode(target_figure['base64'])
                    img_pil = Image.open(io.BytesIO(img_data))
                    
                    if img_pil.mode in ('RGBA', 'LA', 'P'):
                        img_pil = img_pil.convert('RGB')
                    
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                        img_pil.save(tmp_file.name, 'PNG')
                        
                        try:
                            page_width = doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin
                            img_width = min(page_width * 0.8, Inches(6))
                        except:
                            img_width = Inches(5)
                        
                        para = doc.add_paragraph()
                        para.alignment = 1
                        run = para.add_run()
                        run.add_picture(tmp_file.name, width=img_width)
                        
                        os.unlink(tmp_file.name)
                    
                except Exception as img_error:
                    para = doc.add_paragraph(f"[Không thể hiển thị {target_figure['name']}]")
                    para.alignment = 1
                    
        except Exception as e:
            st.error(f"❌ Lỗi chèn figure: {str(e)}")

def display_beautiful_figures(figures, debug_img=None):
    """
    Hiển thị figures đẹp
    """
    if not figures:
        st.warning("⚠️ Không có figures nào")
        return
    
    if debug_img:
        st.image(debug_img, caption="Debug visualization", use_column_width=True)
    
    # Hiển thị figures trong grid
    cols_per_row = 3
    for i in range(0, len(figures), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            if i + j < len(figures):
                fig = figures[i + j]
                with cols[j]:
                    img_data = base64.b64decode(fig['base64'])
                    img_pil = Image.open(io.BytesIO(img_data))
                    
                    st.image(img_pil, use_column_width=True)
                    
                    confidence_color = "🟢" if fig['confidence'] > 70 else "🟡" if fig['confidence'] > 50 else "🔴"
                    type_icon = "📊" if fig['is_table'] else "🖼️"
                    
                    override_text = ""
                    if fig.get('override_reason'):
                        override_text = f"<br><small>✅ Kept: {fig['override_reason']}</small>"
                    
                    st.markdown(f"""
                    <div style="background: #f0f0f0; padding: 0.5rem; border-radius: 5px; margin: 5px 0;">
                        <strong>{type_icon} {fig['name']}</strong><br>
                        {confidence_color} {fig['confidence']:.1f}% | {fig['method']}{override_text}
                    </div>
                    """, unsafe_allow_html=True)

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
    st.markdown('<h1 class="main-header">📝 PDF/LaTeX Converter - Balanced Text Filter</h1>', unsafe_allow_html=True)
    
    # Hero section
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;">
        <h2 style="margin: 0;">⚖️ BALANCED TEXT FILTER - LỌCTEXTMÀVẪNGIỮFIGURES</h2>
        <p style="margin: 1rem 0; font-size: 1.1rem;">✅ 7 phương pháp phân tích • ✅ Cân bằng precision vs recall • ✅ Override logic thông minh</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        
        # API key
        api_key = st.text_input("Gemini API Key", type="password")
        
        if api_key:
            if validate_api_key(api_key):
                st.success("✅ API key hợp lệ")
            else:
                st.error("❌ API key không hợp lệ")
        
        st.markdown("---")
        
        # Cài đặt tách ảnh
        if CV2_AVAILABLE:
            st.markdown("### ⚖️ Balanced Text Filter")
            enable_extraction = st.checkbox("Bật tách ảnh Balanced", value=True)
            
            if enable_extraction:
                st.markdown("**🧠 Balanced Text Filter Features:**")
                st.markdown("""
                <div style="background: #e8f5e8; padding: 0.5rem; border-radius: 5px; margin: 5px 0;">
                <small>
                ✅ <strong>7 phương pháp phân tích:</strong><br>
                • Advanced Text Density<br>
                • Line Structure Analysis<br>
                • Character Pattern Detection<br>
                • Histogram Analysis<br>
                • Geometric Structure Analysis<br>
                • Whitespace Analysis<br>
                • OCR Simulation<br><br>
                ⚖️ <strong>Cân bằng precision vs recall</strong><br>
                🧠 <strong>Override logic thông minh</strong><br>
                ✅ <strong>Giữ lại figures có potential</strong><br>
                🎯 <strong>3+ indicators mới loại bỏ</strong>
                </small>
                </div>
                """, unsafe_allow_html=True)
                
                # Debug mode
                debug_mode = st.checkbox("Debug mode", value=False)
                
                with st.expander("🔧 Cài đặt Balanced Filter"):
                    text_threshold = st.slider("Text Density Threshold", 0.1, 0.9, 0.7, 0.1)
                    min_visual = st.slider("Min Visual Complexity", 0.1, 1.0, 0.2, 0.1)
                    min_diagram = st.slider("Min Diagram Score", 0.0, 1.0, 0.1, 0.1)
                    min_quality = st.slider("Min Figure Quality", 0.1, 1.0, 0.15, 0.05)
                    min_size = st.slider("Min Figure Size", 200, 2000, 1000, 100)
                    
                    st.markdown("**Advanced Options:**")
                    line_threshold = st.slider("Line Density Threshold", 0.05, 0.5, 0.25, 0.05)
                    char_threshold = st.slider("Character Pattern Threshold", 0.1, 1.0, 0.8, 0.1)
                    whitespace_threshold = st.slider("Whitespace Ratio Threshold", 0.1, 0.8, 0.45, 0.05)
                    
                    st.markdown("**Override Settings:**")
                    enable_geometry_override = st.checkbox("Geometry Override", value=True)
                    enable_size_override = st.checkbox("Size Override", value=True)
                    enable_complexity_override = st.checkbox("Complexity Override", value=True)
        else:
            enable_extraction = False
            debug_mode = False
            st.error("❌ OpenCV không khả dụng!")
        
        st.markdown("---")
        
        # Thông tin
        st.markdown("""
        ### ⚖️ **Balanced Text Filter:**
        
        **🧠 Ưu điểm chính:**
        
        1. **Cân bằng Precision vs Recall**
           - Không quá nghiêm ngặt như Ultra
           - Không quá lỏng lẻo
           - Ưu tiên giữ lại figures
        
        2. **Override Logic thông minh**
           - Geometry Override: Giữ figures có geometric complexity
           - Size Override: Giữ figures lớn có structure
           - Complexity Override: Giữ figures nhỏ nhưng phức tạp
        
        3. **Multiple Indicators Required**
           - Cần ít nhất 3 strong text indicators
           - Mới coi là text thật sự
           - Giảm false positives
        
        4. **Flexible Thresholds**
           - Text density: 0.7 (vs 0.4 Ultra)
           - Min visual complexity: 0.2 (vs 0.5 Ultra)
           - Min size: 1000 (vs 2000 Ultra)
           - Aspect ratio: rộng hơn
        
        **🎯 Kết quả mong đợi:**
        - **Lọc được phần lớn text**
        - **Giữ lại hầu hết figures**
        - **Ít false negatives**
        - **Override reasoning rõ ràng**
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key!")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ!")
        return
    
    # Khởi tạo
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction and CV2_AVAILABLE:
            image_extractor = SuperEnhancedImageExtractor()
            
            # Apply Balanced Filter settings
            if 'text_threshold' in locals():
                image_extractor.content_filter.text_filter.text_density_threshold = text_threshold
            if 'min_visual' in locals():
                image_extractor.content_filter.text_filter.min_visual_complexity = min_visual
            if 'min_diagram' in locals():
                image_extractor.content_filter.text_filter.min_diagram_score = min_diagram
            if 'min_quality' in locals():
                image_extractor.content_filter.text_filter.min_figure_quality = min_quality
            if 'min_size' in locals():
                image_extractor.content_filter.text_filter.min_meaningful_size = min_size
            if 'line_threshold' in locals():
                image_extractor.content_filter.text_filter.line_density_threshold = line_threshold
            if 'char_threshold' in locals():
                image_extractor.content_filter.text_filter.char_pattern_threshold = char_threshold
            if 'whitespace_threshold' in locals():
                image_extractor.content_filter.text_filter.whitespace_ratio_threshold = whitespace_threshold
            
            # Debug mode
            if debug_mode:
                image_extractor.debug_mode = True
                image_extractor.content_filter.text_filter.debug_mode = True
        else:
            image_extractor = None
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Main content với tabs - thêm tab mới
    tab1, tab2, tab3 = st.tabs(["📄 PDF sang LaTeX", "🖼️ Ảnh sang LaTeX", "📷 Ảnh chuyển & chèn"])
    
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
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang")
                        
                        # Preview
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
                
                if st.button("🚀 Bắt đầu chuyển đổi PDF", type="primary"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh với Balanced Text Filter
                            extracted_figures = []
                            debug_img = None
                            
                            if enable_extraction and CV2_AVAILABLE and image_extractor:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    if figures:
                                        debug_img = image_extractor.create_beautiful_debug_visualization(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                except Exception as e:
                                    st.error(f"❌ Lỗi tách ảnh trang {page_num}: {str(e)}")
                            
                            # Prompt
                            prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX chính xác.

🎯 YÊU CẦU ĐỊNH DẠNG:

1. **Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi đầy đủ]
A) [đáp án A hoàn chỉnh]
B) [đáp án B hoàn chỉnh]
C) [đáp án C hoàn chỉnh]  
D) [đáp án D hoàn chỉnh]
```

2. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$
- ${\\int_{0}^{1} x^2 dx}$, ${\\lim_{x \\to 0} \\frac{\\sin x}{x}}$
- Ví dụ: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau...

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
Ví dụ: Điểm ${A}$, ${B}$, ${C}$, công thức ${x^2 + 1}$, tỉ số ${\\frac{a}{b}}$

🔹 CHÚ Ý: Chỉ dùng ký tự $ khi có cặp ${...}$, không dùng $ đơn lẻ!
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                
                                if latex_result:
                                    # Chèn figures
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE and image_extractor:
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
                                            latex_result, extracted_figures, h, w
                                        )
                                    
                                    all_latex_content.append(f"<!-- 📄 Trang {page_num} -->\n{latex_result}\n")
                                    
                            except Exception as e:
                                st.error(f"❌ Lỗi API trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        st.success("🎉 Hoàn thành chuyển đổi!")
                        
                        # Kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown("### 📝 Kết quả LaTeX")
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.code(combined_latex, language="latex")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Thống kê
                        if enable_extraction and CV2_AVAILABLE and all_extracted_figures:
                            st.markdown("### 📊 Thống kê Balanced Text Filter")
                            
                            col_1, col_2, col_3, col_4 = st.columns(4)
                            with col_1:
                                st.metric("⚖️ Figures được giữ lại", len(all_extracted_figures))
                            with col_2:
                                tables = sum(1 for f in all_extracted_figures if f['is_table'])
                                st.metric("📊 Bảng", tables)
                            with col_3:
                                figures_count = len(all_extracted_figures) - tables
                                st.metric("🖼️ Hình", figures_count)
                            with col_4:
                                overrides = sum(1 for f in all_extracted_figures if f.get('override_reason'))
                                st.metric("🧠 Overrides", overrides)
                            
                            # Override statistics
                            if overrides > 0:
                                st.markdown("**🧠 Override Reasons:**")
                                override_counts = {}
                                for f in all_extracted_figures:
                                    if f.get('override_reason'):
                                        reason = f['override_reason']
                                        override_counts[reason] = override_counts.get(reason, 0) + 1
                                
                                for reason, count in override_counts.items():
                                    st.markdown(f"• **{reason}**: {count} figures")
                            
                            # Hiển thị figures
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
                        if DOCX_AVAILABLE:
                            if st.button("📄 Tạo Word", key="create_word"):
                                with st.spinner("🔄 Đang tạo Word..."):
                                    try:
                                        extracted_figs = st.session_state.get('pdf_extracted_figures')
                                        
                                        word_buffer = EnhancedWordExporter.create_word_document(
                                            st.session_state.pdf_latex_content,
                                            extracted_figures=extracted_figs
                                        )
                                        
                                        st.download_button(
                                            label="📄 Tải Word (.docx)",
                                            data=word_buffer.getvalue(),
                                            file_name=uploaded_pdf.name.replace('.pdf', '.docx'),
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="download_word"
                                        )
                                        
                                        st.success("✅ Word document đã tạo thành công!")
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
    
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
        
        uploaded_image = st.file_uploader("Chọn file ảnh", type=['png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff'])
        
        if uploaded_image:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🖼️ Preview Ảnh")
                
                # Metrics
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'<div class="metric-card">📁 {uploaded_image.name}</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="metric-card">📏 {format_file_size(uploaded_image.size)}</div>', unsafe_allow_html=True)
                
                # Hiển thị ảnh
                image_pil = Image.open(uploaded_image)
                st.image(image_pil, caption=f"Ảnh đã upload: {uploaded_image.name}", use_column_width=True)
                
                # Extract figures option
                extract_figures_single = st.checkbox("🎯 Tách figures từ ảnh", value=True, key="single_extract")
            
            with col2:
                st.subheader("⚡ Chuyển đổi sang LaTeX")
                
                if st.button("🚀 Chuyển đổi ảnh", type="primary", key="convert_single"):
                    img_bytes = uploaded_image.getvalue()
                    
                    # Tách figures nếu được bật
                    extracted_figures = []
                    debug_img = None
                    h, w = 0, 0
                    
                    if extract_figures_single and enable_extraction and CV2_AVAILABLE and image_extractor:
                        try:
                            figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                            extracted_figures = figures
                            
                            if figures:
                                debug_img = image_extractor.create_beautiful_debug_visualization(img_bytes, figures)
                                st.success(f"🎯 Đã tách được {len(figures)} figures!")
                                
                                # Hiển thị debug visualization
                                with st.expander("🔍 Xem figures được tách"):
                                    display_beautiful_figures(figures, debug_img)
                            else:
                                st.info("ℹ️ Không tìm thấy figures nào trong ảnh")
                            
                        except Exception as e:
                            st.error(f"❌ Lỗi tách figures: {str(e)}")
                    
                    # Prompt cho single image
                    prompt_text = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX chính xác.

🎯 YÊU CẦU ĐỊNH DẠNG:

1. **Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi đầy đủ]
A) [đáp án A hoàn chỉnh]
B) [đáp án B hoàn chỉnh]
C) [đáp án C hoàn chỉnh]  
D) [đáp án D hoàn chỉnh]
```

2. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$
- ${\\int_{0}^{1} x^2 dx}$, ${\\lim_{x \\to 0} \\frac{\\sin x}{x}}$
- Ví dụ: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau...

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
Ví dụ: Điểm ${A}$, ${B}$, ${C}$, công thức ${x^2 + 1}$, tỉ số ${\\frac{a}{b}}$

🔹 CHÚ Ý: Chỉ dùng ký tự $ khi có cặp ${...}$, không dùng $ đơn lẻ!
"""
                    
                    # Gọi API
                    try:
                        with st.spinner("🔄 Đang chuyển đổi..."):
                            latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                            
                            if latex_result:
                                # Chèn figures nếu có
                                if extract_figures_single and extracted_figures and CV2_AVAILABLE and image_extractor:
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
                                        latex_result, extracted_figures, h, w
                                    )
                                
                                st.success("🎉 Chuyển đổi thành công!")
                                
                                # Hiển thị kết quả
                                st.markdown("### 📝 Kết quả LaTeX")
                                st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                st.code(latex_result, language="latex")
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                                # Lưu vào session
                                st.session_state.single_latex_content = latex_result
                                st.session_state.single_extracted_figures = extracted_figures if extract_figures_single else None
                                
                            else:
                                st.error("❌ API không trả về kết quả")
                                
                    except Exception as e:
                        st.error(f"❌ Lỗi chuyển đổi: {str(e)}")
                
                # Download buttons cho single image
                if 'single_latex_content' in st.session_state:
                    st.markdown("---")
                    st.markdown("### 📥 Tải xuống")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        st.download_button(
                            label="📝 Tải LaTeX (.tex)",
                            data=st.session_state.single_latex_content,
                            file_name=uploaded_image.name.replace(uploaded_image.name.split('.')[-1], 'tex'),
                            mime="text/plain",
                            type="primary",
                            key="download_single_latex"
                        )
                    
                    with col_y:
                        if DOCX_AVAILABLE:
                            if st.button("📄 Tạo Word", key="create_single_word"):
                                with st.spinner("🔄 Đang tạo Word..."):
                                    try:
                                        extracted_figs = st.session_state.get('single_extracted_figures')
                                        
                                        word_buffer = EnhancedWordExporter.create_word_document(
                                            st.session_state.single_latex_content,
                                            extracted_figures=extracted_figs
                                        )
                                        
                                        st.download_button(
                                            label="📄 Tải Word (.docx)",
                                            data=word_buffer.getvalue(),
                                            file_name=uploaded_image.name.replace(uploaded_image.name.split('.')[-1], 'docx'),
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="download_single_word"
                                        )
                                        
                                        st.success("✅ Word document đã tạo thành công!")
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
    
    # Tab mới: Ảnh chuyển & chèn
    with tab3:
        st.header("📷 Ảnh chuyển đổi & chèn figures")
        st.markdown("""
        <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
            <h4>🎯 Tính năng đặc biệt:</h4>
            <p>• 📄 Chuyển đổi văn bản thành LaTeX</p>
            <p>• 🖼️ Tách và chèn figures tự động</p>
            <p>• ⚖️ Sử dụng Balanced Text Filter</p>
            <p>• 📝 Xuất Word với figures</p>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_convert_image = st.file_uploader("Chọn ảnh để chuyển đổi & chèn", type=['png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff'], key="convert_insert")
        
        if uploaded_convert_image:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📷 Ảnh gốc")
                
                # Hiển thị ảnh
                convert_image_pil = Image.open(uploaded_convert_image)
                st.image(convert_image_pil, caption=f"Ảnh: {uploaded_convert_image.name}", use_column_width=True)
                
                # Cài đặt
                st.markdown("### ⚙️ Cài đặt chuyển đổi")
                
                extract_and_insert = st.checkbox("🎯 Tách & chèn figures tự động", value=True, key="extract_insert")
                
                if extract_and_insert and enable_extraction:
                    st.success("✅ Balanced Text Filter đã bật")
                elif not enable_extraction:
                    st.warning("⚠️ Cần bật Balanced Text Filter trong sidebar")
                
                # Cài đặt prompt
                with st.expander("📝 Cài đặt prompt"):
                    custom_prompt = st.text_area("Custom prompt (tùy chọn):", 
                        placeholder="Để trống để sử dụng prompt mặc định...")
            
            with col2:
                st.subheader("⚡ Xử lý & Kết quả")
                
                if st.button("🚀 Chuyển đổi & chèn figures", type="primary", key="convert_insert_btn"):
                    convert_img_bytes = uploaded_convert_image.getvalue()
                    
                    # Bước 1: Tách figures
                    extracted_convert_figures = []
                    convert_debug_img = None
                    convert_h, convert_w = 0, 0
                    
                    if extract_and_insert and enable_extraction and CV2_AVAILABLE and image_extractor:
                        st.info("🔍 Bước 1: Tách figures...")
                        try:
                            convert_figures, convert_h, convert_w = image_extractor.extract_figures_and_tables(convert_img_bytes)
                            extracted_convert_figures = convert_figures
                            
                            if convert_figures:
                                convert_debug_img = image_extractor.create_beautiful_debug_visualization(convert_img_bytes, convert_figures)
                                st.success(f"✅ Đã tách được {len(convert_figures)} figures!")
                                
                                # Hiển thị figures tách được
                                with st.expander("🔍 Xem figures đã tách"):
                                    display_beautiful_figures(convert_figures, convert_debug_img)
                            else:
                                st.info("ℹ️ Không tìm thấy figures nào")
                                
                        except Exception as e:
                            st.error(f"❌ Lỗi tách figures: {str(e)}")
                    
                    # Bước 2: Chuyển đổi văn bản
                    st.info("📝 Bước 2: Chuyển đổi văn bản...")
                    
                    # Sử dụng custom prompt hoặc default
                    if custom_prompt.strip():
                        final_prompt = custom_prompt.strip()
                    else:
                        final_prompt = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX chính xác.

🎯 YÊU CẦU ĐỊNH DẠNG:

1. **Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi đầy đủ]
A) [đáp án A hoàn chỉnh]
B) [đáp án B hoàn chỉnh]
C) [đáp án C hoàn chỉnh]  
D) [đáp án D hoàn chỉnh]
```

2. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$
- ${\\int_{0}^{1} x^2 dx}$, ${\\lim_{x \\to 0} \\frac{\\sin x}{x}}$
- Ví dụ: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau...

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
Ví dụ: Điểm ${A}$, ${B}$, ${C}$, công thức ${x^2 + 1}$, tỉ số ${\\frac{a}{b}}$

🔹 CHÚ Ý: Chỉ dùng ký tự $ khi có cặp ${...}$, không dùng $ đơn lẻ!
"""
                    
                    # Gọi API
                    try:
                        convert_latex_result = gemini_api.convert_to_latex(convert_img_bytes, "image/png", final_prompt)
                        
                        if convert_latex_result:
                            st.success("✅ Chuyển đổi văn bản thành công!")
                            
                            # Bước 3: Chèn figures
                            if extract_and_insert and extracted_convert_figures and CV2_AVAILABLE and image_extractor:
                                st.info("🖼️ Bước 3: Chèn figures...")
                                convert_latex_result = image_extractor.insert_figures_into_text_precisely(
                                    convert_latex_result, extracted_convert_figures, convert_h, convert_w
                                )
                                st.success("✅ Đã chèn figures vào văn bản!")
                            
                            # Hiển thị kết quả
                            st.markdown("### 📝 Kết quả cuối cùng")
                            st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                            st.code(convert_latex_result, language="latex")
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            # Thống kê
                            if extracted_convert_figures:
                                st.markdown("### 📊 Thống kê")
                                col_1, col_2, col_3 = st.columns(3)
                                with col_1:
                                    st.metric("🖼️ Figures", len(extracted_convert_figures))
                                with col_2:
                                    tables = sum(1 for f in extracted_convert_figures if f['is_table'])
                                    st.metric("📊 Bảng", tables)
                                with col_3:
                                    figures_count = len(extracted_convert_figures) - tables
                                    st.metric("🖼️ Hình", figures_count)
                            
                            # Lưu vào session
                            st.session_state.convert_latex_content = convert_latex_result
                            st.session_state.convert_extracted_figures = extracted_convert_figures if extract_and_insert else None
                            
                        else:
                            st.error("❌ API không trả về kết quả")
                            
                    except Exception as e:
                        st.error(f"❌ Lỗi chuyển đổi: {str(e)}")
                
                # Download buttons cho convert & insert
                if 'convert_latex_content' in st.session_state:
                    st.markdown("---")
                    st.markdown("### 📥 Tải xuống")
                    
                    col_x, col_y = st.columns(2)
                    with col_x:
                        st.download_button(
                            label="📝 Tải LaTeX (.tex)",
                            data=st.session_state.convert_latex_content,
                            file_name=uploaded_convert_image.name.replace(uploaded_convert_image.name.split('.')[-1], 'tex'),
                            mime="text/plain",
                            type="primary",
                            key="download_convert_latex"
                        )
                    
                    with col_y:
                        if DOCX_AVAILABLE:
                            if st.button("📄 Tạo Word với figures", key="create_convert_word"):
                                with st.spinner("🔄 Đang tạo Word với figures..."):
                                    try:
                                        extracted_figs = st.session_state.get('convert_extracted_figures')
                                        
                                        word_buffer = EnhancedWordExporter.create_word_document(
                                            st.session_state.convert_latex_content,
                                            extracted_figures=extracted_figs
                                        )
                                        
                                        st.download_button(
                                            label="📄 Tải Word (.docx)",
                                            data=word_buffer.getvalue(),
                                            file_name=uploaded_convert_image.name.replace(uploaded_convert_image.name.split('.')[-1], 'docx'),
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="download_convert_word"
                                        )
                                        
                                        st.success("✅ Word document với figures đã tạo thành công!")
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px;'>
        <h3>⚖️ BALANCED TEXT FILTER - CÂN BẰNG PRECISION VS RECALL</h3>
        <p><strong>✅ 7 phương pháp phân tích cân bằng</strong></p>
        <p><strong>⚖️ Lọc text mà vẫn giữ figures</strong></p>
        <p><strong>🧠 Override logic thông minh</strong></p>
        <p><strong>🎯 3+ indicators mới loại bỏ</strong></p>
        <p><strong>📄 Hỗ trợ PDF + 🖼️ Hỗ trợ ảnh đơn lẻ + 📷 Hỗ trợ ảnh chuyển & chèn</strong></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
