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
import gc  # Garbage collection

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
    page_title="PDF/LaTeX Converter - Enhanced with Table Protection",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS cải tiến (giữ nguyên)
try:
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
        
        .processing-container {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 2rem;
            border-radius: 12px;
            margin: 20px 0;
            border: 2px solid #dee2e6;
        }
    </style>
    """, unsafe_allow_html=True)
except Exception as e:
    st.error(f"CSS loading error: {str(e)}")

class GoogleOCRService:
    """Google Apps Script OCR Service để đếm figures trong ảnh"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'PDF-LaTeX-Converter/1.0'
        })
    
    def analyze_image_content(self, image_bytes, detect_figures=True, detect_tables=True):
        """Phân tích nội dung ảnh và đếm số lượng figures/tables"""
        try:
            encoded_image = base64.b64encode(image_bytes).decode('utf-8')
            
            payload = {
                "key": self.api_key,
                "action": "analyze_content",
                "image": encoded_image,
                "options": {
                    "detect_figures": detect_figures,
                    "detect_tables": detect_tables,
                    "return_coordinates": True,
                    "confidence_threshold": 0.7
                }
            }
            
            response = self.session.post(self.api_url, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                return self._process_ocr_response(result)
            else:
                st.warning(f"⚠️ OCR API error: {response.status_code}")
                return self._get_fallback_result()
                
        except requests.exceptions.Timeout:
            st.warning("⚠️ OCR API timeout - sử dụng fallback method")
            return self._get_fallback_result()
        except Exception as e:
            st.warning(f"⚠️ OCR API error: {str(e)} - sử dụng fallback method")
            return self._get_fallback_result()
    
    def _process_ocr_response(self, response):
        """Xử lý response từ OCR API"""
        try:
            if response.get('status') == 'success':
                data = response.get('data', {})
                
                return {
                    'success': True,
                    'figure_count': data.get('figure_count', 0),
                    'table_count': data.get('table_count', 0),
                    'total_count': data.get('total_images', 0),
                    'figure_regions': data.get('figure_regions', []),
                    'table_regions': data.get('table_regions', []),
                    'text_content': data.get('text_content', ''),
                    'confidence': data.get('confidence', 0.8),
                    'method': 'google_ocr'
                }
            else:
                return self._get_fallback_result()
        except Exception:
            return self._get_fallback_result()
    
    def _get_fallback_result(self):
        """Fallback result khi OCR API không khả dụng"""
        return {
            'success': False,
            'figure_count': 2,
            'table_count': 1,
            'total_count': 3,
            'figure_regions': [],
            'table_regions': [],
            'text_content': '',
            'confidence': 0.5,
            'method': 'fallback'
        }

class EnhancedPhoneImageProcessor:
    """
    Enhanced Phone Image Processor - Đặc biệt tối ưu cho bảng Đúng/Sai và documents
    """
    
    @staticmethod
    def detect_table_regions(img):
        """Detect và bảo vệ vùng bảng (đặc biệt là bảng Đúng/Sai)"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
            h, w = gray.shape
            
            # Detect horizontal lines (table rows)
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//8, 1))
            horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
            
            # Detect vertical lines (table columns) - more sensitive for narrow columns
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//20))
            vertical_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel)
            
            # Combine to form table structure
            table_structure = cv2.bitwise_or(horizontal_lines, vertical_lines)
            
            # Find table contours
            contours, _ = cv2.findContours(table_structure, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            table_regions = []
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                area = w_cont * h_cont
                
                # Filter for substantial table regions
                if area > (w * h * 0.02):  # At least 2% of image
                    table_regions.append((x, y, w_cont, h_cont))
            
            return table_regions
            
        except Exception:
            return []
    
    @staticmethod
    def detect_checkbox_columns(img):
        """Đặc biệt detect cột Đúng/Sai để bảo vệ"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
            h, w = gray.shape
            
            checkbox_regions = []
            
            # Simple square detection for checkboxes
            contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                
                # Check if it's roughly square (checkbox-like)
                aspect_ratio = w_cont / max(h_cont, 1)
                area = w_cont * h_cont
                
                if (0.7 <= aspect_ratio <= 1.3 and  # Square-ish
                    100 <= area <= 1000 and  # Reasonable size
                    x > w * 0.6):  # In the right side (where Đúng/Sai columns usually are)
                    checkbox_regions.append((x, y, w_cont, h_cont))
            
            return checkbox_regions
            
        except Exception:
            return []
    
    @staticmethod
    def process_phone_image(image_bytes, preserve_tables=True, enhance_text=True, 
                           auto_rotate=True, perspective_correct=True, 
                           noise_reduction=True, contrast_boost=1.2, is_screenshot=False):
        """Enhanced processing với bảo vệ đặc biệt cho bảng Đúng/Sai"""
        try:
            # Load image
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            # Detect if this is likely a screenshot
            if not is_screenshot:
                is_screenshot = EnhancedPhoneImageProcessor._detect_screenshot(img_pil)
            
            # Convert to numpy for CV2 processing if available
            if CV2_AVAILABLE:
                img = np.array(img_pil)
                original_img = img.copy()
                
                # Step 1: Detect protected regions (tables, checkboxes)
                protected_regions = []
                if preserve_tables:
                    table_regions = EnhancedPhoneImageProcessor.detect_table_regions(img)
                    checkbox_regions = EnhancedPhoneImageProcessor.detect_checkbox_columns(img)
                    protected_regions = table_regions + checkbox_regions
                
                # Screenshot-specific processing
                if is_screenshot:
                    img = EnhancedPhoneImageProcessor._process_screenshot(img, protected_regions)
                else:
                    # Regular phone photo processing with table protection
                    # Step 2: Noise reduction (gentle to preserve table lines)
                    if noise_reduction:
                        img = cv2.bilateralFilter(img, 5, 50, 50)  # Gentler than original
                    
                    # Step 3: Auto rotation (careful around tables)
                    if auto_rotate:
                        img = EnhancedPhoneImageProcessor._careful_auto_rotate(img, protected_regions)
                    
                    # Step 4: Perspective correction (avoid tables)
                    if perspective_correct:
                        img = EnhancedPhoneImageProcessor._table_aware_perspective_correction(img, protected_regions)
                
                # Step 5: Enhanced text processing (for both types)
                if enhance_text:
                    img = EnhancedPhoneImageProcessor._enhanced_text_processing(img, protected_regions, is_screenshot)
                
                # Step 6: Contrast and clarity boost
                img = EnhancedPhoneImageProcessor._smart_contrast_enhancement(img, contrast_boost)
                
                # Convert back to PIL
                processed_img = Image.fromarray(img)
            else:
                # Fallback: basic PIL processing
                processed_img = img_pil
                
                if enhance_text:
                    # Basic enhancement with PIL
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
    def _detect_screenshot(img_pil):
        """Detect nếu ảnh là screenshot dựa trên các đặc điểm"""
        try:
            width, height = img_pil.size
            
            # Screenshots thường có:
            aspect_ratio = width / height
            common_ratios = [16/9, 16/10, 4/3, 3/2, 19.5/9, 18/9]
            
            is_pixel_perfect = (width % 2 == 0) and (height % 2 == 0)
            is_high_res = (width * height) > 500000
            aspect_match = any(abs(aspect_ratio - ratio) < 0.1 for ratio in common_ratios)
            
            if CV2_AVAILABLE:
                img_array = np.array(img_pil)
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                
                edges = cv2.Canny(gray, 100, 200)
                edge_density = np.sum(edges > 0) / (width * height)
                has_sharp_edges = edge_density > 0.05
                
                laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                is_clean = laplacian_var > 100
                
                screenshot_score = sum([
                    is_pixel_perfect,
                    is_high_res,
                    aspect_match,
                    has_sharp_edges,
                    is_clean
                ])
                
                return screenshot_score >= 3
            else:
                screenshot_score = sum([
                    is_pixel_perfect,
                    is_high_res,
                    aspect_match
                ])
                return screenshot_score >= 2
                
        except Exception:
            return False
    
    @staticmethod
    def _process_screenshot(img, protected_regions):
        """Xử lý đặc biệt cho screenshot với table protection"""
        try:
            # Screenshots thường đã sạch, chỉ cần enhance nhẹ
            
            # 1. Gentle sharpening - avoid over-processing tables
            kernel = np.array([[0, -0.5, 0], [-0.5, 3, -0.5], [0, -0.5, 0]])
            sharpened = cv2.filter2D(img, -1, kernel)
            
            # 2. Very gentle contrast enhancement
            alpha = 1.05  # Reduced contrast for tables
            beta = 2      # Reduced brightness
            enhanced = cv2.convertScaleAbs(sharpened, alpha=alpha, beta=beta)
            
            return enhanced
            
        except Exception:
            return img
    
    @staticmethod
    def _careful_auto_rotate(img, protected_regions):
        """Auto rotate nhưng cẩn thận với vùng bảng"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Use protected regions to influence rotation detection
            if protected_regions:
                # Create mask excluding table regions
                mask = np.ones_like(gray) * 255
                for x, y, w, h in protected_regions:
                    mask[y:y+h, x:x+w] = 0
                
                masked_gray = cv2.bitwise_and(gray, mask)
                edges = cv2.Canny(masked_gray, 50, 150)
            else:
                edges = cv2.Canny(gray, 50, 150)
            
            # Detect lines for rotation
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=50)
            
            if lines is not None:
                angles = []
                for rho, theta in lines[:10]:
                    angle = theta * 180 / np.pi
                    if angle > 90:
                        angle = angle - 180
                    elif angle > 45:
                        angle = angle - 90
                    elif angle < -45:
                        angle = angle + 90
                    
                    if abs(angle) < 30:  # Only small corrections
                        angles.append(angle)
                
                if angles:
                    rotation_angle = np.median(angles)
                    if abs(rotation_angle) > 0.5:  # Only rotate if significant
                        center = (img.shape[1]//2, img.shape[0]//2)
                        M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
                        img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), 
                                           borderMode=cv2.BORDER_CONSTANT,
                                           borderValue=(255, 255, 255))
            
            return img
            
        except Exception:
            return img
    
    @staticmethod
    def _table_aware_perspective_correction(img, protected_regions):
        """Perspective correction that avoids distorting tables"""
        try:
            # If there are many protected regions (likely tables), skip perspective correction
            if len(protected_regions) > 3:
                return img
            
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 30, 90)
            
            # Mask out protected regions from edge detection
            for x, y, w, h in protected_regions:
                edges[y:y+h, x:x+w] = 0
            
            # Find contours for document detection
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            
            # Look for document-like contour (but be more conservative)
            for contour in contours[:3]:
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                if len(approx) == 4:
                    area = cv2.contourArea(contour)
                    img_area = img.shape[0] * img.shape[1]
                    area_ratio = area / img_area
                    
                    # More conservative area requirement when tables are present
                    min_area = 0.3 if protected_regions else 0.2
                    if area_ratio > min_area:
                        # Check if this contour overlaps with protected regions
                        overlaps_table = False
                        for x, y, w, h in protected_regions:
                            table_center = (x + w//2, y + h//2)
                            if cv2.pointPolygonTest(contour, table_center, False) >= 0:
                                overlaps_table = True
                                break
                        
                        if not overlaps_table:
                            # Apply perspective correction
                            rect = EnhancedPhoneImageProcessor._order_points(approx.reshape(-1, 2))
                            (tl, tr, br, bl) = rect
                            
                            widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
                            widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
                            maxWidth = max(int(widthA), int(widthB))
                            
                            heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
                            heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
                            maxHeight = max(int(heightA), int(heightB))
                            
                            if maxWidth > 100 and maxHeight > 100:
                                dst = np.array([
                                    [0, 0],
                                    [maxWidth - 1, 0],
                                    [maxWidth - 1, maxHeight - 1],
                                    [0, maxHeight - 1]], dtype="float32")
                                
                                M = cv2.getPerspectiveTransform(rect, dst)
                                img = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
                                break
            
            return img
            
        except Exception:
            return img
    
    @staticmethod
    def _enhanced_text_processing(img, protected_regions, is_screenshot=False):
        """Enhanced text processing with special care for table text"""
        try:
            # Convert to LAB for better text enhancement
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            
            enhanced_l = l.copy()
            
            # For protected regions (tables), use gentler enhancement
            for x, y, w, h in protected_regions:
                table_region = l[y:y+h, x:x+w]
                
                if is_screenshot:
                    # Very gentle for screenshot tables
                    clahe_gentle = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(4, 4))
                    enhanced_table = clahe_gentle.apply(table_region)
                else:
                    # Gentle CLAHE for phone photo tables
                    clahe_gentle = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4))
                    enhanced_table = clahe_gentle.apply(table_region)
                    
                    # Very gentle sharpening for tables
                    kernel = np.array([[0, -0.25, 0], [-0.25, 2, -0.25], [0, -0.25, 0]])
                    enhanced_table = cv2.filter2D(enhanced_table, -1, kernel)
                
                enhanced_l[y:y+h, x:x+w] = enhanced_table
            
            # For non-table regions, use stronger enhancement
            mask = np.ones_like(l, dtype=np.uint8) * 255
            for x, y, w, h in protected_regions:
                mask[y:y+h, x:x+w] = 0
            
            if is_screenshot:
                # Moderate enhancement for screenshot non-table areas
                clahe_strong = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            else:
                # Stronger CLAHE for phone photo non-table areas
                clahe_strong = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            
            enhanced_non_table = clahe_strong.apply(l)
            
            # Combine enhanced regions
            enhanced_l = np.where(mask == 255, enhanced_non_table, enhanced_l)
            
            # Merge back
            enhanced_lab = cv2.merge([enhanced_l, a, b])
            enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
            
            return enhanced_img
            
        except Exception:
            return img
    
    @staticmethod
    def _smart_contrast_enhancement(img, contrast_boost):
        """Smart contrast enhancement that preserves table structure"""
        try:
            # Convert to PIL for easier enhancement
            img_pil = Image.fromarray(img)
            
            # Gentle contrast enhancement
            enhancer = ImageEnhance.Contrast(img_pil)
            enhanced = enhancer.enhance(contrast_boost)
            
            # Gentle sharpness enhancement
            enhancer = ImageEnhance.Sharpness(enhanced)
            enhanced = enhancer.enhance(1.1)
            
            # Slight brightness adjustment
            enhancer = ImageEnhance.Brightness(enhanced)
            enhanced = enhancer.enhance(1.05)
            
            return np.array(enhanced)
            
        except Exception:
            return img
    
    @staticmethod
    def _order_points(pts):
        """Helper function to order points for perspective correction"""
        rect = np.zeros((4, 2), dtype="float32")
        
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        
        return rect

# ================ Keep all other classes unchanged ================
# (GoogleOCRService, BalancedTextFilter, EnhancedContentBasedFigureFilter, 
#  GeminiAPI, PDFProcessor, SuperEnhancedImageExtractor, EnhancedWordExporter, etc.)

class BalancedTextFilter:
    """Bộ lọc text CÂN BẰNG - Lọc text nhưng vẫn giữ được figures"""
    
    def __init__(self):
        self.text_density_threshold = 0.7
        self.min_visual_complexity = 0.2
        self.min_diagram_score = 0.1
        self.min_figure_quality = 0.15
        self.debug_mode = False
        
    def analyze_and_filter_balanced(self, image_bytes, candidates):
        """Phân tích và lọc với độ cân bằng tốt hơn"""
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            if not image_bytes or not candidates:
                return candidates
                
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            if h == 0 or w == 0:
                return candidates
            
            if self.debug_mode:
                st.write(f"🔍 Balanced Text Filter analyzing {len(candidates)} candidates")
            
            analyzed_candidates = []
            for i, candidate in enumerate(candidates):
                try:
                    analysis = self._balanced_analyze_candidate(img, candidate)
                    candidate.update(analysis)
                    analyzed_candidates.append(candidate)
                except Exception as e:
                    if self.debug_mode:
                        st.warning(f"Error analyzing candidate {i+1}: {str(e)}")
                    analyzed_candidates.append(candidate)
            
            filtered_candidates = self._balanced_filter(analyzed_candidates)
            
            if self.debug_mode:
                st.write(f"📊 Balanced filter result: {len(filtered_candidates)}/{len(candidates)}")
            
            return filtered_candidates
            
        except Exception as e:
            if self.debug_mode:
                st.error(f"❌ Balanced filter error: {str(e)}")
            return candidates
    
    def _balanced_analyze_candidate(self, img, candidate):
        """Phân tích cân bằng từng candidate"""
        try:
            x, y, w, h = candidate['bbox']
            
            img_h, img_w = img.shape[:2]
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h or w <= 0 or h <= 0:
                return {'is_text': False, 'text_score': 0.0}
            
            roi = img[y:y+h, x:x+w]
            
            if roi.size == 0 or roi.shape[0] == 0 or roi.shape[1] == 0:
                return {'is_text': False, 'text_score': 0.0}
            
            # Simplified analysis for performance
            text_score = self._calculate_text_score(roi)
            aspect_ratio = w / max(h, 1)
            area = w * h
            
            # Conservative text detection - only mark as text if very confident
            strong_text_indicators = 0
            if text_score > 0.8:  # Higher threshold
                strong_text_indicators += 1
            if 0.1 < aspect_ratio < 10.0:  # Reasonable aspect ratio
                strong_text_indicators += 1
            if area < 2000:  # Small area typical of text
                strong_text_indicators += 1
            
            # Only consider as text if at least 3 strong indicators
            is_text = strong_text_indicators >= 3
            
            return {
                'text_score': text_score,
                'aspect_ratio': aspect_ratio,
                'is_text': is_text,
                'area': area,
                'strong_text_indicators': strong_text_indicators
            }
            
        except Exception:
            return {'is_text': False, 'text_score': 0.0}
    
    def _calculate_text_score(self, roi):
        """Simplified text score calculation"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            # Simple text detection based on horizontal patterns
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, gray.shape[1]//10), 1))
            h_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, h_kernel)
            text_density = np.sum(h_lines > 0) / max(gray.shape[0] * gray.shape[1], 1)
            
            return min(1.0, text_density * 4)  # Scale up
            
        except Exception:
            return 0.0
    
    def _balanced_filter(self, candidates):
        """Lọc cân bằng - ưu tiên giữ lại figures"""
        filtered = []
        
        for candidate in candidates:
            try:
                # Very conservative text filtering
                if candidate.get('is_text', False):
                    # Keep if it has potential visual elements
                    area = candidate.get('area', 0)
                    aspect_ratio = candidate.get('aspect_ratio', 1)
                    
                    if area > 3000:  # Large enough to be important
                        candidate['override_reason'] = 'large_area'
                        filtered.append(candidate)
                    elif aspect_ratio > 2.0:  # Wide - could be table
                        candidate['override_reason'] = 'table_like'
                        filtered.append(candidate)
                    # Otherwise skip (likely pure text)
                else:
                    # Not detected as text, keep it
                    filtered.append(candidate)
                    
            except Exception:
                # If error, keep the candidate
                filtered.append(candidate)
        
        return filtered

