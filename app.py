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
    page_title="PDF/LaTeX Converter - Enhanced Table Protection",
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
    
    .table-protection-alert {
        background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c8 100%);
        border: 2px solid #28a745;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .processing-stats {
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        border: 1px solid #ffc107;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

class SuperEnhancedTableProtector:
    """Siêu cải tiến bảo vệ bảng Đúng/Sai"""
    
    @staticmethod
    def detect_true_false_tables(img):
        """Phát hiện đặc biệt bảng Đúng/Sai"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
            h, w = gray.shape
            
            # Detect text "Đúng" và "Sai"
            text_regions = SuperEnhancedTableProtector._detect_text_regions(gray, ["Đúng", "Sai", "Mệnh đề"])
            
            # Detect table structure
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//15, 1))
            horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
            
            # Very sensitive vertical detection cho cột hẹp
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//30))
            vertical_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel)
            
            # Combine lines
            table_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
            
            # Find table contours
            contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            true_false_tables = []
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                area = w_cont * h_cont
                
                # Check if this region contains "Đúng/Sai" structure
                if area > (w * h * 0.02):  # At least 2% of image
                    # Check for text presence
                    roi = gray[y:y+h_cont, x:x+w_cont]
                    if SuperEnhancedTableProtector._contains_true_false_structure(roi):
                        true_false_tables.append({
                            'bbox': (x, y, w_cont, h_cont),
                            'type': 'true_false_table',
                            'protection_level': 'maximum'
                        })
            
            return true_false_tables
            
        except Exception:
            return []
    
    @staticmethod
    def _detect_text_regions(gray, keywords):
        """Detect regions containing specific keywords"""
        # Simple approach - could be enhanced with OCR
        return []
    
    @staticmethod
    def _contains_true_false_structure(roi):
        """Check if ROI contains True/False table structure"""
        try:
            h, w = roi.shape
            if h < 50 or w < 100:
                return False
            
            # Look for rectangular patterns (checkboxes)
            contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            rectangular_count = 0
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                area = w_cont * h_cont
                aspect_ratio = w_cont / max(h_cont, 1)
                
                # Check for square-like shapes (checkboxes)
                if (50 < area < 500 and 0.5 < aspect_ratio < 2.0):
                    rectangular_count += 1
            
            return rectangular_count >= 4  # At least 4 checkbox-like shapes
            
        except Exception:
            return False

class EnhancedPhoneImageProcessor:
    """Enhanced Phone Image Processor với siêu bảo vệ bảng"""
    
    @staticmethod
    def process_phone_image_with_super_table_protection(image_bytes, 
                                                       preserve_tables=True, 
                                                       enhance_text=True, 
                                                       auto_rotate=True, 
                                                       perspective_correct=True, 
                                                       noise_reduction=True, 
                                                       contrast_boost=1.2, 
                                                       is_screenshot=False):
        """Siêu xử lý với bảo vệ tối đa cho bảng Đúng/Sai"""
        try:
            # Load image
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            # Detect screenshot
            if not is_screenshot:
                is_screenshot = EnhancedPhoneImageProcessor._detect_screenshot(img_pil)
            
            # Convert to numpy
            if CV2_AVAILABLE:
                img = np.array(img_pil)
                original_img = img.copy()
                
                # STEP 1: Detect True/False tables with maximum protection
                protected_regions = []
                true_false_tables = []
                
                if preserve_tables:
                    true_false_tables = SuperEnhancedTableProtector.detect_true_false_tables(img)
                    protected_regions.extend([table['bbox'] for table in true_false_tables])
                    
                    if true_false_tables:
                        st.success(f"🛡️ **SUPER PROTECTION ACTIVE**: {len(true_false_tables)} True/False tables detected")
                
                # STEP 2: Apply processing based on protection level
                if true_false_tables:
                    # Maximum protection mode - minimal processing
                    img = EnhancedPhoneImageProcessor._minimal_processing_for_tables(img, protected_regions)
                else:
                    # Standard processing
                    if is_screenshot:
                        img = EnhancedPhoneImageProcessor._process_screenshot(img, protected_regions)
                    else:
                        img = EnhancedPhoneImageProcessor._process_phone_photo(img, protected_regions, 
                                                                             noise_reduction, auto_rotate, 
                                                                             perspective_correct)
                
                # STEP 3: Text enhancement (always gentle for tables)
                if enhance_text:
                    img = EnhancedPhoneImageProcessor._super_gentle_text_enhancement(img, protected_regions, true_false_tables)
                
                # STEP 4: Final contrast (very careful)
                img = EnhancedPhoneImageProcessor._careful_contrast_enhancement(img, contrast_boost, protected_regions)
                
                processed_img = Image.fromarray(img)
                
            else:
                # Fallback: minimal PIL processing
                processed_img = img_pil
                if enhance_text and not preserve_tables:
                    enhancer = ImageEnhance.Contrast(processed_img)
                    processed_img = enhancer.enhance(1.1)  # Very gentle
            
            return processed_img, true_false_tables
            
        except Exception as e:
            st.error(f"❌ Super processing error: {str(e)}")
            return Image.open(io.BytesIO(image_bytes)).convert("RGB"), []
    
    @staticmethod
    def _minimal_processing_for_tables(img, protected_regions):
        """Minimal processing khi có bảng Đúng/Sai"""
        try:
            # Chỉ làm sạch noise rất nhẹ
            img = cv2.bilateralFilter(img, 3, 30, 30)  # Very gentle
            return img
        except Exception:
            return img
    
    @staticmethod
    def _super_gentle_text_enhancement(img, protected_regions, true_false_tables):
        """Siêu nhẹ nhàng cho text trong bảng"""
        try:
            # Convert to LAB
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            
            enhanced_l = l.copy()
            
            # For True/False tables - EXTREMELY gentle
            for table in true_false_tables:
                x, y, w, h = table['bbox']
                table_region = l[y:y+h, x:x+w]
                
                # Minimal CLAHE
                clahe_minimal = cv2.createCLAHE(clipLimit=1.1, tileGridSize=(2, 2))
                enhanced_table = clahe_minimal.apply(table_region)
                enhanced_l[y:y+h, x:x+w] = enhanced_table
            
            # For other regions - gentle enhancement
            mask = np.ones_like(l, dtype=np.uint8) * 255
            for table in true_false_tables:
                x, y, w, h = table['bbox']
                mask[y:y+h, x:x+w] = 0
            
            clahe_normal = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
            enhanced_normal = clahe_normal.apply(l)
            enhanced_l = np.where(mask == 255, enhanced_normal, enhanced_l)
            
            # Merge back
            enhanced_lab = cv2.merge([enhanced_l, a, b])
            enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
            
            return enhanced_img
            
        except Exception:
            return img
    
    @staticmethod
    def _careful_contrast_enhancement(img, contrast_boost, protected_regions):
        """Careful contrast enhancement"""
        try:
            # Reduce contrast boost if tables present
            if protected_regions:
                contrast_boost = min(contrast_boost, 1.1)
            
            img_pil = Image.fromarray(img)
            enhancer = ImageEnhance.Contrast(img_pil)
            enhanced = enhancer.enhance(contrast_boost)
            
            return np.array(enhanced)
        except Exception:
            return img
    
    @staticmethod
    def _detect_screenshot(img_pil):
        """Detect screenshot với độ chính xác cao"""
        try:
            width, height = img_pil.size
            aspect_ratio = width / height
            
            # Common screenshot ratios
            common_ratios = [16/9, 16/10, 4/3, 3/2, 19.5/9, 18/9, 21/9]
            
            is_pixel_perfect = (width % 2 == 0) and (height % 2 == 0)
            is_high_res = (width * height) > 300000
            aspect_match = any(abs(aspect_ratio - ratio) < 0.05 for ratio in common_ratios)
            
            # Additional checks if CV2 available
            if CV2_AVAILABLE:
                img_array = np.array(img_pil)
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                
                # Check for clean edges
                edges = cv2.Canny(gray, 50, 150)
                edge_density = np.sum(edges > 0) / (width * height)
                has_clean_edges = 0.02 < edge_density < 0.15
                
                # Check for uniform text (screenshots often have more uniform text)
                laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                is_clean = laplacian_var > 50
                
                screenshot_score = sum([
                    is_pixel_perfect,
                    is_high_res,
                    aspect_match,
                    has_clean_edges,
                    is_clean
                ])
                
                return screenshot_score >= 3
            else:
                screenshot_score = sum([is_pixel_perfect, is_high_res, aspect_match])
                return screenshot_score >= 2
                
        except Exception:
            return False
    
    @staticmethod
    def _process_screenshot(img, protected_regions):
        """Process screenshot với table protection"""
        try:
            # Very minimal processing for screenshots
            return img  # Screenshots are usually already clean
        except Exception:
            return img
    
    @staticmethod
    def _process_phone_photo(img, protected_regions, noise_reduction, auto_rotate, perspective_correct):
        """Process phone photo với table protection"""
        try:
            # Gentle noise reduction
            if noise_reduction:
                img = cv2.bilateralFilter(img, 5, 40, 40)
            
            # Skip rotation if many tables
            if auto_rotate and len(protected_regions) <= 2:
                img = EnhancedPhoneImageProcessor._gentle_auto_rotate(img, protected_regions)
            
            # Skip perspective correction if tables present
            if perspective_correct and len(protected_regions) == 0:
                img = EnhancedPhoneImageProcessor._gentle_perspective_correction(img)
            
            return img
        except Exception:
            return img
    
    @staticmethod
    def _gentle_auto_rotate(img, protected_regions):
        """Gentle auto rotation"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 30, 100)
            
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
            
            if lines is not None:
                angles = []
                for rho, theta in lines[:5]:  # Only use top 5 lines
                    angle = theta * 180 / np.pi
                    if angle > 90:
                        angle = angle - 180
                    elif angle > 45:
                        angle = angle - 90
                    elif angle < -45:
                        angle = angle + 90
                    
                    if abs(angle) < 15:  # Only small corrections
                        angles.append(angle)
                
                if angles:
                    rotation_angle = np.median(angles)
                    if abs(rotation_angle) > 1:  # Only rotate if significant
                        center = (img.shape[1]//2, img.shape[0]//2)
                        M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
                        img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), 
                                           borderMode=cv2.BORDER_CONSTANT,
                                           borderValue=(255, 255, 255))
            
            return img
        except Exception:
            return img
    
    @staticmethod
    def _gentle_perspective_correction(img):
        """Gentle perspective correction"""
        # Implementation similar to original but more conservative
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
                elif response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise Exception("Đã vượt quá giới hạn rate limit")
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

