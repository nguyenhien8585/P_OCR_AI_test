import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import io

class EnhancedPhoneImageProcessor:
    """
    Enhanced Phone Image Processor - Đặc biệt tối ưu cho bảng Đúng/Sai và documents
    """
    
    @staticmethod
    def detect_table_regions(img):
        """
        Detect và bảo vệ vùng bảng (đặc biệt là bảng Đúng/Sai)
        """
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
        """
        Đặc biệt detect cột Đúng/Sai để bảo vệ
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
            h, w = gray.shape
            
            # Look for checkbox patterns (squares)
            # Use template matching for checkbox detection
            checkbox_regions = []
            
            # Create a simple checkbox template
            template_size = min(30, h//10)
            if template_size < 10:
                return []
            
            # Simple square detection for checkboxes
            contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                
                # Check if it's roughly square (checkbox-like)
                aspect_ratio = w_cont / max(h_cont, 1)
                area = w_cont * h_cont
                
                if (0.7 <= aspect_ratio <= 1.3 and  # Square-ish
                    100 <= area <= 1000 and  # Reasonable size
                    x > w * 0.6):  # In the right side (where Đúng/Sai columns usually are
                    checkbox_regions.append((x, y, w_cont, h_cont))
            
            return checkbox_regions
            
        except Exception:
            return []
    
    @staticmethod
    def enhanced_process_phone_image(image_bytes, preserve_tables=True, enhance_text=True, 
                                   auto_rotate=True, perspective_correct=True, 
                                   noise_reduction=True, contrast_boost=1.2):
        """
        Enhanced processing với bảo vệ đặc biệt cho bảng Đúng/Sai
        """
        try:
            # Load image
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            original_img = img.copy()
            
            # Step 1: Detect protected regions (tables, checkboxes)
            protected_regions = []
            if preserve_tables:
                table_regions = EnhancedPhoneImageProcessor.detect_table_regions(img)
                checkbox_regions = EnhancedPhoneImageProcessor.detect_checkbox_columns(img)
                protected_regions = table_regions + checkbox_regions
            
            # Step 2: Noise reduction (gentle to preserve table lines)
            if noise_reduction:
                img = cv2.bilateralFilter(img, 5, 50, 50)  # Gentler than original
            
            # Step 3: Auto rotation (careful around tables)
            if auto_rotate:
                img = EnhancedPhoneImageProcessor._careful_auto_rotate(img, protected_regions)
            
            # Step 4: Perspective correction (avoid tables)
            if perspective_correct:
                img = EnhancedPhoneImageProcessor._table_aware_perspective_correction(img, protected_regions)
            
            # Step 5: Enhanced text processing
            if enhance_text:
                img = EnhancedPhoneImageProcessor._enhanced_text_processing(img, protected_regions)
            
            # Step 6: Contrast and clarity boost
            img = EnhancedPhoneImageProcessor._smart_contrast_enhancement(img, contrast_boost)
            
            return Image.fromarray(img)
            
        except Exception as e:
            print(f"Error in enhanced processing: {e}")
            return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    @staticmethod
    def _careful_auto_rotate(img, protected_regions):
        """
        Auto rotate nhưng cẩn thận với vùng bảng
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Use protected regions to influence rotation detection
            if protected_regions:
                # Focus on areas outside protected regions for rotation detection
                mask = np.ones_like(gray) * 255
                for x, y, w, h in protected_regions:
                    # Create mask excluding table regions
                    mask[y:y+h, x:x+w] = 0
                
                masked_gray = cv2.bitwise_and(gray, mask)
                edges = cv2.Canny(masked_gray, 50, 150)
            else:
                edges = cv2.Canny(gray, 50, 150)
            
            # Detect lines for rotation
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=50)
            
            if lines is not None:
                angles = []
                for rho, theta in lines[:10]:  # Limit to avoid noise
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
        """
        Perspective correction that avoids distorting tables
        """
        try:
            # If there are many protected regions (likely tables), skip perspective correction
            if len(protected_regions) > 3:
                return img
            
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            
            # Use edge detection but exclude table regions
            edges = cv2.Canny(gray, 30, 90)
            
            # Mask out protected regions from edge detection
            for x, y, w, h in protected_regions:
                edges[y:y+h, x:x+w] = 0
            
            # Find contours for document detection
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            
            # Look for document-like contour (but be more conservative)
            for contour in contours[:3]:  # Only check top 3
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
                            # Safe to apply perspective correction
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
    def _enhanced_text_processing(img, protected_regions):
        """
        Enhanced text processing with special care for table text
        """
        try:
            # Convert to LAB for better text enhancement
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply different enhancement strategies for table vs non-table regions
            enhanced_l = l.copy()
            
            # For protected regions (tables), use gentler enhancement
            for x, y, w, h in protected_regions:
                table_region = l[y:y+h, x:x+w]
                
                # Gentle CLAHE for table regions
                clahe_gentle = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4))
                enhanced_table = clahe_gentle.apply(table_region)
                
                # Gentle sharpening
                kernel = np.array([[0, -0.5, 0], [-0.5, 3, -0.5], [0, -0.5, 0]])
                enhanced_table = cv2.filter2D(enhanced_table, -1, kernel)
                
                enhanced_l[y:y+h, x:x+w] = enhanced_table
            
            # For non-table regions, use stronger enhancement
            mask = np.ones_like(l, dtype=np.uint8) * 255
            for x, y, w, h in protected_regions:
                mask[y:y+h, x:x+w] = 0
            
            # Stronger CLAHE for non-table areas
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
        """
        Smart contrast enhancement that preserves table structure
        """
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

