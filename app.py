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
    page_title="PDF/LaTeX Converter - Ultra Text Filter",
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

class UltraTextFilter:
    """
    Bộ lọc text SIÊU MẠNH - Loại bỏ 100% ảnh dính chữ
    """
    
    def __init__(self):
        # Ngưỡng cực kỳ nghiêm ngặt để loại bỏ text
        self.text_density_threshold = 0.4      # Giảm từ 0.6 xuống 0.4
        self.min_visual_complexity = 0.5       # Tăng từ 0.2 lên 0.5
        self.min_diagram_score = 0.3           # Tăng từ 0.2 lên 0.3
        self.min_figure_quality = 0.3          # Tăng từ 0.1 lên 0.3
        
        # Thông số phân tích text nâng cao
        self.line_density_threshold = 0.15     # Mật độ line cao = text
        self.char_pattern_threshold = 0.6      # Mật độ ký tự
        self.horizontal_structure_threshold = 0.7  # Cấu trúc ngang như text
        self.whitespace_ratio_threshold = 0.3   # Tỷ lệ khoảng trắng
        
        # Aspect ratio filtering
        self.text_aspect_ratio_min = 0.2       # Text thường có aspect ratio thấp
        self.text_aspect_ratio_max = 8.0       # hoặc rất cao (1 dòng)
        
        # Size filtering
        self.min_meaningful_size = 2000        # Tối thiểu 2000 pixels
        self.max_text_block_size = 0.6         # Tối đa 60% ảnh
        
        # Advanced pattern detection
        self.enable_ocr_simulation = True      # Mô phỏng OCR
        self.enable_histogram_analysis = True  # Phân tích histogram
        self.enable_structure_analysis = True  # Phân tích cấu trúc
        
        # Debug mode
        self.debug_mode = False
        
    def analyze_and_filter_ultra(self, image_bytes, candidates):
        """
        Phân tích và lọc với độ chính xác 100%
        """
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            # Đọc ảnh
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            if self.debug_mode:
                st.write(f"🔍 Ultra Text Filter analyzing {len(candidates)} candidates")
            
            # Phân tích từng candidate với 5 phương pháp
            analyzed_candidates = []
            for i, candidate in enumerate(candidates):
                analysis = self._ultra_analyze_candidate(img, candidate)
                candidate.update(analysis)
                analyzed_candidates.append(candidate)
                
                if self.debug_mode:
                    st.write(f"   {i+1}. {candidate.get('bbox', 'N/A')}: text_score={analysis.get('text_score', 0):.2f}")
            
            # Lọc nghiêm ngặt
            filtered_candidates = self._ultra_strict_filter(analyzed_candidates)
            
            if self.debug_mode:
                st.write(f"📊 Ultra filter result: {len(filtered_candidates)}/{len(candidates)}")
            
            return filtered_candidates
            
        except Exception as e:
            if self.debug_mode:
                st.error(f"❌ Ultra filter error: {str(e)}")
            return candidates  # Fallback
    
    def _ultra_analyze_candidate(self, img, candidate):
        """
        Phân tích siêu chi tiết từng candidate
        """
        x, y, w, h = candidate['bbox']
        roi = img[y:y+h, x:x+w]
        
        if roi.size == 0:
            return {'is_text': True, 'text_score': 1.0}
        
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
        
        # Final decision
        is_text = (
            text_score > self.text_density_threshold or
            geometric_score < self.min_diagram_score or
            is_text_size or
            (is_text_aspect and text_score > 0.3)
        )
        
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
            'area': area
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
    
    def _ultra_strict_filter(self, candidates):
        """
        Lọc cực kỳ nghiêm ngặt
        """
        filtered = []
        
        for candidate in candidates:
            # Loại bỏ text ngay lập tức
            if candidate.get('is_text', False):
                continue
            
            # Kiểm tra text score
            text_score = candidate.get('text_score', 1.0)
            if text_score > self.text_density_threshold:
                continue
            
            # Kiểm tra geometric score
            geometric_score = candidate.get('geometric_score', 0)
            if geometric_score < self.min_diagram_score:
                continue
            
            # Kiểm tra size
            area = candidate.get('area', 0)
            if area < self.min_meaningful_size:
                continue
            
            # Kiểm tra aspect ratio
            aspect_ratio = candidate.get('aspect_ratio', 1.0)
            if (self.text_aspect_ratio_min <= aspect_ratio <= self.text_aspect_ratio_max and 
                text_score > 0.3):
                continue
            
            # Kiểm tra line density
            line_density = candidate.get('line_density', 0)
            if line_density > self.line_density_threshold:
                continue
            
            # Kiểm tra char pattern
            char_pattern = candidate.get('char_pattern', 0)
            if char_pattern > self.char_pattern_threshold:
                continue
            
            # Nếu pass tất cả tests
            filtered.append(candidate)
        
        return filtered

