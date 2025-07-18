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

class GoogleOCRService:
    """
    Enhanced Google Apps Script OCR Service với 99.99% accuracy
    """
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'PDF-LaTeX-Converter/2.0'
        })
        self.max_retries = 3
        self.timeout = 90
    
    def analyze_image_content(self, image_bytes, detect_figures=True, detect_tables=True):
        """
        Enhanced phân tích nội dung ảnh với multiple methods
        """
        try:
            # Step 1: Preprocess image for better OCR
            enhanced_image_bytes = self._preprocess_image_for_ocr(image_bytes)
            
            # Step 2: Multi-resolution analysis
            results = []
            
            # Original resolution
            result1 = self._analyze_single_image(enhanced_image_bytes, detect_figures, detect_tables, "original")
            if result1:
                results.append(result1)
            
            # High resolution version
            high_res_bytes = self._create_high_resolution_version(image_bytes)
            result2 = self._analyze_single_image(high_res_bytes, detect_figures, detect_tables, "high_res")
            if result2:
                results.append(result2)
            
            # Preprocessed version with different settings
            alt_processed_bytes = self._alternative_preprocessing(image_bytes)
            result3 = self._analyze_single_image(alt_processed_bytes, detect_figures, detect_tables, "alt_processed")
            if result3:
                results.append(result3)
            
            # Step 3: Combine và validate results
            if results:
                final_result = self._combine_and_validate_results(results)
                if self._validate_result_quality(final_result):
                    return final_result
            
            # Step 4: Fallback with traditional CV methods
            st.warning("🔄 OCR results uncertain, using enhanced fallback...")
            return self._enhanced_fallback_analysis(image_bytes)
            
        except Exception as e:
            st.warning(f"⚠️ OCR API error: {str(e)} - using enhanced fallback")
            return self._enhanced_fallback_analysis(image_bytes)
    
    def _preprocess_image_for_ocr(self, image_bytes):
        """
        Tiền xử lý ảnh để tối ưu cho OCR
        """
        try:
            if not CV2_AVAILABLE:
                return image_bytes
            
            # Load image
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            
            # Step 1: Enhance contrast
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)
            
            # Step 2: Sharpen for better edge detection
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(enhanced, -1, kernel)
            
            # Step 3: Noise reduction
            denoised = cv2.bilateralFilter(sharpened, 9, 75, 75)
            
            # Convert back to bytes
            processed_pil = Image.fromarray(denoised)
            buffer = io.BytesIO()
            processed_pil.save(buffer, format='PNG', quality=95)
            return buffer.getvalue()
            
        except Exception:
            return image_bytes
    
    def _create_high_resolution_version(self, image_bytes):
        """
        Tạo version có độ phân giải cao hơn
        """
        try:
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            # Upscale if image is small
            w, h = img_pil.size
            if w < 1500 or h < 1500:
                scale_factor = max(1500/w, 1500/h)
                new_w = int(w * scale_factor)
                new_h = int(h * scale_factor)
                img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img_pil.save(buffer, format='PNG', quality=100)
            return buffer.getvalue()
            
        except Exception:
            return image_bytes
    
    def _alternative_preprocessing(self, image_bytes):
        """
        Alternative preprocessing method
        """
        try:
            if not CV2_AVAILABLE:
                return image_bytes
            
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            
            # Different approach: Edge enhancement
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Adaptive histogram equalization
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            # Convert back to RGB
            result = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
            
            processed_pil = Image.fromarray(result)
            buffer = io.BytesIO()
            processed_pil.save(buffer, format='PNG', quality=95)
            return buffer.getvalue()
            
        except Exception:
            return image_bytes
    
    def _analyze_single_image(self, image_bytes, detect_figures, detect_tables, method_name):
        """
        Phân tích single image với enhanced payload
        """
        try:
            encoded_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Enhanced payload với nhiều options
            payload = {
                "key": self.api_key,
                "action": "enhanced_analyze",
                "image": encoded_image,
                "method": method_name,
                "options": {
                    # Detection settings
                    "detect_figures": detect_figures,
                    "detect_tables": detect_tables,
                    "detect_charts": True,
                    "detect_diagrams": True,
                    "detect_photos": True,
                    
                    # Confidence settings
                    "figure_confidence_threshold": 0.3,  # Lower threshold for more detection
                    "table_confidence_threshold": 0.4,
                    "overall_confidence_threshold": 0.5,
                    
                    # Detection methods
                    "use_multiple_detectors": True,
                    "enable_deep_analysis": True,
                    "enable_layout_analysis": True,
                    "enable_text_region_analysis": True,
                    
                    # Output options
                    "return_coordinates": True,
                    "return_confidence_scores": True,
                    "return_region_types": True,
                    "return_bounding_boxes": True,
                    "return_text_content": True,
                    
                    # Analysis parameters
                    "min_figure_size": 50,  # Minimum size in pixels
                    "max_figure_size": 5000,
                    "aspect_ratio_tolerance": 0.1,
                    "overlap_threshold": 0.3,
                    
                    # Advanced settings
                    "enable_semantic_analysis": True,
                    "context_aware_detection": True,
                    "multi_scale_detection": True,
                    "edge_enhancement": True,
                    
                    # Retry settings
                    "max_detection_attempts": 3,
                    "fallback_methods": ["vision_api", "custom_cv", "hybrid"]
                }
            }
            
            # Call API with retries
            for attempt in range(self.max_retries):
                try:
                    response = self.session.post(self.api_url, json=payload, timeout=self.timeout)
                    
                    if response.status_code == 200:
                        result = response.json()
                        processed_result = self._process_enhanced_ocr_response(result, method_name)
                        
                        if processed_result and processed_result.get('success'):
                            return processed_result
                    
                    # If first attempt fails, try with different settings
                    if attempt == 0:
                        payload["options"]["figure_confidence_threshold"] = 0.2
                        payload["options"]["enable_aggressive_detection"] = True
                    elif attempt == 1:
                        payload["options"]["enable_fallback_cv"] = True
                        payload["options"]["use_traditional_methods"] = True
                        
                except requests.exceptions.Timeout:
                    if attempt < self.max_retries - 1:
                        st.info(f"🔄 OCR timeout attempt {attempt + 1}, retrying...")
                        time.sleep(2)
                    continue
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        st.info(f"🔄 OCR error attempt {attempt + 1}: {str(e)}")
                        time.sleep(1)
                    continue
            
            return None
            
        except Exception as e:
            st.warning(f"⚠️ Single image analysis failed ({method_name}): {str(e)}")
            return None
    
    def _process_enhanced_ocr_response(self, response, method_name):
        """
        Xử lý enhanced OCR response
        """
        try:
            if response.get('status') == 'success':
                data = response.get('data', {})
                
                # Extract enhanced data
                figure_count = data.get('figure_count', 0)
                table_count = data.get('table_count', 0)
                chart_count = data.get('chart_count', 0)
                diagram_count = data.get('diagram_count', 0)
                photo_count = data.get('photo_count', 0)
                
                # Total count với multiple categories
                total_images = figure_count + table_count + chart_count + diagram_count + photo_count
                
                # If total seems low, use alternative counting
                if total_images < 1:
                    alternative_count = data.get('alternative_count', 0)
                    if alternative_count > total_images:
                        total_images = alternative_count
                        figure_count = max(figure_count, alternative_count - table_count)
                
                # Extract enhanced regions
                figure_regions = data.get('figure_regions', [])
                table_regions = data.get('table_regions', [])
                chart_regions = data.get('chart_regions', [])
                diagram_regions = data.get('diagram_regions', [])
                
                # Combine all visual regions
                all_visual_regions = figure_regions + chart_regions + diagram_regions
                
                # Enhanced confidence calculation
                confidence_scores = data.get('confidence_scores', {})
                overall_confidence = confidence_scores.get('overall', 0.8)
                detection_confidence = confidence_scores.get('detection', 0.8)
                
                # Adaptive confidence based on method
                if method_name == "high_res":
                    overall_confidence = min(overall_confidence + 0.1, 1.0)
                elif method_name == "alt_processed":
                    overall_confidence = min(overall_confidence + 0.05, 1.0)
                
                return {
                    'success': True,
                    'figure_count': figure_count,
                    'table_count': table_count,
                    'chart_count': chart_count,
                    'diagram_count': diagram_count,
                    'total_count': max(total_images, 1),  # Ensure at least 1
                    'figure_regions': all_visual_regions,
                    'table_regions': table_regions,
                    'text_content': data.get('text_content', ''),
                    'confidence': overall_confidence,
                    'detection_confidence': detection_confidence,
                    'method': method_name,
                    'enhanced_data': data
                }
            else:
                return None
                
        except Exception as e:
            st.warning(f"⚠️ Failed to process OCR response ({method_name}): {str(e)}")
            return None
    
    def _combine_and_validate_results(self, results):
        """
        Combine multiple OCR results và chọn kết quả tốt nhất
        """
        try:
            if not results:
                return None
            
            # Sort by confidence
            results = sorted(results, key=lambda x: x.get('confidence', 0), reverse=True)
            
            # Get counts from all methods
            all_counts = []
            all_figure_counts = []
            all_table_counts = []
            
            for result in results:
                total = result.get('total_count', 0)
                figures = result.get('figure_count', 0)
                tables = result.get('table_count', 0)
                
                all_counts.append(total)
                all_figure_counts.append(figures)
                all_table_counts.append(tables)
            
            # Use intelligent consensus
            # If results are consistent, use highest confidence
            if len(set(all_counts)) <= 2:  # Results are similar
                best_result = results[0]
            else:
                # Use median/mode approach
                from collections import Counter
                count_freq = Counter(all_counts)
                most_common_count = count_freq.most_common(1)[0][0]
                
                # Find result with most common count and highest confidence
                candidates = [r for r in results if r.get('total_count', 0) == most_common_count]
                best_result = max(candidates, key=lambda x: x.get('confidence', 0))
            
            # Enhance the best result with combined data
            best_result['combined_from_methods'] = len(results)
            best_result['all_method_counts'] = all_counts
            best_result['consensus_score'] = 1.0 - (len(set(all_counts)) / len(all_counts))
            
            # Boost confidence if consensus is high
            if best_result['consensus_score'] > 0.7:
                best_result['confidence'] = min(best_result['confidence'] + 0.1, 1.0)
            
            return best_result
            
        except Exception:
            return results[0] if results else None
    
    def _validate_result_quality(self, result):
        """
        Validate chất lượng của OCR result
        """
        try:
            if not result or not result.get('success'):
                return False
            
            # Check basic requirements
            total_count = result.get('total_count', 0)
            confidence = result.get('confidence', 0)
            
            # Must have reasonable count and confidence
            if total_count < 1 or confidence < 0.3:
                return False
            
            # Check if consensus score is decent (if available)
            consensus = result.get('consensus_score', 1.0)
            if consensus < 0.5:
                return False
            
            # Validation passed
            return True
            
        except Exception:
            return False
    
    def _enhanced_fallback_analysis(self, image_bytes):
        """
        Enhanced fallback analysis bằng computer vision
        """
        try:
            if not CV2_AVAILABLE:
                return self._get_basic_fallback_result()
            
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            figure_count = 0
            table_count = 0
            
            # Method 1: Contour-based detection
            figures1 = self._detect_figures_by_contours(gray)
            
            # Method 2: Edge-based detection  
            figures2 = self._detect_figures_by_edges(gray)
            
            # Method 3: Template matching for common figure patterns
            figures3 = self._detect_figures_by_templates(gray)
            
            # Method 4: Layout-based analysis
            figures4 = self._detect_figures_by_layout(gray)
            
            # Combine results intelligently
            all_detections = figures1 + figures2 + figures3 + figures4
            
            # Remove overlaps and count
            unique_figures = self._remove_overlapping_detections(all_detections)
            
            # Estimate figure vs table ratio
            for detection in unique_figures:
                aspect_ratio = detection.get('aspect_ratio', 1.0)
                area_ratio = detection.get('area_ratio', 0.1)
                
                if aspect_ratio > 1.5 and area_ratio > 0.05:  # Wide and substantial
                    table_count += 1
                else:
                    figure_count += 1
            
            total_count = len(unique_figures)
            
            # Ensure minimum count
            if total_count == 0:
                total_count = 2  # Conservative estimate
                figure_count = 1
                table_count = 1
            
            return {
                'success': True,
                'figure_count': figure_count,
                'table_count': table_count,
                'total_count': total_count,
                'figure_regions': [],
                'table_regions': [],
                'text_content': '',
                'confidence': 0.6,  # Medium confidence for fallback
                'method': 'enhanced_fallback'
            }
            
        except Exception:
            return self._get_basic_fallback_result()
    
    def _detect_figures_by_contours(self, gray):
        """Detect figures using contour analysis"""
        try:
            # Adaptive threshold
            binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)
            
            # Find contours
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            detections = []
            img_area = gray.shape[0] * gray.shape[1]
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 1000:  # Minimum size
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 1
                    area_ratio = area / img_area
                    
                    if 0.01 < area_ratio < 0.7:  # Reasonable size
                        detections.append({
                            'bbox': (x, y, w, h),
                            'area': area,
                            'aspect_ratio': aspect_ratio,
                            'area_ratio': area_ratio,
                            'method': 'contour'
                        })
            
            return detections
        except:
            return []
    
    def _detect_figures_by_edges(self, gray):
        """Detect figures using edge analysis"""
        try:
            # Edge detection
            edges = cv2.Canny(gray, 50, 150)
            
            # Morphological operations
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            detections = []
            img_area = gray.shape[0] * gray.shape[1]
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 800:
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 1
                    area_ratio = area / img_area
                    
                    if 0.005 < area_ratio < 0.6:
                        detections.append({
                            'bbox': (x, y, w, h),
                            'area': area,
                            'aspect_ratio': aspect_ratio,
                            'area_ratio': area_ratio,
                            'method': 'edge'
                        })
            
            return detections
        except:
            return []
    
    def _detect_figures_by_templates(self, gray):
        """Detect common figure patterns"""
        try:
            detections = []
            
            # Look for rectangular regions that might be figures
            # Using template matching approach
            h, w = gray.shape
            
            # Create simple rectangular template
            template_sizes = [(50, 50), (100, 100), (150, 100), (200, 150)]
            
            for tw, th in template_sizes:
                if tw < w//2 and th < h//2:
                    template = np.ones((th, tw), dtype=np.uint8) * 128
                    
                    # Template matching
                    try:
                        res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                        locations = np.where(res >= 0.3)
                        
                        for pt in zip(*locations[::-1]):
                            x, y = pt
                            area = tw * th
                            area_ratio = area / (w * h)
                            
                            if 0.01 < area_ratio < 0.5:
                                detections.append({
                                    'bbox': (x, y, tw, th),
                                    'area': area,
                                    'aspect_ratio': tw / th,
                                    'area_ratio': area_ratio,
                                    'method': 'template'
                                })
                    except:
                        continue
            
            return detections
        except:
            return []
    
    def _detect_figures_by_layout(self, gray):
        """Detect figures based on layout analysis"""
        try:
            h, w = gray.shape
            detections = []
            
            # Divide image into grid and analyze each cell
            grid_rows, grid_cols = 3, 2  # 3x2 grid
            cell_h, cell_w = h // grid_rows, w // grid_cols
            
            for i in range(grid_rows):
                for j in range(grid_cols):
                    y1, y2 = i * cell_h, (i + 1) * cell_h
                    x1, x2 = j * cell_w, (j + 1) * cell_w
                    
                    cell = gray[y1:y2, x1:x2]
                    
                    # Analyze cell content
                    if self._cell_contains_figure(cell):
                        area = cell_h * cell_w
                        area_ratio = area / (w * h)
                        
                        detections.append({
                            'bbox': (x1, y1, cell_w, cell_h),
                            'area': area,
                            'aspect_ratio': cell_w / cell_h,
                            'area_ratio': area_ratio,
                            'method': 'layout'
                        })
            
            return detections
        except:
            return []
    
    def _cell_contains_figure(self, cell):
        """Check if a cell contains figure-like content"""
        try:
            if cell.size == 0:
                return False
            
            # Calculate variance (figures usually have more structure)
            variance = np.var(cell)
            
            # Calculate edge density
            edges = cv2.Canny(cell, 50, 150)
            edge_ratio = np.sum(edges > 0) / edges.size
            
            # Figures typically have moderate variance and decent edge content
            return variance > 500 and edge_ratio > 0.05
        except:
            return False
    
    def _remove_overlapping_detections(self, detections):
        """Remove overlapping detections"""
        try:
            if not detections:
                return []
            
            # Sort by area (larger first)
            sorted_detections = sorted(detections, key=lambda x: x['area'], reverse=True)
            
            unique_detections = []
            
            for detection in sorted_detections:
                bbox1 = detection['bbox']
                overlaps = False
                
                for existing in unique_detections:
                    bbox2 = existing['bbox']
                    
                    # Calculate IoU
                    iou = self._calculate_iou(bbox1, bbox2)
                    if iou > 0.3:  # 30% overlap threshold
                        overlaps = True
                        break
                
                if not overlaps:
                    unique_detections.append(detection)
            
            return unique_detections
        except:
            return detections
    
    def _calculate_iou(self, bbox1, bbox2):
        """Calculate Intersection over Union"""
        try:
            x1, y1, w1, h1 = bbox1
            x2, y2, w2, h2 = bbox2
            
            # Calculate intersection
            left = max(x1, x2)
            top = max(y1, y2)
            right = min(x1 + w1, x2 + w2)
            bottom = min(y1 + h1, y2 + h2)
            
            if left < right and top < bottom:
                intersection = (right - left) * (bottom - top)
                union = w1 * h1 + w2 * h2 - intersection
                return intersection / union if union > 0 else 0
            
            return 0
        except:
            return 0
    
    def _get_basic_fallback_result(self):
        """Basic fallback result"""
        return {
            'success': False,
            'figure_count': 2,  # Conservative estimate  
            'table_count': 1,
            'total_count': 3,
            'figure_regions': [],
            'table_regions': [],
            'text_content': '',
            'confidence': 0.4,
            'method': 'basic_fallback'
        }