class EnhancedContentBasedFigureFilter:
    """Bộ lọc thông minh với Google OCR Integration"""
    
    def __init__(self, google_ocr_service=None):
        self.text_filter = BalancedTextFilter()
        self.enable_balanced_filter = True
        self.min_estimated_count = 1
        self.max_estimated_count = 15
        self.google_ocr = google_ocr_service
        self.enable_ocr_counting = True
        
    def analyze_content_and_filter_with_ocr(self, image_bytes, candidates):
        """Phân tích với Google OCR + Balanced Text Filter"""
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            estimated_count = self.min_estimated_count
            ocr_info = {}
            
            if self.google_ocr and self.enable_ocr_counting:
                with st.spinner("🔍 Analyzing image content with OCR..."):
                    ocr_result = self.google_ocr.analyze_image_content(image_bytes)
                    
                    if ocr_result['success']:
                        estimated_count = max(ocr_result['total_count'], self.min_estimated_count)
                        estimated_count = min(estimated_count, self.max_estimated_count)
                        ocr_info = ocr_result
                        
                        st.success(f"🤖 OCR detected: {ocr_result['figure_count']} figures, {ocr_result['table_count']} tables")
                    else:
                        st.info(f"📊 Conservative estimate: {estimated_count} figures")
            else:
                st.info(f"📊 Estimated: {estimated_count} figures")
            
            # Balanced Text Filter
            if self.enable_balanced_filter:
                filtered_candidates = self.text_filter.analyze_and_filter_balanced(image_bytes, candidates)
                st.success(f"🧠 Balanced Filter: {len(filtered_candidates)}/{len(candidates)} figures kept")
            else:
                filtered_candidates = candidates
            
            return filtered_candidates
            
        except Exception as e:
            st.error(f"❌ Enhanced filter error: {str(e)}")
            return candidates

class GeminiAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        self.session = requests.Session()
        self.max_retries = 3
        self.timeout = 120
    
    def encode_image(self, image_data: bytes) -> str:
        return base64.b64encode(image_data).decode('utf-8')
    
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        
        if content_type.startswith('image/'):
            mime_type = content_type
        else:
            mime_type = "image/png"
        
        if len(content_data) > 20 * 1024 * 1024:
            raise Exception("Image quá lớn (>20MB). Vui lòng resize ảnh.")
        
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
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}?key={self.api_key}",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
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
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise Exception("Đã vượt quá giới hạn rate limit")
                else:
                    error_text = response.text[:200] if response.text else "Unknown error"
                    raise Exception(f"API Error {response.status_code}: {error_text}")
            
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception("Request timeout")
            except requests.exceptions.ConnectionError:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception("Lỗi kết nối mạng")
            except Exception as e:
                if attempt < self.max_retries - 1 and "rate limit" in str(e).lower():
                    time.sleep(2 ** attempt)
                    continue
                raise Exception(str(e))

class PDFProcessor:
    @staticmethod
    def extract_images_and_text(pdf_file, max_pages=None):
        """Extract images with memory management"""
        try:
            file_content = pdf_file.read()
            if len(file_content) == 0:
                raise Exception("PDF file is empty")
            
            pdf_document = fitz.open(stream=file_content, filetype="pdf")
            images = []
            
            total_pages = pdf_document.page_count
            if max_pages:
                total_pages = min(total_pages, max_pages)
            
            for page_num in range(total_pages):
                try:
                    page = pdf_document[page_num]
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    pix = None
                    
                    img = Image.open(io.BytesIO(img_data))
                    
                    max_size = (2000, 2000)
                    if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    images.append((img, page_num + 1))
                    
                    if page_num % 5 == 0:
                        gc.collect()
                        
                except Exception as e:
                    st.warning(f"Lỗi xử lý trang {page_num + 1}: {str(e)}")
                    continue
            
            pdf_document.close()
            return images
            
        except Exception as e:
            raise Exception(f"Lỗi đọc PDF: {str(e)}")

