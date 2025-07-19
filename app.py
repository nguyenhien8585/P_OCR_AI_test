# Main content với tabs
        tab1, tab2, tab3 = st.tabs(["📄 PDF sang LaTeX", "🖼️ Ảnh sang LaTeX", "📱 Ảnh điện thoại"])
        
        with tab1:
            st.header("📄 Chuyển đổi PDF sang LaTeX")
            
            uploaded_pdf = st.file_uploader("Chọn file PDF", type=['pdf'])
            
            if uploaded_pdf:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📋 Preview PDF")
                    
                    # File info
                    file_size = format_file_size(uploaded_pdf.size)
                    st.info(f"📁 {uploaded_pdf.name} | 📏 {file_size}")
                    
                    # Check file size
                    if uploaded_pdf.size > 50 * 1024 * 1024:  # 50MB
                        st.warning("⚠️ File lớn (>50MB). Có thể xử lý chậm.")
                    
                    # Page limit option
                    max_pages = st.number_input("Giới hạn số trang (0 = không giới hạn)", 
                                              min_value=0, max_value=100, value=0)
                    
                    with st.spinner("🔄 Đang xử lý PDF..."):
                        try:
                            pdf_images = PDFProcessor.extract_images_and_text(
                                uploaded_pdf, 
                                max_pages if max_pages > 0 else None
                            )
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
                            status_text = st.empty()
                            
                            for i, (img, page_num) in enumerate(pdf_images):
                                try:
                                    status_text.text(f"Đang xử lý trang {page_num}/{len(pdf_images)}...")
                                    
                                    img_buffer = io.BytesIO()
                                    img.save(img_buffer, format='PNG')
                                    img_bytes = img_buffer.getvalue()
                                    
                                    # Check image size
                                    if len(img_bytes) > 20 * 1024 * 1024:  # 20MB
                                        st.warning(f"⚠️ Trang {page_num} quá lớn, resize...")
                                        img_resized = img.copy()
                                        img_resized.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                                        img_buffer = io.BytesIO()
                                        img_resized.save(img_buffer, format='PNG')
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
                                    prompt_text =                             
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
                        
                        except Exception as e:
                            st.error(f"❌ Lỗi xử lý: {str(e)}")
                
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
                                        
                                        st.success("✅ Word document đã tạo thành công với figures được chèn đúng vị trí!")
                                        
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
                <p>• 🤖 Mistral OCR figure counting</p>
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
                                            
                                            st.success("✅ Word document đã tạo thành công với figures được chèn đúng vị trí!")
                                            
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
        
        # Footer
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 15px;'>
            <h3>⚖️ BALANCED TEXT FILTER + 🤖 MISTRAL OCR + 📱 ENHANCED PHONE + 📄 WORD EXPORT</h3>
            <p><strong>✅ 7 phương pháp phân tích cân bằng</strong></p>
            <p><strong>⚖️ Lọc text mà vẫn giữ figures</strong></p>
            <p><strong>🧠 Override logic thông minh</strong></p>
            <p><strong>🎯 3+ indicators mới loại bỏ</strong></p>
            <p><strong>🤖 Mistral Pixtral-12B intelligent figure counting</strong></p>
            <p><strong>📱 Smart document detection + noise reduction + advanced perspective correction</strong></p>
            <p><strong>📄 Word export với figures được chèn đúng vị trí</strong></p>
            <p><strong>📄 PDF + 🖼️ Ảnh đơn + 📱 Professional phone processing + 🤖 Mistral counting + 🎯 Confidence ≥65% + 📄 Smart Word insertion</strong></p>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"❌ Application error: {str(e)}")
        st.error("Please refresh the page and try again.")

