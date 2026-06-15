## Tải Lên Tệp & Đính Kèm

> **Phạm vi — chỉ đính kèm theo từng tin nhắn.** Phần này đề cập đến các tệp được đính kèm trực tiếp vào một tin nhắn trong cuộc trò chuyện (phạm vi theo cuộc hội thoại). Các tệp này được tải lên để làm ngữ cảnh cho một lần tương tác: hình ảnh được gửi dưới dạng đầu vào thị giác (vision); tài liệu được gửi dưới dạng ngữ cảnh văn bản cho phiên trao đổi tin nhắn đó. Cơ chế này khác với **Agent Knowledge** (RAG lâu dài qua file search / vector store), được đề cập trong phần Agents. Khi không chắc nên dùng cơ chế nào, xem [Mối quan hệ với Agent Knowledge](#relationship-to-agent-knowledge) bên dưới.

---

### Nút Đính Kèm (Attach Button)

#### Mục đích
Cung cấp điểm truy cập chính để chọn tệp cục bộ đính kèm vào tin nhắn hiện tại trước khi gửi.

#### Điều kiện tiên quyết / truy cập
- Một cuộc hội thoại phải đang mở (hoặc "New Chat" phải được chọn với endpoint Nufi đang hoạt động).
- Endpoint Nufi phải được chọn; tính năng tải lên tệp bị vô hiệu hóa đối với các endpoint đặt tường minh `disabled: true`.
- Vùng nhập liệu không được ở trạng thái bị vô hiệu hóa (ví dụ: trong khi phản hồi đang được tạo).

#### Thành phần giao diện
- Nút **Attach Files** (biểu tượng kẹp giấy, `aria-label="Attach Files"`, nhãn tooltip `com_sidepanel_attach_files` → "Attach Files") nằm trên thanh công cụ nhập liệu của cuộc trò chuyện.
- Trên endpoint Nufi (endpoint tùy chỉnh không phải Assistants hỗ trợ tệp), nhấp vào nút sẽ mở **menu thả xuống** (`id="attach-file-menu"`, `aria-label="Attach File Options"`) thay vì mở trực tiếp hộp thoại chọn tệp.
- Menu thả xuống liệt kê các tùy chọn đích tải lên tùy theo khả năng của endpoint (xem phần Các loại được hỗ trợ). Đối với endpoint Nufi, menu hiển thị ít nhất: **"Upload to Provider"** (`com_ui_upload_provider`). Tùy chọn "Upload as Text" (`com_ui_upload_ocr_text`) **không có sẵn** trên endpoint Nufi vì khả năng `context` không được bật trong cấu hình server (`agents.capabilities` không bao gồm `context`).
- Thẻ `<input type="file">` ẩn được mở theo chương trình khi người dùng chọn một mục trong menu.
- Bàn phím: nút đính kèm phản hồi `Enter` hoặc `Space` để mở hộp thoại chọn tệp.

#### Hành vi chức năng
1. FR-1: Khi người dùng nhấp vào nút Attach Files, menu thả xuống xuất hiện liệt kê ít nhất các tùy chọn loại tải lên áp dụng cho endpoint Nufi.
2. FR-2: Nhấp vào một mục menu sẽ đặt bộ lọc `accept` trên trường input tệp ẩn (`image/*,.heif,.heic,.pdf,application/pdf` cho "Upload to Provider"; không hạn chế cho các loại khác) và mở hộp thoại chọn tệp của hệ điều hành.
3. FR-3: Sau khi hộp thoại chọn tệp của hệ điều hành bị đóng, các tệp được chọn đi qua quá trình kiểm tra hợp lệ phía client (xem phần Kiểm tra hợp lệ). Các tệp vượt qua kiểm tra được hiển thị ngay lập tức dưới dạng chip đang xử lý trong vùng nhập liệu.
4. FR-4: Nút Attach Files bị vô hiệu hóa về mặt hiển thị (được render với thuộc tính `disabled`) khi `disableInputs` là true (ví dụ: trong quá trình tạo tin nhắn).
5. FR-5: Chọn một mục menu rồi hủy hộp thoại chọn tệp của hệ điều hành mà không chọn tệp nào sẽ không có tác dụng gì; không có lỗi nào được hiển thị.

#### Kiểm tra hợp lệ & lỗi
- Nếu tải lên bị vô hiệu hóa bởi cấu hình server: toast lỗi "File uploads are disabled for this endpoint" (`com_ui_attach_error_disabled`).
- Toàn bộ phần kiểm tra hợp lệ tiếp theo được mô tả trong [Kiểm tra hợp lệ & Xử lý lỗi](#validation--error-handling).

#### Trường hợp đặc biệt
- Nếu không có cuộc hội thoại nào đang hoạt động (ví dụ: chưa chọn endpoint), nút có thể vắng mặt hoặc bị vô hiệu hóa; người dùng thấy toast "Cannot attach file. Create or select a conversation, or try refreshing the page." (`com_ui_attach_error`).
- Nếu người dùng mở menu nhưng nhấp ra ngoài để đóng, hộp thoại chọn tệp sẽ không mở.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử endpoint Nufi đang hoạt động và đầu vào được bật, khi người dùng nhấp vào nút Attach Files, thì menu thả xuống xuất hiện với ít nhất tùy chọn "Upload to Provider" (và "Upload for File Search" khi file search được bật). "Upload as Text" không hiển thị trên endpoint Nufi theo cấu hình hiện tại.
2. AC-2: Giả sử menu thả xuống đang mở, khi người dùng chọn "Upload to Provider", thì hộp thoại chọn tệp của hệ điều hành mở ra với bộ lọc `image/*,.heif,.heic,.pdf,application/pdf`.
3. AC-3: Giả sử vùng nhập liệu bị vô hiệu hóa (đang tạo tin nhắn), khi nút được render, thì nút có thuộc tính `disabled` và nhấp vào nó không có tác dụng gì.
4. AC-4: Giả sử tính năng tải lên tệp bị vô hiệu hóa theo cấu hình endpoint, khi người dùng cố mở hộp thoại chọn tệp, thì xuất hiện toast đỏ "File uploads are disabled for this endpoint".

---

### Kéo và Thả (Drag-and-Drop)

#### Mục đích
Cho phép người dùng thả tệp từ màn hình nền hoặc trình quản lý tệp vào bất kỳ đâu trên vùng trò chuyện mà không cần dùng nút đính kèm.

#### Điều kiện tiên quyết / truy cập
- Một cuộc hội thoại phải đang mở với endpoint Nufi đang hoạt động.
- Tính năng tải lên tệp không được bị vô hiệu hóa cho endpoint.

#### Thành phần giao diện
- Toàn bộ vùng trò chuyện (được bọc trong `DragDropWrapper`) hoạt động như vùng thả tệp.
- Trong khi tệp đang được kéo qua cửa sổ, một **lớp phủ toàn màn hình nửa trong suốt** (`DragDropOverlay`) xuất hiện với:
  - Hình minh họa tải lên (đồ họa SVG).
  - Tiêu đề: **"Upload files"** (`com_ui_upload_files`).
  - Tiêu đề phụ: **"Drop any file here to add it to the conversation"** (`com_ui_drag_drop`).
- Nếu (các) tệp được thả kích hoạt nhiều đích đến có thể (ví dụ: hình ảnh có thể đến các tài nguyên công cụ khác nhau), hộp thoại **"Select Upload Type"** (`com_ui_upload_type`) xuất hiện cung cấp các nút cho mỗi đích đến.

#### Hành vi chức năng
1. FR-1: Khi người dùng kéo tệp vào cửa sổ ứng dụng, lớp phủ hiển thị với hình minh họa tải lên và văn bản hướng dẫn.
2. FR-2: Khi người dùng thả (drop) (các) tệp, nếu tính năng tải lên của endpoint bị vô hiệu hóa thì toast lỗi hiển thị ngay lập tức mà không hiển thị hộp thoại.
3. FR-3: Đối với endpoint Nufi, hộp thoại "Select Upload Type" xuất hiện với **bất kỳ** loại tệp được thả nào khi có ít nhất một khả năng tải lên áp dụng — không chỉ với hình ảnh. Vì `file_search` được bật trong cấu hình Nufi (`fileSearchEnabled = true`, `fileSearchAllowedByAgent = true` theo mặc định), hộp thoại hiển thị với hình ảnh, tài liệu và tất cả các loại tệp được hỗ trợ khác. Tùy chọn chính của hộp thoại cho endpoint Nufi là **"Upload to Provider"** (`com_ui_upload_provider`). Người dùng phải nhấp vào một tùy chọn để tiếp tục.
4. FR-4: Tệp được xử lý trực tiếp (không qua hộp thoại) chỉ khi không có điều kiện khả năng nào được đáp ứng. Theo cấu hình hiện tại của Nufi (`file_search` được bật), hộp thoại luôn xuất hiện với các tệp được thả, do đó đường bỏ qua này không được kích hoạt.
5. FR-5: Sau khi người dùng chọn một tùy chọn trong hộp thoại (hoặc tệp được xử lý trực tiếp), quy trình kiểm tra hợp lệ và tải lên giống như đối với tệp được chọn qua nút sẽ áp dụng.
6. FR-6: Lớp phủ biến mất khi người dùng di chuyển mục đang kéo ra khỏi vùng thả hoặc thả tệp.

#### Kiểm tra hợp lệ & lỗi
- Kiểm tra endpoint bị vô hiệu hóa chạy trước khi hộp thoại được hiển thị; nếu endpoint bị vô hiệu hóa, toast lỗi xuất hiện thay vì hộp thoại.
- Toàn bộ kiểm tra hợp lệ tiếp theo (loại, kích thước, số lượng) chạy sau khi chọn tùy chọn hộp thoại, thông qua cùng pipeline `validateFiles`.

#### Trường hợp đặc biệt
- Thả một thư mục (không có tệp) không dẫn đến hành động nào (trình duyệt không hiển thị nội dung thư mục qua API `FileList` trong luồng này).
- Thả một loại tệp không được hỗ trợ: với `file_search` được bật, hộp thoại vẫn xuất hiện; loại không được hỗ trợ được phát hiện trong quá trình kiểm tra hợp lệ sau khi chọn tùy chọn, hiển thị toast lỗi.
- Thả nhiều tệp hơn giới hạn tệp trên mỗi tin nhắn: được phát hiện trong quá trình kiểm tra hợp lệ sau khi chọn tùy chọn.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử vùng trò chuyện đang hiển thị và tính năng tải lên được bật, khi người dùng kéo tệp vào cửa sổ, thì lớp phủ kéo-thả với hình minh họa tải lên xuất hiện.
2. AC-2: Giả sử lớp phủ đang hiển thị, khi người dùng thả bất kỳ tệp nào (hình ảnh hay tài liệu), thì hộp thoại "Select Upload Type" xuất hiện (vì `file_search` được bật cho endpoint Nufi).
3. AC-3: Giả sử hộp thoại đang hiển thị, khi người dùng nhấp vào "Upload to Provider", thì tệp bắt đầu tải lên và chip tiến trình xuất hiện trong vùng nhập liệu.
4. AC-4: Giả sử tính năng tải lên bị vô hiệu hóa theo cấu hình endpoint, khi người dùng thả tệp, thì toast đỏ "File uploads are disabled for this endpoint" xuất hiện và không có hộp thoại nào được hiển thị.
5. AC-5: Giả sử người dùng kéo tệp vào cửa sổ rồi kéo ra ngoài mà không thả, thì lớp phủ biến mất và không có tệp nào được đính kèm.

---

### Dán Hình Ảnh (Paste Image)

#### Mục đích
Cho phép người dùng dán dữ liệu hình ảnh trực tiếp từ clipboard (ví dụ: ảnh chụp màn hình hoặc hình ảnh đã sao chép) vào vùng nhập văn bản của tin nhắn.

#### Điều kiện tiên quyết / truy cập
- Vùng nhập văn bản của tin nhắn (`data-testid="text-input"`) phải được focus.
- Endpoint Nufi phải hỗ trợ tải lên hình ảnh.
- Clipboard phải chứa dữ liệu tệp (không chỉ là văn bản).

#### Thành phần giao diện
- Không có thành phần giao diện riêng biệt: hành động dán được kích hoạt bằng phím tắt clipboard gốc (Cmd+V / Ctrl+V) trong khi vùng nhập văn bản được focus.
- Sau khi dán, hình ảnh đính kèm xuất hiện dưới dạng chip xem trước (giống như hình ảnh được tải lên qua nút).

#### Hành vi chức năng
1. FR-1: Khi người dùng dán trong khi vùng nhập văn bản đang được focus và clipboard chứa một hoặc nhiều tệp, ứng dụng đọc `clipboardData.files` và khởi tạo xử lý tệp cho từng tệp.
2. FR-2: Mỗi tệp được dán được đổi tên thành `clipboard_<timestamp>_<originalName>` trước khi xử lý; điều này đảm bảo hình ảnh được dán có tên ổn định và duy nhất để phát hiện trùng lặp.
3. FR-3: Các tệp được dán đi qua cùng pipeline `validateFiles` (kiểm tra MIME, kiểm tra kích thước, kiểm tra số lượng, kiểm tra tổng kích thước).
4. FR-4: Nếu clipboard chỉ chứa văn bản, hành vi dán văn bản thông thường xảy ra; không có tải lên tệp nào được kích hoạt.
5. FR-5: Hình ảnh HEIC/HEIF được dán từ clipboard được chuyển đổi sang JPEG trước khi tải lên (xem xử lý HEIC trong phần Hình ảnh vs Tài liệu).

#### Kiểm tra hợp lệ & lỗi
- Toàn bộ kiểm tra hợp lệ giống hệt với đường tải lên qua nút; xem [Kiểm tra hợp lệ & Xử lý lỗi](#validation--error-handling).
- Loại tệp được dán không được hỗ trợ sẽ hiển thị toast "Unsupported file type: `<mime>`".

#### Trường hợp đặc biệt
- Dán nhiều hình ảnh cùng lúc: mỗi hình ảnh được xử lý riêng lẻ; giới hạn số lượng và tổng kích thước áp dụng cho tổng hợp.
- Dán ảnh chụp màn hình: trình duyệt thường hiển thị nó là `image/png` — vượt qua kiểm tra MIME trên endpoint Nufi.
- Dán tệp mà trình duyệt không thể xác định loại: suy luận MIME từ phần mở rộng được thử; nếu suy luận thất bại, tệp bị từ chối với "Unable to determine file type for: `<filename>`".

#### Tiêu chí chấp nhận
1. AC-1: Giả sử vùng nhập văn bản đang được focus, khi người dùng dán hình ảnh từ clipboard, thì chip xem trước hình ảnh xuất hiện trong vùng nhập liệu và tệp bắt đầu tải lên.
2. AC-2: Giả sử vùng nhập văn bản đang được focus, khi người dùng dán văn bản thuần, thì việc chèn văn bản thông thường xảy ra và không có tải lên nào được kích hoạt.
3. AC-3: Giả sử vùng nhập văn bản đang được focus, khi người dùng dán hình ảnh vượt quá 20 MB, thì toast đỏ "File size limit exceeded: 20 MB" xuất hiện và không có chip nào được thêm vào.
4. AC-4: Giả sử đã đính kèm 5 tệp, khi người dùng dán tệp thứ 6, thì toast đỏ "File limit reached: 5 files" xuất hiện và thao tác dán bị từ chối.

---

### Các Loại Được Hỗ Trợ & Giới Hạn

#### Mục đích
Xác định các tệp mà endpoint Nufi chấp nhận và các giới hạn cứng được áp dụng tại thời điểm chọn tệp.

#### Điều kiện tiên quyết / truy cập
- Giới hạn áp dụng mỗi khi xảy ra chọn tệp, kéo-thả, hoặc dán trên endpoint Nufi.

#### Thành phần giao diện
- Không có thành phần giao diện riêng biệt hiển thị giới hạn cho người dùng trước khi thử đính kèm; giới hạn được hiển thị qua thông báo toast lỗi tại thời điểm kiểm tra hợp lệ.

#### Hành vi chức năng
Các giới hạn sau đang hoạt động trên endpoint **Nufi** (lấy từ cấu hình server đã triển khai):

| Giới hạn | Giá trị |
|---|---|
| Số tệp tối đa mỗi tin nhắn | **5** |
| Kích thước tối đa mỗi tệp | **20 MB** (ranh giới loại trừ: tệp phải nghiêm ngặt nhỏ hơn 20 MB) |
| Tổng kích thước tối đa mỗi yêu cầu | **50 MB** |

Các loại MIME được hỗ trợ (MIME được kiểm tra với danh sách regex `supportedMimeTypes` được cấu hình cho endpoint Nufi):

| Loại | MIME |
|---|---|
| Hình ảnh PNG | `image/png` |
| Hình ảnh JPEG | `image/jpeg` |
| Hình ảnh WebP | `image/webp` |
| Hình ảnh GIF | `image/gif` |
| Tài liệu PDF | `application/pdf` |
| Văn bản thuần | `text/plain` |
| Markdown | `text/markdown` |
| CSV | `text/csv` |
| Tài liệu Word (.docx) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| JSON | `application/json` |

> **Lưu ý về HEIC/HEIF:** Khi tải lên qua tùy chọn "Upload to Provider", tệp HEIC/HEIF được chuyển đổi phía client sang JPEG trước khi kiểm tra hợp lệ và tải lên, do đó MIME kết quả là `image/jpeg`. HEIC được chấp nhận như một định dạng nguồn hình ảnh mặc dù `image/heic` không có trong danh sách hỗ trợ của Nufi vì quá trình chuyển đổi xảy ra trước kiểm tra hợp lệ.

> **Lưu ý về ranh giới kích thước:** Kiểm tra `fileSizeLimit` sử dụng `>=` (nghiêm ngặt), vì vậy tệp có kích thước đúng bằng 20 MB bị từ chối. Chỉ các tệp nghiêm ngặt nhỏ hơn 20 MB được chấp nhận.

#### Kiểm tra hợp lệ & lỗi
Xem [Kiểm tra hợp lệ & Xử lý lỗi](#validation--error-handling) để biết bảng thông báo lỗi đầy đủ.

#### Trường hợp đặc biệt
- Tệp có phần mở rộng được nhận dạng nhưng loại MIME do trình duyệt báo cáo là rỗng: `inferMimeType` giải quyết MIME từ phần mở rộng trước khi kiểm tra loại.
- Tệp có phần mở rộng không nhận dạng được và MIME rỗng: bị từ chối với "Unable to determine file type for: `<filename>`".

#### Tiêu chí chấp nhận
1. AC-1: Giả sử endpoint Nufi đang hoạt động, khi người dùng đính kèm tệp `image/png` có dung lượng 5 MB, thì tệp được chấp nhận và bắt đầu tải lên.
2. AC-2: Giả sử endpoint Nufi đang hoạt động, khi người dùng đính kèm tệp có kích thước đúng bằng 20 MB, thì quá trình kiểm tra hợp lệ từ chối tệp với "File size limit exceeded: 20 MB".
3. AC-3: Giả sử endpoint Nufi đang hoạt động, khi người dùng đính kèm tệp 19,9 MB, thì tệp được chấp nhận và bắt đầu tải lên.
4. AC-4: Giả sử endpoint Nufi đang hoạt động, khi người dùng đính kèm tệp `.docx`, thì tệp được chấp nhận.
5. AC-5: Giả sử endpoint Nufi đang hoạt động, khi người dùng đính kèm tệp video `.mp4`, thì quá trình kiểm tra hợp lệ từ chối tệp với "Unsupported file type: video/mp4".
6. AC-6: Giả sử endpoint Nufi đang hoạt động, khi tổng kích thước các tệp đã đính kèm cộng với tệp mới vượt quá 50 MB, thì tệp mới bị từ chối với "Total file size limit exceeded: 50 MB".

---

### Trạng Thái Tải Lên (Tiến Trình, Thành Công, Lỗi)

#### Mục đích
Cung cấp phản hồi trực quan theo thời gian thực trong vòng đời tải lên tệp từ khi chọn đến khi server xác nhận.

#### Điều kiện tiên quyết / truy cập
- Một tệp đã vượt qua kiểm tra hợp lệ phía client và một chip đã được thêm vào vùng nhập liệu.

#### Thành phần giao diện
- **Chip hình ảnh đang xử lý:** Thumbnail 56×56 px với chỉ báo tiến trình hình tròn (`ProgressCircle`) được phủ lên. Tiến trình được hiển thị dưới dạng cung stroke-dashoffset có animation khi `progress` tăng từ `0` đến `1`. Với hình ảnh không phải HEIC các bước là: `0.1` khởi tạo → `0.2` sẵn sàng tải lên → `0.6` kích thước hình ảnh đã tải → `0.9` server đã xác nhận → `1.0` hoàn thành. Với hình ảnh HEIC/đã xử lý, bước `0.2` bị bỏ qua; tiến trình theo: `0.1` → dải chuyển đổi HEIC (0.1–0.5) → `0.5` xử lý hoàn thành → `0.6` hình ảnh đã tải → `0.9` server đã xác nhận → `1.0` hoàn thành.
- **Chip tài liệu đang xử lý:** Chip `FileContainer` (rộng 224 px) với `Spinner` phủ lên biểu tượng loại tệp (hiển thị khi `file.progress < 1`).
- **Cảnh báo tải lên chậm:** Sau khi tải lên mất nhiều thời gian hơn ngưỡng (cơ sở 5 giây + 2 giây mỗi MB kích thước tệp), toast vàng xuất hiện: `"Uploading \"<filename>\" is taking more time than anticipated. Please wait while the file finishes indexing for retrieval."` (`com_ui_upload_delay`).
- **Trạng thái thành công:** Tiến trình đạt `1.0`; spinner/cung tiến trình biến mất; chip render thumbnail tệp hoặc biểu tượng tài liệu bình thường. Không có toast "thành công" rõ ràng nào được hiển thị cho đính kèm theo tin nhắn.
- **Trạng thái lỗi:** Chip bị xóa khỏi danh sách; toast đỏ xuất hiện với thông báo lỗi liên quan (xem bên dưới).

#### Hành vi chức năng
1. FR-1: Ngay sau khi kiểm tra hợp lệ thành công, chip được thêm vào vùng nhập liệu với `progress = 0.1` (trạng thái đang xử lý), cung cấp phản hồi trực quan ngay lập tức trước khi yêu cầu tải lên được thực hiện.
2. FR-2: Đối với hình ảnh không phải HEIC, tiến trình tăng lên `0.2` (sẵn sàng tải lên), sau đó `0.6` (kích thước hình ảnh đã tải), sau đó `0.9` (server phản hồi), sau đó `1.0` sau 300 ms. Đối với hình ảnh HEIC/đã xử lý, bước `0.2` không có; tiến trình đi từ `0.1` qua dải chuyển đổi HEIC (0.1–0.5), đến `0.5` (xử lý hoàn thành), `0.6` (hình ảnh đã tải), `0.9` (server phản hồi), rồi `1.0` sau 300 ms.
3. FR-3: Đối với tài liệu, tiến trình tăng từ `0.1` lên `0.9` (server đã xác nhận) sau đó `1.0` sau 300 ms.
4. FR-4: Nếu tải lên mất nhiều thời gian hơn ngưỡng, toast cảnh báo vàng xuất hiện (xem Thành phần giao diện); tải lên vẫn tiếp tục.
5. FR-5: Khi có lỗi server, chip bị xóa và toast đỏ "An error occurred while uploading the file." (`com_error_files_upload`) xuất hiện, hoặc `response.data.message` của server nếu có.
6. FR-6: Trạng thái `setFilesLoading` là `true` khi bất kỳ tệp nào có `progress < 1`, chặn việc gửi tin nhắn.

#### Kiểm tra hợp lệ & lỗi
- Lỗi mạng khi tải lên: toast "An error occurred while uploading the file."
- Tải lên bị hủy (abort): toast "The file upload request was canceled. Note: the file upload may still be processing and will need to be manually deleted." (`com_error_files_upload_canceled`).
- Lỗi chuyển đổi HEIC: toast "Failed to convert HEIC image to JPEG. Please try converting the image manually or use a different format." (`com_error_heic_conversion`).
- Lỗi xử lý chung: toast "An error occurred while processing the file." (`com_error_files_process`).

#### Trường hợp đặc biệt
- Nếu người dùng xóa chip trong khi tải lên đang xử lý, `abortUpload()` được gọi để hủy yêu cầu HTTP qua `AbortController`; toast hủy xuất hiện.
- Nếu nhiều tệp đang tải lên đồng thời và một tệp thất bại, chỉ chip của tệp đó bị xóa; các tải lên khác tiếp tục.
- Nếu phản hồi thành công từ server trả về `file_id` khác với `temp_file_id`, mục cache xem trước được di chuyển sang ID mới để thumbnail hình ảnh được giữ nguyên.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử tệp hợp lệ được chọn, khi nó được thêm vào vùng nhập liệu, thì chip tiến trình xuất hiện ngay lập tức với lớp phủ spinner/cung.
2. AC-2: Giả sử tệp đang tải lên, khi server trả về phản hồi thành công, thì spinner/cung biến mất và chip hiển thị thumbnail đã render đầy đủ hoặc biểu tượng tài liệu.
3. AC-3: Giả sử tải lên tệp mất hơn 5 giây, thì toast cảnh báo vàng chứa tên tệp xuất hiện.
4. AC-4: Giả sử tải lên tệp thất bại do lỗi mạng, thì chip bị xóa và toast đỏ "An error occurred while uploading the file." xuất hiện.
5. AC-5: Giả sử tệp đang tải lên, khi người dùng nhấp vào nút xóa trên chip, thì tải lên bị hủy và toast hủy xuất hiện.

---

### Xem Trước & Xóa Tệp (File Preview & Removal)

#### Mục đích
Cho phép người dùng kiểm tra các tệp đính kèm trước khi gửi và xóa các đính kèm không mong muốn.

#### Điều kiện tiên quyết / truy cập
- Ít nhất một tệp đã được thêm vào (kể cả trong khi đang tải lên) vào tin nhắn hiện tại.

#### Thành phần giao diện
- **Chip hình ảnh:** Hình vuông bo tròn (56×56 px, class `rounded-2xl`) hiển thị hình ảnh dưới dạng nền. Khi hover, lớp phủ tối nửa trong suốt với biểu tượng `Maximize2` (mở rộng) xuất hiện. Nhấp vào mở lightbox toàn màn hình (`DialogPrimitive.Root`) với nền `bg-black/90`, hình ảnh có `max-h-[85vh] max-w-[90vw]`. Nút đóng (`aria-label="Close"`) ở góc trên bên phải của lightbox; nhấn Escape cũng đóng nó.
- **Chip tài liệu (`FileContainer`):** Chip rộng 224 px với viền hình chữ nhật bo tròn. Phía trái: biểu tượng loại tệp (ví dụ: tài liệu, bảng tính, code). Phía phải: tên tệp (được cắt ngắn với tooltip `title` cho tên dài) và nhãn loại tệp (ví dụ: "Document", "Spreadsheet", "Code").
- **Nút xóa:** Nút `×` hình tròn nhỏ (`aria-label="Remove file"`, translation key `com_ui_attach_remove`) đặt ở góc trên bên phải của mỗi chip (hiển thị mọi lúc, không chỉ khi hover). Nhấp vào xóa tệp.
- **Huy hiệu nguồn:** Biểu tượng nhỏ ở góc dưới bên phải của vùng biểu tượng tệp cho biết nguồn của tệp (ví dụ: logo OpenAI cho tệp từ nguồn OpenAI, "T" cho tệp được trích xuất văn bản, biểu tượng cơ sở dữ liệu cho tệp vector-store). Đối với tải lên cục bộ trên endpoint Nufi, huy hiệu này thường vắng mặt.
- **Trạng thái đang xóa:** Khi nút xóa được nhấp trên tệp đã tải lên hoàn toàn, toast thông tin màu xanh "Deleting file..." (`com_ui_deleting_file`) xuất hiện ngắn gọn trong khi yêu cầu xóa server đang chạy.

#### Hành vi chức năng
1. FR-1: Chip hình ảnh render hình ảnh dưới dạng CSS `background-image`. Nhấp vào chip (khi đã tải lên hoàn toàn, `progress === 1`) sẽ mở lightbox toàn màn hình.
2. FR-2: Chip tài liệu hiển thị tên tệp và nhãn loại dễ đọc được suy ra từ loại MIME (ví dụ: `application/pdf` → "Document", `text/csv` → "Document", các loại code → "Code"). Lưu ý: tệp CSV nhận nhãn "Document" qua cơ chế fallback theo danh mục `text` trong `getFileType()`; nhãn "Spreadsheet" chỉ áp dụng cho các MIME Excel khớp với regex `excelMimeTypes`.
3. FR-3: Nút xóa có mặt trên mỗi chip bất kể trạng thái tải lên. Nếu tệp vẫn đang tải lên (`progress < 1`), nhấp vào xóa sẽ hủy tải lên. Nếu tải lên hoàn thành, yêu cầu xóa server được gửi.
4. FR-4: Các file ID trùng lặp trong danh sách chip được loại bỏ trùng lặp; mỗi `file_id` duy nhất được render một lần.
5. FR-5: Các chip được bố trí theo hàng flex có thể xuống dòng (`gap-4px`, `flexBasis: 70px` mỗi vị trí chip); hình ảnh và tài liệu có thể xuất hiện cùng nhau trong cùng một hàng.

#### Kiểm tra hợp lệ & lỗi
- Nếu lệnh gọi API xóa thất bại, lỗi bị nuốt im lặng ở phía client: `FileRow.tsx` chỉ ghi lỗi vào console (`console.log('Error deleting files:', error)`) và không hiển thị toast hay phản hồi nào cho người dùng khi xóa thất bại.

#### Trường hợp đặc biệt
- Xóa tệp cuối cùng: vùng chip thu gọn; `setFilesLoading(false)` được gọi.
- Tên tệp rất dài: được cắt ngắn bằng CSS `overflow: hidden; text-overflow: ellipsis`; tên đầy đủ có sẵn qua tooltip `title`.
- Nhấp vào thumbnail chip cho tệp vẫn đang tải lên: lightbox không mở (lớp phủ mở rộng chỉ hiển thị khi `progress >= 1`); thay vào đó, cung tiến trình được hiển thị.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử tệp hình ảnh đã được tải lên hoàn toàn, khi người dùng nhấp vào chip hình ảnh, thì lightbox toàn màn hình mở ra hiển thị hình ảnh.
2. AC-2: Giả sử lightbox đang mở, khi người dùng nhấn Escape hoặc nhấp vào nút đóng, thì lightbox đóng lại.
3. AC-3: Giả sử có bất kỳ chip nào, khi người dùng nhấp vào nút xóa (aria-label "Remove file"), thì chip bị xóa khỏi vùng nhập liệu.
4. AC-4: Giả sử tệp vẫn đang tải lên, khi người dùng nhấp vào nút xóa, thì tải lên bị hủy và chip biến mất mà không có lệnh gọi API xóa.
5. AC-5: Giả sử tệp đã được tải lên hoàn toàn, khi người dùng nhấp vào nút xóa, thì toast thông tin màu xanh "Deleting file..." xuất hiện và chip bị xóa.
6. AC-6: Giả sử tệp tài liệu được đính kèm, chip hiển thị tên tệp và nhãn loại (ví dụ: "Document" cho PDF, "Document" cho CSV, "Code" cho các tệp script). Nhãn "Spreadsheet" không xuất hiện cho tệp CSV.

---

### Hình Ảnh (Vision) vs Tài Liệu (Ngữ Cảnh Văn Bản)

#### Mục đích
Làm rõ cách các loại đính kèm khác nhau được mô hình sử dụng và tùy chọn menu tải lên nào cần chọn.

#### Điều kiện tiên quyết / truy cập
- Endpoint Nufi phải được chọn. Hành vi Vision phụ thuộc vào việc mô hình được chọn có hỗ trợ đầu vào đa phương thức hay không (cần xác minh: không phải tất cả mô hình trên endpoint Nufi đều nhất thiết hỗ trợ vision — kiểm tra tài liệu mô hình).

#### Thành phần giao diện
- Tùy chọn **"Upload to Provider"** (`com_ui_upload_provider`) trong menu đính kèm: định tuyến tệp như một đầu vào hình ảnh/tài liệu trực tiếp của nhà cung cấp. Bộ lọc đầu vào tệp được đặt thành `image/*,.heif,.heic,.pdf,application/pdf`.
- Tùy chọn **"Upload as Text"** (`com_ui_upload_ocr_text`): **không khả dụng trên endpoint Nufi** theo cấu hình hiện tại. Tùy chọn này chỉ xuất hiện khi `AgentCapabilities.context` có trong `agents.capabilities`; `librechat.yaml` của Nufi đặt `agents.capabilities: ["file_search"]` — `context` không có trong đó.

#### Hành vi chức năng
1. FR-1: Các tệp được thêm qua "Upload to Provider" được gửi đến mô hình dưới dạng các khối nội dung hình ảnh/tài liệu. Mô hình có thể "nhìn thấy" hình ảnh nếu nó hỗ trợ vision; PDF được truyền dưới dạng nội dung tài liệu.
2. FR-2: Đường "Upload as Text" (OCR/phân tích tài liệu thành tài nguyên công cụ `context`) không khả dụng trên endpoint Nufi theo cấu hình hiện tại. Để bật, cần thêm `context` vào `agents.capabilities` trong `librechat.yaml`.
3. FR-3: Trong `FileRow`, bất kỳ tệp nào có `type` bắt đầu bằng `image/` được render dưới dạng chip `Image` (xem trước thumbnail); tất cả các tệp khác được render dưới dạng `FileContainer` (chip tài liệu).
4. FR-4: Huy hiệu nguồn trên chip phản ánh cách tệp được xử lý (ví dụ: huy hiệu "T" cho các tệp nguồn văn bản).
5. FR-5: Hình ảnh GIF được đính kèm qua "Upload to Provider" được gửi dưới dạng các khung hình tĩnh. (cần xác minh trên sản phẩm đang chạy: hành vi GIF động phụ thuộc vào API nhà cung cấp — mô hình có thể không animate chúng.)

#### Kiểm tra hợp lệ & lỗi
- Đính kèm tệp không phải hình ảnh/PDF qua đường "Upload to Provider": bộ lọc hộp thoại chọn tệp (`image/*,.heif,.heic,.pdf,application/pdf`) hạn chế lựa chọn; nếu bộ lọc bị bỏ qua, kiểm tra MIME trong `validateFiles` sẽ từ chối loại không được hỗ trợ.
- "Upload as Text" không khả dụng trên endpoint Nufi theo cấu hình hiện tại; tình huống bỏ qua nó không áp dụng.

#### Trường hợp đặc biệt
- Tệp `.gif` được tải lên qua "Upload to Provider": được chấp nhận (MIME `image/gif` được hỗ trợ). Được hầu hết các API vision xử lý như hình ảnh tĩnh.
- Tệp `.webp`: được chấp nhận qua "Upload to Provider" (MIME `image/webp` được hỗ trợ).
- Hình ảnh HEIC/HEIF: được chuyển đổi sang JPEG phía client (toast "Converting HEIC image to JPEG..."); JPEG đã chuyển đổi sau đó được tải lên.
- Hình ảnh lớn vượt quá 20 MB trước khi chuyển đổi HEIC: nếu JPEG đã chuyển đổi cũng ≥ 20 MB, nó bị từ chối sau khi chuyển đổi.
- Thay đổi kích thước hình ảnh phía client: `clientImageResize` **bị tắt** trên triển khai Nufi (không có mục `clientImageResize` trong `nufi-chat/librechat.yaml`; giá trị mặc định của LibreChat là `clientImageResize.enabled: false`). Đường code resize và toast "Image resized: X MB → Y MB (Z% smaller)" do đó không hoạt động trên triển khai production Nufi hiện tại.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử mô hình hỗ trợ vision được chọn trên endpoint Nufi, khi người dùng đính kèm hình ảnh PNG qua "Upload to Provider" và gửi tin nhắn, thì mô hình phản hồi với nhận thức về nội dung hình ảnh.
2. AC-2: "Upload as Text" không khả dụng trên endpoint Nufi theo cấu hình hiện tại; tình huống này yêu cầu thêm khả năng `context` vào `agents.capabilities` trong `librechat.yaml`. (cần xác minh trên sản phẩm đang chạy: nếu khả năng `context` được bật sau này, đính kèm PDF qua "Upload as Text" và gửi phải dẫn đến phản hồi của mô hình tham chiếu nội dung tài liệu.)
3. AC-3: Giả sử tệp HEIC được chọn qua "Upload to Provider", thì toast thông tin màu xanh "Converting HEIC image to JPEG..." xuất hiện, và chip tệp hiển thị xem trước JPEG sau khi chuyển đổi.
4. AC-4: Giả sử tệp không phải hình ảnh/PDF (ví dụ: CSV) được đính kèm qua "Upload to Provider" (nếu bộ lọc hộp thoại chọn tệp của hệ điều hành bị bỏ qua), thì quá trình kiểm tra hợp lệ từ chối tệp với "Unsupported file type: text/csv".

---

### Kiểm Tra Hợp Lệ & Xử Lý Lỗi

#### Mục đích
Mô tả đầy đủ pipeline kiểm tra hợp lệ phía client và hành vi lỗi chính xác cho từng điều kiện thất bại.

#### Điều kiện tiên quyết / truy cập
- Được kích hoạt trên mỗi lần chọn tệp (nút, kéo-thả, dán) trước khi bắt đầu tải lên.

#### Thành phần giao diện
- Tất cả lỗi kiểm tra hợp lệ được hiển thị dưới dạng toast thông báo màu đỏ (trạng thái `'error'`, thời gian 5000 ms).
- Nhiều lỗi được loại bỏ trùng lặp và, nếu có nhiều hơn một, hiển thị dưới dạng danh sách dấu đầu dòng trong một toast đơn.
- Thông báo lỗi được render qua hệ thống bản địa hóa.

#### Hành vi chức năng
Kiểm tra hợp lệ được thực hiện bởi `validateFiles()` theo thứ tự liệt kê bên dưới. Pipeline trả về `false` khi gặp lần kiểm tra thất bại đầu tiên (ngoại trừ kiểm tra MIME và kích thước lặp qua danh sách tệp):

1. FR-1 (Endpoint bị vô hiệu hóa): Nếu `endpointFileConfig.disabled === true`, từ chối với `com_ui_attach_error_disabled`.
2. FR-2 (Tệp rỗng): Nếu tổng kích thước byte của tất cả tệp đến là `0`, từ chối với `com_error_files_empty`.
3. FR-3 (Số lượng tệp): Nếu `(số tệp hiện có) + (số tệp đến) > fileLimit (5)`, từ chối với chuỗi ký tự `"File limit reached: 5 files"`.
4. FR-4 (Loại MIME, mỗi tệp): Đối với mỗi tệp đến, nếu loại MIME (sau khi suy luận từ phần mở rộng) không khớp với bất kỳ mẫu nào trong `supportedMimeTypes`, từ chối với `"Unsupported file type: <mime>"`. Nếu MIME không thể xác định, từ chối với `"Unable to determine file type for: <filename>"`.
5. FR-5 (Kích thước mỗi tệp): Đối với mỗi tệp đến, nếu `file.size >= fileSizeLimit (20 MB)`, từ chối với `"File size limit exceeded: 20 MB"`. (Ranh giới là bao gồm — đúng 20 MB bị từ chối.)
6. FR-6 (Tổng kích thước): Sau kiểm tra mỗi tệp, nếu `(tổng kích thước hiện có) + (tổng kích thước đến) > totalSizeLimit (50 MB)`, từ chối với `"Total file size limit exceeded: 50 MB"`.
7. FR-7 (Phát hiện trùng lặp): Nếu bất kỳ kết hợp nào của `name + size + type_category` khớp với một tệp đã đính kèm, từ chối với `com_error_files_dupe` → "Duplicate file detected."

> Lưu ý về nguồn thông báo lỗi: Hàm `validateFiles` tạo ra các thông báo về số lượng tệp, MIME, kích thước và tổng kích thước dưới dạng chuỗi thô (không qua khóa i18n). Các khóa `com_ui_attach_error_limit`, `com_ui_attach_error_type`, `com_ui_attach_error_size` và `com_ui_attach_error_total_size` tồn tại trong tệp dịch nhưng hiện được sử dụng trong các đường code riêng biệt (ví dụ: relay lỗi phía server cũ hơn). Đối với kiểm tra hợp lệ phía client của endpoint Nufi, các thông báo hiển thị là các chuỗi thô được liệt kê trong FR-3 đến FR-6 ở trên. (cần xác minh: xác nhận văn bản toast chính xác trong giao diện đã triển khai cho từng trường hợp lỗi.)

#### Kiểm tra hợp lệ & lỗi (thông báo chính xác)

| Điều kiện | Thông báo toast |
|---|---|
| Endpoint bị vô hiệu hóa | "File uploads are disabled for this endpoint" |
| Tệp rỗng (0 byte) | "Empty files are not allowed." |
| Số lượng vượt quá 5 | "File limit reached: 5 files" |
| Loại MIME không được hỗ trợ | "Unsupported file type: `<mime>`" |
| Không thể suy luận MIME | "Unable to determine file type for: `<filename>`" |
| Tệp ≥ 20 MB | "File size limit exceeded: 20 MB" |
| Tổng > 50 MB | "Total file size limit exceeded: 50 MB" |
| Tệp trùng lặp | "Duplicate file detected." |
| Lỗi mạng khi tải lên | "An error occurred while uploading the file." |
| Tải lên bị hủy | "The file upload request was canceled. Note: the file upload may still be processing and will need to be manually deleted." |
| Lỗi chuyển đổi HEIC | "Failed to convert HEIC image to JPEG. Please try converting the image manually or use a different format." |
| Lỗi xử lý chung | "An error occurred while processing the file." |
| Ngoại lệ kiểm tra hợp lệ | "An error occurred while validating the file." |

#### Trường hợp đặc biệt
- Đính kèm 4 tệp rồi đính kèm thêm 2 tệp cùng lúc: kiểm tra số lượng tính `4 (hiện có) + 2 (đến) = 6 > 5`; toàn bộ batch bị từ chối trước khi bất kỳ tải lên nào bắt đầu.
- Thêm tệp từng cái một đến giới hạn: thêm tệp thứ 5 được cho phép; thêm tệp thứ 6 kích hoạt lỗi số lượng.
- Hai tệp có cùng tên, kích thước và loại trong cùng một batch chọn: kiểm tra trùng lặp bao gồm cả tệp hiện có và tệp đến; bản sao thứ hai kích hoạt "Duplicate file detected."
- Server trả về thông báo lỗi tùy chỉnh trong `response.data.message`: thông báo đó được sử dụng trực tiếp trong toast lỗi thay vì lỗi tải lên chung.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử đã đính kèm 5 tệp, khi người dùng cố đính kèm tệp thứ 6, thì toast đỏ "File limit reached: 5 files" xuất hiện và tệp thứ 6 không được thêm vào.
2. AC-2: Giả sử người dùng đính kèm PDF 20 MB, thì toast đỏ "File size limit exceeded: 20 MB" xuất hiện và không có chip nào được thêm vào.
3. AC-3: Giả sử người dùng đính kèm PDF 19,99 MB, thì tệp được chấp nhận và tải lên bắt đầu.
4. AC-4: Giả sử tổng kích thước đính kèm là 45 MB, khi người dùng đính kèm tệp 6 MB, thì toast đỏ "Total file size limit exceeded: 50 MB" xuất hiện.
5. AC-5: Giả sử người dùng đính kèm tệp âm thanh `.mp3`, thì toast đỏ "Unsupported file type: audio/mpeg" xuất hiện.
6. AC-6: Giả sử người dùng đính kèm cùng một tệp hai lần (cùng tên, kích thước và loại), thì toast đỏ "Duplicate file detected." xuất hiện lần thứ hai.
7. AC-7: Giả sử nhiều lỗi kiểm tra hợp lệ xảy ra (ví dụ: hai tệp không được hỗ trợ trong một lần thả), thì một toast đơn với danh sách dấu đầu dòng các lỗi xuất hiện.

---

### Mối Quan Hệ với Agent Knowledge

#### Mục đích
Làm rõ sự khác biệt giữa đính kèm tệp theo tin nhắn (phần này) và Agent Knowledge lâu dài (RAG qua file search / vector store), để người kiểm thử và người dùng cuối chọn đúng cơ chế.

#### Điều kiện tiên quyết / truy cập
- Cả hai tính năng có thể đồng thời khả dụng khi endpoint Nufi được sử dụng với Agent có File Search được bật.

#### Thành phần giao diện
- **Đính kèm theo tin nhắn** (phần này): tệp được đính kèm qua nút Attach Files trong thanh nhập liệu cuộc trò chuyện. Chúng hiển thị dưới dạng chip giữa vùng nhập văn bản và nút gửi. Chúng có phạm vi theo cuộc hội thoại.
- **Agent Knowledge / File Search**: tệp được tải lên qua bảng cấu hình Agent (Side Panel → Agents → phần File Search). Chúng được lưu trữ trong vector store và tồn tại qua tất cả các cuộc hội thoại sử dụng agent đó. Đây là RAG — agent truy xuất các đoạn liên quan từ các tệp này theo yêu cầu.

#### Hành vi chức năng
1. FR-1: Đính kèm theo tin nhắn được gửi đến mô hình một lần, như một phần của tin nhắn cụ thể mà nó được đính kèm. Nó không được lưu trữ cho các cuộc hội thoại trong tương lai hoặc có thể được truy xuất bởi mô hình trong các tin nhắn sau.
2. FR-2: Các tệp Agent Knowledge được lập chỉ mục vào vector store. Agent tự động truy xuất các đoạn liên quan qua tất cả các cuộc hội thoại.
3. FR-3: Khi menu Attach đang mở, tùy chọn "Upload for File Search" (`com_ui_upload_file_search`) — nếu được hiển thị — định tuyến tệp đến vector store file search của Agent (lâu dài, RAG). Đây không phải là đính kèm theo tin nhắn.
4. FR-4: "Upload to Provider" trong menu đính kèm là đính kèm theo tin nhắn (phạm vi theo cuộc hội thoại). "Upload as Text" không khả dụng trên endpoint Nufi theo cấu hình hiện tại.
5. FR-5: Một tin nhắn có thể bao gồm cả đính kèm theo tin nhắn và hưởng lợi từ Agent Knowledge đồng thời; hai cơ chế không xung đột nhau.

#### Khi nào dùng cơ chế nào
| Mục tiêu | Dùng |
|---|---|
| Chia sẻ tài liệu hoặc hình ảnh một lần cho một câu hỏi duy nhất | Đính kèm theo tin nhắn (phần này) |
| Cung cấp cho agent tài liệu tham khảo lâu dài để truy xuất qua tất cả các cuộc hội thoại | Agent Knowledge (File Search trong bảng cấu hình Agent) |
| Vision: để mô hình mô tả hoặc phân tích hình ảnh | Đính kèm theo tin nhắn qua "Upload to Provider" |
| Trích xuất văn bản từ PDF hoặc hình ảnh cho một tin nhắn | Đính kèm theo tin nhắn qua "Upload as Text" (yêu cầu khả năng `context` — không được bật mặc định trên Nufi) |

#### Kiểm tra hợp lệ & lỗi
- Các tệp được tải lên qua "Upload for File Search" từ menu đính kèm tin nhắn phải tuân theo cùng kiểm tra MIME và kích thước mỗi tệp, nhưng đích đến của chúng là vector store thay vì tin nhắn. Lỗi kiểm tra hợp lệ xuất hiện dưới dạng toast đỏ.

#### Trường hợp đặc biệt
- Nếu một Agent có File Search bị vô hiệu hóa, tùy chọn "Upload for File Search" không xuất hiện trong menu thả xuống đính kèm hoặc hộp thoại kéo-thả.
- Xóa đính kèm theo tin nhắn chỉ xóa nó khỏi bản nháp tin nhắn hiện tại; không ảnh hưởng đến các tệp Agent Knowledge.

#### Tiêu chí chấp nhận
1. AC-1: Giả sử tệp được đính kèm vào tin nhắn qua "Upload to Provider", khi tin nhắn được gửi, thì tệp hiển thị trong lịch sử cuộc hội thoại chỉ cho tin nhắn đó và không khả dụng trong các tin nhắn tiếp theo.
2. AC-2: Giả sử tệp được tải lên cơ sở kiến thức File Search của Agent, thì nó khả dụng như ngữ cảnh trong tất cả các cuộc hội thoại trong tương lai với agent đó, độc lập với đính kèm theo tin nhắn.
3. AC-3: Giả sử Agent không có File Search được bật, khi người dùng mở menu thả xuống đính kèm, thì "Upload for File Search" không hiển thị trong menu.
