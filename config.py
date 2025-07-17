"""
Cấu hình các tham số cho ImageExtractor
"""

class ExtractorConfig:
    """
    Class chứa các tham số cấu hình cho việc tách ảnh
    """
    
    # ==================== THAM SỐ CHÍNH ====================
    
    # Diện tích tối thiểu
    MIN_AREA_RATIO = 0.008      # 0.8% diện tích ảnh gốc
    MIN_AREA_ABS = 2500         # 2500 pixels
    
    # Kích thước tối thiểu
    MIN_WIDTH = 70              # 70 pixels
    MIN_HEIGHT = 70             # 70 pixels
    
    # Giới hạn
    MAX_FIGURES = 8             # Tối đa 8 ảnh/bảng
    MAX_AREA_RATIO = 0.6        # Tối đa 60% diện tích ảnh gốc
    
    # Tỷ lệ khung hình
    MIN_ASPECT_RATIO = 0.2      # Tỷ lệ tối thiểu (rộng/cao)
    MAX_ASPECT_RATIO = 8.0      # Tỷ lệ tối đa (rộng/cao)
    
    # Độ đặc tối thiểu (solidity)
    MIN_SOLIDITY = 0.4          # 40%
    
    # ==================== THAM SỐ XỬ LÝ ẢNH ====================
    
    # Gaussian Blur
    BLUR_KERNEL = (3, 3)        # Kernel làm mờ
    BLUR_SIGMA = 0              # Sigma (0 = tự động)
    
    # CLAHE (Contrast Limited Adaptive Histogram Equalization)
    CLAHE_CLIP_LIMIT = 2.0      # Giới hạn độ tương phản
    CLAHE_TILE_SIZE = (8, 8)    # Kích thước tile
    
    # Adaptive Threshold
    THRESH_MAX_VALUE = 255      # Giá trị tối đa
    THRESH_ADAPTIVE_METHOD = 'ADAPTIVE_THRESH_MEAN_C'
    THRESH_TYPE = 'THRESH_BINARY_INV'
    THRESH_BLOCK_SIZE = 25      # Kích thước block
    THRESH_C = 10               # Hằng số C
    
    # Morphological Operations
    DILATE_KERNEL = (3, 3)      # Kernel dilate
    DILATE_ITERATIONS = 1       # Số lần dilate
    
    # ==================== THAM SỐ PHÂN LOẠI ====================
    
    # Tiêu chí phân biệt bảng vs hình
    TABLE_MIN_WIDTH_RATIO = 0.25    # Bảng phải rộng ít nhất 25% ảnh gốc
    TABLE_MIN_HEIGHT_RATIO = 0.05   # Bảng phải cao ít nhất 5% ảnh gốc
    TABLE_MIN_ASPECT = 2.0          # Bảng có tỷ lệ ít nhất 2:1
    TABLE_MAX_ASPECT = 10.0         # Bảng có tỷ lệ tối đa 10:1
    
    # Vùng biên (loại bỏ các đối tượng quá gần rìa)
    EDGE_MARGIN_RATIO = 0.03        # 3% từ mép ảnh
    EDGE_MARGIN_MAX_RATIO = 0.97    # 97% đến mép ảnh
    
    # ==================== TỪ KHÓA NHẬN DIỆN ====================
    
    # Từ khóa cho bảng
    TABLE_KEYWORDS = [
        "bảng", "bảng giá trị", "bảng biến thiên", 
        "bảng tần số", "bảng số liệu", "bảng thống kê",
        "table", "data table", "value table"
    ]
    
    # Từ khóa cho hình
    IMAGE_KEYWORDS = [
        "hình vẽ", "hình bên", "(hình", "xem hình", 
        "đồ thị", "biểu đồ", "minh họa", "hình",
        "figure", "diagram", "chart", "graph", "illustration"
    ]
    
    # Pattern cho câu hỏi
    QUESTION_PATTERN = r"^Câu\s*\d+[\.\:]"
    
    # ==================== THAM SỐ DEBUG ====================
    
    # Debug mode
    DEBUG_MODE = False          # Bật/tắt chế độ debug
    SAVE_DEBUG_IMAGES = False   # Lưu ảnh debug
    DEBUG_FOLDER = "debug_output"
    
    # Hiển thị thông tin
    SHOW_CONTOURS = False       # Hiển thị contours
    SHOW_BOUNDING_BOXES = False # Hiển thị bounding boxes
    SHOW_PROCESSING_STEPS = False # Hiển thị các bước xử lý
    
    @classmethod
    def get_table_criteria(cls):
        """
        Trả về tiêu chí phân biệt bảng
        """
        return {
            'min_width_ratio': cls.TABLE_MIN_WIDTH_RATIO,
            'min_height_ratio': cls.TABLE_MIN_HEIGHT_RATIO,
            'min_aspect': cls.TABLE_MIN_ASPECT,
            'max_aspect': cls.TABLE_MAX_ASPECT
        }
    
    @classmethod
    def get_size_criteria(cls):
        """
        Trả về tiêu chí kích thước
        """
        return {
            'min_area_ratio': cls.MIN_AREA_RATIO,
            'min_area_abs': cls.MIN_AREA_ABS,
            'min_width': cls.MIN_WIDTH,
            'min_height': cls.MIN_HEIGHT,
            'max_area_ratio': cls.MAX_AREA_RATIO
        }
    
    @classmethod
    def get_shape_criteria(cls):
        """
        Trả về tiêu chí hình dạng
        """
        return {
            'min_aspect_ratio': cls.MIN_ASPECT_RATIO,
            'max_aspect_ratio': cls.MAX_ASPECT_RATIO,
            'min_solidity': cls.MIN_SOLIDITY
        }
    
    @classmethod
    def get_processing_params(cls):
        """
        Trả về tham số xử lý ảnh
        """
        return {
            'blur_kernel': cls.BLUR_KERNEL,
            'blur_sigma': cls.BLUR_SIGMA,
            'clahe_clip_limit': cls.CLAHE_CLIP_LIMIT,
            'clahe_tile_size': cls.CLAHE_TILE_SIZE,
            'thresh_block_size': cls.THRESH_BLOCK_SIZE,
            'thresh_c': cls.THRESH_C,
            'dilate_kernel': cls.DILATE_KERNEL,
            'dilate_iterations': cls.DILATE_ITERATIONS
        }
    
    @classmethod
    def update_config(cls, **kwargs):
        """
        Cập nhật cấu hình từ dictionary
        
        Args:
            **kwargs: Các tham số cần cập nhật
        """
        for key, value in kwargs.items():
            if hasattr(cls, key.upper()):
                setattr(cls, key.upper(), value)
            else:
                print(f"Warning: Tham số '{key}' không tồn tại")
    
    @classmethod
    def reset_to_default(cls):
        """
        Reset về cấu hình mặc định
        """
        # Này sẽ reset các giá trị về mặc định
        # Có thể implement logic phức tạp hơn nếu cần
        pass
    
    @classmethod
    def print_config(cls):
        """
        In ra cấu hình hiện tại
        """
        print("="*50)
        print("📋 CẤU HÌNH IMAGEEXTRACTOR")
        print("="*50)
        
        print("\n🎯 THAM SỐ CHÍNH:")
        print(f"  - Diện tích tối thiểu: {cls.MIN_AREA_RATIO*100:.1f}% ({cls.MIN_AREA_ABS} px)")
        print(f"  - Kích thước tối thiểu: {cls.MIN_WIDTH}x{cls.MIN_HEIGHT} px")
        print(f"  - Số ảnh tối đa: {cls.MAX_FIGURES}")
        print(f"  - Tỷ lệ khung hình: {cls.MIN_ASPECT_RATIO} - {cls.MAX_ASPECT_RATIO}")
        
        print("\n📊 PHÂN LOẠI BẢNG:")
        print(f"  - Chiều rộng tối thiểu: {cls.TABLE_MIN_WIDTH_RATIO*100:.1f}%")
        print(f"  - Chiều cao tối thiểu: {cls.TABLE_MIN_HEIGHT_RATIO*100:.1f}%")
        print(f"  - Tỷ lệ khung hình: {cls.TABLE_MIN_ASPECT} - {cls.TABLE_MAX_ASPECT}")
        
        print("\n🔍 XỬ LÝ ẢNH:")
        print(f"  - Blur kernel: {cls.BLUR_KERNEL}")
        print(f"  - CLAHE clip limit: {cls.CLAHE_CLIP_LIMIT}")
        print(f"  - Threshold block size: {cls.THRESH_BLOCK_SIZE}")
        
        print("\n🏷️ TỪ KHÓA:")
        print(f"  - Bảng: {len(cls.TABLE_KEYWORDS)} từ khóa")
        print(f"  - Hình: {len(cls.IMAGE_KEYWORDS)} từ khóa")
        
        print("="*50)


