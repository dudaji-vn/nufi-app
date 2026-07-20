## Quản lý Hội thoại & Thanh bên (Sidebar)

Phần này mô tả các tính năng cho phép người dùng tạo, tìm kiếm, điều hướng, tổ chức và xuất hội thoại trong NuFi Chat. Tất cả các tính năng được ghi lại ở đây áp dụng cho bản triển khai NuFi Chat với các cờ cấu hình sau được bật: `sidePanel`, `bookmarks`, `multiConvo`, `temporaryChat`, và `sharedLinksEnabled`. Tính năng tìm kiếm qua Meilisearch (`search.enabled`) được bật khi dịch vụ Meilisearch đang chạy.

---

### Danh sách Hội thoại & Điều hướng (Sidebar)

**Mục đích:** Hiển thị lịch sử hội thoại đã lưu của người dùng trong một thanh bên trái cố định và cho phép điều hướng giữa các hội thoại.

**Điều kiện tiên quyết / truy cập:** Người dùng đã xác thực. Thanh bên đang ở trạng thái mở rộng (`sidebarExpanded = true` trong local storage).

**Thành phần giao diện:**
- Panel thanh bên trái được gán nhãn `"Chat History"` (`com_ui_chat_history`), được render với `role="region"`.
- Danh sách có thể cuộn được ảo hóa (`aria-label="Conversations"`, `containerRole="rowgroup"`, xây dựng bằng `react-virtualized`).
- Thanh tiêu đề phần **"Chats"** có thể thu gọn (`com_ui_chats`) với biểu tượng `ChevronDown` xoay khi mở rộng; trạng thái thu gọn được lưu trong local storage với key `chatsExpanded`.
- Nhãn nhóm theo ngày: **Today**, **Yesterday**, **Previous 7 Days**, **Previous 30 Days**, tiếp theo là tên tháng (ví dụ: **January**), rồi năm đơn thuần (ví dụ: `2024`). Mỗi nhóm là một thẻ `<h2>` với `aria-label` thông báo phần ngày tháng.
- Các hàng hội thoại riêng lẻ (`data-testid="convo-item"`, `role="button"`) hiển thị biểu tượng endpoint (hoặc vòng quay tải khi đang tạo nội dung) và tiêu đề hội thoại.
- Hội thoại đang hoạt động được làm nổi bật bằng thanh màu chính ở bên trái (`before:bg-primary`) và nền `bg-surface-active-alt`; thuộc tính `aria-current="page"` được đặt trên liên kết bên trong.
- Khi di chuột hoặc focus, nút tùy chọn `Ellipsis` (ba chấm) (`aria-label="com_nav_convo_menu_options"`) xuất hiện ở bên phải.
- Phần **Favorites** được render phía trên thanh tiêu đề Chats khi có mục yêu thích hoặc khi Agent Marketplace được bật (ẩn trong khi tìm kiếm).
- Nút NavToggle ở cạnh thanh bên (hai thanh có hiệu ứng hoạt hình, `aria-controls="chat-history-nav"`) dùng để thu gọn/mở rộng thanh bên.

**Hành vi chức năng:**
1. FR-1: Khi tải lần đầu, thanh bên tải danh sách hội thoại thông qua `useConversationsInfiniteQuery`, được nhóm và sắp xếp theo `updatedAt` giảm dần trong mỗi nhóm ngày.
2. FR-2: Các hội thoại được nhóm vào các nhóm ngày được liệt kê trong bản đồ `dateKeys` (`com_ui_date_today`, `com_ui_date_yesterday`, `com_ui_date_previous_7_days`, `com_ui_date_previous_30_days`, tiếp theo là tháng, rồi năm).
3. FR-3: Khi người dùng cuộn đến trong phạm vi 8 hàng tính từ cuối danh sách đang render, `loadMoreConversations` được gọi (throttle 300 ms) và tải thêm một trang. Biểu tượng vòng tải (`com_ui_loading`) được thêm vào cuối danh sách trong khi tải.
4. FR-4: Nhấp vào một hàng hội thoại sẽ điều hướng đến `/c/{conversationId}` và cập nhật `document.title` thành tiêu đề hội thoại. Trên mobile (`max-width: 768px`), thanh bên tự động thu gọn sau khi điều hướng.
5. FR-5: Nhấn `Ctrl`/`Cmd` + nhấp chuột vào một hàng hội thoại sẽ mở hội thoại đó trong tab trình duyệt mới.
6. FR-6: Hàng hội thoại đang hoạt động được xác định bằng cách so khớp tham số URL `conversationId`; nếu URL là `/c/new`, hội thoại tại Recoil index 0 (`activeConvos[0]` từ `allConversationsSelector`) sẽ được làm nổi bật thay thế. Đây là mục đầu tiên trong slot hội thoại Recoil hiện tại, không nhất thiết là hội thoại được truy cập gần nhất theo lịch sử điều hướng trình duyệt. Nếu chưa có hội thoại nào được mở trong phiên hiện tại, hàng được làm nổi bật có thể không xuất hiện.
7. FR-7: Thu gọn thanh tiêu đề Chats sẽ ẩn tất cả các nhóm ngày và hàng hội thoại nhưng vẫn giữ phần Favorites hiển thị.
8. FR-8: Mỗi hàng hội thoại render biểu tượng SVG đang quay (`aria-label="com_ui_generating"`) thay cho biểu tượng endpoint khi một tác vụ tạo nội dung AI đang hoạt động cho hội thoại đó (tập hợp `activeJobIds`).
9. FR-9: Nút NavToggle bật/tắt `sidebarExpanded` trong local storage. Bản thân nút NavToggle trượt theo `translate-x-[260px]` khi thanh bên hiển thị. Trên mobile, vùng chat dịch chuyển với `translateX(min(85vw, 380px))` để nhường chỗ cho overlay thanh bên; trên desktop, thanh bên luôn nằm trong luồng layout và không áp dụng hiệu ứng translate cho vùng chat.
10. FR-10: Trên mobile, thanh bên phủ lên vùng chat; trên desktop, thanh bên hiển thị song song.

**Trạng thái & trường hợp đặc biệt:**
- **Lịch sử trống:** Không có nhóm ngày hay hàng hội thoại nào được render; chỉ hiển thị thanh tiêu đề Chats và (nếu có) các mục Favorites/Marketplace.
- **Tất cả hội thoại trong một nhóm:** Chỉ hiển thị một thanh tiêu đề nhóm ngày.
- **Tìm kiếm đang hoạt động:** Phần Favorites bị ẩn; danh sách hội thoại được thay thế bằng kết quả tìm kiếm (xem phần Tìm kiếm).
- **Thanh bên thu gọn:** NavToggle hiển thị ở `translate-x-0`; nhấp vào để mở lại thanh bên.
- **Lỗi mạng khi tải:** (cần xác minh: cách render trạng thái lỗi — query client có thể hiển thị dữ liệu cũ hoặc danh sách trống).

