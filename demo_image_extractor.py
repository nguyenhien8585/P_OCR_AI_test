import streamlit as st
from PIL import Image
import base64
import io
import numpy as np

# Import từ app chính
try:
    from app_fixed import ImageExtractor, GeminiAPI, validate_api_key
except ImportError:
    st.error("❌ Không thể import từ app_fixed.py. Đảm bảo file app_fixed.py có trong cùng thư mục.")
    st.stop()

# Cấu hình trang
st.set_page_config(
    page_title="Demo Tách Ảnh trong App",
    page_icon="🖼️",
    layout="wide"
)

st.title("🖼️ Demo: Tính năng tách ảnh trong PDF/LaTeX Converter")
st.markdown("Thử nghiệm tính năng tự động tách ảnh/bảng và chèn vào văn bản LaTeX")

# Sidebar
with st.sidebar:
    st.header("⚙️ Cài đặt")
    
    # API Key
    api_key = st.text_input(
        "Gemini API Key", 
        type="password",
        help="Để test chuyển đổi LaTeX"
    )
    
    st.markdown("---")
    
    # Cài đặt tách ảnh
    st.subheader("🔧 Tham số tách ảnh")
    min_area = st.slider("Diện tích tối thiểu (%)", 0.1, 2.0, 0.8, 0.1) / 100
    max_figures = st.slider("Số ảnh tối đa", 1, 15, 8, 1)
    min_size = st.slider("Kích thước tối thiểu (px)", 30, 150, 70, 10)
    
    st.markdown("---")
    
    # Test mode
    test_mode = st.radio(
        "Chế độ test:",
        ["Chỉ tách ảnh", "Tách ảnh + OCR LaTeX"],
        help="Chọn chế độ để test"
    )

# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📤 Upload & Cài đặt")
    
    # Upload ảnh
    uploaded_file = st.file_uploader(
        "Chọn ảnh để test:",
        type=['png', 'jpg', 'jpeg'],
        help="Ảnh nên chứa hình minh họa hoặc bảng số liệu"
    )
    
    if uploaded_file:
        # Hiển thị ảnh gốc
        image = Image.open(uploaded_file)
        st.subheader("🖼️ Ảnh gốc:")
        st.image(image, caption=f"Kích thước: {image.size[0]}x{image.size[1]}", use_column_width=True)
        
        # Văn bản mẫu
        st.subheader("📝 Văn bản test:")
        sample_text = """Câu 1. Cho hàm số y = x² + 2x + 1.
a) Lập bảng biến thiên của hàm số.
b) Vẽ đồ thị hàm số như hình dưới đây.

Câu 2. Dựa vào bảng số liệu sau:
Tính giá trị trung bình.

Câu 3. Quan sát biểu đồ bên dưới:
Cho biết kết quả."""
        
        input_text = st.text_area(
            "Nhập văn bản có từ khóa:",
            value=sample_text,
            height=200
        )

with col2:
    st.header("📊 Kết quả")
    
    if uploaded_file:
        if st.button("🚀 Bắt đầu xử lý", type="primary"):
            
            # Khởi tạo ImageExtractor
            extractor = ImageExtractor()
            extractor.min_area_ratio = min_area
            extractor.max_figures = max_figures
            extractor.min_width = min_size
            extractor.min_height = min_size
            
            # Đọc ảnh
            image_bytes = uploaded_file.getvalue()
            
            with st.spinner("🔄 Đang tách ảnh..."):
                try:
                    # Tách ảnh
                    figures, h, w = extractor.extract_figures_and_tables(image_bytes)
                    
                    st.success(f"✅ Đã tách được {len(figures)} ảnh/bảng từ ảnh {w}x{h}")
                    
                    # Chèn vào văn bản
                    result_text = extractor.insert_figures_into_text(input_text, figures, h, w)
                    
                    # Lưu kết quả
                    st.session_state.figures = figures
                    st.session_state.result_text = result_text
                    st.session_state.original_text = input_text
                    
                except Exception as e:
                    st.error(f"❌ Lỗi tách ảnh: {str(e)}")