# ==================== CÁC PRESET CẤU HÌNH ====================

class PresetConfigs:
    """
    Các cấu hình preset cho các trường hợp khác nhau
    """
    
    @staticmethod
    def get_high_precision():
        """
        Cấu hình độ chính xác cao (ít ảnh hơn nhưng chính xác hơn)
        """
        return {
            'min_area_ratio': 0.015,    # 1.5%
            'min_area_abs': 5000,       # 5000 px
            'min_width': 100,           # 100 px
            'min_height': 100,          # 100 px
            'min_solidity': 0.6,        # 60%
            'max_figures': 5            # Tối đa 5 ảnh
        }
    
    @staticmethod
    def get_high_recall():
        """
        Cấu hình thu thập nhiều (nhiều ảnh hơn, có thể ít chính xác)
        """
        return {
            'min_area_ratio': 0.005,    # 0.5%
            'min_area_abs': 1500,       # 1500 px
            'min_width': 50,            # 50 px
            'min_height': 50,           # 50 px
            'min_solidity': 0.3,        # 30%
            'max_figures': 15           # Tối đa 15 ảnh
        }
    
    @staticmethod
    def get_table_focused():
        """
        Cấu hình tập trung vào bảng
        """
        return {
            'table_min_width_ratio': 0.2,   # 20%
            'table_min_height_ratio': 0.03, # 3%
            'table_min_aspect': 1.5,        # 1.5:1
            'table_max_aspect': 15.0,       # 15:1
            'min_area_ratio': 0.01          # 1%
        }
    
    @staticmethod
    def get_figure_focused():
        """
        Cấu hình tập trung vào hình
        """
        return {
            'min_aspect_ratio': 0.3,        # Hình vuông hơn
            'max_aspect_ratio': 5.0,        # Không quá dài
            'min_area_ratio': 0.012,        # 1.2%
            'table_min_width_ratio': 0.4    # Khó được coi là bảng
        }


if __name__ == "__main__":
    # Demo sử dụng
    ExtractorConfig.print_config()
    
    print("\n" + "="*50)
    print("🔧 THAY ĐỔI CẤU HÌNH")
    print("="*50)
    
    # Thay đổi một số tham số
    ExtractorConfig.update_config(
        min_area_ratio=0.01,
        max_figures=10
    )
    
    print("Đã cập nhật cấu hình!")
    ExtractorConfig.print_config()