**Tiêu chí chấp nhận:**
- AC-1: Giả sử người dùng đã xác thực có 10 hội thoại đã lưu, khi thanh bên tải xong, thì tất cả 10 hội thoại xuất hiện được nhóm theo nhãn ngày phù hợp, sắp xếp mới nhất trước trong mỗi nhóm.
- AC-2: Giả sử danh sách được cuộn đến trong phạm vi 8 hàng tính từ cuối và `hasNextPage` là true, khi sự kiện cuộn kích hoạt, thì một trang hội thoại bổ sung được tải và thêm vào mà không render lại toàn bộ các hàng hiện có.
- AC-3: Giả sử người dùng nhấp vào một hàng hội thoại không phải hội thoại hiện tại, khi click được xử lý, thì URL thay đổi thành `/c/{conversationId}` và hàng đó nhận kiểu nổi bật đang hoạt động.
- AC-4: Giả sử người dùng giữ `Ctrl` (Windows/Linux) hoặc `Cmd` (Mac) và nhấp vào một hàng, khi click kích hoạt, thì hội thoại mở trong tab trình duyệt mới và thanh bên đóng lại trên mobile.
- AC-5: Giả sử nút thu gọn thanh tiêu đề Chats được nhấp, khi bật/tắt, thì tất cả các hàng hội thoại biến mất và trạng thái thu gọn được lưu qua lần tải lại trang.

---

### Hội thoại Mới

**Mục đích:** Bắt đầu một hội thoại mới và xóa mọi ngữ cảnh tin nhắn đang hoạt động.

**Điều kiện tiên quyết / truy cập:** Người dùng đã xác thực. Nút hiển thị trong vùng tiêu đề thanh bên.

**Thành phần giao diện:**
- Nút biểu tượng (`data-testid="new-chat-button"`, `aria-label="com_ui_new_chat"`) được render với `NewChatIcon`, kiểu dáng `size-9 rounded-xl`; ẩn trên mobile (`max-md:hidden`).
- Tooltip hiển thị `com_ui_new_chat` khi di chuột vào.
- Trên mobile, nút `NewChat` bị ẩn qua `max-md:hidden`. Không có mục "New Chat" riêng biệt dành cho mobile. Người dùng mobile mở thanh bên qua nút `OpenSidebar` trong tiêu đề chat (`md:hidden`) rồi điều hướng; để bắt đầu hội thoại mới trên mobile, người dùng điều hướng đến `/c/new` qua URL.

**Hành vi chức năng:**
1. FR-1: Nhấp vào nút New Chat sẽ gọi `clearMessagesCache`, vô hiệu hóa query tin nhắn, gọi `newConversation()` để reset trạng thái hội thoại, và điều hướng đến `/c/new`.
2. FR-2: Nhấn `Ctrl`/`Cmd` + nhấp sẽ mở tab trình duyệt mới tại `/c/new` mà không thay đổi tab hiện tại.
3. FR-3: Hội thoại mới chưa được lưu vào cơ sở dữ liệu cho đến khi tin nhắn đầu tiên được gửi.

**Trạng thái & trường hợp đặc biệt:**
- **Đã ở `/c/new`:** Nhấp New Chat thêm lần nữa không gây hại; trạng thái được reset nhưng không có điều hướng trùng lặp.
- **Đang tạo nội dung:** Nút vẫn có thể nhấp; nhấp vào sẽ bắt đầu ngữ cảnh hội thoại mới nhưng không hủy tác vụ tạo nội dung đang chạy của hội thoại trước.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử đang mở bất kỳ hội thoại nào, khi người dùng nhấp "New Chat", thì URL thay đổi thành `/c/new` và vùng chat được xóa trắng.
- AC-2: Giả sử người dùng giữ `Ctrl`/`Cmd` và nhấp "New Chat", khi click kích hoạt, thì một tab mới mở tại `/c/new` và tab hiện tại không thay đổi.

---

### Tìm kiếm Hội thoại

**Mục đích:** Tìm hội thoại theo từ khóa trong tiêu đề và nội dung tin nhắn bằng Meilisearch.

**Điều kiện tiên quyết / truy cập:** `search.enabled` là `true` (dịch vụ Meilisearch đang chạy). Người dùng đã xác thực. Thanh tìm kiếm được render trong thanh bên.

**Thành phần giao diện:**
- Ô nhập tìm kiếm (`aria-label="com_nav_search_placeholder"`, placeholder `com_nav_search_placeholder`) bên trong container với biểu tượng `Search` (trái) và nút xóa (`X`) (phải, `aria-label="com_ui_clear_search"`).
- Nút xóa bị ẩn (`opacity-0`) khi ô nhập trống.
- Biểu tượng vòng tải hiển thị trong vùng danh sách hội thoại khi `isSearchLoading` là true.

**Hành vi chức năng:**
1. FR-1: Khi người dùng gõ, truy vấn được lưu ngay vào trạng thái Recoil (`search.query`), và bản sao debounced (`search.debouncedQuery`) được đặt sau 500 ms với `isTyping` được xóa.
2. FR-2: Khi `debouncedQuery` không rỗng, `useConversationsInfiniteQuery` được gọi với `search: debouncedQuery`, thay thế danh sách hội thoại thông thường.
3. FR-3: Trong khi đang gõ (trước khi debounce kích hoạt), danh sách hiển thị biểu tượng vòng tải (`isSearchLoading = true`).
4. FR-4: URL thay đổi thành `/search` ngay khi có truy vấn không rỗng được nhập.
5. FR-5: Nhấp nút xóa (`X`) hoặc nhấn `Backspace` khi ô nhập trống sẽ xóa `search.query` và `search.debouncedQuery`, ẩn kết quả tìm kiếm, điều hướng về `/c/new` nếu đang ở `/search`, và focus lại vào ô nhập.
6. FR-6: Phần Favorites bị ẩn khi có truy vấn tìm kiếm đang hoạt động.
7. FR-7: Kết quả tìm kiếm được render trong cùng danh sách hội thoại ảo hóa với cùng cấu trúc nhóm ngày. Trong kết quả, các hội thoại vẫn được nhóm theo ngày `updatedAt`.

