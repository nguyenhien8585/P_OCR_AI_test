# 📝 Hướng dẫn sử dụng Enhanced PDF/LaTeX Converter

## 🎯 Tổng quan tính năng

### ✨ Cải tiến chính trong phiên bản Enhanced:

1. **🔍 Tách ảnh thông minh (Enhanced Image Extraction)**
   - Loại bỏ text regions để tránh cắt nhầm
   - Phát hiện geometric shapes chính xác
   - Quality assessment cho từng figure
   - Smart cropping với padding tối ưu
   - Confidence scoring để đánh giá chất lượng

2. **🎯 Chèn vị trí chính xác (Precise Figure Insertion)**
   - Phân tích cấu trúc văn bản chi tiết
   - Ánh xạ figure-question mapping
   - Priority-based insertion theo ngữ cảnh
   - Context-aware positioning

3. **📄 Xuất Word giữ nguyên LaTeX (LaTeX-preserved Word Export)**
   - Giữ nguyên ${...}$ format cho công thức
   - Cambria Math font cho equations
   - Color coding để phân biệt
   - Appendix với thống kê chi tiết

---

## 🚀 Bước 1: Cài đặt và khởi chạy

### 1.1 Cài đặt dependencies

```bash
pip install streamlit requests Pillow PyMuPDF python-docx opencv-python numpy scipy scikit-image
```

### 1.2 Lấy API Key

1. Truy cập [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Tạo API key mới (miễn phí)
3. Copy API key để sử dụng

### 1.3 Chạy ứng dụng

```bash
streamlit run enhanced_app.py
```

---

## ⚙️ Bước 2: Cài đặt tham số

### 2.1 Cài đặt API Key
- Nhập API key vào sidebar
- Ứng dụng sẽ validate tự động

### 2.2 Cài đặt tách ảnh (Advanced Settings)

#### 🔧 Tham số cơ bản:
- **Diện tích tối thiểu**: 0.3-2.0% (khuyến nghị: 0.5%)
- **Số ảnh tối đa**: 1-20 (khuyến nghị: 12)
- **Kích thước tối thiểu**: 40-200px (khuyến nghị: 60px)
- **Smart padding**: 10-50px (khuyến nghị: 20px)
- **Confidence threshold**: 50-95% (khuyến nghị: 75%)

#### 🎯 Tuning tips:
- **Tách ít ảnh**: Tăng diện tích tối thiểu và confidence threshold
- **Tách nhiều ảnh**: Giảm các thresholds, tăng số ảnh tối đa
- **Chất lượng cao**: Tăng confidence threshold lên 85-90%

---

## 📄 Bước 3: Chuyển đổi PDF

### 3.1 Upload PDF
1. Click "Chọn file PDF"
2. Chọn file PDF từ máy tính
3. Xem preview các trang được trích xuất

### 3.2 Bắt đầu chuyển đổi
1. Click "🚀 Bắt đầu chuyển đổi PDF"
2. Theo dõi progress bar
3. Xem kết quả LaTeX trong text area

### 3.3 Kiểm tra kết quả tách ảnh
- Xem thống kê: Tổng figures, bảng, hình
- Xem debug visualization (nếu bật)
- Kiểm tra confidence scores

### 3.4 Xuất file Word
1. Click "📥 Tạo Word với LaTeX ${...}$"
2. Tải file Word đã tạo
3. Hoặc tải LaTeX source (.tex)

---

## 🖼️ Bước 4: Chuyển đổi ảnh

### 4.1 Upload ảnh
1. Click "Chọn ảnh (có thể chọn nhiều)"
2. Chọn các file ảnh (PNG, JPG, JPEG, BMP, TIFF)
3. Xem preview và tổng kích thước

### 4.2 Quy trình tương tự PDF
- Bước convert, kiểm tra, xuất file tương tự như PDF

---

## 🔍 Bước 5: Hiểu kết quả tách ảnh

### 5.1 Thống kê hiển thị
- **Tổng figures**: Số lượng ảnh/bảng đã tách
- **Bảng**: Số lượng bảng (aspect ratio > 2.0)
- **Hình**: Số lượng hình minh họa
- **Avg Confidence**: Confidence trung bình

### 5.2 Debug Visualization
Khi bật "Hiển thị debug":
- **Bounding boxes**: Khung màu quanh figures
- **Labels**: Tên, loại, confidence, quality
- **Center points**: Điểm trung tâm của figure

### 5.3 Thông tin chi tiết mỗi figure
- **Name**: Tên file (figure-1.jpeg, table-1.jpeg)
- **Type**: Loại (Bảng/Hình)
- **Confidence**: Độ tin cậy (0-100%)
- **Quality**: Chất lượng hình học (0-1)
- **Aspect Ratio**: Tỷ lệ khung hình (rộng/cao)

---

## 📝 Bước 6: Hiểu chèn vị trí

### 6.1 Phân tích cấu trúc văn bản
Ứng dụng phân tích:
- **Questions**: Câu 1, Câu 2, etc.
- **Insertion candidates**: Vị trí có thể chèn
- **Priority scoring**: Điểm ưu tiên cho mỗi vị trí

### 6.2 Priority-based insertion
Ưu tiên cao → thấp:
1. **100 pts**: Kết thúc bằng "sau:", "dưới đây:", "như hình:"
2. **80 pts**: Chứa "hình vẽ", "biểu đồ", "đồ thị", "bảng"
3. **40 pts**: Chứa "xét", "tính", "tìm", "xác định"
4. **20 pts**: Kết thúc bằng ":"

### 6.3 Figure-question mapping