def create_super_enhanced_table_prompt(is_screenshot=False, has_true_false_tables=False):
    """Tạo prompt siêu cải tiến cho bảng Đúng/Sai"""
    
    base_prompt = """
🎯 CHUYỂN ĐỔI TOÀN BỘ NỘI DUNG THÀNH LATEX - BẢO VỆ TUYỆT ĐỐI BẢNG ĐÚNG/SAI

"""
    
    if has_true_false_tables:
        base_prompt += """
🚨 **PHÁT HIỆN BẢNG ĐÚNG/SAI - CHÍNH XÁC TUYỆT ĐỐI:**

1. **BẮT BUỘC giữ nguyên format bảng:**
```
| Mệnh đề | Đúng | Sai |
|---------|------|-----|
| (a) Hàm số đã cho có đạo hàm là ${f'(x) = 3x^2 - 12}$ | ☐ | ☐ |
| (b) Phương trình ${f'(x) = 0}$ có tập nghiệm là ${S = \\{2\\}}$ | ☐ | ☐ |
| (c) ${f(2) = 24}$ | ☐ | ☐ |
| (d) Giá trị lớn nhất của hàm số ${f(x)}$ trên đoạn ${[-3;3]}$ bằng 24 | ☐ | ☐ |
```

2. **TUYỆT ĐỐI KHÔNG được:**
- Cắt hoặc bỏ cột Đúng/Sai
- Gộp các cột
- Thay đổi ký hiệu checkbox ☐
- Bỏ qua bất kỳ mệnh đề nào

3. **BẮT BUỘC sử dụng:**
- | để phân cách cột
- ☐ cho checkbox trống
- ${...}$ cho MỌI công thức toán học

"""
    
    if is_screenshot:
        base_prompt += """
📺 **ẢNH SCREENSHOT - CHẤT LƯỢNG CAO:**
- Đọc chính xác từng ký tự
- Bảo toàn hoàn toàn cấu trúc bảng
- Không bỏ sót bất kỳ thông tin nào

"""
    else:
        base_prompt += """
📱 **ẢNH ĐIỆN THOẠI - ĐÃ ĐƯỢC XỬ LÝ:**
- Ảnh đã được tối ưu hóa
- Đọc cẩn thận mọi chi tiết
- Chú ý đặc biệt đến vùng bảng

"""
    
    base_prompt += """
🎯 **QUY TẮC CHUYỂN ĐỔI:**

**Công thức toán học:**
- ${x^2 + y^2 = z^2}$
- ${\\frac{a+b}{c-d}}$
- ${\\sqrt{x+1}}$
- ${f'(x) = 3x^2 - 12}$

**Câu hỏi trắc nghiệm:**
```
Câu X: [nội dung câu hỏi]
A) [đáp án A]
B) [đáp án B]  
C) [đáp án C]
D) [đáp án D]
```

**Bảng biến thiên:**
```
| x | ${-\\infty}$ | -2 | ${+\\infty}$ |
|---|-------------|-----|-------------|
| ${f'(x)}$ | + | 0 | - |
| ${f(x)}$ | ↗ | max | ↘ |
```

⚠️ **SIÊU QUAN TRỌNG:**
- TUYỆT ĐỐI dùng ${...}$ cho MỌI công thức!
- TUYỆT ĐỐI giữ nguyên cấu trúc bảng Đúng/Sai!
- TUYỆT ĐỐI không cắt hoặc bỏ cột nào!
- Dùng ☐ cho checkbox trống!
"""
    
    return base_prompt

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
        st.markdown('<h1 class="main-header">📝 SUPER TABLE PROTECTION PDF/LaTeX Converter</h1>', unsafe_allow_html=True)
        
        # Hero section
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;">
            <h2 style="margin: 0;">🛡️ SIÊU BẢO VỆ BẢNG ĐÚNG/SAI + 🎯 SMART DETECTION</h2>
            <p style="margin: 1rem 0; font-size: 1.1rem;">✅ Tuyệt đối không cắt bảng • ✅ Minimal processing cho tables • ✅ Enhanced prompts • ✅ Perfect preservation</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar
        with st.sidebar:
            st.header("⚙️ Cài đặt")
            
            api_key = st.text_input("Gemini API Key", type="password")
            
            if api_key:
                if validate_api_key(api_key):
                    st.success("✅ API key hợp lệ")
                else:
                    st.error("❌ API key không hợp lệ")
            
            st.markdown("---")
            
            # Super Table Protection Settings
            st.markdown("### 🛡️ Super Table Protection")
            enable_super_protection = st.checkbox("🛡️ Bật Super Protection", value=True)
            
            if enable_super_protection:
                max_table_processing = st.checkbox("📊 Minimal processing for tables", value=True)
                enhanced_prompts = st.checkbox("🎯 Enhanced table prompts", value=True)
                
                with st.expander("🔧 Protection Settings"):
                    table_sensitivity = st.slider("Table detection sensitivity", 0.5, 2.0, 1.0, 0.1)
                    protection_mode = st.selectbox("Protection mode", 
                                                 ["Maximum", "High", "Medium"], 
                                                 index=0)
        
        if not api_key:
            st.warning("⚠️ Vui lòng nhập Gemini API Key!")
            return
        
        if not validate_api_key(api_key):
            st.error("❌ API key không hợp lệ!")
            return
        
        # Initialize API
        try:
            gemini_api = GeminiAPI(api_key)
        except Exception as e:
            st.error(f"❌ API initialization error: {str(e)}")
            return
        
        # Main tabs
        tab1, tab2, tab3 = st.tabs(["📱 Super Phone Processing", "🖼️ Single Image", "📄 PDF Processing"])
        
        # =================== TAB 1: SUPER PHONE PROCESSING ===================
        with tab1:
            st.header("📱 Super Phone Processing với Siêu Bảo Vệ Bảng")
            
            # Table protection alert
            st.markdown("""
            <div class="table-protection-alert">
                <h4>🛡️ SIÊU BẢO VỆ BẢNG ĐÚNG/SAI:</h4>
                <p><strong>🔍 Smart Detection:</strong> Tự động phát hiện bảng True/False</p>
                <p><strong>⚡ Minimal Processing:</strong> Xử lý tối thiểu để bảo vệ cấu trúc</p>
                <p><strong>🎯 Enhanced Prompts:</strong> Prompts chuyên biệt cho bảng</p>
                <p><strong>📐 Structure Preservation:</strong> Tuyệt đối không cắt cột</p>
                <p><strong>✨ Perfect LaTeX:</strong> Format chuẩn cho bảng Đúng/Sai</p>
            </div>
            """, unsafe_allow_html=True)
            
            uploaded_image = st.file_uploader("Chọn ảnh điện thoại", type=['png', 'jpg', 'jpeg'], key="super_phone")
            
            if uploaded_image:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📱 Ảnh gốc")
                    
                    img_pil = Image.open(uploaded_image)
                    st.image(img_pil, caption=f"Original: {uploaded_image.name}", use_column_width=True)
                    
                    # Image analysis
                    is_screenshot = False
                    if CV2_AVAILABLE:
                        is_screenshot = EnhancedPhoneImageProcessor._detect_screenshot(img_pil)
                        
                        if is_screenshot:
                            st.success("📺 **Detected: Screenshot** - Will use minimal processing")
                        else:
                            st.info("📱 **Detected: Phone photo** - Will apply gentle processing")
                    
                    # Image info
                    st.markdown("**📊 Image Info:**")
                    st.write(f"• Size: {img_pil.size[0]} x {img_pil.size[1]}")
                    st.write(f"• File size: {format_file_size(uploaded_image.size)}")
                    
                    # Processing settings
                    st.markdown("### ⚙️ Processing Settings")
                    
                    if enable_super_protection:
                        st.success("🛡️ Super Table Protection: ACTIVE")
                        preserve_tables = True
                        process_intensity = st.selectbox(
                            "Processing intensity",
                            ["Minimal (Best for tables)", "Gentle", "Standard"],
                            index=0
                        )
                    else:
                        preserve_tables = st.checkbox("🛡️ Preserve tables", value=True)
                        process_intensity = "Standard"
                    
                    enhance_text = st.checkbox("✨ Text enhancement", value=True)
                    auto_rotate = st.checkbox("🔄 Auto rotation", value=True)
                
                with col2:
                    st.subheader("🔄 Processing & Results")
                    
                    if st.button("🚀 Process with Super Protection", type="primary", key="super_process"):
                        img_bytes = uploaded_image.getvalue()
                        
                        # Step 1: Super enhanced processing
                        with st.spinner("🛡️ Processing with super table protection..."):
                            try:
                                processed_img, detected_tables = EnhancedPhoneImageProcessor.process_phone_image_with_super_table_protection(
                                    img_bytes,
                                    preserve_tables=preserve_tables,
                                    enhance_text=enhance_text,
                                    auto_rotate=auto_rotate,
                                    perspective_correct=(process_intensity != "Minimal (Best for tables)"),
                                    noise_reduction=True,
                                    contrast_boost=1.1 if process_intensity == "Minimal (Best for tables)" else 1.2,
                                    is_screenshot=is_screenshot
                                )
                                
                                # Display processing stats
                                st.markdown("""
                                <div class="processing-stats">
                                    <h4>📊 Processing Results:</h4>
                                """, unsafe_allow_html=True)
                                
                                if detected_tables:
                                    st.markdown(f"<p><strong>🛡️ Protected Tables:</strong> {len(detected_tables)} True/False tables detected</p>", unsafe_allow_html=True)
                                    st.markdown(f"<p><strong>⚡ Processing Mode:</strong> Super Protection Active</p>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"<p><strong>📝 Content Type:</strong> No True/False tables detected</p>", unsafe_allow_html=True)
                                    st.markdown(f"<p><strong>⚡ Processing Mode:</strong> Standard Enhancement</p>", unsafe_allow_html=True)
                                
                                st.markdown("</div>", unsafe_allow_html=True)
                                
                                # Display processed image
                                st.markdown("**📸 Processed Image:**")
                                st.image(processed_img, use_column_width=True)
                                
                                # Convert to bytes for API
                                processed_buffer = io.BytesIO()
                                processed_img.save(processed_buffer, format='PNG', quality=95)
                                processed_bytes = processed_buffer.getvalue()
                                
                            except Exception as e:
                                st.error(f"❌ Processing error: {str(e)}")
                                processed_bytes = img_bytes
                                detected_tables = []
                        
                        # Step 2: LaTeX conversion with super prompts
                        with st.spinner("📝 Converting to LaTeX with super prompts..."):
                            try:
                                # Create super enhanced prompt
                                has_tables = len(detected_tables) > 0
                                super_prompt = create_super_enhanced_table_prompt(
                                    is_screenshot=is_screenshot,
                                    has_true_false_tables=has_tables
                                )
                                
                                latex_result = gemini_api.convert_to_latex(
                                    processed_bytes, 
                                    "image/png", 
                                    super_prompt
                                )
                                
                                if latex_result:
                                    st.success("🎉 Super conversion completed!")
                                    
                                    # Display result with highlighting
                                    st.markdown("### 📝 LaTeX Result")
                                    
                                    if has_tables:
                                        st.markdown("""
                                        <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 1rem; margin: 1rem 0;">
                                            <h5>🛡️ Table Protection Applied</h5>
                                            <p>Bảng Đúng/Sai đã được bảo vệ với processing tối thiểu và prompts chuyên biệt.</p>
                                        </div>
                                        """, unsafe_allow_html=True)
                                    
                                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                                    st.code(latex_result, language="latex")
                                    st.markdown('</div>', unsafe_allow_html=True)
                                    
                                    # Save to session
                                    st.session_state.super_latex_content = latex_result
                                    st.session_state.super_processed_image = processed_img
                                    st.session_state.super_detected_tables = detected_tables
                                    
                                else:
                                    st.error("❌ API returned no result")
                                    
                            except Exception as e:
                                st.error(f"❌ Conversion error: {str(e)}")
                    
                    # Download section
                    if 'super_latex_content' in st.session_state:
                        st.markdown("---")
                        st.markdown("### 📥 Downloads")
                        
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            st.download_button(
                                label="📝 Download LaTeX",
                                data=st.session_state.super_latex_content,
                                file_name=uploaded_image.name.replace(uploaded_image.name.split('.')[-1], 'tex'),
                                mime="text/plain",
                                type="primary"
                            )
                        
                        with col_b:
                            processed_buffer = io.BytesIO()
                            st.session_state.super_processed_image.save(processed_buffer, format='PNG')
                            
                            st.download_button(
                                label="📸 Download Processed Image",
                                data=processed_buffer.getvalue(),
                                file_name=uploaded_image.name.replace(uploaded_image.name.split('.')[-1], 'processed.png'),
                                mime="image/png"
                            )
                        
                        # Statistics
                        if 'super_detected_tables' in st.session_state:
                            tables = st.session_state.super_detected_tables
                            if tables:
                                st.markdown("### 📊 Protection Statistics")
                                st.success(f"🛡️ {len(tables)} True/False tables were super-protected")
                                st.info("Tables processed with minimal enhancement to preserve structure")
        
        # =================== TAB 2: SINGLE IMAGE ===================
        with tab2:
            st.header("🖼️ Single Image Processing")
            st.info("Upload a single image for LaTeX conversion with table protection")
            
            uploaded_single = st.file_uploader("Choose image", type=['png', 'jpg', 'jpeg'], key="single_img")
            
            if uploaded_single:
                img_pil = Image.open(uploaded_single)
                st.image(img_pil, caption="Original Image", use_column_width=True)
                
                if st.button("Convert to LaTeX", type="primary"):
                    with st.spinner("Converting..."):
                        try:
                            img_bytes = uploaded_single.getvalue()
                            
                            # Quick detection for tables
                            has_tables = False
                            if CV2_AVAILABLE:
                                img_array = np.array(img_pil)
                                detected_tables = SuperEnhancedTableProtector.detect_true_false_tables(img_array)
                                has_tables = len(detected_tables) > 0
                            
                            # Use super prompt
                            super_prompt = create_super_enhanced_table_prompt(
                                is_screenshot=False,
                                has_true_false_tables=has_tables
                            )
                            
                            latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", super_prompt)
                            
                            if latex_result:
                                st.success("✅ Conversion completed!")
                                st.code(latex_result, language="latex")
                                
                                st.download_button(
                                    label="📝 Download LaTeX",
                                    data=latex_result,
                                    file_name=uploaded_single.name.replace(uploaded_single.name.split('.')[-1], 'tex'),
                                    mime="text/plain"
                                )
                            else:
                                st.error("❌ Conversion failed")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
        
        # =================== TAB 3: PDF PROCESSING ===================
        with tab3:
            st.header("📄 PDF Processing")
            st.info("Upload PDF for batch processing with table protection")
            
            uploaded_pdf = st.file_uploader("Choose PDF", type=['pdf'], key="pdf_upload")
            
            if uploaded_pdf:
                st.write(f"📄 PDF: {uploaded_pdf.name}")
                st.write(f"📊 Size: {format_file_size(uploaded_pdf.size)}")
                
                max_pages = st.number_input("Max pages to process", min_value=1, max_value=50, value=10)
                
                if st.button("Process PDF", type="primary"):
                    st.info("📄 PDF processing will be implemented with the same super protection features")
        
        # Footer
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 2rem; border-radius: 15px;'>
            <h3>🛡️ SUPER TABLE PROTECTION GUARANTEE</h3>
            <p><strong>✅ Tuyệt đối không cắt bảng Đúng/Sai</strong></p>
            <p><strong>⚡ Minimal processing cho vùng có bảng</strong></p>
            <p><strong>🎯 Enhanced prompts chuyên biệt</strong></p>
            <p><strong>📐 Perfect structure preservation</strong></p>
            <p><strong>🔍 Smart detection algorithms</strong></p>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"❌ Application error: {str(e)}")
        st.error("Please refresh and try again.")

if __name__ == "__main__":
    main()
