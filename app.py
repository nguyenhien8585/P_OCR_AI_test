import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
from docx import Document
import tempfile
import os
import re
import time
import cv2
import numpy as np

# Cấu hình trang
st.set_page_config(
    page_title="PDF/Image to LaTeX Converter - Ultra Enhanced",
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
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-medium { color: #ffc107; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

class UltraImageExtractor:
    """
    Class siêu nâng cao để tách ảnh/bảng với độ chính xác cực cao
    """
    
    def __init__(self):
        self.min_area_ratio = 0.003    # Diện tích tối thiểu (% của ảnh gốc)
        self.min_area_abs = 1000       # Diện tích tối thiểu (pixel)
        self.min_width = 40            # Chiều rộng tối thiểu
        self.min_height = 40           # Chiều cao tối thiểu
        self.max_figures = 12          # Số lượng ảnh tối đa
        self.padding = 8               # Padding xung quanh ảnh cắt
        self.confidence_threshold = 50 # Ngưỡng confidence tối thiểu
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng với thuật toán siêu chính xác"""
        # 1. Đọc và tiền xử lý ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # 2. Tiền xử lý ảnh đa cấp độ
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Khử nhiễu mạnh
        gray = cv2.medianBlur(gray, 5)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Tăng cường độ tương phản adaptive
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # 3. Phát hiện cạnh đa phương pháp
        # Phương pháp 1: Adaptive threshold với nhiều kích thước kernel
        thresh1 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 3)
        
        # Phương pháp 2: Canny với multiple scales
        edges1 = cv2.Canny(gray, 30, 100, apertureSize=3)
        edges2 = cv2.Canny(gray, 50, 150, apertureSize=3)
        edges3 = cv2.Canny(gray, 80, 200, apertureSize=5)
        
        # Phương pháp 3: Gradient-based detection
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient = np.sqrt(sobelx**2 + sobely**2)
        gradient = np.uint8(gradient / gradient.max() * 255)
        _, gradient_thresh = cv2.threshold(gradient, 50, 255, cv2.THRESH_BINARY)
        
        # 4. Kết hợp tất cả phương pháp
        combined = cv2.bitwise_or(thresh1, thresh2)
        combined = cv2.bitwise_or(combined, edges1)
        combined = cv2.bitwise_or(combined, edges2) 
        combined = cv2.bitwise_or(combined, edges3)
        combined = cv2.bitwise_or(combined, gradient_thresh)
        
        # 5. Morphological operations để làm sạch
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_close)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_open)
        
        # Dilate nhẹ để kết nối các thành phần
        kernel_dilate = np.ones((2, 2), np.uint8)
        combined = cv2.dilate(combined, kernel_dilate, iterations=1)
        
        # 6. Tìm contours với hierarchy
        contours, hierarchy = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 7. Lọc và phân tích contours với nhiều tiêu chí
        candidates = []
        
        for i, cnt in enumerate(contours):
            # Tính toán bounding box
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc kích thước cơ bản
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.8):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            # Lọc aspect ratio hợp lý
            if not (0.05 < aspect_ratio < 20.0):
                continue
            
            # Loại bỏ vùng ở rìa ảnh
            margin = 0.01
            if (x < margin*w or y < margin*h or 
                (x+ww) > (1-margin)*w or (y+hh) > (1-margin)*h):
                continue
            
            # Tính các đặc trưng hình học nâng cao
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(cnt)
            
            if hull_area == 0 or contour_area < 100:
                continue
            
            # Tính toán các metrics chất lượng
            solidity = float(contour_area) / hull_area
            extent = float(contour_area) / area
            
            # Tính chu vi và circularity
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * contour_area / (perimeter ** 2)
            
            # Lọc các shape quá phức tạp hoặc quá đơn giản
            if solidity < 0.2 or extent < 0.15:
                continue
            
            # Tính moments để kiểm tra shape regularity
            moments = cv2.moments(cnt)
            if moments['m00'] == 0:
                continue
            
            # Phân tích nội dung vùng để phân loại
            roi = gray[y:y+hh, x:x+ww]
            content_analysis = self._analyze_region_content(roi)
            
            # Phân loại bảng vs hình
            is_table = self._advanced_table_classification(x, y, ww, hh, w, h, cnt, roi, content_analysis)
            
            # Tính điểm confidence nâng cao
            confidence = self._calculate_advanced_confidence(
                area_ratio, aspect_ratio, solidity, extent, circularity,
                ww, hh, w, h, content_analysis, contour_area
            )
            
            # Chỉ giữ lại những vùng có confidence cao
            if confidence < self.confidence_threshold:
                continue
            
            candidates.append({
                "area": area,
                "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                "width": ww, "height": hh,
                "is_table": is_table,
                "confidence": confidence,
                "aspect_ratio": aspect_ratio,
                "solidity": solidity,
                "extent": extent,
                "circularity": circularity,
                "content_analysis": content_analysis,
                "bbox": (x, y, ww, hh),
                "contour": cnt
            })
        
        # 8. Sắp xếp và lọc overlapping với thuật toán NMS
        candidates = sorted(candidates, key=lambda f: f['confidence'], reverse=True)
        candidates = self._non_maximum_suppression(candidates, iou_threshold=0.3)
        candidates = candidates[:self.max_figures]
        
        # 9. Sắp xếp theo vị trí đọc (top-to-bottom, left-to-right)
        candidates = sorted(candidates, key=lambda box: (box["y0"] + box["height"]//2, box["x0"]))
        
        # 10. Tạo ảnh kết quả với quality cao
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Cắt ảnh với padding thông minh
            x0 = max(0, fig_data["x0"] - self.padding)
            y0 = max(0, fig_data["y0"] - self.padding)
            x1 = min(w, fig_data["x1"] + self.padding)
            y1 = min(h, fig_data["y1"] + self.padding)
            
            crop = img[y0:y1, x0:x1]
            
            if crop.size == 0:
                continue
            
            # Post-process ảnh cắt
            crop = self._enhance_cropped_image(crop)
            
            # Chuyển thành base64 với quality cao
            buf = io.BytesIO()
            Image.fromarray(crop).save(buf, format="JPEG", quality=98, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            # Đặt tên file thông minh
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
                "bbox": (x0, y0, x1-x0, y1-y0),
                "original_bbox": fig_data["bbox"],
                "confidence": fig_data["confidence"],
                "aspect_ratio": fig_data["aspect_ratio"],
                "area": fig_data["area"],
                "solidity": fig_data["solidity"],
                "content_analysis": fig_data["content_analysis"]
            })
        
        return final_figures, h, w
    
    def _analyze_region_content(self, roi):
        """Phân tích nội dung vùng để hỗ trợ phân loại"""
        if roi.shape[0] < 10 or roi.shape[1] < 10:
            return {"has_text": False, "has_lines": 0, "density": 0, "uniformity": 0}
        
        # Phát hiện text regions (vùng có nhiều pixel đen nhỏ)
        kernel_text = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))
        _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        text_regions = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_text)
        has_text = np.sum(text_regions) > roi.shape[0] * roi.shape[1] * 0.05
        
        # Phát hiện đường kẻ ngang và dọc
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min(roi.shape[1]//3, 40), 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min(roi.shape[0]//3, 40)))
        
        horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
        
        h_lines = len(cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
        v_lines = len(cv2.findContours(vertical_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
        
        # Tính mật độ pixel
        density = np.sum(binary) / (roi.shape[0] * roi.shape[1] * 255)
        
        # Tính độ đồng đều (uniformity)
        hist = cv2.calcHist([roi], [0], None, [256], [0, 256])
        uniformity = np.sum((hist / hist.sum()) ** 2)
        
        return {
            "has_text": has_text,
            "has_lines": h_lines + v_lines,
            "h_lines": h_lines,
            "v_lines": v_lines,
            "density": density,
            "uniformity": uniformity
        }
    
    def _advanced_table_classification(self, x, y, w, h, img_w, img_h, contour, roi, content_analysis):
        """Phân loại bảng vs hình ảnh với thuật toán nâng cao"""
        aspect_ratio = w / (h + 1e-6)
        
        # Điểm từ kích thước và tỷ lệ
        size_score = 0
        if w > 0.25 * img_w:  # Bảng thường rộng
            size_score += 3
        if h > 0.08 * img_h and h < 0.7 * img_h:  # Chiều cao vừa phải
            size_score += 2
        if 1.5 < aspect_ratio < 10.0:  # Tỷ lệ phù hợp cho bảng
            size_score += 3
        
        # Điểm từ phân tích nội dung
        content_score = 0
        if content_analysis["has_lines"] > 2:  # Có đường kẻ
            content_score += 4
        if content_analysis["h_lines"] > 1:  # Có đường kẻ ngang
            content_score += 3
        if content_analysis["v_lines"] > 0:  # Có đường kẻ dọc
            content_score += 2
        if content_analysis["has_text"]:  # Có text
            content_score += 2
        if 0.1 < content_analysis["density"] < 0.4:  # Mật độ vừa phải
            content_score += 2
        
        # Điểm từ vị trí (bảng thường ở giữa)
        position_score = 0
        center_x_ratio = (x + w/2) / img_w
        if 0.1 < center_x_ratio < 0.9:
            position_score += 1
        
        total_score = size_score + content_score + position_score
        
        # Ngưỡng phân loại động dựa trên confidence
        threshold = 6 if content_analysis["has_lines"] > 3 else 8
        
        return total_score >= threshold
    
    def _calculate_advanced_confidence(self, area_ratio, aspect_ratio, solidity, extent, 
                                     circularity, w, h, img_w, img_h, content_analysis, contour_area):
        """Tính confidence score nâng cao"""
        confidence = 0
        
        # Điểm từ kích thước (30 điểm)
        if 0.005 < area_ratio < 0.6:
            if 0.02 < area_ratio < 0.3:
                confidence += 30
            elif 0.01 < area_ratio < 0.5:
                confidence += 20
            else:
                confidence += 10
        
        # Điểm từ aspect ratio (25 điểm)
        if 0.3 < aspect_ratio < 5.0:
            confidence += 25
        elif 0.1 < aspect_ratio < 10.0:
            confidence += 15
        elif 0.05 < aspect_ratio < 20.0:
            confidence += 5
        
        # Điểm từ solidity (20 điểm)
        if solidity > 0.85:
            confidence += 20
        elif solidity > 0.7:
            confidence += 15
        elif solidity > 0.5:
            confidence += 10
        elif solidity > 0.3:
            confidence += 5
        
        # Điểm từ extent (15 điểm)
        if extent > 0.7:
            confidence += 15
        elif extent > 0.5:
            confidence += 10
        elif extent > 0.3:
            confidence += 5
        
        # Điểm từ nội dung (10 điểm)
        if content_analysis["has_text"] or content_analysis["has_lines"] > 1:
            confidence += 10
        elif content_analysis["density"] > 0.05:
            confidence += 5
        
        # Điểm từ kích thước tuyệt đối
        if contour_area > 5000:
            confidence += 10
        elif contour_area > 2000:
            confidence += 5
        
        # Phạt cho shape quá tròn (có thể là noise)
        if circularity > 0.8 and area_ratio < 0.01:
            confidence -= 20
        
        # Phạt cho vùng quá nhỏ hoặc quá lớn
        if area_ratio > 0.7 or area_ratio < 0.002:
            confidence -= 15
        
        return max(0, confidence)
    
    def _non_maximum_suppression(self, candidates, iou_threshold=0.3):
        """Non-Maximum Suppression để loại bỏ overlapping boxes"""
        if not candidates:
            return []
        
        # Sắp xếp theo confidence
        candidates = sorted(candidates, key=lambda x: x['confidence'], reverse=True)
        
        keep = []
        while candidates:
            # Lấy candidate có confidence cao nhất
            current = candidates.pop(0)
            keep.append(current)
            
            # Loại bỏ các candidates overlap quá nhiều
            remaining = []
            for candidate in candidates:
                iou = self._calculate_iou(current, candidate)
                if iou < iou_threshold:
                    remaining.append(candidate)
            
            candidates = remaining
        
        return keep
    
    def _calculate_iou(self, box1, box2):
        """Tính Intersection over Union"""
        x1_1, y1_1, x2_1, y2_1 = box1['x0'], box1['y0'], box1['x1'], box1['y1']
        x1_2, y1_2, x2_2, y2_2 = box2['x0'], box2['y0'], box2['x1'], box2['y1']
        
        # Tính intersection
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right <= x_left or y_bottom <= y_top:
            return 0.0
        
        intersection = (x_right - x_left) * (y_bottom - y_top)
        
        # Tính union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _enhance_cropped_image(self, crop):
        """Cải thiện chất lượng ảnh cắt"""
        # Khử nhiễu nhẹ
        crop = cv2.medianBlur(crop, 3)
        
        # Tăng cường độ tương phản
        lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        l = clahe.apply(l)
        crop = cv2.merge([l, a, b])
        crop = cv2.cvtColor(crop, cv2.COLOR_LAB2RGB)
        
        return crop
    
    def create_debug_image(self, image_bytes, figures):
        """Tạo ảnh debug với thông tin chi tiết"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'magenta', 'lime']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            bbox = fig['original_bbox']
            x, y, w, h = bbox
            
            # Vẽ khung với độ dày tùy theo confidence
            thickness = 4 if fig['confidence'] > 80 else 3 if fig['confidence'] > 60 else 2
            draw.rectangle([x, y, x+w, y+h], outline=color, width=thickness)
            
            # Vẽ label với thông tin chi tiết
            conf_class = "HIGH" if fig['confidence'] > 80 else "MED" if fig['confidence'] > 60 else "LOW"
            label = f"{fig['name']}\n{conf_class}: {fig['confidence']:.0f}%\nAR: {fig['aspect_ratio']:.2f}"
            
            # Vẽ background cho text
            lines = label.split('\n')
            max_width = max(len(line) for line in lines) * 7
            text_height = len(lines) * 15
            draw.rectangle([x, y-text_height-5, x+max_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(lines):
                draw.text((x+2, y-text_height+j*12), line, fill='white')
        
        return img_pil
    
    def insert_figures_into_text(self, text, figures, img_h, img_w):
        """Chèn ảnh/bảng vào văn bản với logic cải thiện"""
        lines = self._preprocess_text_lines(text)
        
        figures_sorted = sorted(
            [fig for fig in figures if fig.get('bbox')],
            key=lambda f: (f['bbox'][1], f['bbox'][0])
        )
        
        processed_lines = []
        used_figures = set()
        fig_idx = 0
        
        for i, line in enumerate(lines):
            processed_lines.append(line)
            
            inserted = self._try_insert_figure(
                line, figures_sorted, used_figures, 
                processed_lines, fig_idx
            )
            
            if isinstance(inserted, int):
                fig_idx = inserted
        
        # Chèn các ảnh còn lại
        processed_lines = self._insert_remaining_figures(
            processed_lines, figures_sorted, used_figures, fig_idx
        )
        
        return '\n'.join(processed_lines)
    
    def _preprocess_text_lines(self, text):
        """Tiền xử lý văn bản"""
        lines = []
        current_line = ""
        
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped:
                if current_line:
                    current_line += " " + stripped
                else:
                    current_line = stripped
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                if lines:
                    lines.append('')
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def _try_insert_figure(self, line, figures_sorted, used_figures, processed_lines, fig_idx):
        """Thử chèn ảnh/bảng dựa trên từ khóa"""
        lower_line = line.lower()
        
        # Từ khóa cho bảng (mở rộng)
        table_keywords = [
            "bảng", "bảng giá trị", "bảng biến thiên", "bảng tần số", 
            "bảng số liệu", "table", "cho bảng", "theo bảng", "bảng sau",
            "quan sát bảng", "từ bảng", "dựa vào bảng", "bảng trên",
            "trong bảng", "bảng dưới", "xem bảng"
        ]
        
        # Từ khóa cho hình
        image_keywords = [
            "hình vẽ", "hình bên", "(hình", "xem hình", "đồ thị", 
            "biểu đồ", "minh họa", "hình", "figure", "chart", "graph",
            "cho hình", "theo hình", "hình sau", "quan sát hình",
            "từ hình", "dựa vào hình", "sơ đồ", "hình trên",
            "trong hình", "hình dưới"
        ]
        
        # Kiểm tra bảng trước
        if any(keyword in lower_line for keyword in table_keywords):
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[BẢNG: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        # Kiểm tra hình ảnh
        elif any(keyword in lower_line for keyword in image_keywords):
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if not fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[HÌNH: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        return fig_idx
    
    def _insert_remaining_figures(self, processed_lines, figures_sorted, used_figures, fig_idx):
        """Chèn các ảnh còn lại"""
        question_patterns = [
            r"^(Câu|Question|Problem)\s*\d+",
            r"^\d+[\.\)]\s*",
            r"^[A-D][\.\)]\s*",
            r"^[a-d][\.\)]\s*"
        ]
        
        for i, line in enumerate(processed_lines):
            is_question = any(re.match(pattern, line.strip()) for pattern in question_patterns)
            
            if is_question and fig_idx < len(figures_sorted):
                next_line = processed_lines[i+1] if i+1 < len(processed_lines) else ""
                has_image = re.match(r"\[(HÌNH|BẢNG):.*\]", next_line.strip())
                
                if not has_image:
                    while (fig_idx < len(figures_sorted) and 
                           figures_sorted[fig_idx]['name'] in used_figures):
                        fig_idx += 1
                    
                    if fig_idx < len(figures_sorted):
                        fig = figures_sorted[fig_idx]
                        tag = (f"\n[BẢNG: {fig['name']}]\n" if fig['is_table'] 
                               else f"\n[HÌNH: {fig['name']}]\n")
                        processed_lines.insert(i+1, tag)
                        used_figures.add(fig['name'])
                        fig_idx += 1
        
        return processed_lines

class GeminiAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    def encode_image(self, image_data: bytes) -> str:
        """Mã hóa ảnh thành base64"""
        return base64.b64encode(image_data).decode('utf-8')
    
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str:
        """Chuyển đổi nội dung sang LaTeX sử dụng Gemini API"""
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
        """Trích xuất ảnh và chuyển đổi trang PDF thành ảnh"""
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        images = []
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            mat = fitz.Matrix(3.0, 3.0)  # Tăng độ phân giải lên 3x
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class WordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        """Tạo file Word với định dạng LaTeX chuẩn"""
        doc = Document()
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu đã chuyển đổi từ PDF/Ảnh', 0)
        title.alignment = 1
        
        # Thêm thông tin
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter Ultra")
        doc.add_paragraph(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        # Xử lý nội dung LaTeX với định dạng ${......}$
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua các dòng ```latex nếu có
            if line.startswith('```') or line.endswith('```'):
                continue
            
            # Xử lý tag ảnh/bảng đã tách
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
            
            # Xử lý công thức LaTeX với định dạng ${......}$
            if '${' in line and '}$'
        
        # Thêm ảnh gốc nếu có (fallback)
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
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """Chèn ảnh đã tách vào Word document"""
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
    """Kiểm tra tính hợp lệ của API key"""
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    """Chuyển đổi kích thước file sang định dạng human-readable"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Ultra Enhanced</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key
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
        
        # Cài đặt tách ảnh siêu nâng cao
        st.subheader("🖼️ Tách ảnh siêu chính xác")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng siêu nâng cao", value=True, 
                                       help="Thuật toán AI tách ảnh với độ chính xác cực cao")
        
        if enable_extraction:
            st.write("**Cài đặt siêu nâng cao:**")
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 5.0, 0.3, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 25, 12, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 300, 40, 10)
            padding = st.slider("Padding xung quanh (px)", 0, 30, 8, 1)
            confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 50, 5)
            
            show_debug = st.checkbox("Hiển thị ảnh debug nâng cao", value=True,
                                   help="Hiển thị ảnh với confidence score và phân tích chi tiết")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng siêu nâng cao:
        - ✅ Thuật toán AI cắt ảnh với NMS
        - ✅ Confidence scoring thông minh
        - ✅ Định dạng LaTeX chuẩn: `${......}$`
        - ✅ Phân tích nội dung vùng
        - ✅ Multi-scale edge detection
        
        ### 📝 Định dạng OUTPUT chuẩn:
        **Công thức toán học:** `${x^2 + y^2}import streamlit as st
import requests
import base64
import io
import json
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
from docx import Document
import tempfile
import os
import re
import time
import cv2
import numpy as np

# Cấu hình trang
st.set_page_config(
    page_title="PDF/Image to LaTeX Converter - Ultra Enhanced",
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
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-medium { color: #ffc107; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

class UltraImageExtractor:
    """
    Class siêu nâng cao để tách ảnh/bảng với độ chính xác cực cao
    """
    
    def __init__(self):
        self.min_area_ratio = 0.003    # Diện tích tối thiểu (% của ảnh gốc)
        self.min_area_abs = 1000       # Diện tích tối thiểu (pixel)
        self.min_width = 40            # Chiều rộng tối thiểu
        self.min_height = 40           # Chiều cao tối thiểu
        self.max_figures = 12          # Số lượng ảnh tối đa
        self.padding = 8               # Padding xung quanh ảnh cắt
        self.confidence_threshold = 50 # Ngưỡng confidence tối thiểu
    
    def extract_figures_and_tables(self, image_bytes):
        """Tách ảnh và bảng với thuật toán siêu chính xác"""
        # 1. Đọc và tiền xử lý ảnh
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(img_pil)
        h, w = img.shape[:2]
        
        # 2. Tiền xử lý ảnh đa cấp độ
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Khử nhiễu mạnh
        gray = cv2.medianBlur(gray, 5)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Tăng cường độ tương phản adaptive
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # 3. Phát hiện cạnh đa phương pháp
        # Phương pháp 1: Adaptive threshold với nhiều kích thước kernel
        thresh1 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 3)
        
        # Phương pháp 2: Canny với multiple scales
        edges1 = cv2.Canny(gray, 30, 100, apertureSize=3)
        edges2 = cv2.Canny(gray, 50, 150, apertureSize=3)
        edges3 = cv2.Canny(gray, 80, 200, apertureSize=5)
        
        # Phương pháp 3: Gradient-based detection
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient = np.sqrt(sobelx**2 + sobely**2)
        gradient = np.uint8(gradient / gradient.max() * 255)
        _, gradient_thresh = cv2.threshold(gradient, 50, 255, cv2.THRESH_BINARY)
        
        # 4. Kết hợp tất cả phương pháp
        combined = cv2.bitwise_or(thresh1, thresh2)
        combined = cv2.bitwise_or(combined, edges1)
        combined = cv2.bitwise_or(combined, edges2) 
        combined = cv2.bitwise_or(combined, edges3)
        combined = cv2.bitwise_or(combined, gradient_thresh)
        
        # 5. Morphological operations để làm sạch
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_close)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_open)
        
        # Dilate nhẹ để kết nối các thành phần
        kernel_dilate = np.ones((2, 2), np.uint8)
        combined = cv2.dilate(combined, kernel_dilate, iterations=1)
        
        # 6. Tìm contours với hierarchy
        contours, hierarchy = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 7. Lọc và phân tích contours với nhiều tiêu chí
        candidates = []
        
        for i, cnt in enumerate(contours):
            # Tính toán bounding box
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            area_ratio = area / (w * h)
            aspect_ratio = ww / (hh + 1e-6)
            
            # Lọc kích thước cơ bản
            if (area < self.min_area_abs or 
                area_ratio < self.min_area_ratio or 
                area_ratio > 0.8):
                continue
            
            if ww < self.min_width or hh < self.min_height:
                continue
            
            # Lọc aspect ratio hợp lý
            if not (0.05 < aspect_ratio < 20.0):
                continue
            
            # Loại bỏ vùng ở rìa ảnh
            margin = 0.01
            if (x < margin*w or y < margin*h or 
                (x+ww) > (1-margin)*w or (y+hh) > (1-margin)*h):
                continue
            
            # Tính các đặc trưng hình học nâng cao
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(cnt)
            
            if hull_area == 0 or contour_area < 100:
                continue
            
            # Tính toán các metrics chất lượng
            solidity = float(contour_area) / hull_area
            extent = float(contour_area) / area
            
            # Tính chu vi và circularity
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * contour_area / (perimeter ** 2)
            
            # Lọc các shape quá phức tạp hoặc quá đơn giản
            if solidity < 0.2 or extent < 0.15:
                continue
            
            # Tính moments để kiểm tra shape regularity
            moments = cv2.moments(cnt)
            if moments['m00'] == 0:
                continue
            
            # Phân tích nội dung vùng để phân loại
            roi = gray[y:y+hh, x:x+ww]
            content_analysis = self._analyze_region_content(roi)
            
            # Phân loại bảng vs hình
            is_table = self._advanced_table_classification(x, y, ww, hh, w, h, cnt, roi, content_analysis)
            
            # Tính điểm confidence nâng cao
            confidence = self._calculate_advanced_confidence(
                area_ratio, aspect_ratio, solidity, extent, circularity,
                ww, hh, w, h, content_analysis, contour_area
            )
            
            # Chỉ giữ lại những vùng có confidence cao
            if confidence < self.confidence_threshold:
                continue
            
            candidates.append({
                "area": area,
                "x0": x, "y0": y, "x1": x+ww, "y1": y+hh,
                "width": ww, "height": hh,
                "is_table": is_table,
                "confidence": confidence,
                "aspect_ratio": aspect_ratio,
                "solidity": solidity,
                "extent": extent,
                "circularity": circularity,
                "content_analysis": content_analysis,
                "bbox": (x, y, ww, hh),
                "contour": cnt
            })
        
        # 8. Sắp xếp và lọc overlapping với thuật toán NMS
        candidates = sorted(candidates, key=lambda f: f['confidence'], reverse=True)
        candidates = self._non_maximum_suppression(candidates, iou_threshold=0.3)
        candidates = candidates[:self.max_figures]
        
        # 9. Sắp xếp theo vị trí đọc (top-to-bottom, left-to-right)
        candidates = sorted(candidates, key=lambda box: (box["y0"] + box["height"]//2, box["x0"]))
        
        # 10. Tạo ảnh kết quả với quality cao
        final_figures = []
        img_idx = 0
        table_idx = 0
        
        for fig_data in candidates:
            # Cắt ảnh với padding thông minh
            x0 = max(0, fig_data["x0"] - self.padding)
            y0 = max(0, fig_data["y0"] - self.padding)
            x1 = min(w, fig_data["x1"] + self.padding)
            y1 = min(h, fig_data["y1"] + self.padding)
            
            crop = img[y0:y1, x0:x1]
            
            if crop.size == 0:
                continue
            
            # Post-process ảnh cắt
            crop = self._enhance_cropped_image(crop)
            
            # Chuyển thành base64 với quality cao
            buf = io.BytesIO()
            Image.fromarray(crop).save(buf, format="JPEG", quality=98, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            # Đặt tên file thông minh
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
                "bbox": (x0, y0, x1-x0, y1-y0),
                "original_bbox": fig_data["bbox"],
                "confidence": fig_data["confidence"],
                "aspect_ratio": fig_data["aspect_ratio"],
                "area": fig_data["area"],
                "solidity": fig_data["solidity"],
                "content_analysis": fig_data["content_analysis"]
            })
        
        return final_figures, h, w
    
    def _analyze_region_content(self, roi):
        """Phân tích nội dung vùng để hỗ trợ phân loại"""
        if roi.shape[0] < 10 or roi.shape[1] < 10:
            return {"has_text": False, "has_lines": 0, "density": 0, "uniformity": 0}
        
        # Phát hiện text regions (vùng có nhiều pixel đen nhỏ)
        kernel_text = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))
        _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        text_regions = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_text)
        has_text = np.sum(text_regions) > roi.shape[0] * roi.shape[1] * 0.05
        
        # Phát hiện đường kẻ ngang và dọc
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min(roi.shape[1]//3, 40), 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min(roi.shape[0]//3, 40)))
        
        horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
        
        h_lines = len(cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
        v_lines = len(cv2.findContours(vertical_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
        
        # Tính mật độ pixel
        density = np.sum(binary) / (roi.shape[0] * roi.shape[1] * 255)
        
        # Tính độ đồng đều (uniformity)
        hist = cv2.calcHist([roi], [0], None, [256], [0, 256])
        uniformity = np.sum((hist / hist.sum()) ** 2)
        
        return {
            "has_text": has_text,
            "has_lines": h_lines + v_lines,
            "h_lines": h_lines,
            "v_lines": v_lines,
            "density": density,
            "uniformity": uniformity
        }
    
    def _advanced_table_classification(self, x, y, w, h, img_w, img_h, contour, roi, content_analysis):
        """Phân loại bảng vs hình ảnh với thuật toán nâng cao"""
        aspect_ratio = w / (h + 1e-6)
        
        # Điểm từ kích thước và tỷ lệ
        size_score = 0
        if w > 0.25 * img_w:  # Bảng thường rộng
            size_score += 3
        if h > 0.08 * img_h and h < 0.7 * img_h:  # Chiều cao vừa phải
            size_score += 2
        if 1.5 < aspect_ratio < 10.0:  # Tỷ lệ phù hợp cho bảng
            size_score += 3
        
        # Điểm từ phân tích nội dung
        content_score = 0
        if content_analysis["has_lines"] > 2:  # Có đường kẻ
            content_score += 4
        if content_analysis["h_lines"] > 1:  # Có đường kẻ ngang
            content_score += 3
        if content_analysis["v_lines"] > 0:  # Có đường kẻ dọc
            content_score += 2
        if content_analysis["has_text"]:  # Có text
            content_score += 2
        if 0.1 < content_analysis["density"] < 0.4:  # Mật độ vừa phải
            content_score += 2
        
        # Điểm từ vị trí (bảng thường ở giữa)
        position_score = 0
        center_x_ratio = (x + w/2) / img_w
        if 0.1 < center_x_ratio < 0.9:
            position_score += 1
        
        total_score = size_score + content_score + position_score
        
        # Ngưỡng phân loại động dựa trên confidence
        threshold = 6 if content_analysis["has_lines"] > 3 else 8
        
        return total_score >= threshold
    
    def _calculate_advanced_confidence(self, area_ratio, aspect_ratio, solidity, extent, 
                                     circularity, w, h, img_w, img_h, content_analysis, contour_area):
        """Tính confidence score nâng cao"""
        confidence = 0
        
        # Điểm từ kích thước (30 điểm)
        if 0.005 < area_ratio < 0.6:
            if 0.02 < area_ratio < 0.3:
                confidence += 30
            elif 0.01 < area_ratio < 0.5:
                confidence += 20
            else:
                confidence += 10
        
        # Điểm từ aspect ratio (25 điểm)
        if 0.3 < aspect_ratio < 5.0:
            confidence += 25
        elif 0.1 < aspect_ratio < 10.0:
            confidence += 15
        elif 0.05 < aspect_ratio < 20.0:
            confidence += 5
        
        # Điểm từ solidity (20 điểm)
        if solidity > 0.85:
            confidence += 20
        elif solidity > 0.7:
            confidence += 15
        elif solidity > 0.5:
            confidence += 10
        elif solidity > 0.3:
            confidence += 5
        
        # Điểm từ extent (15 điểm)
        if extent > 0.7:
            confidence += 15
        elif extent > 0.5:
            confidence += 10
        elif extent > 0.3:
            confidence += 5
        
        # Điểm từ nội dung (10 điểm)
        if content_analysis["has_text"] or content_analysis["has_lines"] > 1:
            confidence += 10
        elif content_analysis["density"] > 0.05:
            confidence += 5
        
        # Điểm từ kích thước tuyệt đối
        if contour_area > 5000:
            confidence += 10
        elif contour_area > 2000:
            confidence += 5
        
        # Phạt cho shape quá tròn (có thể là noise)
        if circularity > 0.8 and area_ratio < 0.01:
            confidence -= 20
        
        # Phạt cho vùng quá nhỏ hoặc quá lớn
        if area_ratio > 0.7 or area_ratio < 0.002:
            confidence -= 15
        
        return max(0, confidence)
    
    def _non_maximum_suppression(self, candidates, iou_threshold=0.3):
        """Non-Maximum Suppression để loại bỏ overlapping boxes"""
        if not candidates:
            return []
        
        # Sắp xếp theo confidence
        candidates = sorted(candidates, key=lambda x: x['confidence'], reverse=True)
        
        keep = []
        while candidates:
            # Lấy candidate có confidence cao nhất
            current = candidates.pop(0)
            keep.append(current)
            
            # Loại bỏ các candidates overlap quá nhiều
            remaining = []
            for candidate in candidates:
                iou = self._calculate_iou(current, candidate)
                if iou < iou_threshold:
                    remaining.append(candidate)
            
            candidates = remaining
        
        return keep
    
    def _calculate_iou(self, box1, box2):
        """Tính Intersection over Union"""
        x1_1, y1_1, x2_1, y2_1 = box1['x0'], box1['y0'], box1['x1'], box1['y1']
        x1_2, y1_2, x2_2, y2_2 = box2['x0'], box2['y0'], box2['x1'], box2['y1']
        
        # Tính intersection
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right <= x_left or y_bottom <= y_top:
            return 0.0
        
        intersection = (x_right - x_left) * (y_bottom - y_top)
        
        # Tính union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _enhance_cropped_image(self, crop):
        """Cải thiện chất lượng ảnh cắt"""
        # Khử nhiễu nhẹ
        crop = cv2.medianBlur(crop, 3)
        
        # Tăng cường độ tương phản
        lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        l = clahe.apply(l)
        crop = cv2.merge([l, a, b])
        crop = cv2.cvtColor(crop, cv2.COLOR_LAB2RGB)
        
        return crop
    
    def create_debug_image(self, image_bytes, figures):
        """Tạo ảnh debug với thông tin chi tiết"""
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img_pil)
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'magenta', 'lime']
        
        for i, fig in enumerate(figures):
            color = colors[i % len(colors)]
            bbox = fig['original_bbox']
            x, y, w, h = bbox
            
            # Vẽ khung với độ dày tùy theo confidence
            thickness = 4 if fig['confidence'] > 80 else 3 if fig['confidence'] > 60 else 2
            draw.rectangle([x, y, x+w, y+h], outline=color, width=thickness)
            
            # Vẽ label với thông tin chi tiết
            conf_class = "HIGH" if fig['confidence'] > 80 else "MED" if fig['confidence'] > 60 else "LOW"
            label = f"{fig['name']}\n{conf_class}: {fig['confidence']:.0f}%\nAR: {fig['aspect_ratio']:.2f}"
            
            # Vẽ background cho text
            lines = label.split('\n')
            max_width = max(len(line) for line in lines) * 7
            text_height = len(lines) * 15
            draw.rectangle([x, y-text_height-5, x+max_width, y], fill=color, outline=color)
            
            # Vẽ text
            for j, line in enumerate(lines):
                draw.text((x+2, y-text_height+j*12), line, fill='white')
        
        return img_pil
    
    def insert_figures_into_text(self, text, figures, img_h, img_w):
        """Chèn ảnh/bảng vào văn bản với logic cải thiện"""
        lines = self._preprocess_text_lines(text)
        
        figures_sorted = sorted(
            [fig for fig in figures if fig.get('bbox')],
            key=lambda f: (f['bbox'][1], f['bbox'][0])
        )
        
        processed_lines = []
        used_figures = set()
        fig_idx = 0
        
        for i, line in enumerate(lines):
            processed_lines.append(line)
            
            inserted = self._try_insert_figure(
                line, figures_sorted, used_figures, 
                processed_lines, fig_idx
            )
            
            if isinstance(inserted, int):
                fig_idx = inserted
        
        # Chèn các ảnh còn lại
        processed_lines = self._insert_remaining_figures(
            processed_lines, figures_sorted, used_figures, fig_idx
        )
        
        return '\n'.join(processed_lines)
    
    def _preprocess_text_lines(self, text):
        """Tiền xử lý văn bản"""
        lines = []
        current_line = ""
        
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped:
                if current_line:
                    current_line += " " + stripped
                else:
                    current_line = stripped
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                if lines:
                    lines.append('')
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def _try_insert_figure(self, line, figures_sorted, used_figures, processed_lines, fig_idx):
        """Thử chèn ảnh/bảng dựa trên từ khóa"""
        lower_line = line.lower()
        
        # Từ khóa cho bảng (mở rộng)
        table_keywords = [
            "bảng", "bảng giá trị", "bảng biến thiên", "bảng tần số", 
            "bảng số liệu", "table", "cho bảng", "theo bảng", "bảng sau",
            "quan sát bảng", "từ bảng", "dựa vào bảng", "bảng trên",
            "trong bảng", "bảng dưới", "xem bảng"
        ]
        
        # Từ khóa cho hình
        image_keywords = [
            "hình vẽ", "hình bên", "(hình", "xem hình", "đồ thị", 
            "biểu đồ", "minh họa", "hình", "figure", "chart", "graph",
            "cho hình", "theo hình", "hình sau", "quan sát hình",
            "từ hình", "dựa vào hình", "sơ đồ", "hình trên",
            "trong hình", "hình dưới"
        ]
        
        # Kiểm tra bảng trước
        if any(keyword in lower_line for keyword in table_keywords):
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[BẢNG: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        # Kiểm tra hình ảnh
        elif any(keyword in lower_line for keyword in image_keywords):
            for j in range(fig_idx, len(figures_sorted)):
                fig = figures_sorted[j]
                if not fig['is_table'] and fig['name'] not in used_figures:
                    tag = f"\n[HÌNH: {fig['name']}]\n"
                    processed_lines.append(tag)
                    used_figures.add(fig['name'])
                    return j + 1
        
        return fig_idx
    
    def _insert_remaining_figures(self, processed_lines, figures_sorted, used_figures, fig_idx):
        """Chèn các ảnh còn lại"""
        question_patterns = [
            r"^(Câu|Question|Problem)\s*\d+",
            r"^\d+[\.\)]\s*",
            r"^[A-D][\.\)]\s*",
            r"^[a-d][\.\)]\s*"
        ]
        
        for i, line in enumerate(processed_lines):
            is_question = any(re.match(pattern, line.strip()) for pattern in question_patterns)
            
            if is_question and fig_idx < len(figures_sorted):
                next_line = processed_lines[i+1] if i+1 < len(processed_lines) else ""
                has_image = re.match(r"\[(HÌNH|BẢNG):.*\]", next_line.strip())
                
                if not has_image:
                    while (fig_idx < len(figures_sorted) and 
                           figures_sorted[fig_idx]['name'] in used_figures):
                        fig_idx += 1
                    
                    if fig_idx < len(figures_sorted):
                        fig = figures_sorted[fig_idx]
                        tag = (f"\n[BẢNG: {fig['name']}]\n" if fig['is_table'] 
                               else f"\n[HÌNH: {fig['name']}]\n")
                        processed_lines.insert(i+1, tag)
                        used_figures.add(fig['name'])
                        fig_idx += 1
        
        return processed_lines

class GeminiAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    def encode_image(self, image_data: bytes) -> str:
        """Mã hóa ảnh thành base64"""
        return base64.b64encode(image_data).decode('utf-8')
    
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str:
        """Chuyển đổi nội dung sang LaTeX sử dụng Gemini API"""
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
        """Trích xuất ảnh và chuyển đổi trang PDF thành ảnh"""
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        images = []
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            mat = fitz.Matrix(3.0, 3.0)  # Tăng độ phân giải lên 3x
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append((img, page_num + 1))
        
        pdf_document.close()
        return images

class WordExporter:
    @staticmethod
    def create_word_document(latex_content: str, extracted_figures=None, images=None) -> io.BytesIO:
        """Tạo file Word với định dạng LaTeX chuẩn"""
        doc = Document()
        
        # Thêm tiêu đề
        title = doc.add_heading('Tài liệu đã chuyển đổi từ PDF/Ảnh', 0)
        title.alignment = 1
        
        # Thêm thông tin
        doc.add_paragraph(f"Được tạo bởi PDF/Image to LaTeX Converter Ultra")
        doc.add_paragraph(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        # Xử lý nội dung LaTeX với định dạng ${......}$
        lines = latex_content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua các dòng ```latex nếu có
            if line.startswith('```') or line.endswith('```'):
                continue
            
            # Xử lý tag ảnh/bảng đã tách
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
            
            # Xử lý công thức LaTeX với định dạng ${......}$
            if '${' in line and '}
        
        # Thêm ảnh gốc nếu có (fallback)
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
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """Chèn ảnh đã tách vào Word document"""
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
    """Kiểm tra tính hợp lệ của API key"""
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    """Chuyển đổi kích thước file sang định dạng human-readable"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Ultra Enhanced</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key
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
        
        # Cài đặt tách ảnh siêu nâng cao
        st.subheader("🖼️ Tách ảnh siêu chính xác")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng siêu nâng cao", value=True, 
                                       help="Thuật toán AI tách ảnh với độ chính xác cực cao")
        
        if enable_extraction:
            st.write("**Cài đặt siêu nâng cao:**")
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 5.0, 0.3, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 25, 12, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 300, 40, 10)
            padding = st.slider("Padding xung quanh (px)", 0, 30, 8, 1)
            confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 50, 5)
            
            show_debug = st.checkbox("Hiển thị ảnh debug nâng cao", value=True,
                                   help="Hiển thị ảnh với confidence score và phân tích chi tiết")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng siêu nâng cao:
        - ✅ Thuật toán AI cắt ảnh với NMS
        - ✅ Confidence scoring thông minh
        - ✅ Định dạng LaTeX chuẩn: `${......}$`
        - ✅ Phân tích nội dung vùng
        - ✅ Multi-scale edge detection
        

        
        **Trắc nghiệm 4 phương án:**
        ```
        Câu X: [nội dung]
        A. [Đáp án]
        B. [Đáp án]  
        C. [Đáp án]
        D. [Đáp án]
        ```
        
        **Trắc nghiệm đúng sai:**
        ```
        Câu X: [nội dung nếu có]
        a) [Đáp án]
        b) [Đáp án]
        c) [Đáp án]
        d) [Đáp án]
        ```
        
        **Tự luận:**
        ```
        Câu X: [nội dung]
        ```
        
        ### 🔑 Lấy API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại Google AI Studio")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX + Ultra Extract", "🖼️ Image to LaTeX + Ultra Extract"])
    
    # Khởi tạo API và ImageExtractor
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction:
            image_extractor = UltraImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.padding = padding
            image_extractor.confidence_threshold = confidence_threshold
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học và hình ảnh"
        )
        
        if uploaded_pdf:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                with st.spinner("🔄 Đang xử lý PDF với độ phân giải cao..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang (3x resolution)")
                        
                        # Hiển thị preview
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)} với AI siêu nâng cao...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh/bảng nếu được bật
                            extracted_figures = []
                            if enable_extraction:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    # Tạo ảnh debug
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_image(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    high_conf = len([f for f in figures if f['confidence'] > 80])
                                    st.write(f"🎯 Trang {page_num}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                                    
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Tạo prompt siêu cải tiến cho Gemini
                            prompt = f"""
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh trang {page_num} thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${{x^2 + y^2}}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${{\\frac{{a+b}}{{c-d}}}}$, ${{\\int_0^1 x dx}}$, ${{\\sqrt{{x^2+1}}}}$, ${{\\perp}}$, ${{\\parallel}}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${{\\perp}}$
- Song song: ${{\\parallel}}$ hoặc //
- Góc: ${{\\angle}}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${{^\\circ}}$

6. **Hình ảnh và bảng:**
{'- Khi thấy hình ảnh/đồ thị: dùng "xem hình", "theo hình", "hình sau"' if enable_extraction else ''}
{'- Khi thấy bảng: dùng "bảng sau", "theo bảng", "quan sát bảng"' if enable_extraction else ''}

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${{...}}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${{ABCD.A'B'C'D'}}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${{ABCD}}$ là hình chữ nhật.
b) ${{A'C' \\perp BD}}$
c) ${{A'B \\perp D'C}}$  
d) ${{BC' \\perp A'D}}$
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    # Chèn ảnh vào văn bản nếu có tách ảnh
                                    if enable_extraction and extracted_figures:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, h, w
                                        )
                                    
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                        
                        # Hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.text_area("📝 Kết quả (định dạng chuẩn - văn bản thuần túy):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị thống kê chi tiết
                        if enable_extraction:
                            total_figs = len(all_extracted_figures)
                            high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                            medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                            low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                            
                            st.markdown(f"""
                            **📊 Thống kê chi tiết:**
                            - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                            - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                            - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                            - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                            """, unsafe_allow_html=True)
                            
                            # Hiển thị ảnh debug và ảnh đã cắt
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    st.write(f"**🔍 Trang {page_num} - AI Detection Analysis:**")
                                    st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng với confidence scores", use_column_width=True)
                                    
                                    # Hiển thị từng ảnh đã cắt với thông tin siêu chi tiết
                                    if figures:
                                        st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                        cols = st.columns(min(len(figures), 3))
                                        for idx, fig in enumerate(figures):
                                            with cols[idx % 3]:
                                                # Decode và hiển thị ảnh cắt
                                                img_data = base64.b64decode(fig['base64'])
                                                img_pil = Image.open(io.BytesIO(img_data))
                                                
                                                st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                                st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                                
                                                # Xác định màu confidence
                                                conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                                
                                                # Thông tin siêu chi tiết
                                                st.markdown(f'''
                                                <div class="image-info">
                                                <strong>{fig['name']}</strong><br>
                                                🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                                <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                                📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                                📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                                🔺 Solidity: {fig['solidity']:.2f}<br>
                                                📊 Diện tích: {fig['area']:,}px²<br>
                                                {'🔍 Phân tích: ' + str(fig.get('content_analysis', {}).get('has_lines', 0)) + ' đường kẻ' if 'content_analysis' in fig else ''}
                                                </div>
                                                ''', unsafe_allow_html=True)
                                                st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_ultra_latex.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
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
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh (tương tự như PDF tab)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học và hình minh họa"
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    all_debug_images = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)} với AI siêu nâng cao...")
                        
                        image_bytes = uploaded_image.getvalue()
                        image_pil = Image.open(uploaded_image)
                        all_original_images.append(image_pil)
                        
                        # Tách ảnh/bảng nếu được bật
                        extracted_figures = []
                        if enable_extraction:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                # Tạo ảnh debug
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_image(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                high_conf = len([f for f in figures if f['confidence'] > 80])
                                st.write(f"🎯 {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt = """
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${x^2 + y^2}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${\\frac{a+b}{c-d}}$, ${\\int_0^1 x dx}$, ${\\sqrt{x^2+1}}$, ${\\perp}$, ${\\parallel}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${\\perp}$
- Song song: ${\\parallel}$ hoặc //
- Góc: ${\\angle}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${^\\circ}$

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${...}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${ABCD}$ là hình chữ nhật.
b) ${A'C' \\perp BD}$
c) ${A'B \\perp D'C}$  
d) ${BC' \\perp A'D}$
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                # Chèn ảnh vào văn bản nếu có tách ảnh
                                if enable_extraction and extracted_figures:
                                    latex_result = image_extractor.insert_figures_into_text(
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
                    
                    status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                    
                    # Hiển thị kết quả
                    combined_latex = "\n".join(all_latex_content)
                    
                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                    st.text_area("📝 Kết quả (định dạng chuẩn - văn bản thuần túy):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Hiển thị thống kê và ảnh debug (tương tự PDF tab)
                    if enable_extraction:
                        total_figs = len(all_extracted_figures)
                        high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                        medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                        low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                        
                        st.markdown(f"""
                        **📊 Thống kê chi tiết:**
                        - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                        - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                        - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                        - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                        """, unsafe_allow_html=True)
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                st.write(f"**🔍 {img_name} - AI Detection Analysis:**")
                                st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng", use_column_width=True)
                                
                                if figures:
                                    st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                    cols = st.columns(min(len(figures), 3))
                                    for idx, fig in enumerate(figures):
                                        with cols[idx % 3]:
                                            img_data = base64.b64decode(fig['base64'])
                                            img_pil = Image.open(io.BytesIO(img_data))
                                            
                                            st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                            st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                            
                                            conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                            
                                            st.markdown(f'''
                                            <div class="image-info">
                                            <strong>{fig['name']}</strong><br>
                                            🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                            <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                            📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                            📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                            🔺 Solidity: {fig['solidity']:.2f}<br>
                                            📊 Diện tích: {fig['area']:,}px²
                                            </div>
                                            ''', unsafe_allow_html=True)
                                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('image_extracted_figures')
                                original_imgs = st.session_state.image_list
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
                                    data=word_buffer.getvalue(),
                                    file_name="images_ultra_latex.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>✨ <strong>Ultra Enhanced Version:</strong> AI siêu thông minh + Định dạng LaTeX chuẩn ${......}$!</p>
        <p>🎯 Thuật toán NMS + Multi-scale Detection + Content Analysis + Confidence Scoring</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main() in line:
                p = doc.add_paragraph()
                
                # Xử lý tất cả công thức ${......}$ trong dòng
                while '${' in line and '}
        
        # Thêm ảnh gốc nếu có (fallback)
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
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """Chèn ảnh đã tách vào Word document"""
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
    """Kiểm tra tính hợp lệ của API key"""
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    """Chuyển đổi kích thước file sang định dạng human-readable"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Ultra Enhanced</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key
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
        
        # Cài đặt tách ảnh siêu nâng cao
        st.subheader("🖼️ Tách ảnh siêu chính xác")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng siêu nâng cao", value=True, 
                                       help="Thuật toán AI tách ảnh với độ chính xác cực cao")
        
        if enable_extraction:
            st.write("**Cài đặt siêu nâng cao:**")
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 5.0, 0.3, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 25, 12, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 300, 40, 10)
            padding = st.slider("Padding xung quanh (px)", 0, 30, 8, 1)
            confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 50, 5)
            
            show_debug = st.checkbox("Hiển thị ảnh debug nâng cao", value=True,
                                   help="Hiển thị ảnh với confidence score và phân tích chi tiết")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng siêu nâng cao:
        - ✅ Thuật toán AI cắt ảnh với NMS
        - ✅ Confidence scoring thông minh
        - ✅ Định dạng LaTeX chuẩn: `${......}$`
        - ✅ Phân tích nội dung vùng
        - ✅ Multi-scale edge detection
        
        ### 📝 Định dạng LaTeX chuẩn:
        **Công thức inline:** `${x^2 + y^2}$`
        
        **Trắc nghiệm 4 phương án:**
        ```
        Câu X: [nội dung]
        A. [Đáp án]
        B. [Đáp án]  
        C. [Đáp án]
        D. [Đáp án]
        ```
        
        **Trắc nghiệm đúng sai:**
        ```
        a) [Đáp án]
        b) [Đáp án]
        c) [Đáp án]
        d) [Đáp án]
        ```
        
        ### 🔑 Lấy API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại Google AI Studio")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX + Ultra Extract", "🖼️ Image to LaTeX + Ultra Extract"])
    
    # Khởi tạo API và ImageExtractor
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction:
            image_extractor = UltraImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.padding = padding
            image_extractor.confidence_threshold = confidence_threshold
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học và hình ảnh"
        )
        
        if uploaded_pdf:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                with st.spinner("🔄 Đang xử lý PDF với độ phân giải cao..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang (3x resolution)")
                        
                        # Hiển thị preview
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)} với AI siêu nâng cao...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh/bảng nếu được bật
                            extracted_figures = []
                            if enable_extraction:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    # Tạo ảnh debug
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_image(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    high_conf = len([f for f in figures if f['confidence'] > 80])
                                    st.write(f"🎯 Trang {page_num}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                                    
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Tạo prompt siêu cải tiến cho Gemini
                            prompt = f"""
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh trang {page_num} thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${{x^2 + y^2}}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${{\\frac{{a+b}}{{c-d}}}}$, ${{\\int_0^1 x dx}}$, ${{\\sqrt{{x^2+1}}}}$, ${{\\perp}}$, ${{\\parallel}}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${{\\perp}}$
- Song song: ${{\\parallel}}$ hoặc //
- Góc: ${{\\angle}}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${{^\\circ}}$

6. **Hình ảnh và bảng:**
{'- Khi thấy hình ảnh/đồ thị: dùng "xem hình", "theo hình", "hình sau"' if enable_extraction else ''}
{'- Khi thấy bảng: dùng "bảng sau", "theo bảng", "quan sát bảng"' if enable_extraction else ''}

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${{...}}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${{ABCD.A'B'C'D'}}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${{ABCD}}$ là hình chữ nhật.
b) ${{A'C' \\perp BD}}$
c) ${{A'B \\perp D'C}}$  
d) ${{BC' \\perp A'D}}$
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    # Chèn ảnh vào văn bản nếu có tách ảnh
                                    if enable_extraction and extracted_figures:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, h, w
                                        )
                                    
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                        
                        # Hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.text_area("📝 Kết quả LaTeX (định dạng chuẩn ${......}$):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị thống kê chi tiết
                        if enable_extraction:
                            total_figs = len(all_extracted_figures)
                            high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                            medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                            low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                            
                            st.markdown(f"""
                            **📊 Thống kê chi tiết:**
                            - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                            - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                            - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                            - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                            """, unsafe_allow_html=True)
                            
                            # Hiển thị ảnh debug và ảnh đã cắt
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    st.write(f"**🔍 Trang {page_num} - AI Detection Analysis:**")
                                    st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng với confidence scores", use_column_width=True)
                                    
                                    # Hiển thị từng ảnh đã cắt với thông tin siêu chi tiết
                                    if figures:
                                        st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                        cols = st.columns(min(len(figures), 3))
                                        for idx, fig in enumerate(figures):
                                            with cols[idx % 3]:
                                                # Decode và hiển thị ảnh cắt
                                                img_data = base64.b64decode(fig['base64'])
                                                img_pil = Image.open(io.BytesIO(img_data))
                                                
                                                st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                                st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                                
                                                # Xác định màu confidence
                                                conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                                
                                                # Thông tin siêu chi tiết
                                                st.markdown(f'''
                                                <div class="image-info">
                                                <strong>{fig['name']}</strong><br>
                                                🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                                <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                                📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                                📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                                🔺 Solidity: {fig['solidity']:.2f}<br>
                                                📊 Diện tích: {fig['area']:,}px²<br>
                                                {'🔍 Phân tích: ' + str(fig.get('content_analysis', {}).get('has_lines', 0)) + ' đường kẻ' if 'content_analysis' in fig else ''}
                                                </div>
                                                ''', unsafe_allow_html=True)
                                                st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_ultra_latex.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
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
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh (tương tự như PDF tab)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học và hình minh họa"
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    all_debug_images = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)} với AI siêu nâng cao...")
                        
                        image_bytes = uploaded_image.getvalue()
                        image_pil = Image.open(uploaded_image)
                        all_original_images.append(image_pil)
                        
                        # Tách ảnh/bảng nếu được bật
                        extracted_figures = []
                        if enable_extraction:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                # Tạo ảnh debug
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_image(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                high_conf = len([f for f in figures if f['confidence'] > 80])
                                st.write(f"🎯 {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt = """
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${x^2 + y^2}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${\\frac{a+b}{c-d}}$, ${\\int_0^1 x dx}$, ${\\sqrt{x^2+1}}$, ${\\perp}$, ${\\parallel}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${\\perp}$
- Song song: ${\\parallel}$ hoặc //
- Góc: ${\\angle}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${^\\circ}$

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${...}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${ABCD}$ là hình chữ nhật.
b) ${A'C' \\perp BD}$
c) ${A'B \\perp D'C}$  
d) ${BC' \\perp A'D}$
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                # Chèn ảnh vào văn bản nếu có tách ảnh
                                if enable_extraction and extracted_figures:
                                    latex_result = image_extractor.insert_figures_into_text(
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
                    
                    status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                    
                    # Hiển thị kết quả
                    combined_latex = "\n".join(all_latex_content)
                    
                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                    st.text_area("📝 Kết quả LaTeX (định dạng chuẩn ${......}$):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Hiển thị thống kê và ảnh debug (tương tự PDF tab)
                    if enable_extraction:
                        total_figs = len(all_extracted_figures)
                        high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                        medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                        low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                        
                        st.markdown(f"""
                        **📊 Thống kê chi tiết:**
                        - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                        - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                        - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                        - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                        """, unsafe_allow_html=True)
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                st.write(f"**🔍 {img_name} - AI Detection Analysis:**")
                                st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng", use_column_width=True)
                                
                                if figures:
                                    st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                    cols = st.columns(min(len(figures), 3))
                                    for idx, fig in enumerate(figures):
                                        with cols[idx % 3]:
                                            img_data = base64.b64decode(fig['base64'])
                                            img_pil = Image.open(io.BytesIO(img_data))
                                            
                                            st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                            st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                            
                                            conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                            
                                            st.markdown(f'''
                                            <div class="image-info">
                                            <strong>{fig['name']}</strong><br>
                                            🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                            <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                            📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                            📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                            🔺 Solidity: {fig['solidity']:.2f}<br>
                                            📊 Diện tích: {fig['area']:,}px²
                                            </div>
                                            ''', unsafe_allow_html=True)
                                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('image_extracted_figures')
                                original_imgs = st.session_state.image_list
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
                                    data=word_buffer.getvalue(),
                                    file_name="images_ultra_latex.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>✨ <strong>Ultra Enhanced Version:</strong> AI siêu thông minh + Định dạng LaTeX chuẩn ${......}$!</p>
        <p>🎯 Thuật toán NMS + Multi-scale Detection + Content Analysis + Confidence Scoring</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main() in line:
                    start_idx = line.find('${')
                    if start_idx != -1:
                        end_idx = line.find('}
        
        # Thêm ảnh gốc nếu có (fallback)
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
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """Chèn ảnh đã tách vào Word document"""
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
    """Kiểm tra tính hợp lệ của API key"""
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    """Chuyển đổi kích thước file sang định dạng human-readable"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Ultra Enhanced</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key
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
        
        # Cài đặt tách ảnh siêu nâng cao
        st.subheader("🖼️ Tách ảnh siêu chính xác")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng siêu nâng cao", value=True, 
                                       help="Thuật toán AI tách ảnh với độ chính xác cực cao")
        
        if enable_extraction:
            st.write("**Cài đặt siêu nâng cao:**")
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 5.0, 0.3, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 25, 12, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 300, 40, 10)
            padding = st.slider("Padding xung quanh (px)", 0, 30, 8, 1)
            confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 50, 5)
            
            show_debug = st.checkbox("Hiển thị ảnh debug nâng cao", value=True,
                                   help="Hiển thị ảnh với confidence score và phân tích chi tiết")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng siêu nâng cao:
        - ✅ Thuật toán AI cắt ảnh với NMS
        - ✅ Confidence scoring thông minh
        - ✅ Định dạng LaTeX chuẩn: `${......}$`
        - ✅ Phân tích nội dung vùng
        - ✅ Multi-scale edge detection
        
        ### 📝 Định dạng LaTeX chuẩn:
        **Công thức inline:** `${x^2 + y^2}$`
        
        **Trắc nghiệm 4 phương án:**
        ```
        Câu X: [nội dung]
        A. [Đáp án]
        B. [Đáp án]  
        C. [Đáp án]
        D. [Đáp án]
        ```
        
        **Trắc nghiệm đúng sai:**
        ```
        a) [Đáp án]
        b) [Đáp án]
        c) [Đáp án]
        d) [Đáp án]
        ```
        
        ### 🔑 Lấy API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại Google AI Studio")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX + Ultra Extract", "🖼️ Image to LaTeX + Ultra Extract"])
    
    # Khởi tạo API và ImageExtractor
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction:
            image_extractor = UltraImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.padding = padding
            image_extractor.confidence_threshold = confidence_threshold
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học và hình ảnh"
        )
        
        if uploaded_pdf:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                with st.spinner("🔄 Đang xử lý PDF với độ phân giải cao..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang (3x resolution)")
                        
                        # Hiển thị preview
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)} với AI siêu nâng cao...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh/bảng nếu được bật
                            extracted_figures = []
                            if enable_extraction:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    # Tạo ảnh debug
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_image(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    high_conf = len([f for f in figures if f['confidence'] > 80])
                                    st.write(f"🎯 Trang {page_num}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                                    
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Tạo prompt siêu cải tiến cho Gemini
                            prompt = f"""
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh trang {page_num} thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${{x^2 + y^2}}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${{\\frac{{a+b}}{{c-d}}}}$, ${{\\int_0^1 x dx}}$, ${{\\sqrt{{x^2+1}}}}$, ${{\\perp}}$, ${{\\parallel}}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${{\\perp}}$
- Song song: ${{\\parallel}}$ hoặc //
- Góc: ${{\\angle}}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${{^\\circ}}$

6. **Hình ảnh và bảng:**
{'- Khi thấy hình ảnh/đồ thị: dùng "xem hình", "theo hình", "hình sau"' if enable_extraction else ''}
{'- Khi thấy bảng: dùng "bảng sau", "theo bảng", "quan sát bảng"' if enable_extraction else ''}

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${{...}}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${{ABCD.A'B'C'D'}}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${{ABCD}}$ là hình chữ nhật.
b) ${{A'C' \\perp BD}}$
c) ${{A'B \\perp D'C}}$  
d) ${{BC' \\perp A'D}}$
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    # Chèn ảnh vào văn bản nếu có tách ảnh
                                    if enable_extraction and extracted_figures:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, h, w
                                        )
                                    
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                        
                        # Hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.text_area("📝 Kết quả LaTeX (định dạng chuẩn ${......}$):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị thống kê chi tiết
                        if enable_extraction:
                            total_figs = len(all_extracted_figures)
                            high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                            medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                            low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                            
                            st.markdown(f"""
                            **📊 Thống kê chi tiết:**
                            - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                            - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                            - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                            - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                            """, unsafe_allow_html=True)
                            
                            # Hiển thị ảnh debug và ảnh đã cắt
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    st.write(f"**🔍 Trang {page_num} - AI Detection Analysis:**")
                                    st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng với confidence scores", use_column_width=True)
                                    
                                    # Hiển thị từng ảnh đã cắt với thông tin siêu chi tiết
                                    if figures:
                                        st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                        cols = st.columns(min(len(figures), 3))
                                        for idx, fig in enumerate(figures):
                                            with cols[idx % 3]:
                                                # Decode và hiển thị ảnh cắt
                                                img_data = base64.b64decode(fig['base64'])
                                                img_pil = Image.open(io.BytesIO(img_data))
                                                
                                                st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                                st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                                
                                                # Xác định màu confidence
                                                conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                                
                                                # Thông tin siêu chi tiết
                                                st.markdown(f'''
                                                <div class="image-info">
                                                <strong>{fig['name']}</strong><br>
                                                🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                                <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                                📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                                📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                                🔺 Solidity: {fig['solidity']:.2f}<br>
                                                📊 Diện tích: {fig['area']:,}px²<br>
                                                {'🔍 Phân tích: ' + str(fig.get('content_analysis', {}).get('has_lines', 0)) + ' đường kẻ' if 'content_analysis' in fig else ''}
                                                </div>
                                                ''', unsafe_allow_html=True)
                                                st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_ultra_latex.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
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
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh (tương tự như PDF tab)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học và hình minh họa"
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    all_debug_images = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)} với AI siêu nâng cao...")
                        
                        image_bytes = uploaded_image.getvalue()
                        image_pil = Image.open(uploaded_image)
                        all_original_images.append(image_pil)
                        
                        # Tách ảnh/bảng nếu được bật
                        extracted_figures = []
                        if enable_extraction:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                # Tạo ảnh debug
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_image(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                high_conf = len([f for f in figures if f['confidence'] > 80])
                                st.write(f"🎯 {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt = """
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${x^2 + y^2}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${\\frac{a+b}{c-d}}$, ${\\int_0^1 x dx}$, ${\\sqrt{x^2+1}}$, ${\\perp}$, ${\\parallel}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${\\perp}$
- Song song: ${\\parallel}$ hoặc //
- Góc: ${\\angle}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${^\\circ}$

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${...}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${ABCD}$ là hình chữ nhật.
b) ${A'C' \\perp BD}$
c) ${A'B \\perp D'C}$  
d) ${BC' \\perp A'D}$
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                # Chèn ảnh vào văn bản nếu có tách ảnh
                                if enable_extraction and extracted_figures:
                                    latex_result = image_extractor.insert_figures_into_text(
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
                    
                    status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                    
                    # Hiển thị kết quả
                    combined_latex = "\n".join(all_latex_content)
                    
                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                    st.text_area("📝 Kết quả LaTeX (định dạng chuẩn ${......}$):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Hiển thị thống kê và ảnh debug (tương tự PDF tab)
                    if enable_extraction:
                        total_figs = len(all_extracted_figures)
                        high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                        medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                        low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                        
                        st.markdown(f"""
                        **📊 Thống kê chi tiết:**
                        - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                        - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                        - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                        - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                        """, unsafe_allow_html=True)
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                st.write(f"**🔍 {img_name} - AI Detection Analysis:**")
                                st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng", use_column_width=True)
                                
                                if figures:
                                    st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                    cols = st.columns(min(len(figures), 3))
                                    for idx, fig in enumerate(figures):
                                        with cols[idx % 3]:
                                            img_data = base64.b64decode(fig['base64'])
                                            img_pil = Image.open(io.BytesIO(img_data))
                                            
                                            st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                            st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                            
                                            conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                            
                                            st.markdown(f'''
                                            <div class="image-info">
                                            <strong>{fig['name']}</strong><br>
                                            🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                            <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                            📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                            📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                            🔺 Solidity: {fig['solidity']:.2f}<br>
                                            📊 Diện tích: {fig['area']:,}px²
                                            </div>
                                            ''', unsafe_allow_html=True)
                                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('image_extracted_figures')
                                original_imgs = st.session_state.image_list
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
                                    data=word_buffer.getvalue(),
                                    file_name="images_ultra_latex.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>✨ <strong>Ultra Enhanced Version:</strong> AI siêu thông minh + Định dạng LaTeX chuẩn ${......}$!</p>
        <p>🎯 Thuật toán NMS + Multi-scale Detection + Content Analysis + Confidence Scoring</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main(), start_idx + 2)
                        if end_idx != -1:
                            # Thêm text trước công thức
                            if start_idx > 0:
                                p.add_run(line[:start_idx])
                            
                            # Thêm công thức
                            equation = line[start_idx+2:end_idx]
                            eq_run = p.add_run(f" [{equation}] ")
                            eq_run.font.italic = True
                            eq_run.font.bold = True
                            
                            line = line[end_idx+2:]
                        else:
                            break
                    else:
                        break
                
                # Thêm phần text còn lại
                if line.strip():
                    p.add_run(line)
            else:
                # Thêm đoạn văn bình thường
                doc.add_paragraph(line)
        
        # Thêm ảnh gốc nếu có (fallback)
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
    def _insert_extracted_image(doc, img_name, extracted_figures, caption_prefix):
        """Chèn ảnh đã tách vào Word document"""
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
    """Kiểm tra tính hợp lệ của API key"""
    if not api_key or len(api_key) < 20:
        return False
    return re.match(r'^[A-Za-z0-9_-]+$', api_key) is not None

def format_file_size(size_bytes: int) -> str:
    """Chuyển đổi kích thước file sang định dạng human-readable"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def main():
    st.markdown('<h1 class="main-header">📝 PDF/Image to LaTeX Converter - Ultra Enhanced</h1>', unsafe_allow_html=True)
    
    # Sidebar cho API key
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
        
        # Cài đặt tách ảnh siêu nâng cao
        st.subheader("🖼️ Tách ảnh siêu chính xác")
        enable_extraction = st.checkbox("Bật tách ảnh/bảng siêu nâng cao", value=True, 
                                       help="Thuật toán AI tách ảnh với độ chính xác cực cao")
        
        if enable_extraction:
            st.write("**Cài đặt siêu nâng cao:**")
            min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 5.0, 0.3, 0.1,
                               help="% diện tích ảnh gốc") / 100
            max_figures = st.slider("Số ảnh tối đa", 1, 25, 12, 1)
            min_size = st.slider("Kích thước tối thiểu (px)", 30, 300, 40, 10)
            padding = st.slider("Padding xung quanh (px)", 0, 30, 8, 1)
            confidence_threshold = st.slider("Ngưỡng confidence (%)", 30, 90, 50, 5)
            
            show_debug = st.checkbox("Hiển thị ảnh debug nâng cao", value=True,
                                   help="Hiển thị ảnh với confidence score và phân tích chi tiết")
        
        st.markdown("---")
        st.markdown("""
        ### 📋 Hướng dẫn:
        1. Nhập API key Gemini
        2. Chọn tab PDF hoặc Ảnh  
        3. Upload file
        4. Chờ xử lý và tải file Word
        
        ### 🎯 Tính năng siêu nâng cao:
        - ✅ Thuật toán AI cắt ảnh với NMS
        - ✅ Confidence scoring thông minh
        - ✅ Định dạng LaTeX chuẩn: `${......}$`
        - ✅ Phân tích nội dung vùng
        - ✅ Multi-scale edge detection
        
        ### 📝 Định dạng LaTeX chuẩn:
        **Công thức inline:** `${x^2 + y^2}$`
        
        **Trắc nghiệm 4 phương án:**
        ```
        Câu X: [nội dung]
        A. [Đáp án]
        B. [Đáp án]  
        C. [Đáp án]
        D. [Đáp án]
        ```
        
        **Trắc nghiệm đúng sai:**
        ```
        a) [Đáp án]
        b) [Đáp án]
        c) [Đáp án]
        d) [Đáp án]
        ```
        
        ### 🔑 Lấy API Key:
        [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
    
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở sidebar để bắt đầu!")
        st.info("💡 Bạn có thể lấy API key miễn phí tại Google AI Studio")
        return
    
    if not validate_api_key(api_key):
        st.error("❌ API key không hợp lệ. Vui lòng kiểm tra lại!")
        return
    
    # Tạo tabs
    tab1, tab2 = st.tabs(["📄 PDF to LaTeX + Ultra Extract", "🖼️ Image to LaTeX + Ultra Extract"])
    
    # Khởi tạo API và ImageExtractor
    try:
        gemini_api = GeminiAPI(api_key)
        if enable_extraction:
            image_extractor = UltraImageExtractor()
            image_extractor.min_area_ratio = min_area
            image_extractor.max_figures = max_figures
            image_extractor.min_width = min_size
            image_extractor.min_height = min_size
            image_extractor.padding = padding
            image_extractor.confidence_threshold = confidence_threshold
    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo: {str(e)}")
        return
    
    # Tab xử lý PDF
    with tab1:
        st.header("📄 Chuyển đổi PDF sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_pdf = st.file_uploader(
            "Chọn file PDF",
            type=['pdf'],
            help="Upload file PDF chứa công thức toán học và hình ảnh"
        )
        
        if uploaded_pdf:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Preview PDF")
                st.info(f"📁 File: {uploaded_pdf.name}")
                st.info(f"📏 Kích thước: {format_file_size(uploaded_pdf.size)}")
                
                with st.spinner("🔄 Đang xử lý PDF với độ phân giải cao..."):
                    try:
                        pdf_images = PDFProcessor.extract_images_and_text(uploaded_pdf)
                        st.success(f"✅ Đã trích xuất {len(pdf_images)} trang (3x resolution)")
                        
                        # Hiển thị preview
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_pdf"):
                    if pdf_images:
                        all_latex_content = []
                        all_extracted_figures = []
                        all_debug_images = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, (img, page_num) in enumerate(pdf_images):
                            status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)} với AI siêu nâng cao...")
                            
                            # Chuyển ảnh thành bytes
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_bytes = img_buffer.getvalue()
                            
                            # Tách ảnh/bảng nếu được bật
                            extracted_figures = []
                            if enable_extraction:
                                try:
                                    figures, h, w = image_extractor.extract_figures_and_tables(img_bytes)
                                    extracted_figures = figures
                                    all_extracted_figures.extend(figures)
                                    
                                    # Tạo ảnh debug
                                    if show_debug and figures:
                                        debug_img = image_extractor.create_debug_image(img_bytes, figures)
                                        all_debug_images.append((debug_img, page_num, figures))
                                    
                                    high_conf = len([f for f in figures if f['confidence'] > 80])
                                    st.write(f"🎯 Trang {page_num}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                                    
                                except Exception as e:
                                    st.warning(f"⚠️ Không thể tách ảnh trang {page_num}: {str(e)}")
                            
                            # Tạo prompt siêu cải tiến cho Gemini
                            prompt = f"""
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh trang {page_num} thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${{x^2 + y^2}}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${{\\frac{{a+b}}{{c-d}}}}$, ${{\\int_0^1 x dx}}$, ${{\\sqrt{{x^2+1}}}}$, ${{\\perp}}$, ${{\\parallel}}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${{\\perp}}$
- Song song: ${{\\parallel}}$ hoặc //
- Góc: ${{\\angle}}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${{^\\circ}}$

6. **Hình ảnh và bảng:**
{'- Khi thấy hình ảnh/đồ thị: dùng "xem hình", "theo hình", "hình sau"' if enable_extraction else ''}
{'- Khi thấy bảng: dùng "bảng sau", "theo bảng", "quan sát bảng"' if enable_extraction else ''}

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${{...}}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${{ABCD.A'B'C'D'}}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${{ABCD}}$ là hình chữ nhật.
b) ${{A'C' \\perp BD}}$
c) ${{A'B \\perp D'C}}$  
d) ${{BC' \\perp A'D}}$
"""
                            
                            # Gọi API
                            try:
                                latex_result = gemini_api.convert_to_latex(img_bytes, "image/png", prompt)
                                if latex_result:
                                    # Chèn ảnh vào văn bản nếu có tách ảnh
                                    if enable_extraction and extracted_figures:
                                        latex_result = image_extractor.insert_figures_into_text(
                                            latex_result, extracted_figures, h, w
                                        )
                                    
                                    all_latex_content.append(f"<!-- Trang {page_num} -->\n{latex_result}\n")
                                else:
                                    st.warning(f"⚠️ Không thể xử lý trang {page_num}")
                            except Exception as e:
                                st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(pdf_images))
                        
                        status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                        
                        # Hiển thị kết quả
                        combined_latex = "\n".join(all_latex_content)
                        
                        st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                        st.text_area("📝 Kết quả LaTeX (định dạng chuẩn ${......}$):", combined_latex, height=300)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Hiển thị thống kê chi tiết
                        if enable_extraction:
                            total_figs = len(all_extracted_figures)
                            high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                            medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                            low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                            
                            st.markdown(f"""
                            **📊 Thống kê chi tiết:**
                            - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                            - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                            - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                            - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                            """, unsafe_allow_html=True)
                            
                            # Hiển thị ảnh debug và ảnh đã cắt
                            if show_debug and all_debug_images:
                                st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                                
                                for debug_img, page_num, figures in all_debug_images:
                                    st.write(f"**🔍 Trang {page_num} - AI Detection Analysis:**")
                                    st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng với confidence scores", use_column_width=True)
                                    
                                    # Hiển thị từng ảnh đã cắt với thông tin siêu chi tiết
                                    if figures:
                                        st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                        cols = st.columns(min(len(figures), 3))
                                        for idx, fig in enumerate(figures):
                                            with cols[idx % 3]:
                                                # Decode và hiển thị ảnh cắt
                                                img_data = base64.b64decode(fig['base64'])
                                                img_pil = Image.open(io.BytesIO(img_data))
                                                
                                                st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                                st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                                
                                                # Xác định màu confidence
                                                conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                                
                                                # Thông tin siêu chi tiết
                                                st.markdown(f'''
                                                <div class="image-info">
                                                <strong>{fig['name']}</strong><br>
                                                🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                                <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                                📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                                📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                                🔺 Solidity: {fig['solidity']:.2f}<br>
                                                📊 Diện tích: {fig['area']:,}px²<br>
                                                {'🔍 Phân tích: ' + str(fig.get('content_analysis', {}).get('has_lines', 0)) + ' đường kẻ' if 'content_analysis' in fig else ''}
                                                </div>
                                                ''', unsafe_allow_html=True)
                                                st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Lưu vào session state
                        st.session_state.pdf_latex_content = combined_latex
                        st.session_state.pdf_images = [img for img, _ in pdf_images]
                        st.session_state.pdf_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'pdf_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_pdf"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('pdf_extracted_figures')
                                original_imgs = st.session_state.pdf_images
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.pdf_latex_content, 
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                filename = f"{uploaded_pdf.name.split('.')[0]}_ultra_latex.docx"
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
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
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Tab xử lý ảnh (tương tự như PDF tab)
    with tab2:
        st.header("🖼️ Chuyển đổi Ảnh sang LaTeX + Tách ảnh siêu chính xác")
        
        uploaded_images = st.file_uploader(
            "Chọn ảnh (có thể chọn nhiều)",
            type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="Upload ảnh chứa công thức toán học và hình minh họa"
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
                
                if st.button("🚀 Bắt đầu chuyển đổi siêu nâng cao", key="convert_images"):
                    all_latex_content = []
                    all_extracted_figures = []
                    all_original_images = []
                    all_debug_images = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, uploaded_image in enumerate(uploaded_images):
                        status_text.text(f"Đang xử lý ảnh {i+1}/{len(uploaded_images)} với AI siêu nâng cao...")
                        
                        image_bytes = uploaded_image.getvalue()
                        image_pil = Image.open(uploaded_image)
                        all_original_images.append(image_pil)
                        
                        # Tách ảnh/bảng nếu được bật
                        extracted_figures = []
                        if enable_extraction:
                            try:
                                figures, h, w = image_extractor.extract_figures_and_tables(image_bytes)
                                extracted_figures = figures
                                all_extracted_figures.extend(figures)
                                
                                # Tạo ảnh debug
                                if show_debug and figures:
                                    debug_img = image_extractor.create_debug_image(image_bytes, figures)
                                    all_debug_images.append((debug_img, uploaded_image.name, figures))
                                
                                high_conf = len([f for f in figures if f['confidence'] > 80])
                                st.write(f"🎯 {uploaded_image.name}: Tách được {len(figures)} ảnh/bảng (High conf: {high_conf})")
                            except Exception as e:
                                st.warning(f"⚠️ Không thể tách ảnh {uploaded_image.name}: {str(e)}")
                        
                        prompt = """
Hãy chuyển đổi TẤT CẢ nội dung trong ảnh thành văn bản thuần túy với định dạng chuẩn.

🎯 QUAN TRỌNG - CHỈ XUẤT RA VÄN BẢN THUẦN TÚY, KHÔNG DÙNG ```latex hay markdown:

📝 ĐỊNH DẠNG BẮT BUỘC:

1. **Trắc nghiệm 4 phương án - định dạng chính xác:**
Câu X: [nội dung câu hỏi đầy đủ]
A. [đáp án A chi tiết]
B. [đáp án B chi tiết]  
C. [đáp án C chi tiết]
D. [đáp án D chi tiết]

2. **Trắc nghiệm đúng sai - định dạng chính xác:**
Câu X: [nội dung câu hỏi nếu có]
a) [nội dung đáp án a đầy đủ]
b) [nội dung đáp án b đầy đủ]  
c) [nội dung đáp án c đầy đủ]
d) [nội dung đáp án d đầy đủ]

3. **Trả lời ngắn/Tự luận:**
Câu X: [nội dung câu hỏi đầy đủ]

4. **Công thức toán học - TUYỆT ĐỐI QUAN TRỌNG:**
- **CHỈ sử dụng định dạng:** ${x^2 + y^2}$ cho MỌI công thức
- **VÍ DỤ ĐÚNG:** ${\\frac{a+b}{c-d}}$, ${\\int_0^1 x dx}$, ${\\sqrt{x^2+1}}$, ${\\perp}$, ${\\parallel}$
- **TUYỆT ĐỐI KHÔNG dùng:** ```latex, $...$, $...$, hay bất kỳ markdown nào

5. **Ký hiệu đặc biệt:**
- Vuông góc: ${\\perp}$
- Song song: ${\\parallel}$ hoặc //
- Góc: ${\\angle}$ hoặc dùng từ "góc"
- Độ: ° hoặc ${^\\circ}$

⚠️ LƯU Ý QUAN TRỌNG:
- KHÔNG xuất ra ```latex hay bất kỳ code block nào
- KHÔNG dùng markdown formatting
- CHỈ xuất ra văn bản thuần túy với công thức ${...}$
- Giữ CHÍNH XÁC 100% thứ tự và cấu trúc nội dung
- Bao gồm TẤT CẢ text, số, ký hiệu và công thức từ ảnh
- Viết đầy đủ nội dung, không rút gọn hoặc tóm tắt