**Trạng thái & trường hợp đặc biệt:**
- **Không có kết quả:** Danh sách hội thoại trống; không có nhóm ngày nào được render. Chỉ tiêu đề Chats còn hiển thị. Không có thành phần thông báo trạng thái "Không có kết quả" nào được render — vùng danh sách đơn giản là trống bên dưới tiêu đề.
- **Meilisearch không khả dụng:** Ô tìm kiếm bị ẩn (`search.enabled = false`); danh sách dựa trên phân trang thông thường được hiển thị.
- **Truy vấn một ký tự:** Debounce vẫn áp dụng; Meilisearch thực hiện tìm kiếm tiền tố.
- **Ký tự đặc biệt:** Truy vấn được truyền dưới dạng chuỗi thô đến Meilisearch (không có `encodeURIComponent` trên đường dẫn tìm kiếm thanh bên chính). URL tìm kiếm thanh bên không mang tham số truy vấn nào để encode — chỉ điều hướng đến `/search`. Truy vấn con archived-chats có encode tham số của nó. Render JSX của React ngăn XSS phía client; việc sanitize phía máy chủ xử lý giá trị truy vấn.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử người dùng gõ "invoice" vào thanh tìm kiếm, khi 500 ms trôi qua, thì danh sách hội thoại cập nhật để chỉ hiển thị các hội thoại khớp với "invoice" và URL là `/search`.
- AC-2: Giả sử kết quả tìm kiếm đang hiển thị, khi người dùng nhấp nút xóa `X`, thì truy vấn được xóa, danh sách hội thoại thông thường được khôi phục, và focus trở về ô tìm kiếm.
- AC-3: Giả sử truy vấn không khớp với hội thoại nào, khi kết quả tải xong, thì danh sách hội thoại trống và không có thông báo lỗi nào hiển thị trong vùng danh sách.

---

### Đổi tên Hội thoại

**Mục đích:** Cho phép người dùng đặt tiêu đề tùy chỉnh cho một hội thoại.

**Điều kiện tiên quyết / truy cập:** Người dùng đã xác thực và sở hữu hội thoại.

**Thành phần giao diện:**
- Mục menu **Rename** (nhãn `com_ui_rename`, biểu tượng `Pen`) trong dropdown `ConvoOptions` ba chấm của hội thoại.
- Trên desktop, nhấp đúp vào văn bản tiêu đề hội thoại cũng kích hoạt đổi tên (bị tắt trên màn hình nhỏ).
- Form đổi tên nội tuyến (`role="form"`, `aria-label="com_ui_rename_conversation"`) phủ lên hàng hội thoại: một ô nhập văn bản (`aria-label="com_ui_new_conversation_title"`, `maxLength={100}`) được điền sẵn tiêu đề hiện tại, nút hủy (biểu tượng `X`, `aria-label="com_ui_cancel"`), và nút lưu (biểu tượng `Check`, `aria-label="com_ui_save"`).

**Hành vi chức năng:**
1. FR-1: Khi chế độ đổi tên được kích hoạt, ô nhập tự động được focus và văn bản hiện có được chọn toàn bộ.
2. FR-2: Nhấn `Enter` xác nhận tiêu đề mới; nhấn `Escape` hủy mà không lưu.
3. FR-3: Khi xác nhận, `useUpdateConversationMutation` được gọi với `{ conversationId, title: newTitle.trim() || 'Untitled' }`. Nhãn dự phòng là `com_ui_untitled`.
4. FR-4: Nếu tiêu đề được xác nhận giống với tiêu đề hiện tại, yêu cầu đổi tên bị bỏ qua và form đóng lại.
5. FR-5: Khi API thành công, giao diện cập nhật nội tuyến. Khi thất bại, thông báo toast xuất hiện với `com_ui_rename_failed` và tiêu đề gốc được khôi phục trong ô nhập.
6. FR-6: Trường tiêu đề bị giới hạn tối đa 100 ký tự (được kiểm soát bởi `maxLength`).

**Trạng thái & trường hợp đặc biệt:**
- **Xác nhận rỗng:** Tiêu đề được đặt thành `com_ui_untitled` (tức là sau khi trim cho chuỗi rỗng).
- **Đổi tên trong khi đang tạo nội dung:** Đổi tên có thể được khởi tạo; không làm gián đoạn quá trình tạo nội dung.
- **Lỗi mạng:** Toast lỗi hiển thị; ô nhập khôi phục về tiêu đề gốc và form đóng lại.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử chế độ đổi tên đang hoạt động, khi người dùng nhập tiêu đề mới và nhấn `Enter`, thì tiêu đề hội thoại cập nhật trong thanh bên và form đổi tên đóng lại.
- AC-2: Giả sử chế độ đổi tên đang hoạt động, khi người dùng nhấn `Escape`, thì form đóng lại và tiêu đề không thay đổi.
- AC-3: Giả sử người dùng xác nhận chuỗi rỗng (toàn khoảng trắng), khi lưu, thì tiêu đề được đặt thành "Untitled" (được bản địa hóa `com_ui_untitled`).
- AC-4: Giả sử lệnh gọi API thất bại, khi lỗi được trả về, thì toast với `com_ui_rename_failed` xuất hiện và thanh bên hiển thị tiêu đề gốc.

---

### Xóa Hội thoại

**Mục đích:** Xóa vĩnh viễn một hội thoại và tất cả tin nhắn của nó khỏi máy chủ.

**Điều kiện tiên quyết / truy cập:** Người dùng đã xác thực và sở hữu hội thoại.

**Thành phần giao diện:**
- Mục menu **Delete** (nhãn `com_ui_delete`, biểu tượng `Trash`) trong dropdown `ConvoOptions` (`ariaHasPopup="dialog"`, `ariaControls="delete-conversation-dialog"`).
- Hộp thoại xác nhận (`OGDialog`): tiêu đề `com_ui_delete_conversation`, nội dung hiển thị `com_ui_delete_confirm_strong` với tiêu đề hội thoại được in đậm, nút **Cancel** (`variant="outline"`, `aria-label="cancel"`), và nút **Delete** (`variant="destructive"`).
- **Phím tắt Shift:** Khi hàng hội thoại **đang hoạt động** (được làm nổi bật) có phím `Shift` được giữ, menu ba chấm của hàng đó được thay thế bởi các nút biểu tượng **Archive** và **Delete** trực tiếp; nhấp Delete trong chế độ này bỏ qua hộp thoại và xóa ngay lập tức. Phím tắt chỉ hoạt động trên hàng hội thoại hiện đang hoạt động (`isActiveConvo === true`), không hoạt động trên các hàng khác đang được di chuột qua.

**Hành vi chức năng:**
1. FR-1: Nhấp **Delete** trong menu ba chấm sẽ mở hộp thoại xác nhận mà không thực hiện bất kỳ hành động nào.
2. FR-2: Trong hộp thoại xác nhận, nhấp **Delete** sẽ gọi `useDeleteConversationMutation` với `{ conversationId, thread_id, endpoint, source: 'button' }`.
3. FR-3: Khi thành công: hộp thoại đóng lại, hội thoại bị xóa khỏi danh sách, toast thành công (`com_ui_convo_delete_success`) được hiển thị, và nếu hội thoại bị xóa là hội thoại đang hoạt động thì người dùng được điều hướng đến `/c/new`.
4. FR-4: Khi lỗi: toast lỗi (`com_ui_convo_delete_error`) được hiển thị.
5. FR-5: Đường dẫn xóa tức thì bằng phím tắt Shift (FR trong `handleInstantDelete`) cũng gọi `deleteMutation.mutate` nhưng bỏ qua hộp thoại.
6. FR-6: Nút Delete trong hộp thoại hiển thị `Spinner` khi `deleteMutation.isLoading` là true và bị `disabled`.

