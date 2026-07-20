## Các Yêu Cầu Xuyên Suốt

Những yêu cầu này được áp dụng cho tất cả các tính năng đã đề cập ở trên. Khi một tính năng cụ thể
nhắc lại một trong các yêu cầu này (ví dụ: một thông báo lỗi cụ thể), phần mô tả của tính năng đó
là tài liệu có thẩm quyền cho chi tiết đó.

### Xác thực & phiên làm việc
- **CC-1** Mọi màn hình yêu cầu xác thực trong cả NuFi Chat và NuFi Console đều cần có phiên làm việc hợp lệ.
  Khi phiên làm việc bị thiếu hoặc đã hết hạn, Chat sẽ chuyển hướng về trang đăng nhập và Console hiển thị
  trang *unauthorized* có liên kết tới trang đăng nhập.
- **CC-2** Chat và Console dùng chung một phiên đăng nhập (JWT). Đăng xuất khỏi Chat phải
  vô hiệu hóa quyền truy cập vào Console trong yêu cầu tiếp theo (cần xác minh: xác nhận hành vi lan truyền
  chính xác và khoảng thời gian làm mới token trong sản phẩm đang chạy).
- **CC-3** Token phiên làm việc được làm mới trong suốt quá trình người dùng hoạt động; người dùng không nên
  bị đăng xuất bất ngờ trong quá trình sử dụng liên tục.

### Kiểm tra đầu vào
- **CC-4** Tất cả các đầu vào của người dùng được kiểm tra ở phía client với thông báo lỗi nội tuyến theo từng
  trường trước khi gửi; các biểu mẫu không hợp lệ không thể được gửi (nút gửi bị vô hiệu hóa hoặc
  việc gửi bị chặn).
- **CC-5** Tệp tải lên được kiểm tra theo giới hạn của NuFi (tối đa 5 files mỗi tin nhắn, 20 MB mỗi
  tệp, 50 MB tổng cộng) và danh sách MIME type được phép; các vi phạm sẽ được thông báo đến người dùng
  và tệp vi phạm sẽ bị từ chối.

### Xử lý lỗi & thông báo
- **CC-6** Lỗi mạng hoặc lỗi backend phải hiển thị thông báo có thể đọc được (toast, banner hoặc
  thông báo nội tuyến) thay vì thất bại trong im lặng hoặc hiển thị stack trace thô.
- **CC-7** Khi backend AI không thể tiếp cận, danh sách model sẽ hiển thị placeholder dự phòng và
  các lượt gửi chat sẽ thất bại với thông báo lỗi hiển thị rõ ràng; ứng dụng phải vẫn có thể sử dụng được
  (người dùng có thể thử lại).
- **CC-8** Các hành động không thể hoàn tác (xóa cuộc trò chuyện, thu hồi API key, xóa tài khoản, xóa tất cả
  các cuộc trò chuyện) phải yêu cầu xác nhận rõ ràng trước khi thực hiện.

### Hiệu năng & khả năng phản hồi
- **CC-9** Các phản hồi streaming được hiển thị từng phần; giao diện người dùng phải vẫn phản hồi được (cuộn,
  dừng, điều hướng) trong khi phản hồi đang streaming.
- **CC-10** Danh sách cuộc trò chuyện dài được tải từng phần (cuộn vô hạn / phân trang) thay vì
  chặn lại trên một lần tải lớn duy nhất.
- **CC-11** Việc tải lên và nhúng tài liệu Knowledge là bất đồng bộ; giao diện người dùng phải hiển thị
  tiến trình và không chặn các tương tác khác.

### Bản địa hóa (i18n)
- **CC-12** Giao diện hỗ trợ nhiều ngôn ngữ có thể chọn trong Settings → General. Tất cả
  các chuỗi hiển thị với người dùng đều được lấy từ các tệp dịch (không có chuỗi tiếng Anh cứng
  trong các màn hình đã bản địa hóa). Ngôn ngữ mặc định của NuFi là tiếng Anh (cần xác minh: xác nhận
  ngôn ngữ mặc định được cấu hình cho deployment).
- **CC-13** Thông báo chào mừng tùy chỉnh "Welcome to Nufi Chat." được hiển thị trên màn hình
  landing của chat.

### Khả năng tiếp cận
- **CC-14** Các điều khiển tương tác hiển thị tên tiếp cận (`aria-label` / labels) và các thông báo
  lỗi xác thực sử dụng `role="alert"`; các luồng chính có thể thao tác bằng bàn phím (cần xác minh:
  duyệt toàn bộ từng luồng chính chỉ bằng bàn phím trên sản phẩm đang chạy).
- **CC-15** Các phím tắt được ghi lại trong các phần tính năng (ví dụ: Enter để gửi, Shift+Enter cho
  xuống dòng) hoạt động đúng như mô tả.

### Chủ đề & giao diện
- **CC-16** Ứng dụng hỗ trợ các chủ đề sáng, tối và theo hệ thống có thể chọn trong Settings; chủ đề
  đã chọn được lưu lại qua các phiên làm việc.

### Bảo mật & quyền riêng tư
- **CC-17** Secret của Console API key mới tạo chỉ được hiển thị đúng **một lần** và không thể
  truy xuất lại sau đó; dạng lưu trữ/hiển thị danh sách được che đi.
- **CC-18** Người dùng chỉ có thể xem và quản lý **các cuộc trò chuyện, agents, tệp, keys và
  usage của chính họ**. Truy cập chéo giữa các người dùng không được phép từ giao diện người dùng cuối.
- **CC-19** Các cuộc trò chuyện tạm thời không được lưu vào lịch sử; đóng/rời khỏi chúng sẽ xóa bỏ
  nội dung.

### Hỗ trợ trình duyệt
- **CC-20** Ứng dụng hướng tới các phiên bản hiện tại của các trình duyệt desktop phổ biến (Chrome, Edge,
  Firefox, Safari). Ma trận hỗ trợ chính xác cần được xác nhận và ghi lại bởi QA
  (cần xác minh: xác định và ghi lại ma trận trình duyệt được hỗ trợ chính thức).

### Các hạn chế đã biết / tính năng chưa được bật (NuFi)
Các tính năng LibreChat thượng nguồn sau đây **không được bật** trong deployment NuFi và **không**
được kỳ vọng trong quá trình kiểm thử (các điều khiển của chúng phải vắng mặt, hoặc nếu hiển thị,
được coi là ngoài phạm vi): tìm kiếm web, trình thông dịch code / thực thi artifacts, nhập/xuất giọng
nói (TTS/STT), đăng nhập mạng xã hội / OAuth qua các nhà cung cấp **khác ngoài Google** (GitHub,
Discord, Facebook, Apple, OpenID, SAML — lưu ý rằng **đăng nhập bằng Google ĐÃ được bật**), đặt lại
mật khẩu (`ALLOW_PASSWORD_RESET=false`), và bất kỳ chat endpoint nào khác ngoài **Nufi** và
**Agents**. Nếu bất kỳ tính năng nào trong số này xuất hiện và hoạt động được, hãy ghi nhận đó là sự
khác biệt về cấu hình.