VÍ DỤ OUTPUT ĐÚNG:
Câu 64: Trong hình hộp ${ABCD.A'B'C'D'}$ có tất cả các cạnh đều bằng nhau. Xét tính đúng sai của các khẳng định sau:
a) ${ABCD}$ là hình chữ nhật.
b) ${A'C' \\perp BD}$
c) ${A'B \\perp D'C}$  
d) ${BC' \\perp A'D}$
"""
                        
                        try:
                            latex_result = gemini_api.convert_to_latex(
                                image_bytes, uploaded_image.type, prompt
                            )
                            if latex_result:
                                # Chèn ảnh vào văn bản nếu có tách ảnh
                                if enable_extraction and extracted_figures:
                                    latex_result = image_extractor.insert_figures_into_text(
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
                    
                    status_text.text("✅ Hoàn thành chuyển đổi siêu nâng cao!")
                    
                    # Hiển thị kết quả
                    combined_latex = "\n".join(all_latex_content)
                    
                    st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                    st.text_area("📝 Kết quả LaTeX (định dạng chuẩn ${......}$):", combined_latex, height=300)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Hiển thị thống kê và ảnh debug (tương tự PDF tab)
                    if enable_extraction:
                        total_figs = len(all_extracted_figures)
                        high_conf = len([f for f in all_extracted_figures if f['confidence'] > 80])
                        medium_conf = len([f for f in all_extracted_figures if 60 <= f['confidence'] <= 80])
                        low_conf = len([f for f in all_extracted_figures if f['confidence'] < 60])
                        
                        st.markdown(f"""
                        **📊 Thống kê chi tiết:**
                        - 🎯 Tổng cộng: **{total_figs}** ảnh/bảng đã tách
                        - <span class="confidence-high">🟢 High confidence (>80%): {high_conf}</span>
                        - <span class="confidence-medium">🟡 Medium confidence (60-80%): {medium_conf}</span>  
                        - <span class="confidence-low">🔴 Low confidence (<60%): {low_conf}</span>
                        """, unsafe_allow_html=True)
                        
                        if show_debug and all_debug_images:
                            st.subheader("🔍 Debug Siêu Nâng Cao - Phân Tích AI")
                            
                            for debug_img, img_name, figures in all_debug_images:
                                st.write(f"**🔍 {img_name} - AI Detection Analysis:**")
                                st.image(debug_img, caption=f"AI phát hiện {len(figures)} vùng", use_column_width=True)
                                
                                if figures:
                                    st.write("**📋 Chi tiết từng vùng đã cắt:**")
                                    cols = st.columns(min(len(figures), 3))
                                    for idx, fig in enumerate(figures):
                                        with cols[idx % 3]:
                                            img_data = base64.b64decode(fig['base64'])
                                            img_pil = Image.open(io.BytesIO(img_data))
                                            
                                            st.markdown(f'<div class="extracted-image">', unsafe_allow_html=True)
                                            st.image(img_pil, caption=f"{fig['name']} - {fig['confidence']:.1f}%", use_column_width=True)
                                            
                                            conf_class = "confidence-high" if fig['confidence'] > 80 else "confidence-medium" if fig['confidence'] >= 60 else "confidence-low"
                                            
                                            st.markdown(f'''
                                            <div class="image-info">
                                            <strong>{fig['name']}</strong><br>
                                            🏷️ Loại: {"📊 Bảng" if fig['is_table'] else "🖼️ Hình ảnh"}<br>
                                            <span class="{conf_class}">🎯 Confidence: {fig['confidence']:.1f}%</span><br>
                                            📐 Tỷ lệ: {fig['aspect_ratio']:.2f}<br>
                                            📏 Kích thước: {fig['bbox'][2]}×{fig['bbox'][3]}px<br>
                                            🔺 Solidity: {fig['solidity']:.2f}<br>
                                            📊 Diện tích: {fig['area']:,}px²
                                            </div>
                                            ''', unsafe_allow_html=True)
                                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Lưu vào session
                    st.session_state.image_latex_content = combined_latex
                    st.session_state.image_list = all_original_images
                    st.session_state.image_extracted_figures = all_extracted_figures if enable_extraction else None
                
                # Tạo file Word
                if 'image_latex_content' in st.session_state:
                    st.markdown("---")
                    if st.button("📥 Tạo file Word (định dạng chuẩn ${......}$)", key="create_word_images"):
                        with st.spinner("🔄 Đang tạo file Word với định dạng chuẩn..."):
                            try:
                                extracted_figs = st.session_state.get('image_extracted_figures')
                                original_imgs = st.session_state.image_list
                                
                                word_buffer = WordExporter.create_word_document(
                                    st.session_state.image_latex_content,
                                    extracted_figures=extracted_figs,
                                    images=original_imgs
                                )
                                
                                st.download_button(
                                    label="📥 Tải file Word (Ultra Enhanced)",
                                    data=word_buffer.getvalue(),
                                    file_name="images_ultra_latex.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                                
                                st.download_button(
                                    label="📝 Tải LaTeX source (.tex)",
                                    data=st.session_state.image_latex_content,
                                    file_name="images_converted.tex",
                                    mime="text/plain"
                                )
                                
                                st.success("✅ File Word với định dạng chuẩn ${......}$ đã được tạo thành công!")
                            
                            except Exception as e:
                                st.error(f"❌ Lỗi tạo file Word: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Được phát triển với ❤️ sử dụng Streamlit và Gemini 2.0 API</p>
        <p>✨ <strong>Ultra Enhanced Version:</strong> AI siêu thông minh + Định dạng LaTeX chuẩn ${......}$!</p>
        <p>🎯 Thuật toán NMS + Multi-scale Detection + Content Analysis + Confidence Scoring</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