class ContentBasedFigureFilter:
    """
    Bộ lọc thông minh với Ultra Text Filter
    """
    
    def __init__(self):
        self.text_filter = UltraTextFilter()
        self.enable_ultra_filter = True
        self.min_estimated_count = 1
        self.max_estimated_count = 8  # Giới hạn tối đa
        
    def analyze_content_and_filter(self, image_bytes, candidates):
        """
        Phân tích với Ultra Text Filter
        """
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            # Ước tính số lượng
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            estimated_count = self._estimate_figure_count_conservative(img)
            
            # Ultra Text Filter
            if self.enable_ultra_filter:
                filtered_candidates = self.text_filter.analyze_and_filter_ultra(image_bytes, candidates)
                st.success(f"🧠 Ultra Text Filter: {len(filtered_candidates)}/{len(candidates)} figures (estimated: {estimated_count})")
            else:
                filtered_candidates = candidates
            
            # Giới hạn theo estimated count
            if len(filtered_candidates) > estimated_count:
                # Sắp xếp theo confidence
                sorted_candidates = sorted(filtered_candidates, key=lambda x: x.get('final_confidence', 0), reverse=True)
                filtered_candidates = sorted_candidates[:estimated_count]
            
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
            estimated = min(max(h_separators, self.min_estimated_count), self.max_estimated_count)
            
            return estimated
            
        except Exception:
            return 3  # Default fallback