**Trạng thái & trường hợp đặc biệt:**
- **Xóa hội thoại duy nhất:** Sau khi xóa, danh sách trống; người dùng chuyển đến `/c/new`.
- **Xóa hội thoại đang được tạo nội dung:** Việc xóa vẫn tiến hành; yêu cầu đang chạy có thể vẫn hoàn thành phía máy chủ (cần xác minh thủ công trên sản phẩm đang chạy: liệu máy chủ có hủy luồng SSE cho hội thoại bị xóa hay không).
- **Hộp thoại bị đóng qua Cancel hoặc backdrop:** Không có xóa nào xảy ra.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử người dùng chọn "Delete" từ menu ba chấm, khi hộp thoại xuất hiện, thì chưa có xóa nào xảy ra và hội thoại vẫn còn trong danh sách.
- AC-2: Giả sử hộp thoại xác nhận đang mở và người dùng nhấp nút "Delete", khi lệnh gọi API thành công, thì hội thoại biến mất khỏi danh sách và toast thành công được hiển thị.
- AC-3: Giả sử hội thoại đang xem bị xóa, khi xóa thành công, thì trình duyệt điều hướng đến `/c/new`.
- AC-4: Giả sử người dùng nhấp Cancel trong hộp thoại, khi đóng, thì hội thoại vẫn còn và danh sách không thay đổi.

---

### Lưu trữ / Hủy lưu trữ Hội thoại

**Mục đích:** Chuyển hội thoại ra khỏi danh sách hoạt động mà không xóa vĩnh viễn; có thể khôi phục lại sau.

**Điều kiện tiên quyết / truy cập:** Người dùng đã xác thực và sở hữu hội thoại.

**Thành phần giao diện:**
- Mục menu **Archive** (nhãn `com_ui_archive`, biểu tượng `Archive`) trong dropdown `ConvoOptions`.
- Phím tắt Shift: khi giữ `Shift` trên hội thoại đang hoạt động, nút biểu tượng **Archive** được hiển thị trực tiếp (tương tự đường dẫn phím tắt Delete).
- Phần **Settings > General > Archived Chats** (nhãn `com_nav_archived_chats`) với nút **Manage** mở hộp thoại archived chats.
- Hộp thoại archived chats: `DataTable` với các cột **Name** (có thể sắp xếp), **Created At** (có thể sắp xếp), và **Actions** (Hủy lưu trữ biểu tượng `ArchiveRestore`, Xóa biểu tượng `TrashIcon`). Ô tìm kiếm/lọc có sẵn trong tiêu đề bảng.
- Vùng live-region dành cho trình đọc màn hình thông báo `com_ui_convo_archived` sau khi lưu trữ.

**Hành vi chức năng:**
1. FR-1: Nhấp **Archive** sẽ gọi `useArchiveConvoMutation` với `{ conversationId, isArchived: true }`.
2. FR-2: Khi thành công: hội thoại bị xóa khỏi danh sách thanh bên hoạt động; nếu đây là hội thoại đang hoạt động thì người dùng được điều hướng đến `/c/new`; thông báo trình đọc màn hình `com_ui_convo_archived` kích hoạt trong 10 giây; popover tùy chọn đóng lại.
3. FR-3: Khi lỗi: toast (`com_ui_archive_error`) được hiển thị.
4. FR-4: Trong bảng Archived Chats, nhấp biểu tượng `ArchiveRestore` sẽ gọi `useArchiveConvoMutation` với `{ conversationId, isArchived: false }`, đưa hội thoại trở lại danh sách hoạt động.
5. FR-5: Bảng archived chats hỗ trợ sắp xếp theo Name và Created At (tăng dần/giảm dần); sắp xếp mặc định là `createdAt` giảm dần.
6. FR-6: Cuộn vô hạn được sử dụng trong bảng archived chats (`fetchNextPage` khi `hasNextPage`).
7. FR-7: **Ô Name/tiêu đề** của mỗi hàng chứa biểu tượng `ExternalLink` nội tuyến; nhấp vào tiêu đề hội thoại (hoặc biểu tượng) sẽ mở nó trong tab trình duyệt mới. Biểu tượng `ExternalLink` được nhúng trong ô tiêu đề, không phải nút độc lập trong cột Actions. Cột Actions chỉ chứa nút Hủy lưu trữ (`ArchiveRestore`) và Xóa (`TrashIcon`).

**Trạng thái & trường hợp đặc biệt:**
- **Không có hội thoại đã lưu trữ:** Bảng trống; chỉ hiển thị tiêu đề cột. Không có thành phần thông báo trạng thái rỗng tùy chỉnh nào được render.
- **Lưu trữ hội thoại hoạt động duy nhất:** Danh sách hoạt động trở nên trống; người dùng điều hướng đến `/c/new`.
- **Hủy lưu trữ khôi phục hội thoại:** Hội thoại xuất hiện lại trong thanh bên hoạt động dưới nhóm ngày chính xác sau lần làm mới query tiếp theo.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử người dùng chọn "Archive" từ menu ba chấm, khi API thành công, thì hội thoại biến mất khỏi danh sách thanh bên hoạt động và xuất hiện trong bảng Archived Chats.
- AC-2: Giả sử một hội thoại đã lưu trữ đang hiển thị trong bảng Archived Chats, khi người dùng nhấp biểu tượng Unarchive, thì hội thoại bị xóa khỏi bảng và xuất hiện lại trong thanh bên hoạt động.
- AC-3: Giả sử hội thoại đã lưu trữ là hội thoại đang xem, khi lưu trữ, thì URL thay đổi thành `/c/new`.

---

### Bookmarks / Tags

**Mục đích:** Cho phép người dùng tạo các nhãn bookmark có tên, gán chúng cho các hội thoại, và lọc danh sách hội thoại theo một hoặc nhiều nhãn.

**Điều kiện tiên quyết / truy cập:** Tính năng `bookmarks` được bật (`PermissionTypes.BOOKMARKS`, `Permissions.USE` được cấp). Người dùng đã xác thực với một hội thoại đang hoạt động (không phải new, không phải search).