# Advanced Table-Preserving Image Extractor
class TablePreservingImageExtractor:
    """
    Image extractor that specifically preserves table formats like Đúng/Sai columns
    """
    
    def __init__(self):
        self.min_table_confidence = 80  # Higher confidence for tables
        self.checkbox_detection_enabled = True
        self.preserve_narrow_columns = True
    
    def extract_with_table_preservation(self, image_bytes):
        """
        Extract figures while preserving table structure
        """
        try:
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            
            # Step 1: Detect all table regions first
            table_regions = self._detect_complete_tables(img)
            checkbox_regions = self._detect_checkbox_patterns(img)
            
            # Step 2: Mark these as high-priority protected regions
            protected_figures = []
            
            for region in table_regions:
                x, y, w, h = region
                protected_figures.append({
                    'bbox': (x, y, w, h),
                    'type': 'table',
                    'confidence': 90,
                    'preserve_reason': 'complete_table_structure'
                })
            
            for region in checkbox_regions:
                x, y, w, h = region
                protected_figures.append({
                    'bbox': (x, y, w, h),
                    'type': 'checkbox_column',
                    'confidence': 85,
                    'preserve_reason': 'checkbox_pattern'
                })
            
            # Step 3: Regular figure extraction for other regions
            other_figures = self._extract_other_figures(img, protected_figures)
            
            return protected_figures + other_figures
            
        except Exception as e:
            print(f"Error in table-preserving extraction: {e}")
            return []
    
    def _detect_complete_tables(self, img):
        """Detect complete table structures"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            # Enhanced table detection
            # 1. Horizontal lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w//6, 1))
            horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
            
            # 2. Vertical lines (especially important for Đúng/Sai columns)
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//15))
            vertical_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel)
            
            # 3. Combine and find table structures
            table_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
            
            # Dilate to connect nearby lines
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            table_mask = cv2.dilate(table_mask, kernel, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            table_regions = []
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                area = w_cont * h_cont
                
                # Check if it's a substantial table
                if area > (w * h * 0.03):  # At least 3% of image
                    aspect_ratio = w_cont / max(h_cont, 1)
                    
                    # Tables with Đúng/Sai columns tend to be wider
                    if aspect_ratio > 1.5:  # Wide table
                        table_regions.append((x, y, w_cont, h_cont))
                    elif h_cont > h * 0.2:  # Tall table
                        table_regions.append((x, y, w_cont, h_cont))
            
            return table_regions
            
        except Exception:
            return []
    
    def _detect_checkbox_patterns(self, img):
        """Detect checkbox patterns in Đúng/Sai columns"""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            # Look for small square patterns (checkboxes)
            # Use template matching approach
            checkbox_regions = []
            
            # Edge detection for square patterns
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            checkbox_candidates = []
            for contour in contours:
                x, y, w_cont, h_cont = cv2.boundingRect(contour)
                area = w_cont * h_cont
                aspect_ratio = w_cont / max(h_cont, 1)
                
                # Check for checkbox characteristics
                if (0.7 <= aspect_ratio <= 1.4 and  # Roughly square
                    50 <= area <= 800 and  # Reasonable checkbox size
                    x > w * 0.5):  # In the right half (where Đúng/Sai usually is)
                    checkbox_candidates.append((x, y, w_cont, h_cont))
            
            # Group nearby checkboxes into columns
            if len(checkbox_candidates) >= 2:
                # Sort by x coordinate to find columns
                checkbox_candidates.sort(key=lambda c: c[0])
                
                # Group into columns
                columns = []
                current_column = [checkbox_candidates[0]]
                
                for i in range(1, len(checkbox_candidates)):
                    curr_x = checkbox_candidates[i][0]
                    prev_x = checkbox_candidates[i-1][0]
                    
                    if abs(curr_x - prev_x) < 50:  # Same column
                        current_column.append(checkbox_candidates[i])
                    else:  # New column
                        if len(current_column) >= 2:  # Valid column
                            columns.append(current_column)
                        current_column = [checkbox_candidates[i]]
                
                # Add last column
                if len(current_column) >= 2:
                    columns.append(current_column)
                
                # Create bounding boxes for each column
                for column in columns:
                    if len(column) >= 2:  # Valid checkbox column
                        min_x = min(c[0] for c in column)
                        min_y = min(c[1] for c in column)
                        max_x = max(c[0] + c[2] for c in column)
                        max_y = max(c[1] + c[3] for c in column)
                        
                        checkbox_regions.append((min_x, min_y, max_x - min_x, max_y - min_y))
            
            return checkbox_regions
            
        except Exception:
            return []
    
    def _extract_other_figures(self, img, protected_figures):
        """Extract other figures while avoiding protected table regions"""
        # This would integrate with the existing SuperEnhancedImageExtractor
        # but with exclusion zones for protected figures
        return []

# Usage example function
def process_phone_image_preserve_tables(image_bytes):
    """
    Main function to process phone images while preserving table formats
    """
    processor = EnhancedPhoneImageProcessor()
    extractor = TablePreservingImageExtractor()
    
    # Step 1: Enhance image quality
    enhanced_image = processor.enhanced_process_phone_image(
        image_bytes,
        preserve_tables=True,
        enhance_text=True,
        auto_rotate=True,
        perspective_correct=True,
        noise_reduction=True,
        contrast_boost=1.2
    )
    
    # Convert back to bytes for extraction
    buffer = io.BytesIO()
    enhanced_image.save(buffer, format='PNG')
    enhanced_bytes = buffer.getvalue()
    
    # Step 2: Extract figures with table preservation
    extracted_figures = extractor.extract_with_table_preservation(enhanced_bytes)
    
    return enhanced_image, extracted_figures

# Demo usage
if __name__ == "__main__":
    print("Enhanced Phone Image Processor - Table Format Preserving")
    print("Features:")
    print("✅ Detect and preserve table regions")
    print("✅ Protect Đúng/Sai checkbox columns")
    print("✅ Table-aware perspective correction")
    print("✅ Gentle processing for table areas")
    print("✅ Enhanced text clarity without damaging tables")
    print("✅ Smart contrast enhancement")
    print("✅ Checkbox pattern recognition")
    print("✅ Complete table structure detection")