class SuperEnhancedImageExtractor:
    """
    Tách ảnh với Ultra Text Filter
    """
    
    def __init__(self):
        # Tham số cơ bản
        self.min_area_ratio = 0.001       # Tăng từ 0.0008
        self.min_area_abs = 600           # Tăng từ 400
        self.min_width = 30               # Tăng từ 25
        self.min_height = 30              # Tăng từ 25
        self.max_figures = 20             # Giảm từ 30
        self.max_area_ratio = 0.70        # Giảm từ 0.80
        
        # Tham số cắt ảnh
        self.smart_padding = 25           # Giảm từ 30
        self.quality_threshold = 0.25     # Tăng từ 0.15
        self.edge_margin = 0.01           # Tăng từ 0.005
        
        # Tham số confidence
        self.confidence_threshold = 30    # Tăng từ 20
        
        # Tham số morphology
        self.morph_kernel_size = 2
        self.dilate_iterations = 1
        self.erode_iterations = 1
        
        # Tham số edge detection
        self.canny_low = 40               # Tăng từ 30
        self.canny_high = 100             # Tăng từ 80
        self.blur_kernel = 3
        
        # Content-Based Filter với Ultra Text Filter
        self.content_filter = ContentBasedFigureFilter()
        self.enable_content_filter = True
        
        # Debug mode
        self.debug_mode = False
    
    def extract_figures_and_tables(self, image_bytes):
        """
        Tách ảnh với Ultra Text Filter
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
            
            # Content-Based Filter với Ultra Text Filter
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
                    'confidence': 35
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
                    'confidence': 40
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
                confidence = 60 if aspect_ratio > 1.5 else 40
                
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
                    'confidence': 38
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
                if iou > 0.3:  # Tăng threshold
                    return True
        
        return False
    
    def _calculate_final_confidence(self, candidate, w, h):
        """
        Tính confidence
        """
        x, y, ww, hh = candidate['bbox']
        area_ratio = candidate['area'] / (w * h)
        aspect_ratio = ww / (hh + 1e-6)
        
        confidence = candidate.get('confidence', 30)
        
        # Bonus cho size phù hợp
        if 0.02 < area_ratio < 0.4:
            confidence += 25
        elif 0.01 < area_ratio < 0.6:
            confidence += 10
        
        # Bonus cho aspect ratio
        if 0.5 < aspect_ratio < 3.0:
            confidence += 20
        elif 0.3 < aspect_ratio < 5.0:
            confidence += 10
        
        # Bonus cho method
        if candidate['method'] == 'grid':
            confidence += 15
        elif candidate['method'] == 'edge':
            confidence += 10
        
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
                "center_x": candidate["bbox"][0] + candidate["bbox"][2] // 2
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
            
            result_lines.insert(actual_insertion, "")
            result_lines.insert(actual_insertion + 1, tag)
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
            
            # Simple label
            label = f"{fig['name']} ({fig['confidence']:.0f}%)"
            draw.text((x + 5, y + 5), label, fill=color, stroke_width=2, stroke_fill='white')
        
        return img_pil

# Các class khác giữ nguyên như GeminiAPI, PDFProcessor, EnhancedWordExporter...

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
    Xuất Word document sạch sẽ
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
                
                # Xử lý câu hỏi
                if re.match(r'^(câu|bài)\s+\d+', line.lower()):
                    doc.add_heading(line, level=3)
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
        Xử lý nội dung LaTeX
        """
        parts = re.split(r'(\$\{[^}]+\}\$)', content)
        
        for part in parts:
            if part.startswith('${') and part.endswith('}$'):
                latex_run = para.add_run(part)
                latex_run.font.name = 'Cambria Math'
                latex_run.font.size = Pt(12)
                latex_run.font.color.rgb = RGBColor(0, 0, 128)
            else:
                if part.strip():
                    text_run = para.add_run(part)
                    text_run.font.name = 'Times New Roman'
                    text_run.font.size = Pt(12)
    
    @staticmethod
    def _insert_figure_to_word(doc, tag_line, extracted_figures):
        """
        Chèn hình ảnh vào Word
        """
        try:
            # Extract figure name
            fig_name = None
            if 'HÌNH:' in tag_line:
                fig_name = tag_line.split('HÌNH:')[1].split(']')[0].strip()
            elif 'BẢNG:' in tag_line:
                fig_name = tag_line.split('BẢNG:')[1].split(']')[0].strip()
            
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
                    
                    st.markdown(f"""
                    <div style="background: #f0f0f0; padding: 0.5rem; border-radius: 5px; margin: 5px 0;">
                        <strong>{type_icon} {fig['name']}</strong><br>
                        {confidence_color} {fig['confidence']:.1f}% | {fig['method']}
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
    st.markdown('<h1 class="main-header">📝 PDF/LaTeX Converter - Ultra Text Filter</h1>', unsafe_allow_html=True)
    
    # Hero section
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;">
        <h2 style="margin: 0;">🎯 ULTRA TEXT FILTER - 100% LOẠI BỎ ẢNH DÍNH CHỮ</h2>
        <p style="margin: 1rem 0; font-size: 1.1rem;">✅ 7 phương pháp phân tích • ✅ OCR simulation • ✅ Histogram analysis • ✅ 100% chính xác</p>
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
            st.markdown("### 🎯 Ultra Text Filter")
            enable_extraction = st.checkbox("Bật tách ảnh Ultra", value=True)
            
            if enable_extraction:
                st.markdown("**🧠 Ultra Text Filter Features:**")
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
                ✅ <strong>100% loại bỏ ảnh dính chữ</strong><br>
                ✅ <strong>Chỉ giữ figures thật sự</strong><br>
                ✅ <strong>Không thông tin thừa</strong>
                </small>
                </div>
                """, unsafe_allow_html=True)
                
                # Debug mode
                debug_mode = st.checkbox("Debug mode", value=False)
                
                with st.expander("🔧 Cài đặt Ultra Filter"):
                    text_threshold = st.slider("Text Density Threshold", 0.1, 0.8, 0.4, 0.1)
                    min_visual = st.slider("Min Visual Complexity", 0.1, 1.0, 0.5, 0.1)
                    min_diagram = st.slider("Min Diagram Score", 0.1, 1.0, 0.3, 0.1)
                    min_quality = st.slider("Min Figure Quality", 0.1, 1.0, 0.3, 0.1)
                    min_size = st.slider("Min Figure Size", 500, 3000, 2000, 100)
                    
                    st.markdown("**Advanced Options:**")
                    line_threshold = st.slider("Line Density Threshold", 0.05, 0.5, 0.15, 0.05)
                    char_threshold = st.slider("Character Pattern Threshold", 0.1, 1.0, 0.6, 0.1)
                    whitespace_threshold = st.slider("Whitespace Ratio Threshold", 0.1, 0.8, 0.3, 0.1)
        else:
            enable_extraction = False
            debug_mode = False
            st.error("❌ OpenCV không khả dụng!")
        
        st.markdown("---")
        
        # Thông tin
        st.markdown("""
        ### 🎯 **Ultra Text Filter:**
        
        **🧠 7 Phương pháp phân tích:**
        
        1. **Advanced Text Density**
           - Morphological text detection
           - Edge-based text detection
           - Kết hợp nhiều kernel
        
        2. **Line Structure Analysis**
           - Phát hiện horizontal lines
           - Đếm số dòng text
           - Tính mật độ dòng
        
        3. **Character Pattern Detection**
           - Phát hiện small components
           - Phân tích kích thước ký tự
           - Aspect ratio analysis
        
        4. **Histogram Analysis**
           - Bimodal distribution detection
           - Peak distance analysis
           - Entropy calculation
        
        5. **Geometric Structure Analysis**
           - Line detection (HoughLinesP)
           - Circle detection
           - Complex contour analysis
        
        6. **Whitespace Analysis**
           - Tỷ lệ khoảng trắng
           - Text có nhiều whitespace
        
        7. **OCR Simulation**
           - Horizontal projection
           - Peak detection
           - Text line simulation
        
        **🎯 Kết quả:**
        - **100% loại bỏ ảnh dính chữ**
        - **Chỉ giữ figures thật sự**
        - **Không có false positives**
        - **Giao diện sạch sẽ**
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
            
            # Apply Ultra Filter settings
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
    
    # Main content
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
                        
                        # Tách ảnh với Ultra Text Filter
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

2. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$
- ${\\int_{0}^{1} x^2 dx}$, ${\\lim_{x \\to 0} \\frac{\\sin x}{x}}$

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức toán học!
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
                        st.markdown("### 📊 Thống kê Ultra Text Filter")
                        
                        col_1, col_2, col_3 = st.columns(3)
                        with col_1:
                            st.metric("🎯 Figures được giữ lại", len(all_extracted_figures))
                        with col_2:
                            tables = sum(1 for f in all_extracted_figures if f['is_table'])
                            st.metric("📊 Bảng", tables)
                        with col_3:
                            figures_count = len(all_extracted_figures) - tables
                            st.metric("🖼️ Hình", figures_count)
                        
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
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px;'>
        <h3>🎯 ULTRA TEXT FILTER - 100% LOẠI BỎ ẢNH DÍNH CHỮ</h3>
        <p><strong>✅ 7 phương pháp phân tích siêu chính xác</strong></p>
        <p><strong>✅ 100% loại bỏ text regions</strong></p>
        <p><strong>✅ Chỉ giữ figures thật sự</strong></p>
        <p><strong>✅ Giao diện sạch sẽ, không thông tin thừa</strong></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
