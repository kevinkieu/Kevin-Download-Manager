# KDM - Kevin Download Manager (Phiên bản Windows Tải Tốc Độ Cao & Miễn Phí)

**KDM (Kevin Download Manager)** là phần mềm hỗ trợ tăng tốc tải tập tin đa luồng và tải video trực tuyến (YouTube, TikTok không logo, Facebook, Reels...) dành cho hệ điều hành Windows, sở hữu đầy đủ các tính năng mạnh mẽ tương tự IDM:

* **Tăng tốc đa luồng (HTTP Multi-segment Acceleration)**: Tự động chia file làm 8, 16 hoặc 32 phần và tải song song qua các kết nối độc lập.
* **Ghi trực tiếp theo Offset (Direct Sparse Writing)**: Các luồng ghi thẳng vào đúng vị trí byte trên ổ đĩa, tải xong là có ngay file hoàn chỉnh, **không mất thời gian ghép nối (merge file)** như các trình duyệt thông thường.
* **Tạm dừng và Tiếp tục (Pause / Resume)**: Lưu vết trạng thái byte đã tải vào tệp `.kdm_state`. Nếu mất mạng hoặc bấm Pause, có thể tiếp tục tải bất kỳ lúc nào mà không phải tải lại từ đầu.
* **Tự động bắt link và giữ đúng tên phim**: Bắt luồng HLS (`.m3u8`), MP4 và tự động lấy đúng tiêu đề tập phim (ví dụ: `Xem phim The pitt tập 11.mp4`) thay vì lưu tệp thành tên mặc định `index.mp4`.
* **Khay hệ thống (System Tray - Chuẩn IDM)**: Bấm nút `[X]` ở góc phải cửa sổ sẽ tự động ẩn KDM xuống khay hệ thống cạnh đồng hồ Windows để tiếp tục chạy nền bắt link tải. Bấm vào icon ở khay hệ thống để mở lại giao diện hoặc chọn "Thoát hoàn toàn".

---

## 🌟 6 Tính Năng Cao Cấp Mới (Chuẩn IDM)

1. **Quản lý Hàng Đợi & Lập Lịch Tải (Queue & Scheduler)**:
   * Giới hạn số tệp được tải cùng một lúc (`max_active_tasks`, ví dụ: 2 tệp cùng lúc). Các tệp vượt quá sẽ nằm ở trạng thái `⏳ Đang chờ hàng đợi (Queued)` và tự động kích hoạt khi có tệp tải xong.
   * Hẹn giờ tự động tải theo khung giờ (ví dụ: tự động chạy từ 02:00 sáng đến 06:00 sáng).
   * Tùy chọn **Tự động tắt máy tính** sau 60 giây đếm ngược khi toàn bộ danh sách tải hoàn thành.

2. **Giới Hạn Tốc Độ Tải (Speed Limiter)**:
   * Cho phép đặt mức băng thông tối đa (KB/s) trên toàn cục để không làm lag mạng hay ảnh hưởng đến người khác đang chơi game, xem phim.
   * Nút bật/tắt nhanh giới hạn tốc độ được tích hợp ngay dưới thanh trạng thái của KDM.

3. **Bắt Link Tự Động Từ Clipboard (Clipboard Monitoring)**:
   * Khi bạn copy bất kỳ liên kết tải tệp hoặc video (Ctrl+C), KDM sẽ tự động phát hiện và mở bảng hỏi tải về ngay tức thì.

4. **Phím Tắt Bắt Buộc / Bỏ Qua Trên Trình Duyệt**:
   * **Alt + Click vào link**: Ép buộc tải ngay bằng KDM.
   * **Ctrl + Click vào link**: Bỏ qua KDM, để trình duyệt tải bình thường.

5. **Tải Hàng Loạt Bằng Dải Mẫu (Batch Downloader)**:
   * Hỗ trợ cú pháp dải số `[start-end]` (ví dụ: `https://example.com/files/part_[01-20].zip` hoặc `episode_[1-12].mp4`).
   * Có nút kiểm tra & xem trước toàn bộ danh sách link được sinh ra trước khi đưa vào hàng đợi.

6. **Hỗ Trợ Proxy & Xác Thực HTTP Basic (Proxy & HTTP Auth)**:
   * Hỗ trợ cấu hình máy chủ Proxy (HTTP, HTTPS, SOCKS5) có username/password.
   * Hỗ trợ HTTP Basic Authentication khi tải từ các server nội bộ hoặc website yêu cầu đăng nhập tài khoản.

---

## 📁 Cấu Trúc Dự Án

```
Tai-nhanh/
├── dist/KDM/                 # Thư mục chứa bản EXE Độc Lập (Chạy không cần cài Python!)
│   ├── KDM.exe               # File chạy chính KDM
│   ├── kdm_extension/        # Tiện ích trình duyệt đính kèm
│   └── kdm_extension_firefox.zip # Tiện ích cho Firefox
├── kdm_app.py                # Điểm khởi chạy ứng dụng chính (Chạy Server nền + GUI)
├── kdm_engine.py             # Lõi tải tăng tốc đa luồng, yt-dlp, hàng đợi & lập lịch
├── kdm_server.py             # Local Bridge Server (cổng 59123) kết nối với Trình duyệt
├── kdm_gui.py                # Giao diện đồ họa CustomTkinter (Phong cách IDM Dark Mode)
├── kdm_settings.py           # Quản lý cấu hình Settings & khởi động cùng Windows
├── build_exe.bat             # Script 1-click đóng gói KDM thành file EXE độc lập
├── run_kdm.bat               # File chạy nhanh qua Python
├── package_firefox_extension.py # Công cụ đóng gói Extension cho Firefox
└── kdm_extension/            # Mã nguồn Tiện ích Trình duyệt (Chrome, Cốc Cốc, Edge, Firefox)
    ├── manifest.json         # Manifest V3 (Chromium)
    ├── manifest_firefox.json # Manifest cho Firefox
    ├── background.js         # Bắt link tải trình duyệt & xử lý Alt/Ctrl Click
    ├── content.js            # Bắt video YouTube/TikTok & neo thanh nổi trên player
    └── icons/                # Bộ biểu tượng KDM
```

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Khởi động KDM
* **Cách 1 (Khuyên dùng)**: Mở thư mục `dist\KDM` và nhấp đúp vào **`KDM.exe`** (Chạy độc lập 100%, không cần cài đặt Python).
* **Cách 2**: Chạy qua file `run_kdm.bat` nếu máy có sẵn Python.

### 2. Cài đặt Extension vào Trình duyệt

#### Dành cho Chrome, Cốc Cốc, Microsoft Edge, Brave:
1. Mở trình duyệt và vào mục Quản lý Tiện ích:
   * **Chrome / Cốc Cốc**: Nhập `chrome://extensions/` hoặc `coccoc://extensions/`
   * **Edge**: Nhập `edge://extensions/`
2. Bật công tắc **"Chế độ dành cho nhà phát triển"** (Developer mode) ở góc trên bên phải.
3. Bấm vào nút **"Tải tiện ích đã giải nén"** (Load unpacked).
4. Chọn thư mục `kdm_extension` (hoặc `dist\KDM\kdm_extension`).
5. Đã xong! Biểu tượng KDM sẽ xuất hiện trên thanh công cụ của trình duyệt.

#### Dành cho Mozilla Firefox:
1. Mở Firefox và truy cập: `about:debugging#/runtime/this-firefox`
2. Bấm vào nút **"Tải Tiện ích Tạm thời..."** (Load Temporary Add-on...)
3. Chọn tệp `kdm_extension_firefox.zip`.