**Thành phần giao diện:**
- Dropdown **BookmarkNav** trong thanh công cụ thanh bên: nút toggle `BookmarkIcon`/`BookmarkFilledIcon` (`data-testid="bookmark-menu"`, `aria-label="com_ui_bookmarks"` hoặc `com_ui_bookmarks_count_selected` khi có nhãn được chọn). Tooltip hiển thị lựa chọn hiện tại hoặc `com_ui_bookmarks`.
- Các mục dropdown BookmarkNav: **Clear All** (biểu tượng `CrossCircledIcon`, nhãn `com_ui_clear_all`), tiếp theo là một mục cho mỗi nhãn hiện có có ít nhất một hội thoại (`count > 0`). Nếu không có nhãn nào, mục bị vô hiệu hóa `com_ui_no_bookmarks` được hiển thị.
- **BookmarkMenu** trong tiêu đề chat (trong hội thoại): nút `BookmarkIcon`/`BookmarkFilledIcon` (`data-testid="bookmark-menu"`, `aria-label="com_ui_bookmarks_add"` hoặc `com_ui_bookmarks_count_selected`). Chỉ hiển thị khi một hội thoại thực sự đang mở và hội thoại không phải tạm thời (`expiredAt` phải là null).
- Dropdown BookmarkMenu: mục **New Bookmark** (nhãn `com_ui_bookmarks_new`, biểu tượng `BookmarkPlusIcon`), tiếp theo là tất cả các nhãn bookmark hiện có, mỗi nhãn được hiển thị dưới dạng mục có thể toggle.
- **BookmarkEditDialog**: tiêu đề `com_ui_bookmarks_new` (tạo mới) hoặc `com_ui_bookmarks_edit` (chỉnh sửa). Các trường: ô nhập **Title** (`id="bookmark-tag"`, tối đa 128 ký tự, bắt buộc), textarea **Description** (`id="bookmark-description"`, tối đa 1048 ký tự), hộp kiểm tùy chọn **"Add to conversation"** (`com_ui_bookmarks_add_to_conversation`, chỉ hiển thị khi `conversationId` được cung cấp). Nút **Save** xác nhận form.
- Các nút **Edit** (`EditBookmarkButton`) và **Delete** (`DeleteBookmarkButton`) trên các view quản lý bookmark (cần xác minh: vị trí chính xác — giao diện quản lý nhãn trong thanh bên).

**Hành vi chức năng:**
1. FR-1: Nhấp vào một nhãn trong dropdown BookmarkNav sẽ toggle nhãn đó trong tập lọc đang hoạt động; nhiều nhãn có thể được chọn đồng thời (logic lọc OR được áp dụng ở cấp query API qua tham số `tags`).
2. FR-2: Khi một hoặc nhiều nhãn được chọn, `useConversationsInfiniteQuery` được gọi với `{ tags: [...selectedTags] }`; chỉ hiển thị các hội thoại khớp với bất kỳ nhãn được chọn nào.
3. FR-3: Nhấp **Clear All** trong BookmarkNav sẽ xóa tất cả nhãn được chọn và khôi phục danh sách hội thoại không lọc.
4. FR-4: Nhấp **New Bookmark** trong BookmarkMenu mở `BookmarkEditDialog` ở chế độ tạo mới.
5. FR-5: Xác nhận BookmarkEditDialog sẽ gọi `useConversationTagMutation`; khi thành công, toast `com_ui_bookmarks_create_success` được hiển thị; nếu **Add to conversation** được chọn, nhãn mới cũng được gán cho hội thoại hiện tại.
6. FR-6: Nhấp vào một nhãn hiện có trong BookmarkMenu sẽ gọi `useTagConversationMutation` để toggle nhãn đó trên hội thoại hiện tại; nếu đã được gán thì gỡ ra, nếu chưa được gán thì thêm vào.
7. FR-7: Tên nhãn phải là duy nhất toàn cục; xác nhận tên trùng lặp sẽ hiển thị toast cảnh báo `com_ui_bookmarks_create_exists` và form không được xác nhận.
8. FR-8: Nhãn được hiển thị với `BookmarkFilledIcon` khi được chọn trên một hội thoại và `BookmarkIcon` khi chưa được chọn.

**Trạng thái & trường hợp đặc biệt:**
- **Không có bookmark nào tồn tại:** Dropdown BookmarkNav hiển thị mục bị vô hiệu hóa `com_ui_no_bookmarks`.
- **Hội thoại tạm thời đang mở:** BookmarkMenu không được render (`isTemporary === true` được kiểm tra).
- **Hội thoại mới (`/c/new`):** BookmarkMenu không được render (`isActiveConvo === false`).
- **Tên nhãn > 128 ký tự:** Form hiển thị lỗi trường và việc xác nhận bị chặn.
- **Tên nhãn trùng lặp:** Toast cảnh báo và không có lệnh gọi API nào.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử không có nhãn bookmark nào tồn tại, khi người dùng mở dropdown BookmarkNav, thì mục "No bookmarks" bị vô hiệu hóa được hiển thị.
- AC-2: Giả sử có hai nhãn bookmark và người dùng chọn cả hai trong BookmarkNav, khi danh sách hội thoại tải lại, thì chỉ hiển thị các hội thoại được gán nhãn với bất kỳ nhãn nào.
- AC-3: Giả sử BookmarkEditDialog đang mở, khi người dùng xác nhận tên nhãn đã tồn tại, thì toast cảnh báo xuất hiện và không có nhãn mới nào được tạo.
- AC-4: Giả sử một hội thoại đang mở mà chưa có nhãn, khi người dùng nhấp vào một nhãn hiện có trong BookmarkMenu, thì nhãn đó được gán cho hội thoại và `BookmarkFilledIcon` được hiển thị cho nhãn đó.
- AC-5: Giả sử một temporary chat đang hoạt động, khi tiêu đề chat được kiểm tra, thì nút BookmarkMenu không có mặt.

---

### Chia sẻ Hội thoại (Liên kết Công khai)

**Mục đích:** Tạo liên kết có thể truy cập công khai, chỉ đọc đến một hội thoại để chia sẻ với bất kỳ ai mà không cần tài khoản.

**Điều kiện tiên quyết / truy cập:** `sharedLinksEnabled = true` trong cấu hình khởi động. Người dùng đã xác thực với một hội thoại đã lưu đang mở.