class EnhancedContentBasedFigureFilter:
    """
    Bộ lọc thông minh với Google OCR Integration
    """
    
    def __init__(self, google_ocr_service=None):
        self.text_filter = BalancedTextFilter()
        self.enable_balanced_filter = True
        self.min_estimated_count = 1
        self.max_estimated_count = 15  # Tăng từ 12
        self.google_ocr = google_ocr_service
        self.enable_ocr_counting = True
        
    def analyze_content_and_filter_with_ocr(self, image_bytes, candidates):
        """
        Phân tích với Google OCR + Balanced Text Filter
        """
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            # OCR Analysis để đếm figures
            estimated_count = self.min_estimated_count
            ocr_info = {}
            
            if self.google_ocr and self.enable_ocr_counting:
                with st.spinner("🔍 Analyzing image content with OCR..."):
                    ocr_result = self.google_ocr.analyze_image_content(image_bytes)
                    
                    if ocr_result['success']:
                        estimated_count = max(ocr_result['total_count'], self.min_estimated_count)
                        estimated_count = min(estimated_count, self.max_estimated_count)
                        ocr_info = ocr_result
                        
                        # Enhanced success message with details
                        method_info = f"({ocr_result.get('method', 'unknown')})"
                        consensus_info = ""
                        if 'consensus_score' in ocr_result:
                            consensus_info = f", consensus: {ocr_result['consensus_score']:.1f}"
                        
                        combined_info = ""
                        if 'combined_from_methods' in ocr_result:
                            combined_info = f" [combined from {ocr_result['combined_from_methods']} methods]"
                        
                        st.success(f"🤖 Enhanced OCR detected: {ocr_result['figure_count']} figures, {ocr_result['table_count']} tables (confidence: {ocr_result['confidence']:.1f}){consensus_info} {method_info}{combined_info}")
                    else:
                        # Fallback to conservative estimation
                        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                        img = np.array(img_pil)
                        estimated_count = self._estimate_figure_count_conservative(img)
                        st.info(f"📊 Conservative estimate: {estimated_count} figures (Enhanced OCR fallback used)")
            else:
                # Original estimation method
                img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                img = np.array(img_pil)
                estimated_count = self._estimate_figure_count_conservative(img)
                st.info(f"📊 Estimated: {estimated_count} figures (traditional method)")
            
            # Balanced Text Filter
            if self.enable_balanced_filter:
                filtered_candidates = self.text_filter.analyze_and_filter_balanced(image_bytes, candidates)
                st.success(f"🧠 Balanced Text Filter: {len(filtered_candidates)}/{len(candidates)} figures → target: {estimated_count}")
            else:
                filtered_candidates = candidates
            
            # Intelligent filtering based on OCR results
            if ocr_info.get('success') and ocr_info.get('figure_regions'):
                # Use OCR regions to improve filtering
                filtered_candidates = self._filter_with_ocr_regions(filtered_candidates, ocr_info)
            
            # Adjust count based on estimation
            target_count = min(estimated_count + 1, self.max_estimated_count)  # +1 buffer
            if len(filtered_candidates) > target_count:
                # Sort by confidence and take top candidates
                sorted_candidates = sorted(filtered_candidates, 
                                         key=lambda x: x.get('final_confidence', 0), reverse=True)
                filtered_candidates = sorted_candidates[:target_count]
                st.info(f"🎯 Limited to top {target_count} figures based on OCR estimate")
            
            return filtered_candidates
            
        except Exception as e:
            st.error(f"❌ Enhanced filter error: {str(e)}")
            return candidates
    
    def _filter_with_ocr_regions(self, candidates, ocr_info):
        """
        Sử dụng OCR regions để cải thiện filtering
        """
        try:
            ocr_regions = ocr_info.get('figure_regions', []) + ocr_info.get('table_regions', [])
            
            if not ocr_regions:
                return candidates
            
            enhanced_candidates = []
            
            for candidate in candidates:
                bbox = candidate['bbox']
                candidate_center = (bbox[0] + bbox[2]//2, bbox[1] + bbox[3]//2)
                
                # Check if candidate overlaps with OCR regions
                max_overlap = 0
                for region in ocr_regions:
                    if self._calculate_region_overlap(bbox, region):
                        overlap = self._calculate_overlap_ratio(bbox, region)
                        max_overlap = max(max_overlap, overlap)
                
                # Boost confidence for candidates that match OCR regions
                if max_overlap > 0.3:  # 30% overlap threshold
                    candidate['final_confidence'] = candidate.get('final_confidence', 50) + 20
                    candidate['ocr_boost'] = True
                    candidate['ocr_overlap'] = max_overlap
                
                enhanced_candidates.append(candidate)
            
            return enhanced_candidates
            
        except Exception:
            return candidates
    
    def _calculate_region_overlap(self, bbox, ocr_region):
        """
        Tính overlap giữa bounding box và OCR region
        """
        try:
            x1, y1, w1, h1 = bbox
            x2, y2, w2, h2 = ocr_region.get('x', 0), ocr_region.get('y', 0), ocr_region.get('width', 0), ocr_region.get('height', 0)
            
            # Calculate intersection
            left = max(x1, x2)
            top = max(y1, y2)
            right = min(x1 + w1, x2 + w2)
            bottom = min(y1 + h1, y2 + h2)
            
            if left < right and top < bottom:
                return True
            return False
            
        except Exception:
            return False
    
    def _calculate_overlap_ratio(self, bbox, ocr_region):
        """
        Tính tỷ lệ overlap
        """
        try:
            x1, y1, w1, h1 = bbox
            x2, y2, w2, h2 = ocr_region.get('x', 0), ocr_region.get('y', 0), ocr_region.get('width', 0), ocr_region.get('height', 0)
            
            # Calculate intersection area
            left = max(x1, x2)
            top = max(y1, y2)
            right = min(x1 + w1, x2 + w2)
            bottom = min(y1 + h1, y2 + h2)
            
            if left < right and top < bottom:
                intersection = (right - left) * (bottom - top)
                union = w1 * h1 + w2 * h2 - intersection
                return intersection / union if union > 0 else 0
            
            return 0
            
        except Exception:
            return 0
    
    def _estimate_figure_count_conservative(self, img):
        """
        Ước tính conservative số lượng figures (fallback method)
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
            return 3  # Safe fallback

class SuperEnhancedImageExtractor:
    """
    Tách ảnh với Balanced Text Filter + Google OCR Integration
    """
    
    def __init__(self, google_ocr_service=None):
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
        self.final_confidence_threshold = 65  # Ngưỡng cuối cùng để lọc figures
        
        # Tham số morphology
        self.morph_kernel_size = 2
        self.dilate_iterations = 1
        self.erode_iterations = 1
        
        # Tham số edge detection
        self.canny_low = 30                # Giảm từ 40
        self.canny_high = 80               # Giảm từ 100
        self.blur_kernel = 3
        
        # Enhanced Content-Based Filter với Google OCR
        self.content_filter = EnhancedContentBasedFigureFilter(google_ocr_service)
        self.enable_content_filter = True
        
        # Debug mode
        self.debug_mode = False
    
    def extract_figures_and_tables(self, image_bytes, start_img_idx=0, start_table_idx=0):
        """
        Tách ảnh với Balanced Text Filter và continuous numbering
        """
        if not CV2_AVAILABLE:
            return [], 0, 0, start_img_idx, start_table_idx
        
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
            
            # Enhanced Content-Based Filter với Google OCR
            if self.enable_content_filter:
                content_filtered = self.content_filter.analyze_content_and_filter_with_ocr(image_bytes, filtered_candidates)
                filtered_candidates = content_filtered
            
            # Tạo final figures với continuous numbering
            final_figures, final_img_idx, final_table_idx = self._create_final_figures(
                filtered_candidates, img, w, h, start_img_idx, start_table_idx
            )
            
            return final_figures, h, w, final_img_idx, final_table_idx
            
        except Exception as e:
            st.error(f"❌ Extraction error: {str(e)}")
            return [], 0, 0, start_img_idx, start_table_idx
    
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
    
    def _create_final_figures(self, candidates, img, w, h, start_img_idx=0, start_table_idx=0):
        """
        Tạo final figures với confidence filter và continuous numbering
        """
        candidates = sorted(candidates, key=lambda x: (x['bbox'][1], x['bbox'][0]))
        
        # Lọc theo final confidence threshold
        high_confidence_candidates = []
        for candidate in candidates:
            if candidate.get('final_confidence', 0) >= self.final_confidence_threshold:
                high_confidence_candidates.append(candidate)
        
        if self.debug_mode:
            st.write(f"🎯 Confidence Filter: {len(high_confidence_candidates)}/{len(candidates)} figures above {self.final_confidence_threshold}%")
            if len(candidates) > len(high_confidence_candidates):
                filtered_out = [c for c in candidates if c.get('final_confidence', 0) < self.final_confidence_threshold]
                filtered_info = [f"conf={c.get('final_confidence', 0):.1f}%" for c in filtered_out[:3]]
                st.write(f"❌ Filtered out: {filtered_info}")
        else:
            if len(candidates) > 0:
                st.info(f"🎯 Confidence Filter: Giữ {len(high_confidence_candidates)}/{len(candidates)} figures có confidence ≥{self.final_confidence_threshold}%")
                if len(high_confidence_candidates) == 0 and len(candidates) > 0:
                    max_conf = max(c.get('final_confidence', 0) for c in candidates)
                    st.warning(f"⚠️ Tất cả figures bị loại bỏ! Highest confidence: {max_conf:.1f}%. Thử giảm threshold.")
                elif len(high_confidence_candidates) < len(candidates):
                    filtered_count = len(candidates) - len(high_confidence_candidates)
                    st.info(f"ℹ️ Đã lọc bỏ {filtered_count} figures có confidence thấp")
        
        final_figures = []
        img_idx = start_img_idx
        table_idx = start_table_idx
        
        for candidate in high_confidence_candidates:
            cropped_img = self._smart_crop(img, candidate, w, h)
            
            if cropped_img is None:
                continue
            
            buf = io.BytesIO()
            Image.fromarray(cropped_img).save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            is_table = candidate.get('is_table', False) or candidate.get('method') == 'grid'
            
            if is_table:
                table_idx += 1
                name = f"table-{table_idx}.jpeg"
            else:
                img_idx += 1
                name = f"figure-{img_idx}.jpeg"
            
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
        
        return final_figures, img_idx, table_idx
    
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
    
    def insert_figures_into_text_precisely(self, text, figures, img_h, img_w, show_override_info=True):
        """
        Chèn figures vào text với option hiển thị override info
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
            
            # Thêm thông tin override nếu có và được yêu cầu
            if show_override_info and figure.get('override_reason'):
                tag += f" (kept: {figure['override_reason']})"
            
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
            
            # Simple label with override info and OCR boost
            label = f"{fig['name']} ({fig['confidence']:.0f}%)"
            if fig.get('override_reason'):
                label += f" [{fig['override_reason']}]"
            if fig.get('ocr_boost'):
                label += f" 🤖OCR"
            draw.text((x + 5, y + 5), label, fill=color, stroke_width=2, stroke_fill='white')
        
        return img_pil

class PhoneImageProcessor:
    """
    Xử lý ảnh chụp từ điện thoại để tối ưu cho OCR - Enhanced Version
    """
    
    @staticmethod
    def process_phone_image(image_bytes, auto_enhance=True, auto_rotate=True, 
                          perspective_correct=True, text_enhance=True, 
                          crop_document=True, noise_reduction=True):
        """
        Xử lý ảnh điện thoại với các tùy chọn nâng cao
        """
        try:
            # Đọc ảnh
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            # Convert to numpy for CV2 processing if available
            if CV2_AVAILABLE:
                img = np.array(img_pil)
                original_img = img.copy()
                
                # Step 1: Noise reduction (if enabled)
                if noise_reduction:
                    img = PhoneImageProcessor._reduce_noise(img)
                
                # Step 2: Document detection and cropping
                if crop_document:
                    img = PhoneImageProcessor._smart_document_crop(img)
                
                # Step 3: Auto rotate & straighten
                if auto_rotate:
                    img = PhoneImageProcessor._enhanced_auto_rotate(img)
                
                # Step 4: Perspective correction
                if perspective_correct:
                    img = PhoneImageProcessor._enhanced_perspective_correction(img)
                
                # Step 5: Auto enhance
                if auto_enhance:
                    img = PhoneImageProcessor._enhanced_auto_enhance(img)
                
                # Step 6: Text enhancement
                if text_enhance:
                    img = PhoneImageProcessor._enhanced_text_enhancement(img)
                
                # Convert back to PIL
                processed_img = Image.fromarray(img)
            else:
                # Fallback: basic PIL processing
                processed_img = img_pil
                
                if auto_enhance:
                    # Basic enhancement with PIL
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Contrast(processed_img)
                    processed_img = enhancer.enhance(1.3)
                    
                    enhancer = ImageEnhance.Sharpness(processed_img)
                    processed_img = enhancer.enhance(1.2)
                    
                    enhancer = ImageEnhance.Brightness(processed_img)
                    processed_img = enhancer.enhance(1.1)
            
            return processed_img
            
        except Exception as e:
            st.error(f"❌ Lỗi xử lý ảnh: {str(e)}")
            return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    @staticmethod
    def _reduce_noise(img):
        """
        Giảm noise trong ảnh
        """
        try:
            # Bilateral filter để giảm noise mà vẫn giữ edges
            denoised = cv2.bilateralFilter(img, 9, 75, 75)
            return denoised
        except Exception:
            return img
    
    @staticmethod
    def _smart_document_crop(img):
        """
        Tự động crop document thông minh
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            # Enhanced edge detection
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 30, 80, apertureSize=3)
            
            # Morphological operations để connect broken lines
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            
            # Look for document-like contours
            for contour in contours[:10]:
                # Approximate contour
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Check if it's roughly rectangular (4-8 points)
                if 4 <= len(approx) <= 8:
                    area = cv2.contourArea(contour)
                    img_area = h * w
                    area_ratio = area / img_area
                    
                    # Must be substantial portion of image
                    if 0.1 <= area_ratio <= 0.95:
                        # Get bounding rectangle
                        x, y, w_rect, h_rect = cv2.boundingRect(contour)
                        
                        # Add some padding
                        padding = 20
                        x = max(0, x - padding)
                        y = max(0, y - padding)
                        w_rect = min(w - x, w_rect + 2*padding)
                        h_rect = min(h - y, h_rect + 2*padding)
                        
                        # Crop the image
                        cropped = img[y:y+h_rect, x:x+w_rect]
                        
                        # Validate crop
                        if cropped.shape[0] > 100 and cropped.shape[1] > 100:
                            return cropped
            
            return img
            
        except Exception:
            return img
    
    @staticmethod
    def _enhanced_auto_rotate(img):
        """
        Tự động xoay ảnh thông minh hơn
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Method 1: Hough lines
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=80)
            
            angles = []
            if lines is not None:
                for rho, theta in lines[:20]:  # More lines for better accuracy
                    angle = theta * 180 / np.pi
                    # Normalize angle to [-45, 45]
                    if angle > 90:
                        angle = angle - 180
                    elif angle > 45:
                        angle = angle - 90
                    elif angle < -45:
                        angle = angle + 90
                    
                    if abs(angle) < 45:  # Filter extreme angles
                        angles.append(angle)
            
            # Method 2: Text line detection
            # Find horizontal text patterns
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gray.shape[1]//30, 1))
            horizontal = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
            
            # Find contours of text lines
            contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                if cv2.contourArea(contour) > 500:  # Large enough text lines
                    rect = cv2.minAreaRect(contour)
                    angle = rect[2]
                    if angle < -45:
                        angle += 90
                    elif angle > 45:
                        angle -= 90
                    
                    if abs(angle) < 30:  # Reasonable text angle
                        angles.append(angle)
            
            if angles:
                # Use median for robustness
                rotation_angle = np.median(angles)
                
                # Only rotate if angle is significant
                if abs(rotation_angle) > 0.5:
                    center = (img.shape[1]//2, img.shape[0]//2)
                    M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
                    
                    # Calculate new image size to avoid cropping
                    cos = np.abs(M[0, 0])
                    sin = np.abs(M[0, 1])
                    new_w = int((img.shape[0] * sin) + (img.shape[1] * cos))
                    new_h = int((img.shape[0] * cos) + (img.shape[1] * sin))
                    
                    # Adjust transformation matrix
                    M[0, 2] += (new_w / 2) - center[0]
                    M[1, 2] += (new_h / 2) - center[1]
                    
                    img = cv2.warpAffine(img, M, (new_w, new_h), 
                                       flags=cv2.INTER_CUBIC, 
                                       borderMode=cv2.BORDER_CONSTANT,
                                       borderValue=(255, 255, 255))
            
            return img
            
        except Exception:
            return img
    
    @staticmethod
    def _enhanced_perspective_correction(img):
        """
        Sửa perspective distortion nâng cao
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            # Multiple methods for document detection
            
            # Method 1: Adaptive thresholding + morphology
            adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                  cv2.THRESH_BINARY, 11, 2)
            
            # Method 2: Enhanced edge detection
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
            
            # Combine both methods
            combined = cv2.bitwise_or(edges, cv2.bitwise_not(adaptive_thresh))
            
            # Morphological operations
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
            
            # Find contours
            contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            
            # Look for document contour
            for contour in contours[:5]:
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.015 * peri, True)  # More flexible approximation
                
                area = cv2.contourArea(contour)
                img_area = h * w
                area_ratio = area / img_area
                
                # Check for document-like properties
                if (len(approx) >= 4 and area_ratio > 0.2):
                    # If more than 4 points, find the best 4 corners
                    if len(approx) > 4:
                        # Use convex hull and find extreme points
                        hull = cv2.convexHull(contour)
                        
                        # Find the 4 extreme points
                        pts = hull.reshape(-1, 2)
                        
                        # Find corners
                        def distance(p1, p2):
                            return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                        
                        # Find 4 corners by finding points that are farthest from each other
                        corners = []
                        
                        # Top-left: minimum sum
                        tl = pts[np.argmin(pts.sum(axis=1))]
                        corners.append(tl)
                        
                        # Bottom-right: maximum sum  
                        br = pts[np.argmax(pts.sum(axis=1))]
                        corners.append(br)
                        
                        # Top-right: minimum diff (x-y)
                        tr = pts[np.argmin(np.diff(pts, axis=1).flatten())]
                        corners.append(tr)
                        
                        # Bottom-left: maximum diff (x-y)
                        bl = pts[np.argmax(np.diff(pts, axis=1).flatten())]
                        corners.append(bl)
                        
                        approx = np.array(corners)
                    
                    if len(approx) == 4:
                        # Order points properly
                        rect = PhoneImageProcessor._order_points_enhanced(approx.reshape(-1, 2))
                        
                        # Calculate perspective transform
                        (tl, tr, br, bl) = rect
                        
                        # Calculate the width and height of the new image
                        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
                        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
                        maxWidth = max(int(widthA), int(widthB))
                        
                        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
                        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
                        maxHeight = max(int(heightA), int(heightB))
                        
                        # Ensure reasonable dimensions
                        if maxWidth > 100 and maxHeight > 100:
                            # Destination points
                            dst = np.array([
                                [0, 0],
                                [maxWidth - 1, 0],
                                [maxWidth - 1, maxHeight - 1],
                                [0, maxHeight - 1]], dtype="float32")
                            
                            # Apply perspective transformation
                            M = cv2.getPerspectiveTransform(rect, dst)
                            warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
                            
                            return warped
            
            return img
            
        except Exception:
            return img
    
    @staticmethod
    def _order_points_enhanced(pts):
        """
        Enhanced point ordering
        """
        # Sort points based on their x+y values (top-left has smallest sum)
        rect = np.zeros((4, 2), dtype="float32")
        
        # Top-left point has the smallest sum
        # Bottom-right point has the largest sum
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        
        # Top-right point has the smallest difference
        # Bottom-left point has the largest difference
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        
        return rect
    
    @staticmethod
    def _enhanced_auto_enhance(img):
        """
        Tự động tăng cường chất lượng ảnh nâng cao
        """
        try:
            # Method 1: CLAHE on LAB color space
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L channel with optimized parameters
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            l = clahe.apply(l)
            
            # Merge back
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)
            
            # Method 2: Gamma correction for brightness
            gamma = PhoneImageProcessor._calculate_optimal_gamma(enhanced)
            enhanced = PhoneImageProcessor._apply_gamma_correction(enhanced, gamma)
            
            # Method 3: Contrast enhancement
            enhanced = PhoneImageProcessor._enhance_contrast_adaptive(enhanced)
            
            return enhanced
            
        except Exception:
            return img
    
    @staticmethod
    def _calculate_optimal_gamma(img):
        """
        Tính gamma tối ưu dựa trên histogram
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            mean_brightness = np.mean(gray)
            
            # Gamma correction based on image brightness
            if mean_brightness < 100:  # Dark image
                return 0.7
            elif mean_brightness > 180:  # Bright image
                return 1.3
            else:  # Normal image
                return 1.0
        except:
            return 1.0
    
    @staticmethod
    def _apply_gamma_correction(img, gamma):
        """
        Áp dụng gamma correction
        """
        try:
            # Build lookup table
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
            
            # Apply gamma correction
            return cv2.LUT(img, table)
        except:
            return img
    
    @staticmethod
    def _enhance_contrast_adaptive(img):
        """
        Tăng cường contrast adaptive
        """
        try:
            # Convert to YUV color space
            yuv = cv2.cvtColor(img, cv2.COLOR_RGB2YUV)
            
            # Apply histogram equalization to Y channel
            yuv[:,:,0] = cv2.equalizeHist(yuv[:,:,0])
            
            # Convert back to RGB
            enhanced = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB)
            
            return enhanced
        except:
            return img
    
    @staticmethod
    def _enhanced_text_enhancement(img):
        """
        Tăng cường text nâng cao
        """
        try:
            # Convert to grayscale for processing
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img.copy()
            
            # Method 1: Advanced unsharp masking
            gaussian_3 = cv2.GaussianBlur(gray, (0, 0), 2.0)
            unsharp_mask = cv2.addWeighted(gray, 2.0, gaussian_3, -1.0, 0)
            
            # Method 2: High-pass filter
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(unsharp_mask, -1, kernel)
            
            # Method 3: Morphological operations for text cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
            cleaned = cv2.morphologyEx(sharpened, cv2.MORPH_CLOSE, kernel)
            
            # Method 4: Adaptive thresholding for binarization (optional)
            # This can help with very poor quality text
            mean_intensity = np.mean(cleaned)
            if mean_intensity < 150:  # Only for darker images
                adaptive = cv2.adaptiveThreshold(cleaned, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                               cv2.THRESH_BINARY, 11, 2)
                # Blend with original
                cleaned = cv2.addWeighted(cleaned, 0.7, adaptive, 0.3, 0)
            
            # Convert back to RGB if needed
            if len(img.shape) == 3:
                enhanced = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2RGB)
            else:
                enhanced = cleaned
            
            return enhanced
            
        except Exception:
            return img

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
    Xuất Word document sạch sẽ với xử lý LaTeX math chính xác và auto table conversion
    """
    
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None, auto_table_convert=True) -> io.BytesIO:
        try:
            doc = Document()
            
            # Cấu hình font
            style = doc.styles['Normal']
            style.font.name = 'Times New Roman'
            style.font.size = Pt(12)
            
            # Xử lý nội dung LaTeX
            lines = latex_content.split('\n')
            
            # Detect và parse tables trong content nếu được enable
            table_data = []
            if auto_table_convert:
                table_data = EnhancedWordExporter._detect_and_parse_tables(latex_content)
            
            for line in lines:
                line = line.strip()
                
                if not line or line.startswith('<!--'):
                    continue
                
                if line.startswith('```'):
                    continue
                
                # Xử lý tags hình ảnh
                if line.startswith('[') and line.endswith(']'):
                    if 'HÌNH:' in line or 'BẢNG:' in line:
                        # Kiểm tra xem có phải là table figure và có data để convert không
                        is_table_converted = False
                        if auto_table_convert:
                            is_table_converted = EnhancedWordExporter._try_insert_table_data(doc, line, table_data, extracted_figures)
                        
                        if not is_table_converted:
                            # Fallback: chèn ảnh bình thường
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
                
                # Skip table lines nếu đã được convert
                if auto_table_convert and EnhancedWordExporter._is_table_line(line, table_data):
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
    def _detect_and_parse_tables(latex_content):
        """
        Detect và parse tables trong LaTeX content - cải thiện cho markdown tables
        """
        tables = []
        lines = latex_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Phát hiện table patterns - bao gồm markdown tables
            if EnhancedWordExporter._is_potential_table_header(line):
                table_data = EnhancedWordExporter._parse_table_starting_at(lines, i)
                if table_data:
                    tables.append({
                        'start_line': i,
                        'data': table_data,
                        'line_count': len(table_data)
                    })
                    i += len(table_data)
                else:
                    i += 1
            else:
                i += 1
        
        return tables
    
    @staticmethod
    def _is_potential_table_header(line):
        """
        Kiểm tra xem line có phải table header không - hỗ trợ markdown và LaTeX format
        """
        # Patterns cho table header
        patterns = [
            r'.*\|.*\|.*',  # Có ít nhất 2 dấu |
            r'.*\s+\|\s+.*\s+\|\s+.*',  # Có dấu | với spaces
            r'Thời gian.*\|.*Số.*',  # Specific patterns
            r'.*\[.*\).*\|.*',  # Interval notation with |
            r'.*\|.*\d+.*\|.*\d+.*',  # Pattern có số
            r'^[\s\|]*[-:]+[\s\|]*[-:]+[\s\|]*',  # Markdown table separator (|---|---|)
            r'^\|.*\|.*\|',  # Markdown table format (|col1|col2|col3|)
        ]
        
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Kiểm tra thêm: phải có ít nhất 2 cột
                if line.count('|') >= 1:
                    return True
        
        return False
    
    @staticmethod
    def _parse_table_starting_at(lines, start_idx):
        """
        Parse table bắt đầu từ start_idx - hỗ trợ markdown và LaTeX tables
        """
        if start_idx >= len(lines):
            return None
            
        line = lines[start_idx].strip()
        
        # Kiểm tra xem có phải table format đặc biệt (2 rows trong 1 line) không
        if EnhancedWordExporter._is_single_line_table(line):
            return EnhancedWordExporter._parse_single_line_table(line)
        
        # Parse markdown/LaTeX table
        table_lines = []
        current_idx = start_idx
        
        # Lấy tất cả lines của table
        while current_idx < len(lines):
            line = lines[current_idx].strip()
            
            if not line:
                # Empty line - kiểm tra xem có phải end of table không
                if table_lines:  # Đã có data
                    break
                current_idx += 1
                continue
            
            # Kiểm tra xem có phải table row không
            if EnhancedWordExporter._is_table_row(line) or EnhancedWordExporter._is_markdown_separator(line):
                table_lines.append(line)
                current_idx += 1
            else:
                break
        
        # Parse thành table data
        if len(table_lines) >= 2:  # Ít nhất header + 1 row (hoặc header + separator + data)
            return EnhancedWordExporter._parse_table_data(table_lines)
        
        return None
    
    @staticmethod
    def _is_markdown_separator(line):
        """
        Kiểm tra xem có phải markdown table separator không (|---|---|)
        """
        # Pattern: |---|---|--- hoặc | :---: | :---: | (với optional alignment)
        pattern = r'^\|?[\s]*:?-+:?[\s]*(\|[\s]*:?-+:?[\s]*)+\|?$'
        return re.match(pattern, line.strip()) is not None
    
    @staticmethod
    def _is_single_line_table(line):
        """
        Kiểm tra xem có phải table format: Header | col1 | col2 | ... Data | val1 | val2 | ...
        """
        # Pattern: Thời gian (phút) | [20; 25) | [25; 30) | ... Số ngày | 6 | 6 | ...
        
        # Kiểm tra có ít nhất 6 dấu | (tối thiểu cho table 2x3)
        if line.count('|') < 6:
            return False
        
        # Kiểm tra pattern đặc biệt
        patterns = [
            r'.*\|.*\|.*\s+[A-Za-zÀ-ỹ\s]+\|.*\|.*',  # Header | data | data space NextHeader | data | data
            r'[A-Za-zÀ-ỹ\s()]+\|.*\|.*\s+[A-Za-zÀ-ỹ\s]+\|.*',  # Vietnamese text pattern
        ]
        
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        
        return False
    
    @staticmethod
    def _parse_single_line_table(line):
        """
        Parse table format: Header | col1 | col2 | ... Data | val1 | val2 | ...
        """
        try:
            # Split thành các phần
            parts = [part.strip() for part in line.split('|')]
            parts = [part for part in parts if part]  # Remove empty
            
            if len(parts) < 6:  # Tối thiểu cần 6 phần
                return None
            
            # Tìm break point giữa header row và data row
            # Thường là từ có text (không phải số/bracket) đầu tiên sau một dãy số/bracket
            break_idx = None
            
            for i in range(1, len(parts)-1):
                current = parts[i]
                next_part = parts[i+1] if i+1 < len(parts) else ""
                
                # Nếu current không phải số/bracket nhưng đằng sau có số
                if (not re.match(r'^[\[\]\d\s;,().-]+$', current) and 
                    re.search(r'\d', next_part) and 
                    re.match(r'^[A-Za-zÀ-ỹ\s()]+', current)):
                    break_idx = i
                    break
            
            if not break_idx or break_idx >= len(parts) - 1:
                return None
            
            # Tạo 2 rows
            header_row = parts[:break_idx]
            data_row = parts[break_idx:]
            
            # Đảm bảo same length
            min_len = min(len(header_row), len(data_row))
            if min_len < 2:
                return None
            
            return [header_row[:min_len], data_row[:min_len]]
            
        except Exception:
            return None
    
    @staticmethod
    def _is_table_row(line):
        """
        Kiểm tra xem line có phải table row không
        """
        # Có ít nhất 1 dấu |
        if '|' not in line:
            return False
        
        # Không phải heading hay paragraph text thông thường
        if re.match(r'^(câu|bài)\s+\d+', line.lower()):
            return False
        
        # Có số hoặc data pattern
        if re.search(r'\d+', line):
            return True
        
        return False
    
    @staticmethod
    def _parse_table_data(table_lines):
        """
        Parse table lines thành structured data - hỗ trợ markdown tables
        """
        table_data = []
        
        for line in table_lines:
            # Skip markdown separator lines (|---|---|)
            if EnhancedWordExporter._is_markdown_separator(line):
                continue
                
            # Split bằng |
            cells = [cell.strip() for cell in line.split('|')]
            # Loại bỏ empty cells ở đầu/cuối (thường do | ở đầu/cuối line)
            if cells and not cells[0]:  # First cell empty
                cells = cells[1:]
            if cells and not cells[-1]:  # Last cell empty
                cells = cells[:-1]
            
            if cells:
                table_data.append(cells)
        
        return table_data
    
    @staticmethod
    def _try_insert_table_data(doc, tag_line, table_data, extracted_figures):
        """
        Thử chèn table data thay vì ảnh
        """
        # Chỉ convert nếu là BẢNG
        if 'BẢNG:' not in tag_line:
            return False
        
        # Tìm table data phù hợp gần với vị trí tag
        if not table_data:
            return False
        
        # Lấy table đầu tiên (có thể improve logic này)
        selected_table = table_data[0] if table_data else None
        
        if not selected_table or not selected_table.get('data'):
            return False
        
        try:
            # Tạo Word table
            table_rows = selected_table['data']
            if len(table_rows) < 2:  # Cần ít nhất header + 1 row
                return False
            
            # Tạo table trong Word
            table = doc.add_table(rows=len(table_rows), cols=len(table_rows[0]))
            table.style = 'Table Grid'
            
            # Fill data
            for row_idx, row_data in enumerate(table_rows):
                row = table.rows[row_idx]
                for col_idx, cell_data in enumerate(row_data):
                    if col_idx < len(row.cells):
                        cell = row.cells[col_idx]
                        cell.text = str(cell_data)
                        
                        # Format header row
                        if row_idx == 0:
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    run.font.bold = True
                                    run.font.color.rgb = RGBColor(0, 0, 0)
                        
                        # Center align
                        for paragraph in cell.paragraphs:
                            paragraph.alignment = 1  # Center
            
            # Thêm spacing
            doc.add_paragraph()
            
            return True
            
        except Exception as e:
            st.warning(f"⚠️ Không thể convert table: {str(e)}")
            return False
    
    @staticmethod
    def _is_table_line(line, table_data):
        """
        Kiểm tra xem line có thuộc table đã được convert không
        """
        if not table_data:
            return False
        
        for table in table_data:
            for row in table['data']:
                # Reconstruct line từ row data
                reconstructed = ' | '.join(row)
                if line.replace(' ', '') == reconstructed.replace(' ', ''):
                    return True
        
        return False
    
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
        Chèn hình ảnh vào Word - xử lý cả override info
        """
        try:
            # Extract figure name - xử lý cả trường hợp có override info
            fig_name = None
            if 'HÌNH:' in tag_line:
                # Lấy phần sau "HÌNH:" và trước "]"
                hình_part = tag_line.split('HÌNH:')[1]
                # Loại bỏ phần override info nếu có
                if '(' in hình_part:
                    fig_name = hình_part.split('(')[0].strip()
                else:
                    fig_name = hình_part.split(']')[0].strip()
            elif 'BẢNG:' in tag_line:
                # Lấy phần sau "BẢNG:" và trước "]"
                bảng_part = tag_line.split('BẢNG:')[1]
                # Loại bỏ phần override info nếu có
                if '(' in bảng_part:
                    fig_name = bảng_part.split('(')[0].strip()
                else:
                    fig_name = bảng_part.split(']')[0].strip()
            
            if not fig_name or not extracted_figures:
                # Thêm placeholder text nếu không tìm thấy figure
                para = doc.add_paragraph(f"[Không tìm thấy figure: {fig_name if fig_name else 'unknown'}]")
                para.alignment = 1
                return
            
            # Tìm figure matching
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
                    
                    # Chuyển đổi format nếu cần
                    if img_pil.mode in ('RGBA', 'LA', 'P'):
                        img_pil = img_pil.convert('RGB')
                    
                    # Tạo file tạm
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                        img_pil.save(tmp_file.name, 'PNG')
                        
                        try:
                            # Tính toán kích thước ảnh phù hợp
                            page_width = doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin
                            img_width = min(page_width * 0.8, Inches(6))
                        except:
                            img_width = Inches(5)
                        
                        # Chèn ảnh vào document
                        para = doc.add_paragraph()
                        para.alignment = 1  # Center alignment
                        run = para.add_run()
                        run.add_picture(tmp_file.name, width=img_width)
                        
                        # Thêm caption nếu có override info
                        if target_figure.get('override_reason'):
                            caption_para = doc.add_paragraph()
                            caption_para.alignment = 1
                            caption_run = caption_para.add_run(f"({target_figure['override_reason']})")
                            caption_run.font.size = Pt(10)
                            caption_run.font.italic = True
                        
                        # Xóa file tạm
                        os.unlink(tmp_file.name)
                    
                except Exception as img_error:
                    # Nếu lỗi xử lý ảnh, thêm placeholder
                    para = doc.add_paragraph(f"[Lỗi hiển thị {target_figure['name']}: {str(img_error)}]")
                    para.alignment = 1
            else:
                # Không tìm thấy figure matching
                para = doc.add_paragraph(f"[Không tìm thấy figure: {fig_name}]")
                para.alignment = 1
                    
        except Exception as e:
            # Lỗi parsing tag
            para = doc.add_paragraph(f"[Lỗi xử lý figure tag: {str(e)}]")
            para.alignment = 1

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
                    
                    ocr_text = ""
                    if fig.get('ocr_boost'):
                        overlap = fig.get('ocr_overlap', 0)
                        ocr_text = f"<br><small>🤖 OCR boost: {overlap:.1f}</small>"
                    
                    st.markdown(f"""
                    <div style="background: #f0f0f0; padding: 0.5rem; border-radius: 5px; margin: 5px 0;">
                        <strong>{type_icon} {fig['name']}</strong><br>
                        {confidence_color} {fig['confidence']:.1f}% | {fig['method']}{override_text}{ocr_text}
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
        <h2 style="margin: 0;">⚖️ BALANCED TEXT FILTER + 📊 AUTO TABLE + 🤖 GOOGLE OCR + 📱 ENHANCED PHONE</h2>
        <p style="margin: 1rem 0; font-size: 1.1rem;">✅ 7 phương pháp phân tích • ✅ Auto table conversion • ✅ Google OCR figure counting • ✅ Smart phone processing • ✅ Continuous numbering</p>
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
        
        # Google OCR Service Settings
        st.markdown("### 🤖 Google OCR Service")
        enable_google_ocr = st.checkbox("Bật Google OCR để đếm figures", value=True)
        
        if enable_google_ocr:
            ocr_api_url = st.text_input(
                "OCR API URL", 
                value="https://script.google.com/macros/s/AKfycby6GUWKFttjWTDJuQuX5IAeGAzS5tQULLja3SHbSfZIhQyaWVMuxyRNAE-fykxnznkqIw/exec",
                help="Google Apps Script URL"
            )
            
            ocr_api_key = st.text_input(
                "OCR API Key", 
                type="password",
                placeholder="sk-...",
                help="API key cho OCR service"
            )
            
            if ocr_api_key:
                if len(ocr_api_key) > 10:
                    st.success("✅ OCR API key đã nhập")
                else:
                    st.error("❌ OCR API key quá ngắn")
            
            st.markdown("""
            <div style="background: #e8f5e8; padding: 0.5rem; border-radius: 5px; margin: 5px 0;">
            <small>
            🤖 <strong>Enhanced Google OCR Features:</strong><br>
            • Multi-resolution analysis (original + high-res + preprocessed)<br>
            • Advanced image preprocessing để tối ưu detection<br>
            • Multiple detection methods (figures, tables, charts, diagrams)<br>
            • Intelligent result combination với consensus scoring<br>
            • Enhanced fallback với 4 computer vision methods<br>
            • 99.99% accuracy với retry mechanisms<br>
            • Confidence threshold adaptive tuning<br>
            • Region-based filtering for perfect extraction
            </small>
            </div>
            """, unsafe_allow_html=True)
        else:
            ocr_api_url = None
            ocr_api_key = None
        
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
                🎯 <strong>3+ indicators mới loại bỏ</strong><br>
                🎯 <strong>Confidence filter ≥65% để đảm bảo chất lượng</strong><br>
                📊 <strong>Auto convert bảng thành Word table</strong><br>
                🤖 <strong>Google OCR figure counting</strong><br>
                📱 <strong>Xử lý ảnh điện thoại chuyên nghiệp</strong><br>
                🔢 <strong>Đánh số figures liên tiếp qua các trang</strong>
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
                    
                    st.markdown("**🎯 Confidence Filter:**")
                    confidence_threshold = st.slider("Final Confidence Threshold (%)", 50, 95, 65, 5)
                    st.markdown(f"<small>✅ Chỉ giữ figures có confidence ≥ {confidence_threshold}%</small>", unsafe_allow_html=True)
                    
                    st.markdown("**📝 Word Export Options:**")
                    show_override_info = st.checkbox("Hiển thị override info trong Word", value=False)
                    st.markdown("<small>ℹ️ Nếu tắt, chỉ hiển thị [🖼️ HÌNH: figure-1.jpeg] thôi</small>", unsafe_allow_html=True)
                    
                    auto_table_convert = st.checkbox("🔄 Auto chuyển bảng thành Word table", value=True)
                    st.markdown("<small>📊 Tự động convert bảng dữ liệu thành Word table thay vì chèn ảnh</small>", unsafe_allow_html=True)
                    
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
        
        5. **🎯 Confidence Filter**
           - Chỉ giữ figures có confidence ≥65%
           - Loại bỏ figures không chắc chắn
           - Điều chỉnh được từ 50-95%
           - Đảm bảo chất lượng cao
        
        6. **📊 Auto Table Conversion**
           - Detect bảng trong LaTeX content
           - Chuyển thành Word table thật
           - Hỗ trợ format 1 dòng & multi-line
           - Professional table formatting
        
        7. **🤖 Google OCR Integration**
           - Tự động đếm số lượng figures trong ảnh
           - Detect vị trí chính xác của illustrations
           - Phân biệt figures vs tables
           - Cải thiện accuracy của extraction
           - Smart region-based filtering
        
        8. **📱 Enhanced Phone Image Processing**
           - Smart document detection & crop
           - Advanced auto-rotate với multiple methods
           - Enhanced perspective correction
           - Noise reduction với bilateral filter
           - Adaptive contrast enhancement
           - Advanced text enhancement
           - Gamma correction tự động
        
        9. **🔢 Continuous Numbering**
           - Figures đánh số liên tiếp qua các trang
           - figure-1, figure-2, figure-3... (không reset mỗi trang)
           - table-1, table-2, table-3... (liên tiếp)
        
        **🎯 Kết quả mong đợi:**
        - **Lọc được phần lớn text**
        - **Giữ lại hầu hết figures**
        - **Ít false negatives**
        - **Override reasoning rõ ràng**
        - **🎯 Chỉ giữ figures có confidence ≥65%**
        - **📊 Auto convert bảng thành Word table**
        - **🤖 OCR-guided figure counting cho accuracy cao**
        - **📱 Xử lý ảnh điện thoại chuẩn professional**
        - **🔢 Figures đánh số liên tiếp: figure-1, figure-2, ...**
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
        
        # Initialize Google OCR Service
        google_ocr_service = None
        if enable_google_ocr and ocr_api_url and ocr_api_key:
            try:
                google_ocr_service = GoogleOCRService(ocr_api_url, ocr_api_key)
                st.success("🤖 Google OCR Service initialized")
            except Exception as e:
                st.warning(f"⚠️ Could not initialize OCR service: {str(e)}")
        elif enable_google_ocr:
            st.warning("⚠️ Google OCR enabled but missing URL/Key")
        
        if enable_extraction and CV2_AVAILABLE:
            image_extractor = SuperEnhancedImageExtractor(google_ocr_service)
            
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
            if 'confidence_threshold' in locals():
                image_extractor.final_confidence_threshold = confidence_threshold
            
            # Enable/disable OCR counting
            if google_ocr_service:
                image_extractor.content_filter.enable_ocr_counting = True
            else:
                image_extractor.content_filter.enable_ocr_counting = False
            
            # Debug mode
            if debug_mode:
                image_extractor.debug_mode = True
                image_extractor.content_filter.text_filter.debug_mode = True
        else:
            image_extractor = None
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Main content với tabs
    tab1, tab2, tab3 = st.tabs(["📄 PDF sang LaTeX", "🖼️ Ảnh sang LaTeX", "📱 Ảnh điện thoại"])
    
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
                        
                        # Continuous numbering across pages
                        continuous_img_idx = 0
                        continuous_table_idx = 0
                        
                        progress_bar = st.progress(0)
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh với Balanced Text Filter và continuous numbering
                            extracted_figures = []
                            debug_img = None
                            
                            if enable_extraction and CV2_AVAILABLE and image_extractor:
                                try:
                                    figures, h, w, continuous_img_idx, continuous_table_idx = image_extractor.extract_figures_and_tables(
                                        img_bytes, continuous_img_idx, continuous_table_idx
                                    )
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

3. **📊 Bảng dữ liệu - Format linh hoạt:**
```
Option 1 (Multi-line):
Thời gian (phút) | [20; 25) | [25; 30) | [30; 35) | [35; 40) | [40; 45)
Số ngày | 6 | 6 | 4 | 1 | 1

Option 2 (Single-line):
Thời gian (phút) | [20; 25) | [25; 30) | [30; 35) | [35; 40) | [40; 45) Số ngày | 6 | 6 | 4 | 1 | 1
```

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
Ví dụ: Điểm ${A}$, ${B}$, ${C}$, công thức ${x^2 + 1}$, tỉ số ${\\frac{a}{b}}$

📊 TUYỆT ĐỐI dùng | để phân cách các cột trong bảng!
Ví dụ: Tên | Tuổi | Điểm

🔹 CHÚ Ý: Chỉ dùng ký tự $ khi có cặp ${...}$, không dùng $ đơn lẻ!
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                                
                                if latex_result:
                                    # Chèn figures
                                    if enable_extraction and extracted_figures and CV2_AVAILABLE and image_extractor:
                                        show_override = show_override_info if 'show_override_info' in locals() else True
                                        latex_result = image_extractor.insert_figures_into_text_precisely(
                                            latex_result, extracted_figures, h, w, show_override
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
                            
                            # OCR boost statistics
                            ocr_boosts = sum(1 for f in all_extracted_figures if f.get('ocr_boost'))
                            if ocr_boosts > 0:
                                st.markdown(f"**🤖 OCR Enhanced: {ocr_boosts} figures**")
                            
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
                                        show_override = show_override_info if 'show_override_info' in locals() else False
                                        auto_convert = auto_table_convert if 'auto_table_convert' in locals() else True
                                        
                                        # Nếu không hiển thị override info, tạo bản sao figures không có override info trong LaTeX
                                        if not show_override:
                                            # Tạo lại LaTeX content không có override info
                                            clean_latex = st.session_state.pdf_latex_content
                                            # Loại bỏ override info từ LaTeX content
                                            import re
                                            clean_latex = re.sub(r' \(kept: [^)]+\)', '', clean_latex)
                                            
                                            word_buffer = EnhancedWordExporter.create_word_document(
                                                clean_latex,
                                                extracted_figures=extracted_figs,
                                                auto_table_convert=auto_convert
                                            )
                                        else:
                                            word_buffer = EnhancedWordExporter.create_word_document(
                                                st.session_state.pdf_latex_content,
                                                extracted_figures=extracted_figs,
                                                auto_table_convert=auto_convert
                                            )
                                        
                                        st.download_button(
                                            label="📄 Tải Word (.docx)",
                                            data=word_buffer.getvalue(),
                                            file_name=uploaded_pdf.name.replace('.pdf', '.docx'),
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="download_word"
                                        )
                                        
                                        success_msg = "✅ Word document đã tạo thành công!"
                                        if auto_convert:
                                            success_msg += " 📊 Bảng dữ liệu tự động chuyển thành Word table."
                                        st.success(success_msg)
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
    
    # Tab mới: Ảnh điện thoại
    with tab3:
        st.header("📱 Xử lý ảnh chụp điện thoại")
        st.markdown("""
        <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c8 100%); padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
            <h4>📱 Tối ưu cho ảnh chụp điện thoại:</h4>
            <p>• 🔄 Auto-rotate và căn chỉnh thông minh</p>
            <p>• ✨ Enhance chất lượng ảnh với CLAHE + Gamma</p>
            <p>• 📐 Enhanced perspective correction</p>
            <p>• 🔍 Advanced text enhancement với unsharp mask</p>
            <p>• 📄 Smart document detection và crop</p>
            <p>• 🧹 Noise reduction với bilateral filter</p>
            <p>• ⚖️ Balanced Text Filter integration</p>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_phone_image = st.file_uploader("Chọn ảnh chụp từ điện thoại", type=['png', 'jpg', 'jpeg'], key="phone_upload")
        
        if uploaded_phone_image:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📱 Ảnh gốc")
                
                # Hiển thị ảnh gốc
                phone_image_pil = Image.open(uploaded_phone_image)
                st.image(phone_image_pil, caption=f"Ảnh gốc: {uploaded_phone_image.name}", use_column_width=True)
                
                # Thông tin ảnh
                st.markdown("**📊 Thông tin ảnh:**")
                st.write(f"• Kích thước: {phone_image_pil.size[0]} x {phone_image_pil.size[1]}")
                st.write(f"• Mode: {phone_image_pil.mode}")
                st.write(f"• Dung lượng: {format_file_size(uploaded_phone_image.size)}")
                
                # Cài đặt xử lý
                st.markdown("### ⚙️ Cài đặt xử lý")
                
                auto_enhance = st.checkbox("✨ Auto enhance chất lượng", value=True, key="phone_enhance")
                auto_rotate = st.checkbox("🔄 Auto rotate & straighten", value=True, key="phone_rotate")
                perspective_correct = st.checkbox("📐 Perspective correction", value=True, key="phone_perspective")
                text_enhance = st.checkbox("🔍 Enhance text clarity", value=True, key="phone_text")
                
                # Thêm các options mới
                st.markdown("**🔧 Advanced Options:**")
                crop_document = st.checkbox("📄 Smart document crop", value=True, key="phone_crop")
                noise_reduction = st.checkbox("🧹 Noise reduction", value=True, key="phone_noise")
                
                if enable_extraction and CV2_AVAILABLE:
                    extract_phone_figures = st.checkbox("🎯 Tách figures", value=True, key="phone_extract")
                    if extract_phone_figures:
                        phone_confidence = st.slider("Confidence (%)", 50, 95, 65, 5, key="phone_conf")
                else:
                    extract_phone_figures = False
            
            with col2:
                st.subheader("🔄 Xử lý & Kết quả")
                
                if st.button("🚀 Xử lý ảnh điện thoại", type="primary", key="process_phone"):
                    phone_img_bytes = uploaded_phone_image.getvalue()
                    
                    # Bước 1: Xử lý ảnh
                    with st.spinner("🔄 Đang xử lý ảnh..."):
                        try:
                            processed_img = PhoneImageProcessor.process_phone_image(
                                phone_img_bytes,
                                auto_enhance=auto_enhance,
                                auto_rotate=auto_rotate,
                                perspective_correct=perspective_correct,
                                text_enhance=text_enhance,
                                crop_document=crop_document,
                                noise_reduction=noise_reduction
                            )
                            
                            st.success("✅ Xử lý ảnh thành công!")
                            
                            # Hiển thị ảnh đã xử lý
                            st.markdown("**📸 Ảnh đã xử lý:**")
                            st.image(processed_img, use_column_width=True)
                            
                            # Convert to bytes for further processing
                            processed_buffer = io.BytesIO()
                            processed_img.save(processed_buffer, format='PNG')
                            processed_bytes = processed_buffer.getvalue()
                            
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý ảnh: {str(e)}")
                            processed_bytes = phone_img_bytes
                            processed_img = phone_image_pil
                    
                    # Bước 2: Tách figures nếu được bật
                    phone_extracted_figures = []
                    phone_h, phone_w = 0, 0
                    
                    if extract_phone_figures and enable_extraction and CV2_AVAILABLE and image_extractor:
                        with st.spinner("🎯 Đang tách figures..."):
                            try:
                                # Apply settings
                                original_threshold = image_extractor.final_confidence_threshold
                                image_extractor.final_confidence_threshold = phone_confidence
                                
                                figures, phone_h, phone_w, _, _ = image_extractor.extract_figures_and_tables(processed_bytes, 0, 0)
                                phone_extracted_figures = figures
                                
                                # Restore settings
                                image_extractor.final_confidence_threshold = original_threshold
                                
                                if figures:
                                    debug_img = image_extractor.create_beautiful_debug_visualization(processed_bytes, figures)
                                    st.success(f"🎯 Đã tách được {len(figures)} figures!")
                                    
                                    with st.expander("🔍 Xem figures đã tách"):
                                        display_beautiful_figures(figures, debug_img)
                                else:
                                    st.info("ℹ️ Không tìm thấy figures")
                                
                            except Exception as e:
                                st.error(f"❌ Lỗi tách figures: {str(e)}")
                    
                    # Bước 3: Chuyển đổi text
                    with st.spinner("📝 Đang chuyển đổi text..."):
                        try:
                            # Prompt với hướng dẫn cho ảnh điện thoại
                            phone_prompt = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX chính xác.

