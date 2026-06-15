## Phụ Lục A — Hướng Dẫn Bắt Đầu Nhanh Cho Kiểm Thử Viên

Phụ lục này là điểm khởi đầu thực tế để kiểm thử sản phẩm NuFi (NuFi Chat tại
**https://chat.nufi.me**, NuFi Console tại **https://console.nufi.me**). Nó không thay thế các phần
mô tả tính năng; nó hướng dẫn bạn cách tiếp cận chúng.

### Làm quen với sản phẩm trước
1. Đọc toàn bộ phần **Introduction**, **Product Overview & Architecture** và **Glossary**. Khái niệm
   quan trọng nhất cần nắm vững là sự khác biệt giữa **Agent Knowledge** (lưu trữ bền vững,
   có thể truy xuất, RAG) và **tệp đính kèm theo từng tin nhắn** (ngữ cảnh trong phạm vi cuộc trò chuyện).
   Phần lớn các báo cáo lỗi gây nhầm lẫn xuất phát từ việc trộn lẫn hai khái niệm này.
2. Lướt qua từng phần tính năng một lần để nắm hình dung tổng thể về sản phẩm trước khi kiểm thử
   bất kỳ phần nào một cách chuyên sâu.

### Thiết lập tài khoản kiểm thử
- Tạo ít nhất **hai** tài khoản người dùng cuối để có thể xác minh tính cô lập (một người dùng
  không được nhìn thấy cuộc trò chuyện, agents, tệp, keys hay usage của người dùng khác).
- Giữ một tài khoản "sạch" (không có cuộc trò chuyện) để kiểm thử trạng thái trống, và một tài
  khoản "phong phú" (nhiều cuộc trò chuyện, agents, keys) để kiểm thử danh sách, tìm kiếm và
  phân trang.

### Chuẩn bị dữ liệu kiểm thử
- **Tài liệu cho File Search / tệp đính kèm:** ít nhất một tệp của mỗi loại được hỗ trợ — PDF, TXT, MD,
  CSV, DOCX, JSON — cùng với hình ảnh (PNG, JPEG, WEBP, GIF). Cần chuẩn bị:
  - một tệp hợp lệ nhỏ của mỗi loại,
  - một tệp **vừa vượt quá 20 MB** (giới hạn mỗi tệp),
  - một bộ tệp mà tổng dung lượng vượt quá **50 MB** (giới hạn tổng) và/hoặc vượt quá **5 files** (giới hạn
    số lượng),
  - một loại **không được hỗ trợ** (ví dụ: `.zip`, `.exe`) để xác nhận rằng tệp bị từ chối.
- **Nội dung Knowledge cho RAG:** một tài liệu chứa một thông tin đặc biệt, không thể đoán được
  (ví dụ: một mã chính sách tự đặt ra) để bạn có thể chứng minh rằng model đã truy xuất từ tài liệu
  đó chứ không phải từ kiến thức chung của nó.

### Thứ tự kiểm thử được khuyến nghị (theo mức độ ưu tiên)
1. **Xác thực & truy cập tài khoản** — bạn không thể kiểm thử bất cứ điều gì khác cho đến khi
   đăng nhập hoạt động.
2. **Chức năng chat cốt lõi** — gửi tin nhắn, streaming, dừng, tạo lại, chỉnh sửa. Giá trị chính
   của sản phẩm.
3. **Endpoint / model / tham số** — xác nhận Nufi endpoint và danh sách model hiện có.
4. **Agents & File Search (RAG)** — tính năng nổi bật của NuFi; dành nhiều thời gian nhất ở đây.
5. **Tải lên tệp & tệp đính kèm** — giới hạn và xác thực.
6. **Quản lý cuộc trò chuyện** — tìm kiếm, đổi tên, xóa, lưu trữ, đánh dấu, chia sẻ, xuất dữ liệu,
   nhiều cuộc trò chuyện, cuộc trò chuyện tạm thời.
7. **Thư viện Prompts.**
8. **Settings & liên kết Console.**
9. **NuFi Console** — cấp phát, hồ sơ cá nhân, vòng đời API key (đặc biệt là chỉ hiển thị một lần),
   ngân sách & usage.

### Cách sử dụng tiêu chí chấp nhận
Mỗi **AC-n** được viết theo dạng *Giả sử / Khi / Thì* và có thể kiểm thử độc lập. Hãy coi mỗi AC
là mức tối thiểu cần đạt. Để có độ bao phủ kỹ lưỡng, hãy kiểm thử thêm các **trường hợp biên**
được liệt kê trong mỗi phần và các đường dẫn âm (đầu vào không hợp lệ, tệp quá kích thước, backend
không thể tiếp cận, phiên làm việc đã hết hạn).

### Đặc biệt xác minh các hành vi chỉ có ở NuFi
- Thông báo chào mừng phải hiển thị đúng là **"Welcome to Nufi Chat."**
- Đúng hai endpoint được cung cấp: **Nufi** và **Agents** — không có gì khác.
- Menu tài khoản chứa mục **Console** mở NuFi Console **trong tab mới**.
- Giới hạn tệp là **5 files / 20 MB mỗi tệp / 50 MB tổng cộng** với đúng các loại tệp được hỗ trợ
  đã liệt kê.
- RAG chỉ hoạt động **thông qua một Agent có File Search** — xác nhận rằng không có RAG trong
  chat thông thường.
- Secret của Console API key mới chỉ được hiển thị **một lần** và không thể truy xuất lại sau đó.
- Các tính năng được liệt kê trong phần *Các hạn chế đã biết / tính năng chưa được bật* phải **vắng mặt**.

### Giải quyết mọi dấu hiệu "(cần xác minh: …)"
Trong toàn bộ tài liệu này, `(cần xác minh: …)` đánh dấu một chi tiết chưa thể xác nhận chỉ từ
mã nguồn. Mỗi dấu hiệu là một nhiệm vụ xác nhận nhỏ trên sản phẩm đang chạy. Khi bạn xác nhận
từng cái, tài liệu cần được cập nhật để xóa dấu hiệu đó và ghi rõ hành vi đã được xác nhận.

### Báo cáo sự cố
Khi ghi nhận lỗi, hãy tham chiếu **phần tính năng** liên quan và **FR-n** hoặc **AC-n** cụ thể bị
vi phạm, và bao gồm: môi trường/phiên bản build, tài khoản đã dùng, các bước thực hiện chính xác,
kết quả mong đợi (trích dẫn AC), kết quả thực tế, và ảnh chụp màn hình hoặc bản ghi. Việc gắn mỗi
báo cáo với FR/AC giúp các lỗi không còn mơ hồ và làm cho việc kiểm thử hồi quy có thể lặp lại được.