**Thành phần giao diện:**
- Mục menu **Share** (nhãn `com_ui_share`, biểu tượng `Share2`) trong dropdown `ConvoOptions` ba chấm của hội thoại (chỉ hiển thị khi `startupConfig.sharedLinksEnabled` là true).
- Menu **Export & Share** trong tiêu đề chat (biểu tượng `Share2`, nhãn `com_endpoint_export_share`), với các mục dropdown **Share** (`com_ui_share`) và **Export** (`com_endpoint_export`).
- Hộp thoại **Share Link to Chat** (`com_ui_share_link_to_chat`): hiển thị `com_ui_share_create_message` (chưa có liên kết) hoặc `com_ui_share_update_message` (đã có liên kết). Chứa URL có thể chia sẻ trong hộp hiển thị chỉ đọc với nút **Copy** (`aria-label="com_ui_copy_link"`, biểu tượng `Copy` / `CopyCheck`), và khi đã có liên kết: nút **Refresh link** (biểu tượng `RotateCw`, `aria-label="com_ui_refresh_link"`), nút **QR code** (biểu tượng `QrCode`, toggle `com_ui_show_qr` / `com_ui_hide_qr`), và nút **Delete** (biểu tượng `Trash2`, `aria-label="com_ui_delete"`, mở hộp thoại xác nhận xóa lồng nhau).
- Nút **Create Link** (`com_ui_create_link`, `variant="submit"`) hiển thị khi chưa có liên kết.
- Mã QR được render qua `QRCodeSVG` ở kích thước 200 px, hiển thị bên dưới URL khi được toggle.
- Phần **Settings > Data > Shared Links** (`com_nav_shared_links`) với nút **Manage** liệt kê tất cả liên kết công khai trong `DataTable` với các cột Name, Date, và Actions; hỗ trợ tìm kiếm/lọc và cuộn vô hạn.

**Hành vi chức năng:**
1. FR-1: Mở hộp thoại Share sẽ gọi `useGetSharedLinkQuery(conversationId)` để kiểm tra xem đã có liên kết chia sẻ hay chưa.
2. FR-2: Nếu chưa có liên kết, nút **Create Link** được hiển thị; nhấp vào sẽ gọi `useCreateSharedLinkMutation({ conversationId, targetMessageId })` trong đó `targetMessageId` là ID tin nhắn mới nhất.
3. FR-3: Khi tạo liên kết thành công, URL được hiển thị, nút Copy được kích hoạt, và các nút Refresh/QR/Delete xuất hiện.
4. FR-4: Nhấp **Refresh link** sẽ gọi `useUpdateSharedLinkMutation({ shareId })`, tạo `shareId` và URL mới; thông báo live-region `com_ui_link_refreshed` kích hoạt.
5. FR-5: Nhấp **Copy** ghi URL vào clipboard; biểu tượng thay đổi thành `CopyCheck` trong thời gian ngắn; live-region thông báo `com_ui_link_copied`.
6. FR-6: Nhấp **Delete** (nút `Trash2`) mở hộp thoại xác nhận lồng nhau (`com_ui_delete_shared_link_heading`); xác nhận sẽ gọi `useDeleteSharedLinkMutation({ shareId })`; khi thành công, toast `com_ui_shared_link_delete_success` được hiển thị và hộp thoại trở về trạng thái "create".
7. FR-7: URL liên kết chia sẻ được xây dựng bằng `new URL('{apiBaseUrl}/share/{shareId}', window.location.origin)` qua `buildShareLinkUrl`, trong đó `apiBaseUrl` lấy từ `librechat-data-provider` (mặc định là `/api`). Trong bản triển khai có tiền tố `/api` tiêu chuẩn, kết quả là `{origin}/api/share/{shareId}`. URL chính xác phụ thuộc vào cấu hình `apiBaseUrl`.
8. FR-8: Trong Settings > Data > Shared Links, các liên kết riêng lẻ có thể bị xóa (xóa từng hàng) và không có hộp kiểm xóa hàng loạt (`showCheckboxes={false}`). Xóa hàng loạt được triển khai một phần ở cấp handler (`handleDelete` nhận mảng và hiển thị toast `com_ui_shared_link_bulk_delete_success`) nhưng không được hiển thị qua giao diện.
9. FR-9: Mục menu Share trong dropdown ba chấm bị ẩn hoàn toàn khi `startupConfig.sharedLinksEnabled` là false.

**Trạng thái & trường hợp đặc biệt:**
- **Lỗi API khi tạo liên kết:** Toast `com_ui_share_error` được hiển thị; không có liên kết nào được lưu.
- **Lỗi API khi xóa liên kết:** Toast `com_ui_share_delete_error` được hiển thị; liên kết hiện có vẫn còn hiệu lực.
- **Hội thoại mới hoặc chưa lưu:** Component `ExportAndShareMenu` kiểm tra `conversation.conversationId != null && conversationId !== 'new' && conversationId !== 'search'`; nếu bất kỳ điều kiện nào thất bại thì menu không được render.
- **Liên kết chia sẻ được truy cập bởi người dùng chưa xác thực:** Liên kết chia sẻ (`/share/{shareId}`) có thể truy cập công khai mà không cần xác thực. Route được định nghĩa bên ngoài cây route đã xác thực (`AuthLayout`) và `ShareView` không thực hiện kiểm tra xác thực.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử `sharedLinksEnabled` là true và chưa có liên kết, khi người dùng mở hộp thoại Share, thì nút "Create Link" hiển thị và không có URL nào được hiển thị.
- AC-2: Giả sử người dùng nhấp "Create Link", khi API thành công, thì URL được hiển thị và các nút Copy, Refresh, QR và Delete xuất hiện.
- AC-3: Giả sử đã có liên kết chia sẻ, khi người dùng nhấp Refresh, thì URL mới được tạo và URL cũ trở nên không hợp lệ (cần xác minh: hành vi hủy hiệu lực phía máy chủ).
- AC-4: Giả sử đã có liên kết chia sẻ, khi người dùng nhấp Delete và xác nhận, thì liên kết bị thu hồi và hộp thoại hiển thị lại "Create Link".
- AC-5: Giả sử `sharedLinksEnabled` là false, khi người dùng mở menu ba chấm, thì mục menu "Share" không hiển thị.

---

### Xuất Hội thoại

**Mục đích:** Tải xuống hội thoại theo một trong nhiều định dạng file để sử dụng ngoại tuyến hoặc lưu trữ.

**Điều kiện tiên quyết / truy cập:** Một hội thoại đã lưu đang mở (`conversationId` khác null, không phải `"new"`, không phải `"search"`). Menu **Export & Share** được render.

**Thành phần giao diện:**
- Mục **Export** (nhãn `com_endpoint_export`, biểu tượng `Upload`) trong dropdown `ExportAndShareMenu`.
- Hộp thoại **Export Conversation** (`com_nav_export_conversation`): form hai cột với:
  - Trường **Filename** (`id="filename"`, nhãn `com_nav_export_filename`, placeholder `com_nav_export_filename_placeholder`). Mặc định là tiêu đề hội thoại được xử lý qua `filenamify`.
  - Dropdown **Type** (`id="type"`, nhãn `com_nav_export_type`) với các tùy chọn:
    - `screenshot (.png)` (giá trị `screenshot`)
    - `text (.txt)` (giá trị `text`)
    - `markdown (.md)` (giá trị `markdown`)
    - `json (.json)` (giá trị `json`)
    - `csv (.csv)` (giá trị `csv`)
    - `webpage (.html)` (giá trị `webpage`)
  - Hộp kiểm **Include endpoint options** (`id="includeOptions"`, nhãn `com_nav_export_include_endpoint_options`); bị vô hiệu hóa và gán nhãn `com_nav_not_supported` cho các loại `csv` và `screenshot`.
  - Hộp kiểm **Export all message branches** (`id="exportBranches"`, nhãn `com_nav_export_all_message_branches`); bị vô hiệu hóa cho các loại khác `json`, `csv`, và `webpage`; gán nhãn `com_nav_not_supported` khi bị vô hiệu hóa.
  - Phần **Recursive** (chỉ hiển thị khi loại là `json`): nhãn tiêu đề phần `com_nav_export_recursive_or_sequential`; hộp kiểm (`id="recursive"`) với văn bản nhãn `com_nav_export_recursive`.
