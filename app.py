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
    page_title="PDF/LaTeX Converter - Smart Figure Detection",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enhanced CSS
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
        max-height: 500px;
        overflow-y: auto;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .figure-container {
        border: 3px solid #28a745;
        border-radius: 12px;
        margin: 15px 0;
        padding: 10px;
        background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    
    .protection-alert {
        background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c8 100%);
        border: 2px solid #28a745;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class SmartTableClassifier:
    """Phân loại thông minh: Bảng Đúng/Sai vs Figures minh họa"""
    
    @staticmethod
    def classify_table_type(img_region):
        """Phân loại loại bảng: content (Đúng/Sai) vs illustration (biến thiên, etc.)"""
        try:
            h, w = img_region.shape[:2] if len(img_region.shape) == 3 else img_region.shape
            
            # Detect True/False table characteristics
            is_true_false = SmartTableClassifier._detect_true_false_pattern(img_region)
            
            # Detect illustration table characteristics  
            is_illustration = SmartTableClassifier._detect_illustration_pattern(img_region)
            
            if is_true_false:
                return "true_false_table"  # KHÔNG cắt
            elif is_illustration:
                return "illustration_table"  # CÓ THỂ cắt
            else:
                return "unknown_table"  # CÓ THỂ cắt
                
        except Exception:
            return "unknown_table"
    
    @staticmethod
    def _detect_true_false_pattern(img_region):
        """Detect pattern của bảng Đúng/Sai"""
        try:
            h, w = img_region.shape[:2] if len(img_region.shape) == 3 else img_region.shape
            
            # Look for multiple rows with similar structure
            gray = cv2.cvtColor(img_region, cv2.COLOR_RGB2GRAY) if len(img_region.shape) == 3 else img_region
            
            # Detect horizontal lines (rows)
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//10, 1))
            horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
            
            # Count horizontal line segments
            contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            horizontal_count = len([c for c in contours if cv2.contourArea(c) > 100])
            
            # Detect small rectangular regions (checkboxes)
            checkbox_count = SmartTableClassifier._count_checkbox_patterns(gray)
            
            # True/False tables typically have:
            # - Multiple horizontal lines (3-10)
            # - Multiple checkbox-like patterns (4-20)
            # - Aspect ratio suggesting text rows
            aspect_ratio = w / max(h, 1)
            
            is_true_false = (
                3 <= horizontal_count <= 10 and 
                checkbox_count >= 4 and
                1.5 <= aspect_ratio <= 6.0  # Wide table with text
            )
            
            return is_true_false
            
        except Exception:
            return False
    
    @staticmethod
    def _detect_illustration_pattern(img_region):
        """Detect pattern của bảng minh họa (biến thiên, đồ thị, etc.)"""
        try:
            h, w = img_region.shape[:2] if len(img_region.shape) == 3 else img_region.shape
            gray = cv2.cvtColor(img_region, cv2.COLOR_RGB2GRAY) if len(img_region.shape) == 3 else img_region
            
            # Look for mathematical symbols, arrows, graphs
            # Detect curves and non-linear patterns
            edges = cv2.Canny(gray, 30, 100)
            
            # Count non-rectangular contours (curves, arrows)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            curved_count = 0
            for contour in contours:
                # Calculate contour complexity
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # More vertices = more complex shape = likely illustration
                if len(approx) > 6:
                    curved_count += 1
            
            # Mathematical illustration tables typically have:
            # - Complex shapes (arrows, curves)
            # - Less regular structure than True/False tables
            # - May be more compact
            
            aspect_ratio = w / max(h, 1)
            total_contours = len(contours)
            curve_ratio = curved_count / max(total_contours, 1)
            
            is_illustration = (
                curve_ratio > 0.3 or  # Many complex shapes
                aspect_ratio < 1.2 or aspect_ratio > 8.0  # Very tall or very wide
            )
            
            return is_illustration
            
        except Exception:
            return False
    
    @staticmethod
    def _count_checkbox_patterns(gray):
        """Count checkbox-like rectangular patterns"""
        try:
            # Find small rectangular contours
            contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            checkbox_count = 0
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                aspect_ratio = w / max(h, 1)
                
                # Checkbox characteristics: small, roughly square
                if (50 <= area <= 1000 and 0.5 <= aspect_ratio <= 2.0):
                    checkbox_count += 1
            
            return checkbox_count
            
        except Exception:
            return 0

class SuperEnhancedImageExtractor:
    """Tách ảnh thông minh: Chỉ cắt figures minh họa, bảo vệ bảng Đúng/Sai"""
    
    def __init__(self):
        # Basic parameters
        self.min_area_ratio = 0.001
        self.min_area_abs = 500
        self.min_width = 30
        self.min_height = 30
        self.max_figures = 20
        self.max_area_ratio = 0.75
        
        # Confidence thresholds
        self.confidence_threshold = 20
        self.final_confidence_threshold = 60
        
        # Debug mode
        self.debug_mode = False
    
    def extract_illustration_figures(self, image_bytes, start_img_idx=0, start_table_idx=0):
        """Tách chỉ figures minh họa, bảo vệ bảng Đúng/Sai"""
        if not CV2_AVAILABLE:
            return [], 0, 0, start_img_idx, start_table_idx
        
        try:
            if not image_bytes or len(image_bytes) == 0:
                return [], 0, 0, start_img_idx, start_table_idx
            
            # Load and prepare image
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            max_size = (2500, 2500)
            if img_pil.size[0] > max_size[0] or img_pil.size[1] > max_size[1]:
                img_pil.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            if h == 0 or w == 0:
                return [], 0, 0, start_img_idx, start_table_idx
            
            # Enhanced preprocessing
            enhanced_img = self._enhance_image(img)
            
            # Multiple detection methods
            all_candidates = []
            
            # Edge detection
            try:
                edge_candidates = self._detect_by_edges(enhanced_img, w, h)
                all_candidates.extend(edge_candidates)
            except Exception as e:
                if self.debug_mode:
                    st.warning(f"Edge detection error: {str(e)}")
            
            # Contour detection
            try:
                contour_candidates = self._detect_by_contours(enhanced_img, w, h)
                all_candidates.extend(contour_candidates)
            except Exception as e:
                if self.debug_mode:
                    st.warning(f"Contour detection error: {str(e)}")
            
            # Grid detection for tables/figures
            try:
                grid_candidates = self._detect_by_grid(enhanced_img, w, h)
                all_candidates.extend(grid_candidates)
            except Exception as e:
                if self.debug_mode:
                    st.warning(f"Grid detection error: {str(e)}")
            
            # Filter and classify candidates
            filtered_candidates = self._filter_and_classify_candidates(all_candidates, img, w, h)
            
            # Create final figures (only illustrations)
            final_figures, final_img_idx, final_table_idx = self._create_final_figures(
                filtered_candidates, img, w, h, start_img_idx, start_table_idx
            )
            
            return final_figures, h, w, final_img_idx, final_table_idx
            
        except Exception as e:
            st.error(f"❌ Extraction error: {str(e)}")
            return [], 0, 0, start_img_idx, start_table_idx
    
    def _enhance_image(self, img):
        """Enhanced preprocessing"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(blurred)
            return cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
        except Exception:
            return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
    
    def _detect_by_edges(self, gray_img, w, h):
        """Edge-based detection"""
        try:
            edges = cv2.Canny(gray_img, 30, 90)
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
                            'confidence': 30
                        })
                except Exception:
                    continue
            
            return candidates
        except Exception:
            return []
    
    def _detect_by_contours(self, gray_img, w, h):
        """Contour-based detection"""
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
                            'confidence': 35
                        })
                except Exception:
                    continue
            
            return candidates
        except Exception:
            return []
    
    def _detect_by_grid(self, gray_img, w, h):
        """Grid-based detection for tables and structured content"""
        try:
            # Horizontal lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//15, 1))
            horizontal_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, horizontal_kernel)
            
            # Vertical lines
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//20))
            vertical_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, vertical_kernel)
            
            # Combine
            grid_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            grid_dilated = cv2.dilate(grid_mask, kernel, iterations=1)
            
            contours, _ = cv2.findContours(grid_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            candidates = []
            for cnt in contours:
                try:
                    x, y, ww, hh = cv2.boundingRect(cnt)
                    area = ww * hh
                    
                    if self._is_valid_candidate(x, y, ww, hh, area, w, h):
                        aspect_ratio = ww / max(hh, 1)
                        confidence = 40
                        
                        # Higher confidence for table-like structures
                        if aspect_ratio > 1.5:
                            confidence = 60
                        
                        candidates.append({
                            'bbox': (x, y, ww, hh),
                            'area': area,
                            'method': 'grid',
                            'confidence': confidence,
                            'aspect_ratio': aspect_ratio
                        })
                except Exception:
                    continue
            
            return candidates
        except Exception:
            return []
    
    def _is_valid_candidate(self, x, y, ww, hh, area, img_w, img_h):
        """Validate candidate"""
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
            
            # Avoid edge regions
            edge_margin = 0.01
            if (x < edge_margin * img_w or 
                y < edge_margin * img_h or 
                (x + ww) > (1 - edge_margin) * img_w or 
                (y + hh) > (1 - edge_margin) * img_h):
                return False
            
            return True
        except Exception:
            return False
    
    def _filter_and_classify_candidates(self, candidates, img, w, h):
        """Filter and classify candidates using smart table classifier"""
        try:
            if not candidates:
                return []
            
            # Remove overlapping candidates
            candidates = sorted(candidates, key=lambda x: x.get('area', 0), reverse=True)
            filtered = []
            
            for candidate in candidates:
                try:
                    if not self._is_overlapping_with_list(candidate, filtered):
                        # Calculate confidence
                        candidate['final_confidence'] = self._calculate_final_confidence(candidate, w, h)
                        
                        if candidate['final_confidence'] >= self.confidence_threshold:
                            # Classify table type
                            x, y, ww, hh = candidate['bbox']
                            roi = img[y:y+hh, x:x+ww]
                            table_type = SmartTableClassifier.classify_table_type(roi)
                            
                            candidate['table_type'] = table_type
                            
                            # Only keep illustration tables and unknown tables
                            if table_type in ['illustration_table', 'unknown_table']:
                                candidate['extractable'] = True
                                filtered.append(candidate)
                            else:
                                # Mark as protected (True/False table)
                                candidate['extractable'] = False
                                candidate['protection_reason'] = 'True/False table - content protection'
                                
                                if self.debug_mode:
                                    st.info(f"🛡️ Protected: True/False table detected")
                
                except Exception:
                    continue
            
            return filtered[:self.max_figures]
        except Exception:
            return []
    
    def _is_overlapping_with_list(self, candidate, existing_list):
        """Check overlap"""
        try:
            x1, y1, w1, h1 = candidate['bbox']
            
            for existing in existing_list:
                x2, y2, w2, h2 = existing['bbox']
                
                intersection_area = max(0, min(x1+w1, x2+w2) - max(x1, x2)) * max(0, min(y1+h1, y2+h2) - max(y1, y2))
                union_area = w1*h1 + w2*h2 - intersection_area
                
                if union_area > 0:
                    iou = intersection_area / union_area
                    if iou > 0.3:
                        return True
            
            return False
        except Exception:
            return False
    
    def _calculate_final_confidence(self, candidate, w, h):
        """Calculate final confidence"""
        try:
            x, y, ww, hh = candidate['bbox']
            area_ratio = candidate['area'] / max(w * h, 1)
            aspect_ratio = ww / max(hh, 1)
            
            confidence = candidate.get('confidence', 25)
            
            # Bonus for good size
            if 0.01 < area_ratio < 0.6:
                confidence += 25
            elif 0.005 < area_ratio < 0.8:
                confidence += 15
            
            # Bonus for reasonable aspect ratio
            if 0.3 < aspect_ratio < 5.0:
                confidence += 20
            elif 0.2 < aspect_ratio < 8.0:
                confidence += 10
            
            # Method bonus
            if candidate['method'] == 'grid':
                confidence += 20
            elif candidate['method'] == 'edge':
                confidence += 10
            
            return min(100, confidence)
        except Exception:
            return 25
    
    def _create_final_figures(self, candidates, img, w, h, start_img_idx=0, start_table_idx=0):
        """Create final extractable figures"""
        try:
            # Filter by confidence
            candidates = sorted(candidates, key=lambda x: (x['bbox'][1], x['bbox'][0]))
            high_confidence = [c for c in candidates if c.get('final_confidence', 0) >= self.final_confidence_threshold]
            
            if self.debug_mode and len(candidates) > 0:
                st.write(f"🎯 Confidence Filter: {len(high_confidence)}/{len(candidates)} figures above {self.final_confidence_threshold}%")
            
            final_figures = []
            img_idx = start_img_idx
            table_idx = start_table_idx
            
            for candidate in high_confidence:
                try:
                    if not candidate.get('extractable', True):
                        continue
                    
                    cropped_img = self._smart_crop(img, candidate, w, h)
                    if cropped_img is None:
                        continue
                    
                    # Convert to base64
                    buf = io.BytesIO()
                    Image.fromarray(cropped_img).save(buf, format="JPEG", quality=95)
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    
                    # Determine type
                    is_table = (candidate.get('method') == 'grid' or 
                              candidate.get('table_type') == 'illustration_table')
                    
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
                        "table_type": candidate.get("table_type", "unknown"),
                        "method": candidate["method"]
                    })
                    
                except Exception as e:
                    if self.debug_mode:
                        st.warning(f"Error creating figure: {str(e)}")
                    continue
            
            return final_figures, img_idx, table_idx
        except Exception:
            return [], start_img_idx, start_table_idx
    
    def _smart_crop(self, img, candidate, img_w, img_h):
        """Smart cropping with padding"""
        try:
            x, y, w, h = candidate['bbox']
            
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
                return None
            
            # Add padding
            padding = 15
            padding_x = min(padding, w // 5)
            padding_y = min(padding, h // 5)
            
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
    
    def insert_figures_into_text(self, text, figures, img_h, img_w):
        """Insert figures into text at appropriate positions"""
        try:
            if not figures:
                return text
            
            lines = text.split('\n')
            sorted_figures = sorted(figures, key=lambda f: f['bbox'][1])  # Sort by y position
            
            result_lines = lines[:]
            offset = 0
            
            for i, figure in enumerate(sorted_figures):
                try:
                    # Calculate insertion position
                    relative_y = figure['bbox'][1] / img_h
                    insertion_line = int(relative_y * len(lines))
                    insertion_line = max(0, min(insertion_line, len(lines) - 1))
                    
                    actual_insertion = insertion_line + offset
                    if actual_insertion > len(result_lines):
                        actual_insertion = len(result_lines)
                    
                    # Create figure tag
                    if figure['is_table']:
                        tag = f"[📊 BẢNG MINH HỌA: {figure['name']}]"
                    else:
                        tag = f"[🖼️ HÌNH MINH HỌA: {figure['name']}]"
                    
                    # Insert figure reference
                    result_lines.insert(actual_insertion, "")
                    result_lines.insert(actual_insertion + 1, tag)
                    result_lines.insert(actual_insertion + 2, "")
                    
                    offset += 3
                    
                except Exception:
                    continue
            
            return '\n'.join(result_lines)
        except Exception:
            return text

class EnhancedPhoneImageProcessor:
    """Enhanced processing cho ảnh điện thoại"""
    
    @staticmethod
    def process_phone_image(image_bytes, preserve_tables=True, enhance_text=True, 
                           auto_rotate=True, contrast_boost=1.2):
        """Process phone image với bảo vệ bảng Đúng/Sai"""
        try:
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            if CV2_AVAILABLE:
                img = np.array(img_pil)
                
                # Detect True/False tables for protection
                protected_regions = []
                if preserve_tables:
                    protected_regions = EnhancedPhoneImageProcessor._detect_protected_regions(img)
                
                # Apply gentle processing
                if len(protected_regions) > 0:
                    img = EnhancedPhoneImageProcessor._gentle_processing(img, protected_regions)
                else:
                    img = EnhancedPhoneImageProcessor._standard_processing(img, enhance_text, auto_rotate, contrast_boost)
                
                processed_img = Image.fromarray(img)
            else:
                # Fallback PIL processing
                processed_img = img_pil
                if enhance_text:
                    enhancer = ImageEnhance.Contrast(processed_img)
                    processed_img = enhancer.enhance(contrast_boost)
            
            return processed_img
            
        except Exception as e:
            st.error(f"❌ Processing error: {str(e)}")
            return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    @staticmethod
    def _detect_protected_regions(img):
        """Detect regions that should be protected (True/False tables)"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
            h, w = gray.shape
            
            # Look for True/False table patterns
            protected_regions = []
            
            # Simple table detection
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//12, 1))
            horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
            
            contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                area = w_cont * h_cont
                
                if area > (w * h * 0.02):  # Significant area
                    roi = gray[y:y+h_cont, x:x+w_cont]
                    table_type = SmartTableClassifier.classify_table_type(roi)
                    
                    if table_type == "true_false_table":
                        protected_regions.append((x, y, w_cont, h_cont))
            
            return protected_regions
            
        except Exception:
            return []
    
    @staticmethod
    def _gentle_processing(img, protected_regions):
        """Gentle processing when True/False tables are present"""
        try:
            # Very minimal processing
            img = cv2.bilateralFilter(img, 3, 30, 30)
            return img
        except Exception:
            return img
    
    @staticmethod
    def _standard_processing(img, enhance_text, auto_rotate, contrast_boost):
        """Standard processing when no protected content"""
        try:
            # Noise reduction
            img = cv2.bilateralFilter(img, 5, 50, 50)
            
            # Text enhancement
            if enhance_text:
                lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
                l, a, b = cv2.split(lab)
                
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                l = clahe.apply(l)
                
                img = cv2.merge([l, a, b])
                img = cv2.cvtColor(img, cv2.COLOR_LAB2RGB)
            
            # Gentle rotation if needed
            if auto_rotate:
                img = EnhancedPhoneImageProcessor._gentle_auto_rotate(img)
            
            return img
        except Exception:
            return img
    
    @staticmethod
    def _gentle_auto_rotate(img):
        """Gentle auto rotation"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
            
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
                    
                    if abs(angle) < 20:
                        angles.append(angle)
                
                if angles:
                    rotation_angle = np.median(angles)
                    if abs(rotation_angle) > 1:
                        center = (img.shape[1]//2, img.shape[0]//2)
                        M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
                        img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), 
                                           borderMode=cv2.BORDER_CONSTANT,
                                           borderValue=(255, 255, 255))
            
            return img
        except Exception:
            return img

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
            raise Exception("Image quá lớn (>20MB)")
        
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
                        raise Exception("API không trả về kết quả")
                elif response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise Exception("Rate limit exceeded")
                else:
                    raise Exception(f"API Error {response.status_code}")
            
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception("Request timeout")
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception(str(e))

class PDFProcessor:
    @staticmethod
    def extract_images_from_pdf(pdf_file, max_pages=None):
        """Extract images from PDF with memory management"""
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
                    # Convert to image
                    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    pix = None
                    
                    img = Image.open(io.BytesIO(img_data))
                    
                    # Resize if too large
                    max_size = (2000, 2000)
                    if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    images.append((img, page_num + 1))
                    
                    # Memory cleanup
                    if page_num % 5 == 0:
                        gc.collect()
                        
                except Exception as e:
                    st.warning(f"Error processing page {page_num + 1}: {str(e)}")
                    continue
            
            pdf_document.close()
            return images
            
        except Exception as e:
            raise Exception(f"PDF reading error: {str(e)}")

def create_enhanced_prompt(has_illustrations=False):
    """Create enhanced prompt for LaTeX conversion"""
    
    base_prompt = """
🎯 CHUYỂN ĐỔI TOÀN BỘ NỘI DUNG THÀNH LATEX

⚠️ **QUY TẮC QUAN TRỌNG:**

1. **Bảng Đúng/Sai - TUYỆT ĐỐI KHÔNG CẮT:**
```
| Mệnh đề | Đúng | Sai |
|---------|------|-----|
| (a) Hàm số đã cho có đạo hàm là ${f'(x) = 3x^2 - 12}$ | ☐ | ☐ |
| (b) Phương trình ${f'(x) = 0}$ có tập nghiệm là ${S = \\{2\\}}$ | ☐ | ☐ |
| (c) ${f(2) = 24}$ | ☐ | ☐ |
| (d) Giá trị lớn nhất của hàm số ${f(x)}$ trên đoạn ${[-3;3]}$ bằng 24 | ☐ | ☐ |
```

2. **Công thức toán học - LUÔN dùng ${...}$:**
- ${x^2 + y^2 = z^2}$
- ${\\frac{a+b}{c-d}}$
- ${\\sqrt{x+1}}$
- ${f'(x) = 3x^2 - 12}$

3. **Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi]
A) [đáp án A]
B) [đáp án B]  
C) [đáp án C]
D) [đáp án D]
```

"""
    
    if has_illustrations:
        base_prompt += """
4. **Figures minh họa đã được tách riêng:**
- Các bảng biến thiên, đồ thị, hình vẽ minh họa sẽ được chèn tự động
- Tập trung vào text content chính
- Không cần mô tả chi tiết các hình minh họa

"""
    
    base_prompt += """
🚨 **TUYỆT ĐỐI:**
- Dùng ${...}$ cho MỌI công thức toán học!
- Giữ nguyên cấu trúc bảng Đúng/Sai!
- Không cắt hoặc bỏ cột nào trong bảng!
- Dùng ☐ cho checkbox trống!
- Dùng | để phân cách cột trong bảng!
"""
    
    return base_prompt

def display_figures(figures):
    """Display extracted figures in a nice grid"""
    if not figures:
        st.info("ℹ️ Không có figures nào được tách")
        return
    
    st.success(f"🎯 Đã tách {len(figures)} figures minh họa")
    
    # Display in grid
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
                        
                        type_icon = "📊" if fig['is_table'] else "🖼️"
                        confidence = fig.get('confidence', 0)
                        table_type = fig.get('table_type', 'unknown')
                        
                        st.markdown(f"""
                        <div class="figure-container">
                            <strong>{type_icon} {fig['name']}</strong><br>
                            🎯 {confidence:.1f}% | {table_type}<br>
                            📏 {fig['method']} detection
                        </div>
                        """, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error displaying figure: {str(e)}")

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
    try:
        st.markdown('<h1 class="main-header">📝 Smart Figure Detection PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
        
        # Hero section
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;">
            <h2 style="margin: 0;">🎯 SMART DETECTION: Bảo vệ bảng Đúng/Sai + Tách figures minh họa</h2>
            <p style="margin: 1rem 0; font-size: 1.1rem;">✅ Không cắt bảng Đúng/Sai • ✅ Tách bảng biến thiên/đồ thị • ✅ Smart classification • ✅ Full PDF support</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar
        with st.sidebar:
            st.header("⚙️ Settings")
            
            api_key = st.text_input("Gemini API Key", type="password")
            
            if api_key:
                if validate_api_key(api_key):
                    st.success("✅ Valid API key")
                else:
                    st.error("❌ Invalid API key")
            
            st.markdown("---")
            
            # Figure extraction settings
            if CV2_AVAILABLE:
                st.markdown("### 🎯 Figure Extraction")
                enable_extraction = st.checkbox("🖼️ Extract illustration figures", value=True)
                
                if enable_extraction:
                    confidence_threshold = st.slider("Confidence threshold (%)", 50, 95, 60, 5)
                    max_figures = st.slider("Max figures per page", 5, 25, 15, 5)
                    debug_mode = st.checkbox("Debug mode", value=False)
            else:
                enable_extraction = False
                st.error("❌ OpenCV not available - no figure extraction")
            
            st.markdown("---")
            st.markdown("### 🛡️ Protection Rules")
            st.markdown("""
            **🚫 KHÔNG cắt:**
            - Bảng Đúng/Sai (nội dung chính)
            - Text content chính
            
            **✅ CÓ THỂ cắt:**
            - Bảng biến thiên  
            - Đồ thị, hình vẽ
            - Figures minh họa
            """)
        
        if not api_key:
            st.warning("⚠️ Please enter Gemini API Key!")
            return
        
        if not validate_api_key(api_key):
            st.error("❌ Invalid API key!")
            return
        
        # Initialize API and extractor
        try:
            gemini_api = GeminiAPI(api_key)
            
            if enable_extraction and CV2_AVAILABLE:
                image_extractor = SuperEnhancedImageExtractor()
                image_extractor.final_confidence_threshold = confidence_threshold if 'confidence_threshold' in locals() else 60
                image_extractor.max_figures = max_figures if 'max_figures' in locals() else 15
                image_extractor.debug_mode = debug_mode if 'debug_mode' in locals() else False
            else:
                image_extractor = None
        except Exception as e:
            st.error(f"❌ Initialization error: {str(e)}")
            return
        
        # Main tabs
        tab1, tab2, tab3 = st.tabs(["📱 Phone Image", "🖼️ Single Image", "📄 PDF Processing"])
        
        # =================== TAB 1: PHONE IMAGE ===================
        with tab1:
            st.header("📱 Phone Image Processing")
            
            st.markdown("""
            <div class="protection-alert">
                <h4>🎯 Smart Processing:</h4>
                <p><strong>🛡️ Content Protection:</strong> Bảng Đúng/Sai được bảo vệ tuyệt đối</p>
                <p><strong>🖼️ Figure Extraction:</strong> Tách figures minh họa (bảng biến thiên, đồ thị)</p>
                <p><strong>📱 Phone Optimization:</strong> Xử lý tối ưu cho ảnh điện thoại</p>
            </div>
            """, unsafe_allow_html=True)
            
            uploaded_phone = st.file_uploader("Choose phone image", type=['png', 'jpg', 'jpeg'], key="phone_img")
            
            if uploaded_phone:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📱 Original Image")
                    
                    img_pil = Image.open(uploaded_phone)
                    st.image(img_pil, caption=f"Original: {uploaded_phone.name}", use_column_width=True)
                    
                    st.markdown("**📊 Image Info:**")
                    st.write(f"• Size: {img_pil.size[0]} x {img_pil.size[1]}")
                    st.write(f"• File size: {format_file_size(uploaded_phone.size)}")
                    
                    # Processing options
                    st.markdown("### ⚙️ Processing Options")
                    preserve_tables = st.checkbox("🛡️ Protect True/False tables", value=True)
                    enhance_text = st.checkbox("✨ Enhance text", value=True)
                    auto_rotate = st.checkbox("🔄 Auto rotate", value=True)
                    contrast_boost = st.slider("Contrast boost", 1.0, 1.5, 1.2, 0.1)
                    
                    if enable_extraction:
                        extract_figures = st.checkbox("🎯 Extract illustration figures", value=True)
                    else:
                        extract_figures = False
                
                with col2:
                    st.subheader("🔄 Processing & Results")
                    
                    if st.button("🚀 Process Phone Image", type="primary", key="process_phone"):
                        img_bytes = uploaded_phone.getvalue()
                        
                        # Step 1: Image processing
                        with st.spinner("🔄 Processing phone image..."):
                            try:
                                processed_img = EnhancedPhoneImageProcessor.process_phone_image(
                                    img_bytes,
                                    preserve_tables=preserve_tables,
                                    enhance_text=enhance_text,
                                    auto_rotate=auto_rotate,
                                    contrast_boost=contrast_boost
                                )
                                
                                st.success("✅ Image processed!")
                                st.image(processed_img, caption="Processed Image", use_column_width=True)
                                
                                # Convert to bytes
                                processed_buffer = io.BytesIO()
                                processed_img.save(processed_buffer, format='PNG')
                                processed_bytes = processed_buffer.getvalue()
                                
                            except Exception as e:
                                st.error(f"❌ Processing error: {str(e)}")
                                processed_bytes = img_bytes
                        
                        # Step 2: Figure extraction
                        extracted_figures = []
                        if extract_figures and image_extractor:
                            with st.spinner("🎯 Extracting illustration figures..."):
                                try:
                                    figures, img_h, img_w, _, _ = image_extractor.extract_illustration_figures(processed_bytes)
                                    extracted_figures = figures
                                    
                                    if figures:
                                        st.success(f"🎯 Extracted {len(figures)} illustration figures!")
                                        with st.expander("🖼️ View extracted figures"):
                                            display_figures(figures)
                                    else:
                                        st.info("ℹ️ No illustration figures found")
                                        
                                except Exception as e:
                                    st.error(f"❌ Figure extraction error: {str(e)}")
                        
                        # Step 3: LaTeX conversion
                        with st.spinner("📝 Converting to LaTeX..."):
                            try:
                                prompt = create_enhanced_prompt(has_illustrations=len(extracted_figures) > 0)
                                latex_result = gemini_api.convert_to_latex(processed_bytes, "image/png", prompt)
                                
                                if latex_result:
                                    # Insert figures if available
                                    if extracted_figures and image_extractor:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, img_h, img_w
                                        )
                                    
                                    st.success("🎉 Conversion completed!")
                                    
                                    st.markdown("### 📝 LaTeX Result")
                                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                    st.code(latex_result, language="latex")
                                    st.markdown('</div>', unsafe_allow_html=True)
                                    
                                    # Save to session
                                    st.session_state.phone_latex = latex_result
                                    st.session_state.phone_figures = extracted_figures
                                    
                                else:
                                    st.error("❌ No result from API")
                                    
                            except Exception as e:
                                st.error(f"❌ Conversion error: {str(e)}")
                    
                    # Download section
                    if 'phone_latex' in st.session_state:
                        st.markdown("---")
                        st.markdown("### 📥 Download")
                        
                        st.download_button(
                            label="📝 Download LaTeX (.tex)",
                            data=st.session_state.phone_latex,
                            file_name=uploaded_phone.name.replace(uploaded_phone.name.split('.')[-1], 'tex'),
                            mime="text/plain",
                            type="primary"
                        )
        
        # =================== TAB 2: SINGLE IMAGE ===================
        with tab2:
            st.header("🖼️ Single Image Processing")
            
            uploaded_single = st.file_uploader("Choose image", type=['png', 'jpg', 'jpeg'], key="single_image")
            
            if uploaded_single:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("🖼️ Original Image")
                    
                    img_pil = Image.open(uploaded_single)
                    st.image(img_pil, caption=f"Original: {uploaded_single.name}", use_column_width=True)
                    
                    st.markdown("**📊 Image Info:**")
                    st.write(f"• Size: {img_pil.size[0]} x {img_pil.size[1]}")
                    st.write(f"• File size: {format_file_size(uploaded_single.size)}")
                    
                    if enable_extraction:
                        extract_figures_single = st.checkbox("🎯 Extract figures", value=True, key="extract_single")
                    else:
                        extract_figures_single = False
                
                with col2:
                    st.subheader("🔄 Processing")
                    
                    if st.button("🚀 Convert to LaTeX", type="primary", key="convert_single"):
                        img_bytes = uploaded_single.getvalue()
                        
                        # Figure extraction
                        extracted_figures = []
                        if extract_figures_single and image_extractor:
                            with st.spinner("🎯 Extracting figures..."):
                                try:
                                    figures, img_h, img_w, _, _ = image_extractor.extract_illustration_figures(img_bytes)
                                    extracted_figures = figures
                                    
                                    if figures:
                                        st.success(f"🎯 Extracted {len(figures)} figures!")
                                        with st.expander("🖼️ View figures"):
                                            display_figures(figures)
                                    
                                except Exception as e:
                                    st.error(f"❌ Figure extraction error: {str(e)}")
                        
                        # LaTeX conversion
                        with st.spinner("📝 Converting to LaTeX..."):
                            try:
                                prompt = create_enhanced_prompt(has_illustrations=len(extracted_figures) > 0)
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                
                                if latex_result:
                                    # Insert figures
                                    if extracted_figures and image_extractor:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, img_h, img_w
                                        )
                                    
                                    st.success("✅ Conversion completed!")
                                    
                                    st.markdown("### 📝 LaTeX Result")
                                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                    st.code(latex_result, language="latex")
                                    st.markdown('</div>', unsafe_allow_html=True)
                                    
                                    # Download
                                    st.download_button(
                                        label="📝 Download LaTeX",
                                        data=latex_result,
                                        file_name=uploaded_single.name.replace(uploaded_single.name.split('.')[-1], 'tex'),
                                        mime="text/plain",
                                        type="primary"
                                    )
                                    
                                else:
                                    st.error("❌ Conversion failed")
                                    
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
        
        # =================== TAB 3: PDF PROCESSING ===================
        with tab3:
            st.header("📄 PDF Processing")
            
            uploaded_pdf = st.file_uploader("Choose PDF file", type=['pdf'], key="pdf_file")
            
            if uploaded_pdf:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📄 PDF Information")
                    
                    st.write(f"📄 File: {uploaded_pdf.name}")
                    st.write(f"📊 Size: {format_file_size(uploaded_pdf.size)}")
                    
                    # PDF settings
                    max_pages = st.number_input("Max pages to process", min_value=1, max_value=50, value=10)
                    
                    if enable_extraction:
                        extract_pdf_figures = st.checkbox("🎯 Extract figures from PDF", value=True, key="extract_pdf")
                    else:
                        extract_pdf_figures = False
                
                with col2:
                    st.subheader("🔄 PDF Processing")
                    
                    if st.button("🚀 Process PDF", type="primary", key="process_pdf"):
                        
                        # Extract images from PDF
                        with st.spinner("📄 Extracting pages from PDF..."):
                            try:
                                pdf_images = PDFProcessor.extract_images_from_pdf(uploaded_pdf, max_pages)
                                st.success(f"✅ Extracted {len(pdf_images)} pages")
                                
                            except Exception as e:
                                st.error(f"❌ PDF extraction error: {str(e)}")
                                pdf_images = []
                        
                        if pdf_images:
                            all_latex_content = []
                            all_figures = []
                            
                            # Process each page
                            progress_bar = st.progress(0)
                            
                            for i, (page_img, page_num) in enumerate(pdf_images):
                                try:
                                    progress_bar.progress((i + 1) / len(pdf_images))
                                    
                                    with st.spinner(f"🔄 Processing page {page_num}..."):
                                        # Convert page to bytes
                                        page_buffer = io.BytesIO()
                                        page_img.save(page_buffer, format='PNG')
                                        page_bytes = page_buffer.getvalue()
                                        
                                        # Extract figures from page
                                        page_figures = []
                                        if extract_pdf_figures and image_extractor:
                                            try:
                                                figures, img_h, img_w, _, _ = image_extractor.extract_illustration_figures(
                                                    page_bytes, len(all_figures), 0
                                                )
                                                page_figures = figures
                                                all_figures.extend(figures)
                                                
                                            except Exception as e:
                                                st.warning(f"Figure extraction error on page {page_num}: {str(e)}")
                                        
                                        # Convert page to LaTeX
                                        try:
                                            prompt = create_enhanced_prompt(has_illustrations=len(page_figures) > 0)
                                            page_latex = gemini_api.convert_to_latex(page_bytes, "image/png", prompt)
                                            
                                            if page_latex:
                                                # Insert figures if available
                                                if page_figures and image_extractor:
                                                    page_latex = image_extractor.insert_figures_into_text(
                                                        page_latex, page_figures, img_h, img_w
                                                    )
                                                
                                                # Add page header
                                                page_latex = f"% ===== PAGE {page_num} =====\n\n{page_latex}\n\n"
                                                all_latex_content.append(page_latex)
                                                
                                                st.success(f"✅ Page {page_num} processed")
                                            else:
                                                st.warning(f"⚠️ Page {page_num}: No LaTeX result")
                                                
                                        except Exception as e:
                                            st.error(f"❌ Page {page_num} conversion error: {str(e)}")
                                            
                                except Exception as e:
                                    st.error(f"❌ Error processing page {page_num}: {str(e)}")
                                    continue
                            
                            progress_bar.progress(1.0)
                            
                            # Combine all content
                            if all_latex_content:
                                combined_latex = "\n".join(all_latex_content)
                                
                                st.success(f"🎉 PDF processing completed! {len(all_latex_content)} pages processed")
                                
                                # Display results
                                st.markdown("### 📝 Combined LaTeX Result")
                                st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                st.code(combined_latex, language="latex")
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                                # Show extracted figures
                                if all_figures:
                                    st.markdown("### 🖼️ Extracted Figures")
                                    display_figures(all_figures)
                                
                                # Download section
                                st.markdown("### 📥 Download Results")
                                
                                col_a, col_b = st.columns(2)
                                
                                with col_a:
                                    st.download_button(
                                        label="📝 Download Combined LaTeX",
                                        data=combined_latex,
                                        file_name=uploaded_pdf.name.replace('.pdf', '_combined.tex'),
                                        mime="text/plain",
                                        type="primary"
                                    )
                                
                                with col_b:
                                    if all_figures:
                                        st.write(f"📊 Total figures extracted: {len(all_figures)}")
                            else:
                                st.error("❌ No content was successfully processed")
        
        # Footer
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 2rem; border-radius: 15px;'>
            <h3>🎯 SMART FIGURE DETECTION</h3>
            <p><strong>🛡️ Tuyệt đối bảo vệ bảng Đúng/Sai</strong></p>
            <p><strong>🖼️ Tách thông minh figures minh họa</strong></p>
            <p><strong>📱 Tối ưu cho ảnh điện thoại</strong></p>
            <p><strong>📄 Xử lý PDF đầy đủ</strong></p>
            <p><strong>🎯 Classification thông minh</strong></p>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"❌ Application error: {str(e)}")

if __name__ == "__main__":
    main()