if __name__ == "__main__":
    main()
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
                                        continue
                                    
                                    progress_bar.progress((i + 1) / len(pdf_images))
                                    
                                except Exception as e:
                                    st.error(f"❌ Lỗi xử lý trang {page_num}: {str(e)}")
                                    continue
                            
                            status_text.text("✅ Hoàn thành!")
                            
                            # Kết quả
                            combined_latex = "\n".join(all_latex_content)
                            
                            st.markdown("### 📝 Kết quả LaTeX")
                            st.markdown('<div class="latex-output">', unsafe_allow_html=True)
                            st.code(combined_latex[:5000] + ("..." if len(combined_latex) > 5000 else ""), language="latex")
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
                                
                                # Mistral boost statistics
                                mistral_boosts = sum(1 for f in all_extracted_figures if f.get('mistral_boost'))
                                if mistral_boosts > 0:
                                    st.markdown(f"**🤖 Mistral Enhanced: {mistral_boosts} figures**")
                                
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
                                        
                                        st.success("✅ Word document đã tạo thành công với figures được chèn đúng vị trí!")
                                        
                                    except Exception as e:
                                        st.error(f"❌ Lỗi tạo Word: {str(e)}")
                        else:
                            st.error("❌ Cần cài đặt python-docx")
        
        with tab2:
            st.header("🖼️ Chuyển đổi Ảnh sang LaTeX")
            
            uploaded_image = st.file_uploader("Chọn file ảnh", type=['png', 'jpg', 'jpeg', 'bmp'])
            
            if uploaded_image:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("🖼️ Preview Ảnh")
                    
                    # File info
                    file_size = format_file_size(uploaded_image.size)
                    st.info(f"📁 {uploaded_image.name} | 📏 {file_size}")
                    
                    # Hiển thị ảnh
                    try:
                        image_pil = Image.open(uploaded_image)
                        st.image(image_pil, caption=f"Ảnh: {uploaded_image.name}", use_column_width=True)
                        
                        # Image info
                        st.write(f"• Kích thước: {image_pil.size[0]} x {image_pil.size[1]}")
                        st.write(f"• Mode: {image_pil.mode}")
                        
                    except Exception as e:
                        st.error(f"❌ Lỗi đọc ảnh: {str(e)}")
                        st.stop()
                    
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
                        try:
                            img_bytes = uploaded_image.getvalue()
                            
                            # Check image size
                            if len(img_bytes) > 20 * 1024 * 1024:  # 20MB
                                st.error("❌ Ảnh quá lớn (>20MB). Vui lòng resize.")
                                st.stop()
                            
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
""", continuous_table_idx = image_extractor.extract_figures_and_tables(
                                                img_bytes, continuous_img_idximport streamlit as st
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
    page_title="PDF/LaTeX Converter - Enhanced with Mistral OCR & Phone Processing",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS cải tiến
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
except Exception as e:
    st.error(f"CSS loading error: {str(e)}")

class MistralOCRService:
    """
    Mistral OCR Service để đếm figures trong ảnh và phân tích nội dung
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.mistral.ai/v1/chat/completions"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'PDF-LaTeX-Converter/1.0'
        })
        self.max_retries = 3
        self.timeout = 120
    
    def analyze_image_content(self, image_bytes, detect_figures=True, detect_tables=True):
        """
        Phân tích nội dung ảnh và đếm số lượng figures/tables sử dụng Mistral Vision
        """
        try:
            # Encode image
            encoded_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Tạo prompt cho Mistral để phân tích ảnh
            analysis_prompt = """
Phân tích ảnh này và đếm số lượng:

1. **FIGURES** (hình vẽ, biểu đồ, sơ đồ, minh họa):
   - Biểu đồ (bar chart, pie chart, line chart)
   - Sơ đồ khối, sơ đồ luồng
   - Hình vẽ minh họa, hình học
   - Graphs, plots, diagrams

2. **TABLES** (bảng dữ liệu):
   - Bảng có dòng và cột rõ ràng
   - Dữ liệu được tổ chức dạng bảng

3. **TEXT REGIONS** (vùng text thuần túy):
   - Đoạn văn, câu hỏi
   - Text không có hình ảnh đi kèm

Trả về kết quả CHÍNH XÁC theo format JSON:
{
    "figure_count": <số_figures>,
    "table_count": <số_bảng>,
    "text_regions": <số_vùng_text>,
    "total_visual_elements": <tổng_figures_và_bảng>,
    "confidence": <độ_tin_cậy_0_đến_1>,
    "analysis": "Mô tả ngắn gọn về nội dung ảnh",
    "figure_types": ["loại figure 1", "loại figure 2"],
    "complexity": "simple|medium|complex"
}

LưU Ý: 
- Chỉ đếm figures/tables thực sự, không đếm text
- Nếu không chắc chắn, ước tính thấp hơn
- Confidence thể hiện độ chắc chắn của phân tích
"""
            
            # Prepare payload cho Mistral API
            payload = {
                "model": "pixtral-12b-2409",  # Mistral vision model
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": analysis_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.1,
                "top_p": 0.9
            }
            
            # Call Mistral API với retry logic
            for attempt in range(self.max_retries):
                try:
                    response = self.session.post(
                        self.base_url,
                        json=payload,
                        timeout=self.timeout
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result['choices'][0]['message']['content']
                        return self._process_mistral_response(content)
                    elif response.status_code == 401:
                        st.error("❌ Mistral API key không hợp lệ")
                        return self._get_fallback_result()
                    elif response.status_code == 429:
                        if attempt < self.max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        st.warning("⚠️ Mistral API rate limit - sử dụng fallback")
                        return self._get_fallback_result()
                    else:
                        st.warning(f"⚠️ Mistral API error: {response.status_code}")
                        return self._get_fallback_result()
                        
                except requests.exceptions.Timeout:
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    st.warning("⚠️ Mistral API timeout - sử dụng fallback method")
                    return self._get_fallback_result()
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    st.warning(f"⚠️ Mistral API error: {str(e)} - sử dụng fallback method")
                    return self._get_fallback_result()
            
            return self._get_fallback_result()
                
        except Exception as e:
            st.warning(f"⚠️ Mistral OCR error: {str(e)} - sử dụng fallback method")
            return self._get_fallback_result()
    
    def count_figures_in_text(self, text_content):
        """
        Đếm số lượng figures được nhắc đến trong text sử dụng Mistral
        """
        try:
            payload = {
                "model": "mistral-large-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""
Phân tích đoạn text sau và đếm số lượng figures/tables được nhắc đến:

Text: {text_content[:2000]}

Tìm các từ khóa: hình, figure, fig, bảng, table, biểu đồ, đồ thị, sơ đồ

Trả về JSON:
{{
    "figure_count": <số_figures>,
    "table_count": <số_bảng>,
    "mentions": ["các từ khóa tìm thấy"]
}}
"""
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.1
            }
            
            response = self.session.post(self.base_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Parse JSON response
                try:
                    parsed = json.loads(content)
                    return parsed.get('figure_count', 0), parsed.get('table_count', 0)
                except:
                    return 0, 0
            else:
                return 0, 0
                
        except Exception:
            return 0, 0
    
    def _process_mistral_response(self, content):
        """
        Xử lý response từ Mistral API
        """
        try:
            # Tìm JSON trong response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                # Extract và validate data
                figure_count = max(0, int(data.get('figure_count', 0)))
                table_count = max(0, int(data.get('table_count', 0)))
                total_count = figure_count + table_count
                confidence = min(1.0, max(0.0, float(data.get('confidence', 0.8))))
                
                return {
                    'success': True,
                    'figure_count': figure_count,
                    'table_count': table_count,
                    'total_count': total_count,
                    'figure_regions': [],  # Mistral không trả về coordinates
                    'table_regions': [],
                    'text_content': data.get('analysis', ''),
                    'confidence': confidence,
                    'method': 'mistral_ocr',
                    'figure_types': data.get('figure_types', []),
                    'complexity': data.get('complexity', 'medium')
                }
            else:
                return self._get_fallback_result()
                
        except Exception as e:
            st.warning(f"Error parsing Mistral response: {str(e)}")
            return self._get_fallback_result()
    
    def _get_fallback_result(self):
        """
        Fallback result khi Mistral API không khả dụng
        """
        return {
            'success': False,
            'figure_count': 2,  # Conservative estimate
            'table_count': 1,
            'total_count': 3,
            'figure_regions': [],
            'table_regions': [],
            'text_content': '',
            'confidence': 0.5,
            'method': 'fallback',
            'figure_types': [],
            'complexity': 'medium'
        }

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
        """Giảm noise trong ảnh"""
        try:
            # Bilateral filter để giảm noise mà vẫn giữ edges
            denoised = cv2.bilateralFilter(img, 9, 75, 75)
            return denoised
        except Exception:
            return img
    
    @staticmethod
    def _smart_document_crop(img):
        """Tự động crop document thông minh"""
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
        """Tự động xoay ảnh thông minh hơn"""
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
        """Sửa perspective distortion nâng cao"""
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
        """Enhanced point ordering"""
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
        """Tự động tăng cường chất lượng ảnh nâng cao"""
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
        """Tính gamma tối ưu dựa trên histogram"""
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
        """Áp dụng gamma correction"""
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
        """Tăng cường contrast adaptive"""
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
        """Tăng cường text nâng cao"""
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

class BalancedTextFilter:
    """
    Bộ lọc text CÂN BẰNG - Lọc text nhưng vẫn giữ được figures
    """
    
    def __init__(self):
        # Ngưỡng cân bằng - không quá nghiêm ngặt
        self.text_density_threshold = 0.7
        self.min_visual_complexity = 0.2
        self.min_diagram_score = 0.1
        self.min_figure_quality = 0.15
        
        # Thông số phân tích text nâng cao
        self.line_density_threshold = 0.25
        self.char_pattern_threshold = 0.8
        self.horizontal_structure_threshold = 0.8
        self.whitespace_ratio_threshold = 0.45
        
        # Aspect ratio filtering
        self.text_aspect_ratio_min = 0.1
        self.text_aspect_ratio_max = 12.0
        
        # Size filtering
        self.min_meaningful_size = 1000
        self.max_text_block_size = 0.75
        
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
            # Validate inputs
            if not image_bytes or not candidates:
                return candidates
                
            # Đọc ảnh
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = np.array(img_pil)
            h, w = img.shape[:2]
            
            if h == 0 or w == 0:
                return candidates
            
            if self.debug_mode:
                st.write(f"🔍 Balanced Text Filter analyzing {len(candidates)} candidates")
            
            # Phân tích từng candidate với error handling
            analyzed_candidates = []
            for i, candidate in enumerate(candidates):
                try:
                    analysis = self._balanced_analyze_candidate(img, candidate)
                    candidate.update(analysis)
                    analyzed_candidates.append(candidate)
                    
                    if self.debug_mode:
                        st.write(f"   {i+1}. {candidate.get('bbox', 'N/A')}: text_score={analysis.get('text_score', 0):.2f}, is_text={analysis.get('is_text', False)}")
                except Exception as e:
                    if self.debug_mode:
                        st.warning(f"Error analyzing candidate {i+1}: {str(e)}")
                    # Keep original candidate if analysis fails
                    analyzed_candidates.append(candidate)
            
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
        Phân tích cân bằng từng candidate với error handling
        """
        try:
            x, y, w, h = candidate['bbox']
            
            # Validate bbox
            img_h, img_w = img.shape[:2]
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h or w <= 0 or h <= 0:
                return {'is_text': False, 'text_score': 0.0}
            
            roi = img[y:y+h, x:x+w]
            
            if roi.size == 0 or roi.shape[0] == 0 or roi.shape[1] == 0:
                return {'is_text': False, 'text_score': 0.0}
            
            # Các phương pháp phân tích với try-catch
            text_density = self._safe_calculate_advanced_text_density(roi)
            line_density = self._safe_analyze_line_structure(roi)
            char_pattern = self._safe_detect_character_patterns(roi)
            histogram_score = self._safe_analyze_histogram_for_text(roi)
            geometric_score = self._safe_analyze_geometric_structure(roi)
            whitespace_ratio = self._safe_calculate_whitespace_ratio(roi)
            ocr_score = self._safe_simulate_ocr_detection(roi)
            
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
            aspect_ratio = w / max(h, 1)  # Avoid division by zero
            is_text_aspect = (self.text_aspect_ratio_min <= aspect_ratio <= self.text_aspect_ratio_max)
            
            # Size analysis
            area = w * h
            is_text_size = area < self.min_meaningful_size
            
            # Final decision - CÂN BẰNG HỢP LÝ
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
            
        except Exception as e:
            if self.debug_mode:
                st.warning(f"Error in candidate analysis: {str(e)}")
            return {'is_text': False, 'text_score': 0.0}
    
    def _safe_calculate_advanced_text_density(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            # Morphological text detection
            text_kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, gray.shape[1]//10), 1))
            text_kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, gray.shape[0]//10)))
            
            text_h = cv2.morphologyEx(gray, cv2.MORPH_OPEN, text_kernel_h)
            text_v = cv2.morphologyEx(gray, cv2.MORPH_OPEN, text_kernel_v)
            
            text_regions = cv2.bitwise_or(text_h, text_v)
            text_pixels = np.sum(text_regions > 0)
            total_pixels = gray.shape[0] * gray.shape[1]
            
            morphological_density = text_pixels / max(total_pixels, 1)
            
            # Edge-based text detection
            edges = cv2.Canny(gray, 50, 150)
            horizontal_edges = cv2.morphologyEx(edges, cv2.MORPH_OPEN, text_kernel_h)
            edge_density = np.sum(horizontal_edges > 0) / max(total_pixels, 1)
            
            return max(morphological_density, edge_density)
            
        except Exception:
            return 0.0
    
    def _safe_analyze_line_structure(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, gray.shape[1]//5), 1))
            horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel)
            
            contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            line_count = len(contours)
            
            height = gray.shape[0]
            line_density = line_count / max(height / 20, 1)
            
            return min(1.0, line_density)
            
        except Exception:
            return 0.0
    
    def _safe_detect_character_patterns(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            binary = cv2.bitwise_not(binary)
            
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
            
            char_like_components = 0
            total_area = gray.shape[0] * gray.shape[1]
            
            for i in range(1, min(num_labels, 100)):  # Limit to avoid memory issues
                area = stats[i, cv2.CC_STAT_AREA]
                width = stats[i, cv2.CC_STAT_WIDTH]
                height = stats[i, cv2.CC_STAT_HEIGHT]
                
                if (50 < area < 1000 and
                    5 < width < 50 and
                    10 < height < 50 and
                    0.2 < width/max(height, 1) < 3.0):
                    char_like_components += 1
            
            char_density = char_like_components / max(total_area / 500, 1)
            return min(1.0, char_density)
            
        except Exception:
            return 0.0
    
    def _safe_analyze_histogram_for_text(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist.flatten()
            
            # Find peaks
            peaks = []
            for i in range(1, len(hist) - 1):
                if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > np.max(hist) * 0.1:
                    peaks.append(i)
            
            if len(peaks) >= 2:
                peak_distances = [abs(peaks[i+1] - peaks[i]) for i in range(len(peaks) - 1)]
                if max(peak_distances) > 100:
                    return 0.8
            
            # Calculate entropy
            hist_norm = hist / max(np.sum(hist), 1)
            entropy = -np.sum(hist_norm * np.log2(hist_norm + 1e-10))
            
            if entropy < 4.0:
                return 0.6
            
            return 0.2
            
        except Exception:
            return 0.0
    
    def _safe_analyze_geometric_structure(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            edges = cv2.Canny(gray, 50, 150)
            
            # Detect lines
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30, minLineLength=20, maxLineGap=10)
            line_count = len(lines) if lines is not None else 0
            
            # Detect circles
            circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1, minDist=20, 
                                     param1=50, param2=30, minRadius=5, maxRadius=100)
            circle_count = len(circles[0]) if circles is not None else 0
            
            # Detect complex contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            complex_contours = 0
            
            for contour in contours[:20]:  # Limit processing
                area = cv2.contourArea(contour)
                if area > 500:
                    hull = cv2.convexHull(contour)
                    hull_area = cv2.contourArea(hull)
                    if hull_area > 0:
                        solidity = area / hull_area
                        if solidity < 0.8:
                            complex_contours += 1
            
            total_area = gray.shape[0] * gray.shape[1]
            geometric_score = (line_count * 0.1 + circle_count * 0.5 + complex_contours * 0.3) / max(total_area / 1000, 1)
            
            return min(1.0, geometric_score)
            
        except Exception:
            return 0.0
    
    def _safe_calculate_whitespace_ratio(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            
            white_pixels = np.sum(binary == 255)
            total_pixels = gray.shape[0] * gray.shape[1]
            
            return white_pixels / max(total_pixels, 1)
            
        except Exception:
            return 0.0
    
    def _safe_simulate_ocr_detection(self, roi):
        """Safe version with error handling"""
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
            
            if gray.shape[0] == 0 or gray.shape[1] == 0:
                return 0.0
            
            # Resize to standard height
            target_height = 32
            scale = target_height / max(gray.shape[0], 1)
            new_width = max(1, int(gray.shape[1] * scale))
            
            resized = cv2.resize(gray, (new_width, target_height))
            enhanced = cv2.equalizeHist(resized)
            
            # Horizontal projections
            h_projection = np.sum(enhanced < 128, axis=1)
            
            # Count peaks
            h_peaks = 0
            for i in range(1, len(h_projection) - 1):
                if h_projection[i] > h_projection[i-1] and h_projection[i] > h_projection[i+1]:
                    if h_projection[i] > np.max(h_projection) * 0.3:
                        h_peaks += 1
            
            if h_peaks >= 2:
                return 0.9
            elif h_peaks == 1:
                return 0.7
            else:
                return 0.3
                
        except Exception:
            return 0.0
    
    def _balanced_filter(self, candidates):
        """
        Lọc cân bằng - ưu tiên giữ lại figures
        """
        filtered = []
        
        for candidate in candidates:
            try:
                # Chỉ loại bỏ khi RẤT CHẮC CHẮN là text
                if candidate.get('is_text', False):
                    # Cho phép giữ lại nếu có geometric complexity cao
                    geometric_score = candidate.get('geometric_score', 0)
                    if geometric_score >= 0.3:
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
                
                # Kiểm tra các điều kiện khác
                text_score = candidate.get('text_score', 0)
                if text_score > self.text_density_threshold:
                    geometric_score = candidate.get('geometric_score', 0)
                    if geometric_score >= self.min_diagram_score:
                        candidate['override_reason'] = 'has_diagram_elements'
                        filtered.append(candidate)
                    continue
                
                # Kiểm tra size
                area = candidate.get('area', 0)
                if area < self.min_meaningful_size:
                    geometric_score = candidate.get('geometric_score', 0)
                    if geometric_score >= 0.4:
                        candidate['override_reason'] = 'small_but_complex'
                        filtered.append(candidate)
                    continue
                
                # Nếu pass hầu hết tests thì giữ lại
                filtered.append(candidate)
                
            except Exception as e:
                # If error in filtering, keep the candidate
                if self.debug_mode:
                    st.warning(f"Error filtering candidate: {str(e)}")
                filtered.append(candidate)
        
        return filtered

class EnhancedContentBasedFigureFilter:
    """
    Bộ lọc thông minh với Mistral OCR Integration
    """
    
    def __init__(self, mistral_ocr_service=None):
        self.text_filter = BalancedTextFilter()
        self.enable_balanced_filter = True
        self.min_estimated_count = 1
        self.max_estimated_count = 15
        self.mistral_ocr = mistral_ocr_service
        self.enable_ocr_counting = True
        
    def analyze_content_and_filter_with_ocr(self, image_bytes, candidates):
        """
        Phân tích với Mistral OCR + Balanced Text Filter
        """
        if not CV2_AVAILABLE:
            return candidates
        
        try:
            # OCR Analysis để đếm figures
            estimated_count = self.min_estimated_count
            ocr_info = {}
            
            if self.mistral_ocr and self.enable_ocr_counting:
                with st.spinner("🔍 Analyzing image content with Mistral OCR..."):
                    ocr_result = self.mistral_ocr.analyze_image_content(image_bytes)
                    
                    if ocr_result['success']:
                        estimated_count = max(ocr_result['total_count'], self.min_estimated_count)
                        estimated_count = min(estimated_count, self.max_estimated_count)
                        ocr_info = ocr_result
                        
                        # Hiển thị thông tin chi tiết từ Mistral
                        figure_types = ocr_result.get('figure_types', [])
                        complexity = ocr_result.get('complexity', 'medium')
                        
                        types_text = f" ({', '.join(figure_types)})" if figure_types else ""
                        st.success(f"🤖 Mistral OCR detected: {ocr_result['figure_count']} figures, {ocr_result['table_count']} tables{types_text} | Complexity: {complexity} | Confidence: {ocr_result['confidence']:.1f}")
                    else:
                        # Fallback to conservative estimation
                        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                        img = np.array(img_pil)
                        estimated_count = self._estimate_figure_count_conservative(img)
                        st.info(f"📊 Conservative estimate: {estimated_count} figures (Mistral OCR fallback)")
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
            if ocr_info.get('success') and ocr_info.get('complexity'):
                # Điều chỉnh dựa trên complexity của ảnh
                complexity = ocr_info.get('complexity', 'medium')
                if complexity == 'complex':
                    # Với ảnh phức tạp, cho phép nhiều figures hơn
                    target_count = min(estimated_count + 2, self.max_estimated_count)
                elif complexity == 'simple':
                    # Với ảnh đơn giản, hạn chế số lượng
                    target_count = min(estimated_count, self.max_estimated_count - 2)
                else:
                    target_count = min(estimated_count + 1, self.max_estimated_count)
            else:
                target_count = min(estimated_count + 1, self.max_estimated_count)
            
            # Adjust count based on estimation
            if len(filtered_candidates) > target_count:
                # Sort by confidence and take top candidates
                sorted_candidates = sorted(filtered_candidates, 
                                         key=lambda x: x.get('final_confidence', 0), reverse=True)
                filtered_candidates = sorted_candidates[:target_count]
                st.info(f"🎯 Limited to top {target_count} figures based on Mistral OCR estimate")
            
            return filtered_candidates
            
        except Exception as e:
            st.error(f"❌ Enhanced filter error: {str(e)}")
            return candidates
    
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
        
        # Check image size
        if len(content_data) > 20 * 1024 * 1024:  # 20MB limit
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
                "