- Nút xác nhận **Export** (`com_endpoint_export`, `variant="submit"`).

**Hành vi chức năng:**
1. FR-1: Mỗi lần hộp thoại mở, các giá trị mặc định được đặt lại thành: type = `screenshot`, includeOptions = `true`, exportBranches = `false`, recursive = `true`, filename = `filenamify(conversation.title ?? 'file')`.
2. FR-2: Thay đổi loại sẽ điều chỉnh tính khả dụng của hộp kiểm: `exportBranches` được bật cho `json`, `csv`, và `webpage`; `includeOptions` bị tắt cho `csv` và `screenshot`; hộp kiểm `recursive` chỉ hiển thị cho `json`. Khi chuyển sang loại bật `exportBranches`, giá trị cũng được tự động đặt thành `true`; chuyển sang loại không hỗ trợ sẽ đặt giá trị về `false`.
3. FR-3: Nhấp **Export** sẽ gọi `useExportConversation({ conversation, filename: filenamify(filename), type, includeOptions, exportBranches, recursive })` kích hoạt tải xuống phía client.
4. FR-4: Tên file được làm sạch qua `filenamify` trước khi tải xuống để loại bỏ các ký tự không hợp lệ với hệ điều hành.

**Trạng thái & trường hợp đặc biệt:**
- **Loại screenshot được chọn:** Cả hai hộp kiểm `includeOptions` và `exportBranches` đều bị vô hiệu hóa và hiển thị `com_nav_not_supported`.
- **Loại CSV được chọn:** `includeOptions` bị vô hiệu hóa; `exportBranches` được bật và tự động đặt thành `true`.
- **Loại webpage được chọn:** `exportBranches` được bật và tự động đặt thành `true`; `includeOptions` được bật.
- **Trường filename trống:** `filenamify` của chuỗi rỗng mặc định về `'file'` (cần xác minh: giá trị dự phòng chính xác).
- **Hội thoại chưa lưu / mới:** `ExportAndShareMenu` không được render, do đó tùy chọn xuất không thể truy cập.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử hộp thoại xuất đang mở và loại được đặt thành `json`, khi `Export all message branches` được chọn và `Recursive` được chọn, thì nhấp Export tải xuống file `.json` chứa tin nhắn đã phân nhánh ở định dạng đệ quy.
- AC-2: Giả sử loại là `screenshot`, khi hộp thoại render, thì cả hai hộp kiểm `Include endpoint options` và `Export all message branches` đều bị vô hiệu hóa và gán nhãn "Not supported".
- AC-3: Giả sử tiêu đề hội thoại là "Q3 Report / Analysis", khi hộp thoại mở, thì trường filename chứa phiên bản đã làm sạch của tiêu đề đó (dấu gạch chéo được xóa bởi `filenamify`).
- AC-4: Giả sử người dùng đang ở `/c/new`, khi họ kiểm tra tiêu đề chat, thì nút menu Export & Share không được render.

---

### Chế độ Nhiều Hội thoại (Multi-Conversation Mode)

**Mục đích:** Gửi cùng một câu hỏi đồng thời đến hai hoặc nhiều hội thoại song song, mỗi hội thoại có thể sử dụng model hoặc cấu hình khác nhau. Đây là tính năng nâng cao dành cho người dùng muốn so sánh các phản hồi.

**Điều kiện tiên quyết / truy cập:** `PermissionTypes.MULTI_CONVO`, `Permissions.USE` được cấp (được bật trong cấu hình NuFi). Endpoint hiện tại không được là Assistants endpoint.

**Thành phần giao diện:**
- Nút **Add Multi-Conversation** (`data-testid="add-multi-convo-button"`, `aria-label="com_ui_add_multi_conversation"`, biểu tượng `PlusCircle`) trong tiêu đề chat, chỉ hiển thị khi `hasAccessToMultiConvo` là true và endpoint đang hoạt động không phải Assistants endpoint.
- Khi hội thoại thứ hai được thêm, vùng chat chia thành các panel song song; mỗi panel có `ModelSelector` riêng và ngữ cảnh hội thoại riêng (`conversationByIndex(0)` và `conversationByIndex(1)`).

**Hành vi chức năng:**
1. FR-1: Nhấp nút `AddMultiConvo` sẽ sao chép cài đặt của hội thoại chính (index 0) vào slot hội thoại thứ hai (index 1), xóa tiêu đề, và đặt vào `conversationByIndex(1)` qua Recoil.
2. FR-2: Sau khi thêm, focus được chuyển đến ô nhập văn bản `mainTextareaId`.
3. FR-3: Câu hỏi được gõ trong vùng nhập dùng chung sẽ được gửi đồng thời đến tất cả các slot hội thoại đang hoạt động.
4. FR-4: Mỗi panel hội thoại trong chế độ multi-convo duy trì lịch sử tin nhắn, ID hội thoại và lựa chọn model của riêng mình một cách độc lập.
5. FR-5: Nút không được render khi `endpoint` là null (ví dụ: chưa tải hội thoại nào) hoặc khi `isAssistantsEndpoint(endpoint)` là true.
6. FR-6: Mỗi panel hội thoại tạo và lưu phản hồi của mình một cách độc lập; cả hai hội thoại đều xuất hiện trong lịch sử thanh bên.

**Trạng thái & trường hợp đặc biệt:**
- **Assistants endpoint đang hoạt động:** Nút AddMultiConvo không được render.
- **Không có endpoint nào được cấu hình:** Nút không được render.
- **Xóa một panel:** Panel phụ được đóng bằng nút `×` đóng (`aria-label="Close added conversation"`) được render trong chip `AddedConvo` bên trong tiêu đề textarea (`AddedConvo.tsx`). Nhấp vào sẽ gọi `setAddedConvo(null)`, xóa panel phụ khỏi giao diện. Nút đóng không nằm trong `AddMultiConvo.tsx`.
- **Số panel tối đa:** Tối đa là 2 panel đồng thời (panel chính ở index 0 và một panel phụ ở index 1). `AddMultiConvo` chỉ ghi vào `conversationByIndex(1)`; nhấp nhiều lần sẽ ghi đè cùng một slot thay vì thêm panel thứ ba.