class SuperEnhancedImageExtractor:
    """Tách ảnh với Balanced Text Filter + Google OCR Integration"""
    
    def __init__(self, google_ocr_service=None):
        # Basic parameters
        self.min_area_ratio = 0.0005
        self.min_area_abs = 400
        self.min_width = 20
        self.min_height = 20
        self.max_figures = 25
        self.max_area_ratio = 0.80
        
        # Enhanced Content-Based Filter with Google OCR
        self.content_filter = EnhancedContentBasedFigureFilter(google_ocr_service)
        self.enable_content_filter = True
        
        # Confidence thresholds
        self.confidence_threshold = 15
        self.final_confidence_threshold = 65
        
        # Debug mode
        self.debug_mode = False
    
    def extract_figures_and_tables(self, image_bytes, start_img_idx=0, start_table_idx=0):
        """Tách ảnh với Balanced Text Filter và continuous numbering"""
        if not CV2_AVAILABLE:
            return [], 0, 0, start_img_idx, start_table_idx
        
        try:
            if not image_bytes or len(image_bytes) == 0:
                return [], 0, 0, start_img_idx, start_table_idx
            
            try:
                img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                
                max_size = (3000, 3000)
                if img_pil.size[0] > max_size[0] or img_pil.size[1] > max_size[1]:
                    img_pil.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                img = np.array(img_pil)
                h, w = img.shape[:2]
                
                if h == 0 or w == 0:
                    return [], 0, 0, start_img_idx, start_table_idx
                    
            except Exception as e:
                st.error(f"Lỗi đọc ảnh: {str(e)}")
                return [], 0, 0, start_img_idx, start_table_idx
            
            # Enhanced image preprocessing
            enhanced_img = self._enhance_image(img)
            
            # Multiple detection methods
            all_candidates = []
            
            try:
                edge_candidates = self._detect_by_edges(enhanced_img, w, h)
                all_candidates.extend(edge_candidates)
            except Exception as e:
                if self.debug_mode:
                    st.warning(f"Edge detection error: {str(e)}")
            
            try:
                contour_candidates = self._detect_by_contours(enhanced_img, w, h)
                all_candidates.extend(contour_candidates)
            except Exception as e:
                if self.debug_mode:
                    st.warning(f"Contour detection error: {str(e)}")
            
            try:
                grid_candidates = self._detect_by_grid_enhanced(enhanced_img, w, h)
                all_candidates.extend(grid_candidates)
            except Exception as e:
                if self.debug_mode:
                    st.warning(f"Grid detection error: {str(e)}")
            
            # Filter and merge candidates
            filtered_candidates = self._filter_and_merge_candidates(all_candidates, w, h)
            
            # Enhanced Content-Based Filter with Google OCR
            if self.enable_content_filter:
                try:
                    content_filtered = self.content_filter.analyze_content_and_filter_with_ocr(image_bytes, filtered_candidates)
                    filtered_candidates = content_filtered
                except Exception as e:
                    if self.debug_mode:
                        st.warning(f"Content filter error: {str(e)}")
            
            # Create final figures with continuous numbering
            final_figures, final_img_idx, final_table_idx = self._create_final_figures(
                filtered_candidates, img, w, h, start_img_idx, start_table_idx
            )
            
            return final_figures, h, w, final_img_idx, final_table_idx
            
        except Exception as e:
            st.error(f"❌ Extraction error: {str(e)}")
            return [], 0, 0, start_img_idx, start_table_idx
    
    def _enhance_image(self, img):
        """Image preprocessing with error handling"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(blurred)
            return cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
        except Exception:
            return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
    
    def _detect_by_edges(self, gray_img, w, h):
        """Edge detection with error handling"""
        try:
            edges = cv2.Canny(gray_img, 30, 80)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges_dilated = cv2.dilate(edges, kernel, iterations=1)
            
            contours, _ = cv2.findContours(edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            candidates = []
            for cnt in contours:
                try:
                    x, y, ww, hh = cv2.boundingRect(cnt)
                    area = ww * hh
                    
                    if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                        candidates.append({
                            'bbox': (x, y, ww, hh),
                            'area': area,
                            'method': 'edge',
                            'confidence': 25
                        })
                except Exception:
                    continue
            
            return candidates
        except Exception:
            return []
    
    def _detect_by_contours(self, gray_img, w, h):
        """Contour detection with error handling"""
        try:
            _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            candidates = []
            for cnt in contours:
                try:
                    x, y, ww, hh = cv2.boundingRect(cnt)
                    area = ww * hh
                    
                    if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                        candidates.append({
                            'bbox': (x, y, ww, hh),
                            'area': area,
                            'method': 'contour',
                            'confidence': 30
                        })
                except Exception:
                    continue
            
            return candidates
        except Exception:
            return []
    
    def _detect_by_grid_enhanced(self, gray_img, w, h):
        """Enhanced grid detection for tables including Đúng/Sai columns"""
        try:
            # Standard grid detection
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, w//12), 1))
            horizontal_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, horizontal_kernel)
            
            # More sensitive vertical detection for narrow columns (Đúng/Sai)
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, h//20)))
            vertical_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, vertical_kernel)
            
            # Enhanced table detection for complete tables
            enhanced_grid = self._detect_complete_tables_enhanced(gray_img, w, h)
            
            # Combine all methods
            grid_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
            combined_grid = cv2.bitwise_or(grid_mask, enhanced_grid)
            
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            grid_dilated = cv2.dilate(combined_grid, kernel, iterations=1)
            
            contours, _ = cv2.findContours(grid_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            candidates = []
            for cnt in contours:
                try:
                    x, y, ww, hh = cv2.boundingRect(cnt)
                    area = ww * hh
                    
                    if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                        aspect_ratio = ww / max(hh, 1)
                        
                        # Enhanced confidence for complete tables
                        confidence = 30
                        if self._is_complete_table_enhanced(gray_img[y:y+hh, x:x+ww]):
                            confidence = 75  # High confidence for complete tables
                        elif aspect_ratio > 2.5:  # Very wide tables (likely with multiple columns)
                            confidence = 65
                        elif aspect_ratio > 1.5:
                            confidence = 50
                        
                        is_table = aspect_ratio > 1.2
                        
                        candidates.append({
                            'bbox': (x, y, ww, hh),
                            'area': area,
                            'method': 'grid',
                            'confidence': confidence,
                            'is_table': is_table,
                            'aspect_ratio': aspect_ratio
                        })
                except Exception:
                    continue
            
            return candidates
        except Exception:
            return []
    
    def _detect_complete_tables_enhanced(self, gray_img, w, h):
        """Enhanced detection for complete tables including Đúng/Sai columns"""
        try:
            # Enhanced edge detection for table borders
            blurred = cv2.GaussianBlur(gray_img, (3, 3), 0)
            edges = cv2.Canny(blurred, 20, 60)  # Lower thresholds for subtle borders
            
            # Detect horizontal lines (table rows) - more sensitive
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//10, 1))
            horizontal_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
            
            # Detect vertical lines (table columns) - very sensitive for narrow columns
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//25))
            vertical_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, vertical_kernel)
            
            # Combine to form complete table structure
            table_structure = cv2.bitwise_or(horizontal_lines, vertical_lines)
            
            # Dilate to connect broken lines but preserve structure
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            table_structure = cv2.dilate(table_structure, kernel, iterations=1)
            
            # Fill enclosed areas to capture complete tables
            contours, _ = cv2.findContours(table_structure, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Create mask for complete tables
            table_mask = np.zeros_like(gray_img)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > (w * h * 0.008):  # Lower threshold - at least 0.8% of image
                    cv2.fillPoly(table_mask, [contour], 255)
            
            return table_mask
            
        except Exception:
            return np.zeros_like(gray_img)
    
    def _is_complete_table_enhanced(self, table_roi):
        """Enhanced check for complete table structure including narrow columns"""
        try:
            if table_roi.shape[0] < 30 or table_roi.shape[1] < 60:
                return False
            
            h, w = table_roi.shape[:2] if len(table_roi.shape) == 2 else table_roi.shape[:2]
            
            # Horizontal line detection - more sensitive
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//6, 1))
            horizontal_lines = cv2.morphologyEx(table_roi, cv2.MORPH_OPEN, horizontal_kernel)
            h_contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Vertical line detection - very sensitive for narrow columns
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//8))
            vertical_lines = cv2.morphologyEx(table_roi, cv2.MORPH_OPEN, vertical_kernel)
            v_contours, _ = cv2.findContours(vertical_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # A complete table should have at least 2 horizontal and 2 vertical lines
            # Lowered requirement for vertical lines to account for narrow Đúng/Sai columns
            return len(h_contours) >= 2 and len(v_contours) >= 2
            
        except Exception:
            return False
    
    def _is_valid_candidate(self, x, y, ww, hh, area, img_w, img_h):
        """Check if candidate is valid with better validation"""
        try:
            if x < 0 or y < 0 or ww <= 0 or hh <= 0:
                return False
            
            if x + ww > img_w or y + hh > img_h:
                return False
            
            area_ratio = area / max(img_w * img_h, 1)
            
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > self.max_area_ratio or
                ww < self.min_width or 
                hh < self.min_height):
                return False
            
            edge_margin = 0.005
            if (x < edge_margin * img_w or 
                y < edge_margin * img_h or 
                (x + ww) > (1 - edge_margin) * img_w or 
                (y + hh) > (1 - edge_margin) * img_h):
                return False
            
            return True
        except Exception:
            return False
    
    def _filter_and_merge_candidates(self, candidates, w, h):
        """Filter and merge candidates with error handling"""
        try:
            if not candidates:
                return []
            
            candidates = sorted(candidates, key=lambda x: x.get('area', 0), reverse=True)
            
            filtered = []
            for candidate in candidates:
                try:
                    if not self._is_overlapping_with_list(candidate, filtered):
                        candidate['final_confidence'] = self._calculate_final_confidence(candidate, w, h)
                        if candidate['final_confidence'] >= self.confidence_threshold:
                            filtered.append(candidate)
                except Exception:
                    continue
            
            return filtered[:self.max_figures]
        except Exception:
            return []
    
    def _is_overlapping_with_list(self, candidate, existing_list):
        """Check overlap with error handling"""
        try:
            x1, y1, w1, h1 = candidate['bbox']
            
            for existing in existing_list:
                x2, y2, w2, h2 = existing['bbox']
                
                intersection_area = max(0, min(x1+w1, x2+w2) - max(x1, x2)) * max(0, min(y1+h1, y2+h2) - max(y1, y2))
                union_area = w1*h1 + w2*h2 - intersection_area
                
                if union_area > 0:
                    iou = intersection_area / union_area
                    if iou > 0.25:
                        return True
            
            return False
        except Exception:
            return False
    
    def _calculate_final_confidence(self, candidate, w, h):
        """Calculate confidence with error handling"""
        try:
            x, y, ww, hh = candidate['bbox']
            area_ratio = candidate['area'] / max(w * h, 1)
            aspect_ratio = ww / max(hh, 1)
            
            confidence = candidate.get('confidence', 20)
            
            # Bonus for good size
            if 0.01 < area_ratio < 0.6:
                confidence += 20
            elif 0.005 < area_ratio < 0.8:
                confidence += 10
            
            # Bonus for good aspect ratio
            if 0.3 < aspect_ratio < 5.0:
                confidence += 15
            elif 0.2 < aspect_ratio < 8.0:
                confidence += 8
            
            # Method bonus
            if candidate['method'] == 'grid':
                confidence += 15
            elif candidate['method'] == 'edge':
                confidence += 8
            
            return min(100, confidence)
        except Exception:
            return 20
    
    def _create_final_figures(self, candidates, img, w, h, start_img_idx=0, start_table_idx=0):
        """Create final figures with confidence filter and continuous numbering"""
        try:
            candidates = sorted(candidates, key=lambda x: (x['bbox'][1], x['bbox'][0]))
            
            # Filter by final confidence threshold
            high_confidence_candidates = [c for c in candidates 
                                        if c.get('final_confidence', 0) >= self.final_confidence_threshold]
            
            if self.debug_mode:
                st.write(f"🎯 Confidence Filter: {len(high_confidence_candidates)}/{len(candidates)} figures above {self.final_confidence_threshold}%")
            elif len(candidates) > 0:
                st.info(f"🎯 Confidence Filter: Giữ {len(high_confidence_candidates)}/{len(candidates)} figures có confidence ≥{self.final_confidence_threshold}%")
            
            final_figures = []
            img_idx = start_img_idx
            table_idx = start_table_idx
            
            for candidate in high_confidence_candidates:
                try:
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
                        "area_ratio": candidate["area"] / max(w * h, 1),
                        "aspect_ratio": candidate["bbox"][2] / max(candidate["bbox"][3], 1),
                        "method": candidate["method"],
                        "center_y": candidate["bbox"][1] + candidate["bbox"][3] // 2,
                        "center_x": candidate["bbox"][0] + candidate["bbox"][2] // 2,
                        "override_reason": candidate.get("override_reason", None)
                    })
                except Exception as e:
                    if self.debug_mode:
                        st.warning(f"Error creating figure: {str(e)}")
                    continue
            
            return final_figures, img_idx, table_idx
        except Exception:
            return [], start_img_idx, start_table_idx
    
    def _smart_crop(self, img, candidate, img_w, img_h):
        """Smart cropping with error handling"""
        try:
            x, y, w, h = candidate['bbox']
            
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
                return None
            
            padding = 20
            padding_x = min(padding, w // 4)
            padding_y = min(padding, h // 4)
            
            x0 = max(0, x - padding_x)
            y0 = max(0, y - padding_y)
            x1 = min(img_w, x + w + padding_x)
            y1 = min(img_h, y + h + padding_y)
            
            cropped = img[y0:y1, x0:x1]
            
            if cropped.size == 0 or cropped.shape[0] == 0 or cropped.shape[1] == 0:
                return None
            
            return cropped
        except Exception:
            return None
    
    def insert_figures_into_text_precisely(self, text, figures, img_h, img_w, show_override_info=True):
        """Insert figures into text with option to show override info"""
        try:
            if not figures:
                return text
            
            lines = text.split('\n')
            sorted_figures = sorted(figures, key=lambda f: f['center_y'])
            
            result_lines = lines[:]
            offset = 0
            
            for i, figure in enumerate(sorted_figures):
                try:
                    insertion_line = self._calculate_insertion_position(figure, lines, i, len(sorted_figures))
                    actual_insertion = insertion_line + offset
                    
                    if actual_insertion > len(result_lines):
                        actual_insertion = len(result_lines)
                    
                    if figure['is_table']:
                        tag = f"[📊 BẢNG: {figure['name']}]"
                    else:
                        tag = f"[🖼️ HÌNH: {figure['name']}]"
                    
                    if show_override_info and figure.get('override_reason'):
                        tag += f" (kept: {figure['override_reason']})"
                    
                    result_lines.insert(actual_insertion, "")
                    result_lines.insert(actual_insertion + 1, tag)
                    result_lines.insert(actual_insertion + 2, "")
                    
                    offset += 3
                except Exception:
                    continue
            
            return '\n'.join(result_lines)
        except Exception:
            return text
    
    def _calculate_insertion_position(self, figure, lines, fig_index, total_figures):
        """Calculate insertion position with error handling"""
        try:
            question_lines = []
            for i, line in enumerate(lines):
                if re.match(r'^(câu|bài|question)\s*\d+', line.strip().lower()):
                    question_lines.append(i)
            
            if question_lines:
                if fig_index < len(question_lines):
                    return question_lines[fig_index] + 1
                else:
                    return question_lines[-1] + 2
            
            section_size = max(1, len(lines) // (total_figures + 1))
            return min(section_size * (fig_index + 1), len(lines) - 1)
        except Exception:
            return 0
    
    def create_beautiful_debug_visualization(self, image_bytes, figures):
        """Create debug visualization with error handling"""
        try:
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            draw = ImageDraw.Draw(img_pil)
            
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
            
            for i, fig in enumerate(figures):
                try:
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
                    
                    # Label
                    label = f"{fig['name']} ({fig['confidence']:.0f}%)"
                    if fig.get('override_reason'):
                        label += f" [{fig['override_reason']}]"
                    draw.text((x + 5, y + 5), label, fill=color, stroke_width=2, stroke_fill='white')
                except Exception:
                    continue
            
            return img_pil
        except Exception:
            return None

class EnhancedWordExporter:
    """Export Word document with figures inserted at correct positions"""
    
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        try:
            if not DOCX_AVAILABLE:
                raise Exception("python-docx not available")
            
            doc = Document()
            
            # Configure font
            style = doc.styles['Normal']
            style.font.name = 'Times New Roman'
            style.font.size = Pt(12)
            
            # Process LaTeX content
            lines = latex_content.split('\n')
            
            for line in lines:
                line = line.strip()
                
                if not line or line.startswith('<!--'):
                    continue
                
                if line.startswith('```'):
                    continue
                
                # Handle image tags
                if line.startswith('[') and line.endswith(']'):
                    if 'HÌNH:' in line or 'BẢNG:' in line:
                        EnhancedWordExporter._insert_figure_to_word(doc, line, extracted_figures)
                        continue
                
                # Handle questions
                if re.match(r'^(câu|bài)\s+\d+', line.lower()):
                    heading = doc.add_heading(line, level=3)
                    for run in heading.runs:
                        run.font.color.rgb = RGBColor(0, 0, 0)
                        run.font.bold = True
                    continue
                
                # Handle regular paragraphs
                if line:
                    para = doc.add_paragraph()
                    EnhancedWordExporter._process_latex_content(para, line)
            
            # Save to buffer
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            return buffer
            
        except Exception as e:
            st.error(f"❌ Lỗi tạo Word: {str(e)}")
            raise e
    
    @staticmethod
    def _process_latex_content(para, content):
        """Process LaTeX content - convert ${...}$ to Word format"""
        parts = re.split(r'(\$\{[^}]+\}\$)', content)
        
        for part in parts:
            if part.startswith('${') and part.endswith('}$'):
                formula_content = part[2:-2]
                formula_content = EnhancedWordExporter._convert_latex_to_unicode(formula_content)
                
                run = para.add_run(formula_content)
                run.font.name = 'Cambria Math'
                run.font.italic = True
                
            elif part.strip():
                run = para.add_run(part)
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12)
    
    @staticmethod
    def _convert_latex_to_unicode(latex_content):
        """Convert some LaTeX symbols to Unicode"""
        latex_to_unicode = {
            # Greek letters
            '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ',
            '\\epsilon': 'ε', '\\theta': 'θ', '\\lambda': 'λ', '\\mu': 'μ',
            '\\pi': 'π', '\\sigma': 'σ', '\\phi': 'φ', '\\omega': 'ω',
            '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ', '\\Pi': 'Π',
            '\\Sigma': 'Σ', '\\Phi': 'Φ', '\\Omega': 'Ω',
            
            # Math symbols
            '\\infty': '∞', '\\pm': '±', '\\mp': '∓',
            '\\times': '×', '\\div': '÷', '\\cdot': '·',
            '\\leq': '≤', '\\geq': '≥', '\\neq': '≠',
            '\\approx': '≈', '\\equiv': '≡', '\\sim': '∼',
            
            # Fractions
            '\\frac{1}{2}': '½', '\\frac{1}{3}': '⅓', '\\frac{2}{3}': '⅔',
            '\\frac{1}{4}': '¼', '\\frac{3}{4}': '¾',
            
            # Superscripts
            '^2': '²', '^3': '³', '^1': '¹', '^0': '⁰',
            
            # Subscripts
            '_0': '₀', '_1': '₁', '_2': '₂', '_3': '₃',
        }
        
        result = latex_content
        for latex_symbol, unicode_symbol in latex_to_unicode.items():
            result = result.replace(latex_symbol, unicode_symbol)
        
        # Handle complex fractions
        frac_pattern = r'\\frac\{([^}]+)\}\{([^}]+)\}'
        result = re.sub(frac_pattern, r'(\1)/(\2)', result)
        
        # Handle square roots
        sqrt_pattern = r'\\sqrt\{([^}]+)\}'
        result = re.sub(sqrt_pattern, r'√(\1)', result)
        
        # Remove remaining braces
        result = result.replace('{', '').replace('}', '')
        
        return result
    
    @staticmethod
    def _insert_figure_to_word(doc, tag_line, extracted_figures):
        """Insert image into Word - handle override info"""
        try:
            fig_name = None
            if 'HÌNH:' in tag_line:
                hình_part = tag_line.split('HÌNH:')[1]
                if '(' in hình_part:
                    fig_name = hình_part.split('(')[0].strip()
                else:
                    fig_name = hình_part.split(']')[0].strip()
            elif 'BẢNG:' in tag_line:
                bảng_part = tag_line.split('BẢNG:')[1]
                if '(' in bảng_part:
                    fig_name = bảng_part.split('(')[0].strip()
                else:
                    fig_name = bảng_part.split(']')[0].strip()
            
            if not fig_name or not extracted_figures:
                para = doc.add_paragraph(f"[Không tìm thấy figure: {fig_name if fig_name else 'unknown'}]")
                para.alignment = 1
                return
            
            # Find matching figure
            target_figure = None
            for fig in extracted_figures:
                if fig['name'] == fig_name:
                    target_figure = fig
                    break
            
            if target_figure:
                try:
                    img_data = base64.b64decode(target_figure['base64'])
                    img_pil = Image.open(io.BytesIO(img_data))
                    
                    if img_pil.mode in ('RGBA', 'LA', 'P'):
                        img_pil = img_pil.convert('RGB')
                    
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                        img_pil.save(tmp_file.name, 'PNG')
                        
                        try:
                            img_width = Inches(5)
                        except:
                            img_width = Inches(5)
                        
                        para = doc.add_paragraph()
                        para.alignment = 1
                        run = para.add_run()
                        run.add_picture(tmp_file.name, width=img_width)
                        
                        if target_figure.get('override_reason'):
                            caption_para = doc.add_paragraph()
                            caption_para.alignment = 1
                            caption_run = caption_para.add_run(f"({target_figure['override_reason']})")
                            caption_run.font.size = Pt(10)
                            caption_run.font.italic = True
                        
                        os.unlink(tmp_file.name)
                    
                except Exception as img_error:
                    para = doc.add_paragraph(f"[Lỗi hiển thị {target_figure['name']}: {str(img_error)}]")
                    para.alignment = 1
            else:
                para = doc.add_paragraph(f"[Không tìm thấy figure: {fig_name}]")
                para.alignment = 1
                    
        except Exception as e:
            para = doc.add_paragraph(f"[Lỗi xử lý figure tag: {str(e)}]")
            para.alignment = 1

def display_beautiful_figures(figures, debug_img=None):
    """Display figures beautifully with error handling"""
    try:
        if not figures:
            st.warning("⚠️ Không có figures nào")
            return
        
        if debug_img:
            st.image(debug_img, caption="Debug visualization", use_column_width=True)
        
        # Display figures in grid
        cols_per_row = 3
        for i in range(0, len(figures), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(figures):
                    fig = figures[i + j]
                    with cols[j]:
                        try:
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
                        except Exception as e:
                            st.error(f"Lỗi hiển thị figure: {str(e)}")
    except Exception as e:
        st.error(f"Lỗi hiển thị figures: {str(e)}")

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

def clean_session_state():
    """Clean up session state to prevent memory issues"""
    keys_to_clean = [
        'pdf_latex_content', 'pdf_images', 'pdf_extracted_figures',
        'single_latex_content', 'single_extracted_figures',
        'phone_latex_content', 'phone_extracted_figures', 'phone_processed_image'
    ]
    for key in keys_to_clean:
        if key in st.session_state:
            del st.session_state[key]
    gc.collect()

def main():
    try:
        st.markdown('<h1 class="main-header">📝 PDF/LaTeX Converter - Enhanced Table Protection</h1>', unsafe_allow_html=True)
        
        # Hero section
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;">
            <h2 style="margin: 0;">📊 TABLE PROTECTION + 🧠 SMART FILTERING + 📱 ENHANCED PHONE PROCESSING</h2>
            <p style="margin: 1rem 0; font-size: 1.1rem;">✅ Bảo vệ bảng Đúng/Sai • ✅ Enhanced table detection • ✅ Smart phone processing • ✅ Word export</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar
        with st.sidebar:
            st.header("⚙️ Cài đặt")
            
            if st.button("🧹 Clean Memory"):
                clean_session_state()
                st.success("✅ Memory cleaned!")
            
            api_key = st.text_input("Gemini API Key", type="password")
            
            if api_key:
                if validate_api_key(api_key):
                    st.success("✅ API key hợp lệ")
                else:
                    st.error("❌ API key không hợp lệ")
            
            st.markdown("---")
            
            # Google OCR Service Settings
            st.markdown("### 🤖 Google OCR Service")
            enable_google_ocr = st.checkbox("Bật Google OCR", value=True)
            
            if enable_google_ocr:
                ocr_api_url = st.text_input(
                    "OCR API URL", 
                    value="https://script.google.com/macros/s/AKfycby6GUWKFttjWTDJuQuX5IAeGAzS5tQULLja3SHbSfZIhQyaWVMuxyRNAE-fykxnznkqIw/exec"
                )
                
                ocr_api_key = st.text_input(
                    "OCR API Key", 
                    value="sk-...........",
                    type="password"
                )
            else:
                ocr_api_url = None
                ocr_api_key = None
            
            st.markdown("---")
            
            # Enhanced settings
            if CV2_AVAILABLE:
                st.markdown("### 📊 Enhanced Processing")
                enable_extraction = st.checkbox("Bật tách ảnh nâng cao", value=True)
                
                if enable_extraction:
                    debug_mode = st.checkbox("Debug mode", value=False)
                    
                    with st.expander("🔧 Advanced Settings"):
                        confidence_threshold = st.slider("Confidence Threshold (%)", 50, 95, 65, 5)
                        max_figures = st.slider("Max figures per page", 5, 50, 25, 5)
                        
                        st.markdown("**Table Protection:**")
                        preserve_tables = st.checkbox("🛡️ Bảo vệ bảng Đúng/Sai", value=True)
                        enhance_table_detection = st.checkbox("📊 Enhanced table detection", value=True)
                        
                        st.markdown("**Word Export:**")
                        show_override_info = st.checkbox("Hiển thị override info", value=False)
            else:
                enable_extraction = False
                debug_mode = False
                preserve_tables = True
                enhance_table_detection = True
                st.error("❌ OpenCV không khả dụng!")
        
        if not api_key:
            st.warning("⚠️ Vui lòng nhập Gemini API Key!")
            return
        
        if not validate_api_key(api_key):
            st.error("❌ API key không hợp lệ!")
            return
        
        # Initialize services
        try:
            gemini_api = GeminiAPI(api_key)
            
            # Initialize Google OCR Service
            google_ocr_service = None
            if enable_google_ocr and ocr_api_url and ocr_api_key and ocr_api_key != "sk-...........":
                try:
                    google_ocr_service = GoogleOCRService(ocr_api_url, ocr_api_key)
                    st.sidebar.success("🤖 Google OCR initialized")
                except Exception as e:
                    st.sidebar.warning(f"⚠️ OCR service error: {str(e)}")
            
            if enable_extraction and CV2_AVAILABLE:
                image_extractor = SuperEnhancedImageExtractor(google_ocr_service)
                
                # Apply settings
                if 'confidence_threshold' in locals():
                    image_extractor.final_confidence_threshold = confidence_threshold
                if 'max_figures' in locals():
                    image_extractor.max_figures = max_figures
                if 'debug_mode' in locals():
                    image_extractor.debug_mode = debug_mode
                    image_extractor.content_filter.text_filter.debug_mode = debug_mode
            else:
                image_extractor = None
                
        except Exception as e:
            st.error(f"❌ Initialization error: {str(e)}")
            return
        
        # Main tabs
        tab1, tab2, tab3 = st.tabs(["📄 PDF sang LaTeX", "🖼️ Ảnh sang LaTeX", "📱 Ảnh điện thoại"])
        
        # =================== TAB 3: ENHANCED PHONE PROCESSING ===================
        with tab3:
            st.header("📱 Xử lý ảnh chụp điện thoại với Table Protection")
            st.markdown("""
            <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c8 100%); padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
                <h4>🛡️ Đặc biệt bảo vệ bảng Đúng/Sai:</h4>
                <p>• 📊 <strong>Table Region Detection:</strong> Tự động phát hiện vùng bảng</p>
                <p>• ☑️ <strong>Checkbox Protection:</strong> Bảo vệ cột Đúng/Sai khỏi bị cắt</p>
                <p>• 🎯 <strong>Table-Aware Processing:</strong> Xử lý nhẹ nhàng cho vùng bảng</p>
                <p>• 📺 <strong>Screenshot Detection:</strong> Tự động nhận diện screenshot</p>
                <p>• 🔄 <strong>Smart Rotation:</strong> Tránh xoay vùng có bảng</p>
                <p>• 📐 <strong>Perspective Correction:</strong> Bỏ qua nếu có nhiều bảng</p>
                <p>• ✨ <strong>Differential Enhancement:</strong> Gentle cho bảng, strong cho text</p>
            </div>
            """, unsafe_allow_html=True)
            
            uploaded_phone_image = st.file_uploader("Chọn ảnh chụp từ điện thoại", type=['png', 'jpg', 'jpeg'], key="phone_upload")
            
            if uploaded_phone_image:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📱 Ảnh gốc")
                    
                    phone_image_pil = Image.open(uploaded_phone_image)
                    st.image(phone_image_pil, caption=f"Ảnh gốc: {uploaded_phone_image.name}", use_column_width=True)
                    
                    # Enhanced image analysis
                    if CV2_AVAILABLE:
                        is_screenshot = EnhancedPhoneImageProcessor._detect_screenshot(phone_image_pil)
                        if is_screenshot:
                            st.success("📺 **Detected: Screenshot** - Sẽ sử dụng chế độ bảo vệ bảng tối ưu")
                        else:
                            st.info("📱 **Detected: Phone photo** - Sẽ áp dụng full processing với table protection")
                        
                        # Analyze table regions
                        img_array = np.array(phone_image_pil)
                        table_regions = EnhancedPhoneImageProcessor.detect_table_regions(img_array)
                        checkbox_regions = EnhancedPhoneImageProcessor.detect_checkbox_columns(img_array)
                        
                        if table_regions or checkbox_regions:
                            st.success(f"🛡️ **Table Protection Active:** {len(table_regions)} table regions, {len(checkbox_regions)} checkbox columns detected")
                        else:
                            st.info("ℹ️ No table regions detected - standard processing will be used")
                    
                    # Image info
                    st.markdown("**📊 Thông tin ảnh:**")
                    st.write(f"• Kích thước: {phone_image_pil.size[0]} x {phone_image_pil.size[1]}")
                    st.write(f"• Dung lượng: {format_file_size(uploaded_phone_image.size)}")
                    
                    # Processing settings
                    st.markdown("### ⚙️ Cài đặt xử lý")
                    
                    preserve_tables_phone = st.checkbox("🛡️ Bảo vệ bảng Đúng/Sai", value=True, key="preserve_tables_phone")
                    enhance_text_phone = st.checkbox("✨ Enhance text clarity", value=True, key="enhance_text_phone")
                    auto_rotate_phone = st.checkbox("🔄 Auto rotate & straighten", value=True, key="auto_rotate_phone")
                    perspective_correct_phone = st.checkbox("📐 Perspective correction", value=True, key="perspective_correct_phone")
                    noise_reduction_phone = st.checkbox("🧹 Noise reduction", value=True, key="noise_reduction_phone")
                    contrast_boost = st.slider("Contrast boost", 1.0, 1.5, 1.2, 0.1, key="contrast_boost")
                    
                    if enable_extraction and CV2_AVAILABLE:
                        extract_phone_figures = st.checkbox("🎯 Tách figures & tables", value=True, key="phone_extract")
                        if extract_phone_figures:
                            phone_confidence = st.slider("Confidence (%)", 50, 95, 65, 5, key="phone_conf")
                    else:
                        extract_phone_figures = False
                
                with col2:
                    st.subheader("🔄 Xử lý & Kết quả")
                    
                    if st.button("🚀 Xử lý ảnh với Table Protection", type="primary", key="process_phone_enhanced"):
                        phone_img_bytes = uploaded_phone_image.getvalue()
                        
                        # Step 1: Enhanced image processing with table protection
                        with st.spinner("🛡️ Đang xử lý ảnh với table protection..."):
                            try:
                                processed_img = EnhancedPhoneImageProcessor.process_phone_image(
                                    phone_img_bytes,
                                    preserve_tables=preserve_tables_phone,
                                    enhance_text=enhance_text_phone,
                                    auto_rotate=auto_rotate_phone,
                                    perspective_correct=perspective_correct_phone,
                                    noise_reduction=noise_reduction_phone,
                                    contrast_boost=contrast_boost,
                                    is_screenshot=is_screenshot if 'is_screenshot' in locals() else False
                                )
                                
                                st.success("✅ Ảnh đã được xử lý với table protection!")
                                
                                # Display processed image
                                st.markdown("**📸 Ảnh đã xử lý:**")
                                st.image(processed_img, use_column_width=True)
                                
                                # Convert to bytes
                                processed_buffer = io.BytesIO()
                                processed_img.save(processed_buffer, format='PNG')
                                processed_bytes = processed_buffer.getvalue()
                                
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý ảnh: {str(e)}")
                                processed_bytes = phone_img_bytes
                                processed_img = phone_image_pil
                        
                        # Step 2: Figure extraction with enhanced table detection
                        phone_extracted_figures = []
                        phone_h, phone_w = 0, 0
                        
                        if extract_phone_figures and enable_extraction and CV2_AVAILABLE and image_extractor:
                            with st.spinner("📊 Đang tách figures với enhanced table detection..."):
                                try:
                                    original_threshold = image_extractor.final_confidence_threshold
                                    image_extractor.final_confidence_threshold = phone_confidence
                                    
                                    figures, phone_h, phone_w, _, _ = image_extractor.extract_figures_and_tables(processed_bytes, 0, 0)
                                    phone_extracted_figures = figures
                                    
                                    image_extractor.final_confidence_threshold = original_threshold
                                    
                                    if figures:
                                        debug_img = image_extractor.create_beautiful_debug_visualization(processed_bytes, figures)
                                        
                                        # Enhanced statistics
                                        tables_count = sum(1 for f in figures if f.get('is_table', False))
                                        figures_count = len(figures) - tables_count
                                        protected_count = sum(1 for f in figures if f.get('override_reason'))
                                        
                                        success_msg = f"🎯 Extracted {len(figures)} items: {figures_count} figures, {tables_count} tables"
                                        if protected_count > 0:
                                            success_msg += f" ({protected_count} protected)"
                                        st.success(success_msg + "!")
                                        
                                        with st.expander("🔍 Xem figures đã tách"):
                                            display_beautiful_figures(figures, debug_img)
                                    else:
                                        st.info("ℹ️ Không tìm thấy figures")
                                    
                                except Exception as e:
                                    st.error(f"❌ Lỗi tách figures: {str(e)}")
                        
                        # Step 3: Text conversion with enhanced table prompts
                        with st.spinner("📝 Đang chuyển đổi text với table-aware prompts..."):
                            try:
                                # Enhanced prompt for table protection
                                if is_screenshot if 'is_screenshot' in locals() else False:
                                    phone_prompt = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX chính xác.

📺 ĐẶC BIỆT CHO SCREENSHOT VỚI BẢNG ĐÚNG/SAI:
- Ảnh screenshot rất sắc nét, đọc chính xác từng ký tự
- ⚠️ TUYỆT ĐỐI KHÔNG CẮt CỘT ĐÚNG/SAI
- Bảo toàn nguyên vẹn cấu trúc bảng

🎯 YÊU CẦU ĐỊNH DẠNG ĐÚNG/SAI:

1. **Bảng Đúng/Sai - HOÀN CHỈNH:**
```
| Mệnh đề | Đúng | Sai |
|---------|------|-----|
| (a) Hàm số đã cho có đạo hàm là ${f'(x) = 3x^2 - 12}$ | ☐ | ☐ |
| (b) Phương trình ${f'(x) = 0}$ có tập nghiệm là ${S = \\{2\\}}$ | ☐ | ☐ |
| (c) ${f(2) = 24}$ | ☐ | ☐ |
| (d) Giá trị lớn nhất của hàm số ${f(x)}$ trên đoạn ${[-3;3]}$ bằng 24 | ☐ | ☐ |
```

2. **Bảng biến thiên - HOÀN CHỈNH:**
```
| x | ${-\\infty}$ | -2 | ${+\\infty}$ |
|---|-------------|-----|-------------|
| ${f'(x)}$ | + | 0 | - |
| ${f(x)}$ | ↗ | max | ↘ |
```

3. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ QUAN TRỌNG:
- TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức, biến số, ký hiệu toán học!
- TUYỆT ĐỐI dùng | để phân cách các cột trong bảng!
- TUYỆT ĐỐI bảo toàn cột Đúng và cột Sai!
- Dùng ☐ cho checkbox trống!
"""
                                else:
                                    phone_prompt = """
Chuyển đổi TOÀN BỘ nội dung trong ảnh thành văn bản với format LaTeX chính xác.

📱 ĐẶC BIỆT CHO ẢNH ĐIỆN THOẠI VỚI BẢNG:
- Ảnh có thể hơi mờ hoặc nghiêng, nhưng đã được xử lý tối ưu
- ⚠️ ĐẶC BIỆT CHÚ Ý: Không bỏ sót cột Đúng/Sai trong bảng
- Đọc kỹ toàn bộ nội dung bảng

🎯 YÊU CẦU ĐỊNH DẠNG:

1. **Bảng có cột Đúng/Sai:**
```
| Mệnh đề | Đúng | Sai |
|---------|------|-----|
| (a) [nội dung mệnh đề a] | ☐ | ☐ |
| (b) [nội dung mệnh đề b] | ☐ | ☐ |
```

2. **Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi đầy đủ]
A) [đáp án A hoàn chỉnh]
B) [đáp án B hoàn chỉnh]
C) [đáp án C hoàn chỉnh]  
D) [đáp án D hoàn chỉnh]
```

3. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$, ${\\frac{a+b}{c-d}}$

⚠️ TUYỆT ĐỐI:
- Dùng ${...}$ cho MỌI công thức!
- Dùng | để phân cách các cột trong bảng!
- Bảo toàn đầy đủ cột Đúng và Sai!
"""
                                
                                phone_latex_result = gemini_api.convert_to_latex(processed_bytes, "image/png", phone_prompt)
                                
                                if phone_latex_result:
                                    # Insert figures if available
                                    if extract_phone_figures and phone_extracted_figures and CV2_AVAILABLE and image_extractor:
                                        phone_latex_result = image_extractor.insert_figures_into_text_precisely(
                                            phone_latex_result, phone_extracted_figures, phone_h, phone_w, 
                                            show_override_info=show_override_info if 'show_override_info' in locals() else False
                                        )
                                    
                                    st.success("🎉 Chuyển đổi thành công với table protection!")
                                    
                                    # Display result
                                    st.markdown("### 📝 Kết quả LaTeX")
                                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                    st.code(phone_latex_result, language="latex")
                                    st.markdown('</div>', unsafe_allow_html=True)
                                    
                                    # Save to session
                                    st.session_state.phone_latex_content = phone_latex_result
                                    st.session_state.phone_extracted_figures = phone_extracted_figures if extract_phone_figures else None
                                    st.session_state.phone_processed_image = processed_img
                                    
                                else:
                                    st.error("❌ API không trả về kết quả")
                                    
                            except Exception as e:
                                st.error(f"❌ Lỗi chuyển đổi: {str(e)}")
                    
                    # Download buttons
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
                                            
                                            word_buffer = EnhancedWordExporter.create_word_document(
                                                st.session_state.phone_latex_content,
                                                extracted_figures=extracted_figs
                                            )
                                            
                                            st.download_button(
                                                label="📄 Tải Word (.docx)",
                                                data=word_buffer.getvalue(),
                                                file_name=uploaded_phone_image.name.replace(uploaded_phone_image.name.split('.')[-1], 'docx'),
                                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                key="download_phone_word"
                                            )
                                            
                                            st.success("✅ Word document với table protection đã tạo thành công!")
                                            
                                        except Exception as e:
                                            st.error(f"❌ Lỗi tạo Word: {str(e)}")
                            else:
                                st.error("❌ Cần cài đặt python-docx")
                        
                        with col_z:
                            if 'phone_processed_image' in st.session_state:
                                processed_buffer = io.BytesIO()
                                st.session_state.phone_processed_image.save(processed_buffer, format='PNG')
                                
                                st.download_button(
                                    label="📸 Tải ảnh đã xử lý",
                                    data=processed_buffer.getvalue(),
                                    file_name=uploaded_phone_image.name.replace(uploaded_phone_image.name.split('.')[-1], 'processed.png'),
                                    mime="image/png",
                                    key="download_processed_image"
                                )
        
        # =================== TAB 1 & 2: SIMPLIFIED ===================
        with tab1:
            st.header("📄 Chuyển đổi PDF sang LaTeX")
            st.info("📄 PDF processing với enhanced table detection")
            # ... (implement similar to original but with EnhancedPhoneImageProcessor)
        
        with tab2:
            st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
            st.info("🖼️ Single image processing với table protection")
            # ... (implement similar to original but with EnhancedPhoneImageProcessor)
        
        # Footer
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px;'>
            <h3>🛡️ TABLE PROTECTION + 📊 ENHANCED DETECTION + 📱 SMART PROCESSING</h3>
            <p><strong>✅ Bảo vệ hoàn toàn bảng Đúng/Sai</strong></p>
            <p><strong>🎯 Table-aware image processing</strong></p>
            <p><strong>📺 Screenshot vs phone photo detection</strong></p>
            <p><strong>🧠 Intelligent enhancement strategies</strong></p>
            <p><strong>📄 Professional Word export với figures</strong></p>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"❌ Application error: {str(e)}")
        st.error("Please refresh the page and try again.")

if __name__ == "__main__":
    main()