# Hiển thị kết quả chi tiết
if 'figures' in st.session_state:
    st.markdown("---")
    st.header("📊 Chi tiết kết quả")
    
    # Tabs kết quả
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Văn bản", "🖼️ Ảnh đã tách", "📊 So sánh", "🔬 Phân tích"])
    
    with tab1:
        st.subheader("📝 Văn bản sau khi chèn ảnh:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Before (Original):**")
            st.code(st.session_state.original_text, language="markdown")
        
        with col2:
            st.markdown("**After (With Images):**")
            st.code(st.session_state.result_text, language="markdown")
        
        # Test với OCR nếu có API key
        if test_mode == "Tách ảnh + OCR LaTeX" and api_key and validate_api_key(api_key):
            st.markdown("---")
            st.subheader("🤖 Test với Gemini OCR:")
            
            if st.button("🔍 Chuyển đổi sang LaTeX", key="ocr_test"):
                try:
                    gemini_api = GeminiAPI(api_key)
                    
                    prompt = """
Chuyển đổi nội dung trong ảnh thành LaTeX format.
Sử dụng ${...}$ cho công thức inline và $${...}$$ cho display.
Thêm từ khóa như "xem hình", "bảng sau" khi thấy ảnh/bảng.
"""
                    
                    with st.spinner("🔄 Đang xử lý OCR..."):
                        latex_result = gemini_api.convert_to_latex(
                            uploaded_file.getvalue(), 
                            uploaded_file.type, 
                            prompt
                        )
                        
                        # Chèn ảnh vào kết quả OCR
                        final_result = extractor.insert_figures_into_text(
                            latex_result, st.session_state.figures, h, w
                        )
                        
                        st.subheader("📄 Kết quả OCR + Tách ảnh:")
                        st.code(final_result, language="markdown")
                        
                        # Download
                        st.download_button(
                            "📥 Tải kết quả (.txt)",
                            final_result,
                            file_name="ocr_with_extracted_images.txt",
                            mime="text/plain"
                        )
                
                except Exception as e:
                    st.error(f"❌ Lỗi OCR: {str(e)}")
    
    with tab2:
        st.subheader("🖼️ Các ảnh/bảng đã tách:")
        
        figures = st.session_state.figures
        if figures:
            for i, fig in enumerate(figures):
                with st.expander(f"{fig['name']} - {'📊 Bảng' if fig['is_table'] else '🖼️ Hình'}", expanded=True):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        # Hiển thị ảnh
                        img_data = base64.b64decode(fig['base64'])
                        img = Image.open(io.BytesIO(img_data))
                        st.image(img, use_column_width=True)
                    
                    with col2:
                        # Thông tin chi tiết
                        st.write(f"**Tên:** {fig['name']}")
                        st.write(f"**Loại:** {'Bảng' if fig['is_table'] else 'Hình'}")
                        st.write(f"**Vị trí:** {fig['bbox']}")
                        
                        x, y, w, h = fig['bbox']
                        st.write(f"**Kích thước:** {w} x {h}")
                        st.write(f"**Diện tích:** {w*h:,} px")
                        
                        # Download
                        st.download_button(
                            f"📥 Tải {fig['name']}",
                            img_data,
                            file_name=fig['name'],
                            mime="image/jpeg",
                            key=f"download_{i}"
                        )
        else:
            st.info("Không tìm thấy ảnh/bảng nào")
    
    with tab3:
        st.subheader("📊 So sánh Before/After:")
        
        # Đếm từ khóa
        original = st.session_state.original_text
        result = st.session_state.result_text
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            original_lines = len(original.split('\n'))
            result_lines = len(result.split('\n'))
            st.metric("Số dòng", result_lines, result_lines - original_lines)
        
        with col2:
            original_chars = len(original)
            result_chars = len(result)
            st.metric("Số ký tự", result_chars, result_chars - original_chars)
        
        with col3:
            tags_added = result.count('[HÌNH:') + result.count('[BẢNG:')
            st.metric("Tags đã thêm", tags_added)
        
        # Highlight changes
        st.subheader("🔍 Thay đổi chi tiết:")
        
        # Tìm các dòng đã thêm tag
        original_lines = original.split('\n')
        result_lines = result.split('\n')
        
        for i, line in enumerate(result_lines):
            if '[HÌNH:' in line or '[BẢNG:' in line:
                st.success(f"➕ Dòng {i+1}: `{line}`")
    
    with tab4:
        st.subheader("🔬 Phân tích thuật toán:")
        
        figures = st.session_state.figures
        
        # Thống kê phân loại
        tables = sum(1 for fig in figures if fig['is_table'])
        images = sum(1 for fig in figures if not fig['is_table'])
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📊 Bảng", tables)
        with col2:
            st.metric("🖼️ Hình", images)
        with col3:
            st.metric("📐 Tỷ lệ tách", f"{len(figures)/max_figures*100:.1f}%")
        with col4:
            avg_area = np.mean([fig['bbox'][2] * fig['bbox'][3] for fig in figures]) if figures else 0
            st.metric("📏 Diện tích TB", f"{avg_area:,.0f} px")
        
        # Phân tích từ khóa
        st.subheader("🏷️ Phân tích từ khóa:")
        
        keywords_found = []
        text_lower = st.session_state.original_text.lower()
        
        table_keywords = ["bảng", "bảng giá trị", "bảng biến thiên", "bảng tần số"]
        image_keywords = ["hình", "hình vẽ", "đồ thị", "biểu đồ", "minh họa"]
        
        for keyword in table_keywords:
            if keyword in text_lower:
                keywords_found.append(f"📊 '{keyword}' → Bảng")
        
        for keyword in image_keywords:
            if keyword in text_lower:
                keywords_found.append(f"🖼️ '{keyword}' → Hình")
        
        if keywords_found:
            for kw in keywords_found:
                st.write(f"✅ {kw}")
        else:
            st.info("Không tìm thấy từ khóa rõ ràng - dùng vị trí mặc định")
        
        # Cài đặt hiện tại
        st.subheader("⚙️ Cài đặt đã sử dụng:")
        st.json({
            "min_area_ratio": min_area,
            "max_figures": max_figures,
            "min_size": min_size,
            "extracted_count": len(figures),
            "success_rate": f"{len(figures)/max_figures*100:.1f}%"
        })

# Footer
st.markdown("---")
st.markdown("""
### 💡 Cách sử dụng:

1. **Upload ảnh** chứa hình minh họa hoặc bảng số liệu
2. **Điều chỉnh tham số** ở sidebar nếu cần
3. **Nhập văn bản** có từ khóa liên quan
4. **Click "Bắt đầu xử lý"** để xem kết quả
5. **Kiểm tra tabs** để xem chi tiết

### 🎯 Từ khóa hoạt động:
- **Bảng**: "bảng", "bảng giá trị", "bảng biến thiên", "bảng tần số"  
- **Hình**: "hình", "hình vẽ", "đồ thị", "biểu đồ", "minh họa"

### 🔧 Tuning tham số:
- **Tách ít ảnh**: Tăng "Diện tích tối thiểu" và "Kích thước tối thiểu"
- **Tách nhiều ảnh**: Giảm các tham số trên, tăng "Số ảnh tối đa"
""")