**Tiêu chí chấp nhận:**
- AC-1: Giả sử một endpoint không phải Assistants được chọn, khi người dùng nhấp nút `PlusCircle` "Add Multi-Conversation", thì một panel hội thoại thứ hai xuất hiện cạnh panel đầu tiên.
- AC-2: Giả sử hai panel hội thoại đang mở, khi người dùng nhập tin nhắn và gửi, thì cùng một câu hỏi được gửi đến cả hai hội thoại và mỗi hội thoại tạo ra phản hồi độc lập.
- AC-3: Giả sử một Assistants endpoint đang hoạt động, khi tiêu đề chat được kiểm tra, thì nút "Add Multi-Conversation" không có mặt.
- AC-4: Giả sử chế độ multi-convo đang hoạt động, khi cả hai phản hồi hoàn thành, thì hai hội thoại riêng biệt xuất hiện trong lịch sử thanh bên.

---

### Temporary Chat

**Mục đích:** Thực hiện phiên chat **không được lưu** vào lịch sử hội thoại. Phù hợp cho các truy vấn nhạy cảm hoặc một lần sử dụng.

**Điều kiện tiên quyết / truy cập:** `PermissionTypes.TEMPORARY_CHAT`, `Permissions.USE` được cấp (được bật trong cấu hình NuFi). Toggle chỉ hiển thị khi chưa có tin nhắn nào trong hội thoại hiện tại và không có lần gửi nào đang diễn ra.

**Thành phần giao diện:**
- Nút toggle **Temporary Chat** (`aria-label="com_ui_temporary"`, `aria-pressed={isTemporary}`, biểu tượng `MessageCircleDashed`) trong tiêu đề chat. Kiểu dáng: `bg-surface-active` (đang bật/nhấn) so với `bg-presentation shadow-sm hover:bg-surface-active-alt` (tắt).
- Tooltip hiển thị `com_ui_temporary` khi di chuột vào.
- Nút bị ẩn (`return null`) sau khi `conversation.messages.length >= 1` hoặc trong khi đang gửi (`isSubmitting`).
- Toggle **Settings > Chat > Default Temporary Chat** (`switchId="defaultTemporaryChat"`) lưu tùy chọn vào local storage để các hội thoại mới tự động bắt đầu ở chế độ tạm thời.

**Hành vi chức năng:**
1. FR-1: Nhấp toggle sẽ đảo trạng thái Recoil atom `isTemporary` (được sao lưu bởi key local storage `isTemporary`).
2. FR-2: Khi `isTemporary` là `true` tại thời điểm gửi tin nhắn đầu tiên, `isTemporary: true` được gửi trong phần thân yêu cầu đến API.
3. FR-3: Máy chủ **không lưu** hội thoại vào cơ sở dữ liệu khi `isTemporary` là true; không có ID hội thoại nào được lưu vào lịch sử.
4. FR-4: Vì không có hội thoại nào được lưu, hội thoại không xuất hiện trong lịch sử thanh bên sau khi phiên kết thúc.
5. FR-5: `BookmarkMenu` trong tiêu đề chat bị ẩn cho các hội thoại tạm thời (`conversation?.expiredAt != null` được sử dụng làm tín hiệu phát hiện).
6. FR-6: Toggle biến mất sau khi tin nhắn đầu tiên được gửi (component kiểm tra `conversation.messages.length >= 1`), ngăn người dùng toggle ở giữa hội thoại.
7. FR-7: Cài đặt `defaultTemporaryChat` trong Settings > Chat đặt trước `isTemporary = true` cho mọi hội thoại mới, loại bỏ nhu cầu toggle thủ công.

**Trạng thái & trường hợp đặc biệt:**
- **Chế độ tạm thời được bật rồi tắt trước khi gửi:** Chat tiến hành như một hội thoại bình thường, được lưu.
- **Chế độ tạm thời với tải file / RAG:** (cần xác minh thủ công trên sản phẩm đang chạy: liệu file đính kèm trong temporary chat có được lưu hay bị loại bỏ — cần kiểm tra phía máy chủ tại các route `api/`.)
- **Làm mới trình duyệt giữa chừng temporary chat:** Vì `isTemporary` ở trong local storage nên nó tồn tại qua các lần làm mới; tuy nhiên các tin nhắn trong bộ nhớ bị mất. Hội thoại chưa bao giờ được lưu, do đó lịch sử không thể khôi phục.
- **Multi-convo + temporary:** Chế độ tạm thời áp dụng toàn cục cho tất cả các panel. `isTemporary` là một Recoil atom toàn cục duy nhất được đọc bởi cả `ChatForm` và luồng gửi của panel phụ; cả hai panel đều gửi `isTemporary: true` trong phần thân yêu cầu.
- **Nút Share trên temporary chat:** `ExportAndShareMenu` yêu cầu `conversationId` khác null và không phải `"new"`. Trong temporary chat trước tin nhắn đầu tiên, `conversationId` là `"new"`, nên Export & Share không được render. Sau tin nhắn đầu tiên, client nhận `conversationId` từ phản hồi SSE của máy chủ và menu có thể được render, nhưng mọi thao tác tạo liên kết chia sẻ sẽ thất bại phía máy chủ vì hội thoại không được lưu. (cần xác minh thủ công trên sản phẩm đang chạy: liệu hộp thoại Share có xuất hiện và máy chủ phản hồi thế nào với share mutation cho temporary conversation.)

**Tiêu chí chấp nhận:**
- AC-1: Giả sử chế độ temporary chat đang tắt, khi người dùng nhấp toggle `MessageCircleDashed`, thì `aria-pressed` thay đổi thành `true` và nền nút thay đổi thành `bg-surface-active`.
- AC-2: Giả sử chế độ temporary chat đang bật và người dùng gửi tin nhắn, khi hội thoại hoàn thành, thì **không có mục nào xuất hiện** trong lịch sử hội thoại trên thanh bên.
- AC-3: Giả sử chế độ temporary chat đang bật và hội thoại đang hoạt động, khi tiêu đề chat được kiểm tra, thì nút BookmarkMenu không có mặt.
- AC-4: Giả sử chế độ temporary chat đang bật và người dùng đã gõ nhưng chưa gửi tin nhắn, khi họ nhấp toggle lại, thì `aria-pressed` thay đổi thành `false` và hội thoại sẽ được lưu bình thường khi gửi.
- AC-5: Giả sử người dùng đã bật "Default Temporary Chat" trong Settings > Chat, khi họ mở một hội thoại mới, thì toggle được đặt sẵn ở trạng thái hoạt động (đang nhấn).
- AC-6: Giả sử một temporary chat đang diễn ra, khi phản hồi tin nhắn đầu tiên hoàn thành, thì nút toggle temporary chat không còn được render trong tiêu đề.