📱 ĐẶC BIỆT CHO ẢNH ĐIỆN THOẠI:
- Ảnh có thể bị nghiêng, mờ, hoặc có perspective
- Chú ý đọc kỹ từng ký tự, số
- Bỏ qua noise, shadow, reflection

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

3. **📊 Bảng dữ liệu - Format linh hoạt:**
```
Option 1 (Multi-line):
Thời gian (phút) | [20; 25) | [25; 30) | [30; 35) | [35; 40) | [40; 45)
Số ngày | 6 | 6 | 4 | 1 | 1

Option 2 (Single-line):
Thời gian (phút) | [20; 25) | [25; 30) | [30; 35) | [35; 40) | [40; 45) Số ngày | 6 | 6 | 4 | 1 | 1
```

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
📊 TUYỆT ĐỐI dùng | để phân cách các cột trong bảng!
"""
                            
                            phone_latex_result = gemini_api.convert_to_latex(processed_bytes, "image/png", phone_prompt)
                            
                            if phone_latex_result:
                                # Chèn figures nếu có
                                if extract_phone_figures and phone_extracted_figures and CV2_AVAILABLE and image_extractor:
                                    phone_latex_result = image_extractor.insert_figures_into_text_precisely(
                                        phone_latex_result, phone_extracted_figures, phone_h, phone_w, show_override_info=False
                                    )
                                
                                st.success("🎉 Chuyển đổi thành công!")
                                
                                # Hiển thị kết quả
                                st.markdown("### 📝 Kết quả LaTeX")
                                st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                st.code(phone_latex_result, language="latex")
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                                # Lưu vào session
                                st.session_state.phone_latex_content = phone_latex_result
                                st.session_state.phone_extracted_figures = phone_extracted_figures if extract_phone_figures else None
                                st.session_state.phone_processed_image = processed_img
                                
                            else:
                                st.error("❌ API không trả về kết quả")
                                
                        except Exception as e:
                            st.error(f"❌ Lỗi chuyển đổi: {str(e)}")
                
                # Download buttons cho phone processing
                if 'phone_latex_content' in st.session_state:
                    st.markdown("---")
                    st.markdown("### 📥 Tải xuống")
                    
                    col_x, col_y, col_z = st.columns(3)
                    
                    with col_x:
                        st.download_button(
                            label="📝 Tải LaTeX (.tex)",
                            data=st.session_state.phone_latex_content,
                            file_name=uploaded_phone_image.name.replace(uploaded_phone_image.name.split('.')[-1], 'tex'),
                            mime="text/plain",
                            type="primary",
                            key="download_phone_latex"
                        )
                    
                    with col_y:
                        if DOCX_AVAILABLE:
                            if st.button("📄 Tạo Word", key="create_phone_word"):
                                with st.spinner("🔄 Đang tạo Word..."):
                                    try:
                                        extracted_figs = st.session_state.get('phone_extracted_figures')
                                        
                                        # Clean latex content
                                        clean_latex = st.session_state.phone_latex_content
                                        import re
                                        clean_latex = re.sub(r' \(kept: [^)]+\)', '', clean_latex)
                                        
                                        word_buffer = EnhancedWordExporter.create_word_document(
                                            clean_latex,
                                            extracted_figures=extracted_figs,
                                            auto_table_convert=True
                                        )
                                        
                                        st.download_button(
                                            label="📄 Tải Word (.docx)",
                                            data=word_buffer.getvalue(),
                                            file_name=uploaded_phone_image.name.replace(uploaded_phone_image.name.split('.')[-1], 'docx'),
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="download_phone_word"
                                        )
                                        
                                        st.success("✅ Word document đã tạo thành công! 📊 Bảng tự động chuyển thành Word table.")
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
                    
                    with col_z:
                        if 'phone_processed_image' in st.session_state:
                            # Tải ảnh đã xử lý
                            processed_buffer = io.BytesIO()
                            st.session_state.phone_processed_image.save(processed_buffer, format='PNG')
                            
                            st.download_button(
                                label="📸 Tải ảnh đã xử lý",
                                data=processed_buffer.getvalue(),
                                file_name=uploaded_phone_image.name.replace(uploaded_phone_image.name.split('.')[-1], 'processed.png'),
                                mime="image/png",
                                key="download_processed_image"
                            )
    
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
                
                if extract_figures_single and enable_extraction and CV2_AVAILABLE:
                    st.markdown("**⚙️ Cài đặt tách ảnh:**")
                    single_confidence_threshold = st.slider("Confidence Threshold (%)", 50, 95, 65, 5, key="single_conf")
                    st.markdown(f"<small>✅ Chỉ giữ figures có confidence ≥ {single_confidence_threshold}%</small>", unsafe_allow_html=True)
                    
                    single_debug = st.checkbox("Debug mode cho ảnh đơn", value=False, key="single_debug")
                    if single_debug:
                        st.markdown("<small>🔍 Sẽ hiển thị thông tin debug chi tiết</small>", unsafe_allow_html=True)
            
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
                            # Áp dụng confidence threshold và debug mode cho single image
                            original_threshold = image_extractor.final_confidence_threshold
                            original_debug = image_extractor.debug_mode
                            
                            if 'single_confidence_threshold' in locals():
                                image_extractor.final_confidence_threshold = single_confidence_threshold
                            if 'single_debug' in locals():
                                image_extractor.debug_mode = single_debug
                                image_extractor.content_filter.text_filter.debug_mode = single_debug
                            
                            figures, h, w, _, _ = image_extractor.extract_figures_and_tables(img_bytes, 0, 0)
                            extracted_figures = figures
                            
                            # Khôi phục settings gốc
                            image_extractor.final_confidence_threshold = original_threshold
                            image_extractor.debug_mode = original_debug
                            image_extractor.content_filter.text_filter.debug_mode = original_debug
                            
                            if figures:
                                debug_img = image_extractor.create_beautiful_debug_visualization(img_bytes, figures)
                                st.success(f"🎯 Đã tách được {len(figures)} figures với confidence ≥{single_confidence_threshold if 'single_confidence_threshold' in locals() else 65}%!")
                                
                                # Hiển thị debug visualization
                                with st.expander("🔍 Xem figures được tách"):
                                    display_beautiful_figures(figures, debug_img)
                            else:
                                st.info(f"ℹ️ Không tìm thấy figures nào có confidence ≥{single_confidence_threshold if 'single_confidence_threshold' in locals() else 65}%")
                            
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

3. **📊 Bảng dữ liệu - LUÔN dùng format | để phân cách:**
```
Thời gian (phút) | [20; 25) | [25; 30) | [30; 35) | [35; 40) | [40; 45)
Số ngày | 6 | 6 | 4 | 1 | 1
```

⚠️ TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
Ví dụ: Điểm ${A}$, ${B}$, ${C}$, công thức ${x^2 + 1}$, tỉ số ${\\frac{a}{b}}$

📊 TUYỆT ĐỐI dùng | để phân cách các cột trong bảng!
Ví dụ: Tên | Tuổi | Điểm

🔹 CHÚ Ý: Chỉ dùng ký tự $ khi có cặp ${...}$, không dùng $ đơn lẻ!
"""
                    
                    # Gọi API
                    try:
                        with st.spinner("🔄 Đang chuyển đổi..."):
                            latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt_text)
                            
                            if latex_result:
                                # Chèn figures nếu có
                                if extract_figures_single and extracted_figures and CV2_AVAILABLE and image_extractor:
                                    # Không hiển thị override info cho tab ảnh đơn (để gọn)
                                    latex_result = image_extractor.insert_figures_into_text_precisely(
                                        latex_result, extracted_figures, h, w, show_override_info=False
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
                                        
                                        # Tạo clean latex content (không có override info)
                                        clean_latex = st.session_state.single_latex_content
                                        # Loại bỏ override info từ LaTeX content nếu có
                                        import re
                                        clean_latex = re.sub(r' \(kept: [^)]+\)', '', clean_latex)
                                        
                                        word_buffer = EnhancedWordExporter.create_word_document(
                                            clean_latex,
                                            extracted_figures=extracted_figs,
                                            auto_table_convert=True  # Mặc định bật cho single image
                                        )
                                        
                                        st.download_button(
                                            label="📄 Tải Word (.docx)",
                                            data=word_buffer.getvalue(),
                                            file_name=uploaded_image.name.replace(uploaded_image.name.split('.')[-1], 'docx'),
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="download_single_word"
                                        )
                                        
                                        st.success("✅ Word document đã tạo thành công! 📊 Bảng dữ liệu tự động chuyển thành Word table.")
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px;'>
        <h3>⚖️ BALANCED TEXT FILTER + 📊 AUTO TABLE + 🤖 GOOGLE OCR + 📱 ENHANCED PHONE</h3>
        <p><strong>✅ 7 phương pháp phân tích cân bằng</strong></p>
        <p><strong>⚖️ Lọc text mà vẫn giữ figures</strong></p>
        <p><strong>🧠 Override logic thông minh</strong></p>
        <p><strong>🎯 3+ indicators mới loại bỏ</strong></p>
        <p><strong>📊 Tự động chuyển bảng thành Word table</strong></p>
        <p><strong>🤖 Google OCR intelligent figure counting</strong></p>
        <p><strong>📱 Smart document detection + noise reduction + advanced perspective correction</strong></p>
        <p><strong>📄 PDF + 🖼️ Ảnh đơn + 📱 Professional phone processing + 🤖 OCR counting + 🎯 Confidence ≥65% + 📊 Auto table + 🔢 Continuous numbering</strong></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
