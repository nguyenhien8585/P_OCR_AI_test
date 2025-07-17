📝 PDF/Image to LaTeX Converter
Ứng dụng web Streamlit chuyển đổi PDF và ảnh chứa công thức toán học sang định dạng LaTeX, sau đó xuất ra file Word với equations.
✨ Tính năng chính

📄 Chuyển đổi PDF sang LaTeX: Upload file PDF và chuyển đổi toàn bộ nội dung toán học
🖼️ Chuyển đổi ảnh sang LaTeX: Hỗ trợ nhiều định dạng ảnh (PNG, JPG, JPEG, BMP, TIFF)
🤖 Sử dụng Gemini 2.0 API: Độ chính xác cao trong nhận dạng công thức
📥 Xuất file Word: Tự động chuyển đổi LaTeX thành equations trong Word
🎯 Giao diện thân thiện: Interface đơn giản, dễ sử dụng
⚡ Xử lý batch: Có thể xử lý nhiều ảnh cùng lúc

🚀 Demo trực tuyến
Truy cập ứng dụng tại: https://pdf-latex-converter.streamlit.app/
📋 Yêu cầu hệ thống

Python 3.8+
Gemini API Key (miễn phí từ Google AI Studio)
Internet connection

🛠️ Cài đặt
1. Clone repository
bashgit clone https://github.com/yourusername/pdf-latex-converter.git
cd pdf-latex-converter
2. Cài đặt dependencies
bashpip install -r requirements.txt
3. Lấy Gemini API Key

Truy cập Google AI Studio
Tạo API key mới
Copy API key để sử dụng trong ứng dụng

4. Chạy ứng dụng
bashstreamlit run app.py
Ứng dụng sẽ chạy tại http://localhost:8501
📖 Hướng dẫn sử dụng
Chuyển đổi PDF

Nhập API Key: Paste Gemini API key vào sidebar
Chọn tab PDF: Click vào tab "📄 PDF to LaTeX"
Upload file: Chọn file PDF cần chuyển đổi
Preview: Xem trước các trang đã trích xuất
Chuyển đổi: Click "🚀 Bắt đầu chuyển đổi PDF"
Tải file Word: Click "📥 Tạo file Word" để tải kết quả

Chuyển đổi ảnh

Nhập API Key: Paste Gemini API key vào sidebar
Chọn tab Ảnh: Click vào tab "🖼️ Image to LaTeX"
Upload ảnh: Chọn một hoặc nhiều ảnh (PNG, JPG, etc.)
Preview: Xem trước các ảnh đã upload
Chuyển đổi: Click "🚀 Bắt đầu chuyển đổi ảnh"
Tải file Word: Click "📥 Tạo file Word" để tải kết quả

🔧 Cấu trúc dự án
pdf-latex-converter/
│
├── app.py                 # Ứng dụng Streamlit chính
├── requirements.txt       # Python dependencies
├── README.md             # Tài liệu dự án
├── .streamlit/
│   └── config.toml       # Cấu hình Streamlit
├── assets/
│   ├── examples/         # Ảnh ví dụ
│   └── screenshots/      # Screenshots của app
└── tests/
    └── test_app.py       # Unit tests
🌐 Triển khai lên Streamlit Cloud
1. Push code lên GitHub
bashgit add .
git commit -m "Initial commit"
git push origin main
2. Triển khai trên Streamlit Cloud

Truy cập share.streamlit.io
Connect với GitHub account
Chọn repository: yourusername/pdf-latex-converter
Main file path: app.py
Click "Deploy!"

3. Cấu hình secrets (tùy chọn)
Trong Streamlit Cloud dashboard, thêm secrets:
toml[api_keys]
gemini_api_key = "your_gemini_api_key_here"
📚 API Reference
GeminiAPI Class
pythonclass GeminiAPI:
    def __init__(self, api_key: str)
    def convert_to_latex(self, content_data: bytes, content_type: str, prompt: str) -> str
PDFProcessor Class
pythonclass PDFProcessor:
    @staticmethod
    def extract_images_and_text(pdf_file) -> List[Tuple[Image.Image, int]]
WordExporter Class
pythonclass WordExporter:
    @staticmethod
    def create_word_document(latex_content: str, images: List[Image.Image] = None) -> io.BytesIO
🎯 Ví dụ LaTeX Output
Input (PDF/Ảnh):
Phương trình bậc hai: ax² + bx + c = 0
Nghiệm: x = (-b ± √(b² - 4ac)) / 2a
Output (LaTeX):
latexPhương trình bậc hai: ${ax^2 + bx + c = 0}$

Nghiệm: ${x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}}$
🔍 Troubleshooting
Lỗi API Key
❌ Lỗi API: 400 - Invalid API key
Giải pháp: Kiểm tra lại API key từ Google AI Studio
Lỗi xử lý PDF
❌ Lỗi xử lý PDF: [Error details]
Giải pháp:

Đảm bảo file PDF không bị corrupt
Kiểm tra file PDF không bị password protect
Thử với file PDF khác

Lỗi memory
❌ Lỗi: Out of memory
Giải pháp:

Chia nhỏ file PDF
Giảm số lượng ảnh upload cùng lúc
Restart ứng dụng

🤝 Đóng góp

Fork repository
Tạo feature branch: git checkout -b feature-name
Commit changes: git commit -am 'Add feature'
Push branch: git push origin feature-name
Tạo Pull Request

📝 License
MIT License - xem file LICENSE để biết thêm chi tiết.
📞 Liên hệ

GitHub: @yourusername
Email: your.email@example.com

🙏 Acknowledgments

Streamlit - Framework web app
Google Gemini - AI API cho OCR và LaTeX conversion
PyMuPDF - PDF processing
python-docx - Word document generation

📈 Roadmap

 Hỗ trợ thêm định dạng file (DOCX, RTF)
 Cải thiện accuracy của equation detection
 Thêm tính năng edit LaTeX trực tiếp
 Export sang nhiều format (HTML, Markdown)
 Batch processing cho nhiều file
 Integration với Google Drive/Dropbox
 Mobile app version


⭐ Nếu project hữu ích, hãy cho 1 star nhé! ⭐
