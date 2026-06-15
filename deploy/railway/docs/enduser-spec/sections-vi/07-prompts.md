## Prompts Library

Prompts Library là kho lưu trữ phía máy chủ, liên tục và có thể tái sử dụng các mẫu prompt. Mỗi prompt thuộc về một **nhóm prompt** (đơn vị tổ chức), trong đó có thể chứa nhiều **phiên bản** nội dung. Mỗi nhóm chỉ có duy nhất một phiên bản được chỉ định là phiên bản **production** — đây là nội dung hiển thị cho người dùng cuối trong bảng lệnh chat. Người dùng có quyền phù hợp có thể tạo, chỉnh sửa, phân phiên bản, phân loại, chia sẻ và xóa các prompt. Thư viện có thể truy cập qua đường dẫn `/prompts` riêng biệt hoặc dưới dạng bảng trượt trong khi chat.

---

### Truy cập Prompts Library

- **Mục đích:** Điều hướng đến trang thư viện toàn trang hoặc mở bảng prompts trong chat, cho phép người dùng duyệt, quản lý và áp dụng các prompt đã lưu.
- **Điều kiện tiên quyết / truy cập:** Người dùng phải được xác thực và có quyền `PROMPTS › USE` (kiểm soát phía máy chủ). Người dùng không có quyền này sẽ bị chuyển hướng đến `/c/new` sau 1 giây và bảng prompts sẽ không được hiển thị.
- **Thành phần giao diện:**
  - Mục điều hướng thanh bên hoặc đường dẫn `/prompts` riêng — điều hướng đến trang thư viện.
  - Bảng prompts trong chat (thanh bên trượt vào) được mở từ giao diện chat.
  - Thanh tìm kiếm có nhãn **"Filter prompts by name"** (`com_ui_filter_prompts_name`).
  - Dropdown danh mục/lọc với biểu tượng (`ListFilter`) có nhãn **"Filter:"** / `com_ui_filter_prompts`.
  - Các tùy chọn lọc: **All** (`com_ui_all_proper`), **My Prompts** (`com_ui_my_prompts`), **Shared Prompts** (`com_ui_shared_prompts`), tiếp theo là dấu phân cách và các mục danh mục riêng lẻ.
  - Thẻ prompt (một thẻ mỗi nhóm) trong danh sách có thể cuộn; điều khiển phân trang **Prev** / **Next** ở dưới cùng của bảng.
  - Bảng trạng thái trống: biểu tượng + tiêu đề **"No prompts title"** (`com_ui_no_prompts_title`) + văn bản phụ **"Add first prompt"** (`com_ui_add_first_prompt`).
  - Khi không có prompt nào được chọn trong chế độ xem thư viện: thông báo căn giữa **"Select or create a prompt"** (`com_ui_select_or_create_prompt`).
- **Hành vi chức năng:**
  1. FR-1 — Khi tải, hệ thống lấy tất cả các nhóm prompt mà người dùng được phép xem (phân trang) và hiển thị chúng dưới dạng thẻ theo thứ tự mặc định của máy chủ.
  2. FR-2 — Nhập vào thanh tìm kiếm sẽ lọc danh sách phía máy chủ theo tên prompt; giá trị debounce 500 ms được truyền dưới dạng tham số truy vấn tới API, API này áp dụng bộ lọc regex không phân biệt hoa thường trong cơ sở dữ liệu. Vùng live region dành cho trình đọc màn hình thông báo số lượng kết quả.
  3. FR-3 — Chọn một tùy chọn lọc từ dropdown danh mục sẽ giới hạn danh sách chỉ hiển thị các prompt khớp với giá trị `SystemCategory` hoặc danh mục tùy chỉnh đó; chọn **All** sẽ bỏ giới hạn.
  4. FR-4 — Khi bộ lọc **My Prompts** đang hoạt động, máy chủ chỉ trả về các nhóm prompt do người dùng hiện tại tạo ra (được xác định qua `ownedPromptGroupIds` trên máy chủ; client gửi `category = 'sys__my__prompts__sys'`).
  5. FR-5 — Khi bộ lọc **Shared Prompts** đang hoạt động, máy chủ trả về tất cả nhóm prompt mà người dùng có thể truy cập qua ACL nhưng không sở hữu (bao gồm cả các nhóm được chia sẻ công khai), loại trừ những nhóm có trong `ownedPromptGroupIds`. Trường `authorName` chỉ được sử dụng phía client để hiển thị huy hiệu "chia sẻ bởi tác giả" trên thẻ.
  6. FR-6 — Nhấn **Prev** / **Next** sẽ lấy trang liền kề; các điều khiển bị vô hiệu hóa khi `hasPreviousPage` / `hasNextPage` là false.
  7. FR-7 — Trên các viewport di động, bảng prompts xuất hiện dưới dạng lớp phủ toàn màn hình hoặc ngăn kéo.
- **Trạng thái & trường hợp đặc biệt:**
  - Thư viện trống: khu vực danh sách hiển thị trạng thái trống dạng biểu tượng file (`com_ui_no_prompts_title`); nút `Create Prompt` vẫn hiển thị nếu người dùng có quyền `PROMPTS › CREATE`.
  - Tìm kiếm không có kết quả: giao diện trạng thái trống tương tự xuất hiện; live region thông báo "0 results".
  - Đang tải: các thẻ skeleton (`h-[72px]`) xuất hiện thay cho thẻ thật trong khi `groupsQuery.isLoading` là true.
- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử người dùng có quyền `PROMPTS › USE`, khi họ điều hướng đến `/prompts`, thì danh sách prompt tải trong một vòng kết nối mạng mà không có lỗi.
  2. AC-2 — Giả sử một từ tìm kiếm được nhập, khi 500 ms trôi qua, thì chỉ hiển thị các nhóm prompt có tên chứa từ đó (không phân biệt hoa thường).
  3. AC-3 — Giả sử không có prompt nào tồn tại, khi chế độ xem thư viện hiển thị, thì thông báo trạng thái trống hiển thị và không có mục danh sách nào.
  4. AC-4 — Giả sử người dùng không có quyền `PROMPTS › USE`, khi họ truy cập `/prompts/new`, thì họ bị chuyển hướng đến `/c/new` trong vòng 1 giây.

---

### Tạo Prompt

- **Mục đích:** Cho phép người dùng được cấp quyền định nghĩa một prompt có thể tái sử dụng mới (nhóm + phiên bản đầu tiên) với tên, nội dung văn bản, danh mục tùy chọn, mô tả một dòng tùy chọn, và lệnh slash tùy chọn.
- **Điều kiện tiên quyết / truy cập:** Người dùng phải có cả quyền `PROMPTS › USE` và `PROMPTS › CREATE`. Form tạo nằm tại đường dẫn `/prompts/new` và cũng có thể truy cập qua nút **"Create Prompt"** (biểu tượng cộng, `com_ui_create_prompt`) trong thanh công cụ lọc.
- **Thành phần giao diện:**
  - Trường **Prompt Name**: ô nhập văn bản với nhãn nổi (`id="prompt-name"`, `aria-label="Prompt name"`, placeholder `" "`). Nhãn: **"Prompt name"** (`com_ui_prompt_name`) với dấu bắt buộc (`*`). Thông báo lỗi xác thực xuất hiện bên dưới trường theo kiểu `text-status-error`.
  - Dropdown **Category**: nút `CategorySelector` có nhãn `com_ui_prompt_category_selector_aria`, hiển thị nhãn danh mục hiện tại hoặc placeholder **"Category"** khi chưa chọn. Lưu lựa chọn cuối cùng vào `localStorage` theo khóa `LAST_PROMPT_CATEGORY`.
  - Bảng **Prompt Text**: tiêu đề hiển thị biểu tượng `FileText` và nhãn **"Text"** (`com_ui_prompt_text`) với dấu bắt buộc; nội dung là `TextareaAutosize` với `minRows=4`, `maxRows=16`, `font-mono`, placeholder `com_ui_prompt_input`.
  - Nút dropdown **Special Variables** (biểu tượng tia sáng, nhãn `com_ui_special_variables`) — góc trên bên phải bảng prompt text. Chèn token biến đặc biệt vào cuối textarea.
  - Bảng **Variables**: tự động xuất hiện bên dưới textarea khi phát hiện các token `{{...}}` trong nội dung prompt (xem §Biến trong Prompt).
  - Trường **Description**: ô nhập một dòng với nhãn nổi **"Description placeholder"** (`com_ui_description_placeholder`), biểu tượng `Info`, tối đa 120 ký tự; số ký tự hiển thị dưới dạng `n/120`.
  - Trường **Command**: ô nhập một dòng với nhãn nổi **"Command placeholder"** (`com_ui_command_placeholder`), biểu tượng `SquareSlash`; chỉ chấp nhận chữ thường alphanumeric và dấu gạch ngang, khoảng trắng được chuyển thành dấu gạch ngang, tối đa 56 ký tự (`Constants.COMMANDS_MAX_LENGTH`); số ký tự hiển thị dưới dạng `n/56`.
  - Nút **Create Prompt** (`com_ui_create_prompt`): bị vô hiệu hóa (độ mờ 50%) khi form chưa có thay đổi, đang gửi hoặc không vượt qua xác thực.
- **Hành vi chức năng:**
  1. FR-1 — Gửi form sẽ gọi `useCreatePrompt`, tạo nhóm prompt mới và phiên bản prompt đầu tiên trong một lần gọi API.
  2. FR-2 — Trường `name` là bắt buộc; gửi với tên trống sẽ hiển thị lỗi `com_ui_prompt_name_required` bên dưới trường.
  3. FR-3 — Trường `prompt` (nội dung văn bản) là bắt buộc; gửi với nội dung trống sẽ hiển thị `com_ui_prompt_text_required`.
  4. FR-4 — `oneliner` chỉ được đưa vào payload API khi độ dài lớn hơn không; tương tự với `command`.
  5. FR-5 — Giá trị `command` được buộc thành chữ thường và loại bỏ mọi ký tự không thuộc `[a-z0-9-]`; khoảng trắng được chuyển thành dấu gạch ngang.
  6. FR-6 — Sau khi tạo thành công, người dùng được điều hướng đến `/prompts/{groupId}` (thay thế lịch sử điều hướng) trừ khi form được sử dụng trong ngữ cảnh nhúng cung cấp callback `onSuccess`.
  7. FR-7 — Danh mục được chọn được lưu trong `localStorage` theo khóa `LAST_PROMPT_CATEGORY` và được điền sẵn cho các lần sử dụng form tạo tiếp theo.
- **Trạng thái & trường hợp đặc biệt:**
  - Form có/chưa có thay đổi: nút **Create Prompt** hiển thị không hoạt động (độ mờ 50%) khi `isDirty` là false.
  - Gửi đồng thời: nút bị vô hiệu hóa trong khi `isSubmitting` là true.
  - Không chọn danh mục: trường danh mục là tùy chọn; nhóm được tạo với chuỗi rỗng cho `category`.
  - Người dùng điều hướng đi mà không gửi: không có dữ liệu nào được lưu (form không được tự động lưu).
- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử cả hai trường bắt buộc đã được điền, khi người dùng nhấn **Create Prompt**, thì một nhóm prompt mới được tạo và trình duyệt điều hướng đến `/prompts/{newGroupId}`.
  2. AC-2 — Giả sử trường tên trống, khi người dùng gửi, thì lỗi nội tuyến `com_ui_prompt_name_required` xuất hiện và không có lần gọi API nào được thực hiện.
  3. AC-3 — Giả sử một lệnh chứa chữ hoa hoặc khoảng trắng, khi người dùng gõ, thì trường tự động chuyển đổi thành dạng chữ thường có dấu gạch ngang.
  4. AC-4 — Giả sử một mô tả từ 121 ký tự trở lên được dán vào, khi handler kích hoạt, thì các ký tự vượt quá 120 bị từ chối và số đếm dừng ở 120.

---

### Biến trong Prompt và Thay thế

- **Mục đích:** Cho phép tác giả prompt nhúng các token placeholder vào nội dung prompt; khi prompt được sử dụng trong chat, người dùng cuối được yêu cầu cung cấp giá trị trước khi tin nhắn được gửi.
- **Điều kiện tiên quyết / truy cập:** Biến được soạn thảo trong quá trình tạo hoặc chỉnh sửa prompt; chúng được sử dụng trong quá trình dùng prompt (không cần quyền đặc biệt ngoài `USE`).
- **Thành phần giao diện:**

  **Bảng soạn thảo — Xem trước biến (component `PromptVariables`):**
  - Tự động xuất hiện bên dưới nội dung prompt bất cứ khi nào có token `{{...}}`.
  - Tiêu đề: biểu tượng `Variable` + nhãn **"Variables"** (`com_ui_variables`) + huy hiệu số lượng.
  - Ba tiểu mục (mỗi mục chỉ hiển thị khi không trống):
    - **Special variables** (`com_ui_special_variables`): hiển thị dưới dạng `SpecialVariableChip` — biểu tượng, nhãn hiển thị và mô tả.
    - **Dropdown variables** (`com_ui_dropdown_variables`): hiển thị dưới dạng `DropdownVariableCard` — tên biến, huy hiệu số lượng tùy chọn và các chip tùy chọn riêng lẻ.
    - **Text variables** (`com_ui_text_variables`): hiển thị dưới dạng `SimpleVariableChip` — biểu tượng `Variable` + tên rút gọn.

  **Dropdown Special Variables (thanh công cụ trình soạn thảo):**
  - Nút có nhãn `com_ui_add_special_variables` (biểu tượng tia sáng + văn bản `com_ui_special_variables` trên breakpoint ≥`sm`).
  - Bốn biến đặc biệt tích hợp sẵn (từ `specialVariables` trong `librechat-data-provider`):
    - `current_date` — biểu tượng `Calendar`, nhãn `com_ui_special_var_current_date`
    - `current_datetime` — biểu tượng `Clock`, nhãn `com_ui_special_var_current_datetime`
    - `current_user` — biểu tượng `User`, nhãn `com_ui_special_var_current_user`
    - `iso_datetime` — biểu tượng `Globe`, nhãn `com_ui_special_var_iso_datetime`
  - Các biến đã sử dụng được hiển thị với dấu tích và bị vô hiệu hóa.
  - Nhấn vào một mục sẽ thêm `{label}: {{key}}` vào cuối nội dung prompt (được đặt trước bởi `\n\n` nếu nội dung không trống).

  **Hộp thoại điền biến (`VariableForm`):**
  - Tiêu đề: tên của nhóm prompt.
  - Khung xem trước prompt: markdown được render với các giá trị người dùng nhập được tô đậm theo thời gian thực.
  - Ô nhập mỗi biến: `TextareaAutosize` cho biến đơn giản; `InputCombobox` với các tùy chọn định sẵn (cùng với nhập văn bản tự do) cho biến dropdown.
  - Nhãn nổi xác định từng biến theo tên.
  - Nút **Submit** (`com_ui_submit`) gửi nội dung đã điền vào chat.

- **Hành vi chức năng:**
  1. FR-1 — Cú pháp biến: biến văn bản đơn giản dùng `{{variable_name}}`; biến dropdown dùng `{{variable_name:option1|option2|option3}}`. Cú pháp dấu hai chấm-pipe được phân tích bởi `parseFieldConfig`; ít nhất một ký tự pipe trong chuỗi tùy chọn sẽ kích hoạt ô nhập dạng `select` (combobox).
  2. FR-2 — Các token biến đặc biệt (`{{current_date}}`, `{{current_datetime}}`, `{{current_user}}`, `{{iso_datetime}}`) được giải quyết phía máy chủ/máy khách thông qua `replaceSpecialVars` trước khi hộp thoại điền biến hiển thị. Chúng **không** xuất hiện dưới dạng trường có thể chỉnh sửa trong `VariableForm`.
  3. FR-3 — `extractUniqueVariables` loại bỏ trùng lặp biến để mỗi tên chỉ xuất hiện một lần dưới dạng ô nhập bất kể nó xuất hiện bao nhiêu lần trong nội dung prompt.
  4. FR-4 — Khi gửi, `VariableForm` thực hiện thay thế regex toàn cục mỗi lần xuất hiện `{{variable}}` bằng giá trị đã nhập; các trường để trống sẽ giữ nguyên token placeholder trong nội dung được gửi.
  5. FR-5 — Bản xem trước trực tiếp thay thế các giá trị đã điền bằng markdown `**in đậm**` theo thời gian thực khi người dùng gõ.
  6. FR-6 — Các combobox biến dropdown cho phép nhập văn bản tự do ngoài các tùy chọn định sẵn.
  7. FR-7 — Sau khi gửi, `recordUsage` được gọi với ID nhóm để theo dõi phân tích sử dụng prompt.
- **Trạng thái & trường hợp đặc biệt:**
  - Không có biến trong prompt: `VariableDialog` trả về `null` và không bao giờ hiển thị; nội dung prompt được gửi trực tiếp.
  - Biến bỏ trống khi gửi: token placeholder `{{variable}}` được giữ nguyên trong tin nhắn đã gửi.
  - Biến đặc biệt trong prompt: được giải quyết thành giá trị lúc chạy (ví dụ: ngày hôm nay) trước khi hộp thoại mở.
  - Hủy hộp thoại: focus quay lại textarea (thông qua `requestAnimationFrame`).
- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử prompt chứa `{{name}}`, khi nó được chọn để sử dụng, thì Hộp thoại điền biến mở ra với ô nhập văn bản có nhãn "name".
  2. AC-2 — Giả sử prompt chứa `{{tone:formal|casual}}`, khi hộp thoại mở, thì một combobox với các tùy chọn "formal" và "casual" được hiển thị cùng với ô nhập văn bản tự do.
  3. AC-3 — Giả sử người dùng điền giá trị, khi khung xem trước hiển thị, thì placeholder biến được thay thế bằng giá trị được render in đậm.
  4. AC-4 — Giả sử prompt chứa `{{current_date}}`, khi hộp thoại được mở, thì không có ô nhập nào cho `current_date` hiển thị; giá trị đã được giải quyết sẵn.
  5. AC-5 — Giả sử tất cả các trường đã được điền và người dùng nhấn **Submit**, thì nội dung đã lắp ghép (với các thay thế) được gửi vào ô nhập chat và lượt sử dụng được ghi lại.

---

### Chỉnh sửa Prompt và Quản lý Phiên bản

- **Mục đích:** Cho phép người dùng được cấp quyền chỉnh sửa nội dung, tên, mô tả, lệnh và danh mục của prompt. Mỗi lần lưu thay đổi nội dung văn bản sẽ tạo ra một **phiên bản** mới; mỗi nhóm có một phiên bản **production** được dùng trong chat.
- **Điều kiện tiên quyết / truy cập:**
  - Người dùng phải có quyền `EDIT` (`PermissionBits.EDIT`) trên nhóm prompt cụ thể (kiểm tra thông qua `useResourcePermissions`).
  - Người dùng chỉ đọc có quyền `VIEW` sẽ thấy `PromptDetails` mà không có điều khiển chỉnh sửa (`showActions=false`).
  - Người dùng không có quyền `VIEW` hoặc `EDIT` sẽ thấy trạng thái `NoPromptGroup`.
- **Thành phần giao diện:**

  **Trang trình soạn thảo prompt (`/prompts/{groupId}`):**
  - **Prompt Name** (component `PromptName`): tiêu đề có thể chỉnh sửa nội tuyến. Nhấn để vào chế độ chỉnh sửa (ô nhập văn bản có viền); nhấn `Enter` hoặc mất focus để lưu; nhấn `Escape` để hủy. Hiển thị spinner `Loader2` khi đang lưu, `Check` khi thành công, `X` khi có lỗi (mỗi trạng thái khoảng 2 giây).
  - **Trình soạn thảo Prompt Text** (`PromptEditor`): bảng viền bo tròn. Ở **chế độ xem**: markdown được render với các token `{{variable}}` được tô sáng; khi di chuột qua hiện chip căn giữa **"Click to edit"** (`com_ui_click_to_edit`) và nút `EditIcon` (`com_ui_edit`). Ở **chế độ chỉnh sửa**: `TextareaAutosize` (`minRows=4`, `maxRows=16`, `font-mono`) với autofocus; thanh công cụ vẫn giữ dropdown **Special Variables**. Nhấn `Escape` hoặc mất focus để thoát chế độ chỉnh sửa và kích hoạt lưu.
  - Dropdown **Category**: cùng `CategorySelector` như khi tạo; thay đổi danh mục được lưu ngay khi chọn.
  - Trường **Description**: được điền sẵn từ `group.oneliner`; cập nhật được debounce 950 ms trước khi gọi API (`updateGroupMutation`).
  - Trường **Command**: được điền sẵn từ `group.command`; cập nhật được debounce 950 ms.
  - **Bảng Versions** (chỉ ở chế độ Advanced, `PromptsEditorMode.ADVANCED`): hiển thị ở breakpoint `lg` dưới dạng thanh bên phải (rộng 288–320 px); trên màn hình nhỏ hơn, truy cập qua nút **"Versions"** (`com_ui_versions`) mở ra ngăn kéo modal.
    - Huy hiệu đếm tiêu đề hiển thị tổng số phiên bản.
    - Mỗi phiên bản hiển thị dưới dạng `VersionCard` trong danh sách dạng dòng thời gian: số phiên bản, thời gian tạo (tương đối, ví dụ: "3 days ago") và huy hiệu.
    - Huy hiệu phiên bản: **Live** (`com_ui_live`, viên thuốc màu xanh lá với chấm nhấp nháy chậm) cho phiên bản production; **Latest** (`com_ui_latest`, viên thuốc màu xanh dương với biểu tượng tia sét) cho phiên bản mới nhất không phải production.
    - Nút **Make Production / Deploy** (`com_ui_make_production` / `com_ui_deploy`, biểu tượng `Rocket`): bị vô hiệu hóa nếu phiên bản đã chọn là production; khi nhấn gọi `useMakePromptProduction`.
  - **Nút chuyển đổi chế độ trình soạn thảo** (Simple vs Advanced): thanh bên phiên bản chỉ được render khi `editorMode === PromptsEditorMode.ADVANCED` (lưu trong trạng thái Recoil `store.promptsEditorMode`).
  - Cài đặt **Always Make Production** (`store.alwaysMakeProd`): khi bật, mỗi phiên bản mới tự động được đưa lên production ngay sau khi lưu.

- **Hành vi chức năng:**
  1. FR-1 — Thoát chế độ chỉnh sửa nội dung prompt (mất focus hoặc `Escape`) kích hoạt `addPromptToGroupMutation`, tạo một **phiên bản mới** trong cơ sở dữ liệu. Nội dung prompt hiện tại được so sánh với `selectedPrompt.prompt`; nếu không thay đổi, không có lần gọi API nào được thực hiện.
  2. FR-2 — Đổi tên nhóm gọi `updatePromptGroup` với `{ name: newValue }`. Trạng thái lưu chuyển qua `saving → saved → idle` (hoặc `error`) với bộ đếm hiển thị 2 giây.
  3. FR-3 — Thay đổi danh mục gọi `updateGroupMutation` với `{ name, category }` ngay khi chọn từ dropdown, độc lập với trạng thái dirty của form (trường danh mục đặt `shouldDirty: false` nên thay đổi chỉ danh mục không đánh dấu form là dirty).
  4. FR-4 — Thay đổi mô tả và lệnh được debounce 950 ms; các chỉnh sửa liên tiếp nhanh chóng dẫn đến một lần gọi API duy nhất với giá trị cuối cùng.
  5. FR-5 — Chọn một thẻ phiên bản trong bảng phiên bản sẽ tải nội dung của phiên bản đó vào trường form trình soạn thảo. Thẻ được chọn được tô sáng trực quan (nền xanh lá, dấu `CheckCircle2`).
  6. FR-6 — Nhấn **Deploy** trên phiên bản không phải production sẽ gọi `useMakePromptProduction`; khi thành công, huy hiệu phiên bản đổi thành **Live** và nhãn nút thay đổi thành nhãn trạng thái production (`com_ui_production`).
  7. FR-7 — Khi `alwaysMakeProd` là true, mỗi lần gọi `addPromptToGroupMutation` được theo sau ngay bởi `useMakePromptProduction` trên phiên bản vừa tạo.
  8. FR-8 — Điều hướng đến nhóm prompt khác sẽ đặt lại `selectionIndex` về 0 và `isEditing` về false.
  9. FR-9 — Người dùng chỉ đọc (không có quyền `EDIT`) thấy `PromptDetails` ở chế độ tĩnh; nội dung prompt, mô tả và lệnh được hiển thị nhưng không thể chỉnh sửa.

- **Trạng thái & trường hợp đặc biệt:**
  - Thay đổi chưa lưu: các thay đổi được lưu khi mất focus; không có nút "Save" rõ ràng cho nội dung prompt — điều hướng đi ngay sau khi chỉnh sửa mà không mất focus có thể loại bỏ chỉnh sửa đang thực hiện (cần xác minh thủ công trên sản phẩm đang chạy: liệu `onBlur` có kích hoạt đáng tin cậy khi thay đổi route trên tất cả các trình duyệt không).
  - Nội dung prompt trống: nếu người dùng xóa tất cả văn bản và mất focus, việc lưu bị bỏ qua (được bảo vệ bởi `if (!value) return`). Không có toast nào được hiển thị — comment `// TODO: show toast, cannot be empty` tồn tại trong code nhưng chưa được triển khai trong bản build hiện tại.
  - Lỗi lưu khi cập nhật tên: hiển thị `showToast` với `status: 'error'` và thông báo `com_ui_prompt_update_error`.
  - Bảng phiên bản trên di động: bảng trượt vào từ bên phải dưới dạng ngăn kéo modal với `role="dialog"`, `aria-modal="true"`. Focus bị giữ bên trong; `Escape` đóng bảng và trả focus về nút kích hoạt.
  - Trạng thái đang tải: component `Skeleton` lấp đầy khu vực trình soạn thảo trong khi `isLoadingPrompts` là true.

- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử người dùng chỉnh sửa nội dung prompt và nhấn Tab để rời đi, thì một phiên bản mới xuất hiện trong bảng phiên bản với huy hiệu **Latest**.
  2. AC-2 — Giả sử một phiên bản mới tồn tại và không phải production, khi người dùng nhấn **Deploy**, thì phiên bản đó nhận huy hiệu **Live** và huy hiệu **Live** trước đó bị xóa.
  3. AC-3 — Giả sử người dùng đổi tên prompt và nhấn `Enter`, khi API thành công, thì tiêu đề tên hiển thị giá trị đã cập nhật và biểu tượng `Check` xuất hiện khoảng 2 giây.
  4. AC-4 — Giả sử **Always Make Production** được bật, khi người dùng lưu một chỉnh sửa, thì phiên bản mới được đưa lên production ngay mà không cần deploy thủ công.
  5. AC-5 — Giả sử người dùng chỉ có quyền `VIEW` mở một prompt, thì thanh công cụ trình soạn thảo, nút chỉnh sửa và nút deploy trong bảng phiên bản đều không xuất hiện.

---

### Sử dụng Prompt trong Cuộc trò chuyện

- **Mục đích:** Chèn nội dung production của một prompt đã lưu (có thay thế biến nếu cần) vào ô nhập chat đang hoạt động và tùy chọn tự động gửi.
- **Điều kiện tiên quyết / truy cập:** Người dùng phải có quyền `PROMPTS › USE`. Nhóm prompt phải có prompt production được đặt (`productionPrompt.prompt` không trống).
- **Thành phần giao diện:**

  **Bảng lệnh (trong chat `PromptsCommand`):**
  - Được kích hoạt bằng cách gõ `/` trong textarea chat. Một popover xuất hiện phía trên ô nhập (`absolute bottom-28 z-10`).
  - Ô tìm kiếm: `placeholder` = `com_ui_command_usage_placeholder`, bên trong bảng bo tròn (`rounded-2xl`, `bg-surface-tertiary-alt`).
  - Danh sách ảo hóa các nhóm prompt khớp (`react-virtualized`); chiều cao hàng 44 px; chiều cao tối đa hiển thị 160 px.
  - Mỗi hàng được render dưới dạng `MentionItem` với `type="prompt"`, hiển thị biểu tượng nhóm, tên và `oneliner`/mô tả.
  - Điều hướng bàn phím: `ArrowUp` / `ArrowDown` di chuyển lựa chọn; `Enter` hoặc `Tab` chọn mục đang hoạt động; `Escape` hoặc `Backspace` (khi tìm kiếm trống) đóng popover.
  - Spinner hiển thị trong khi `isLoading && matches.length === 0`.

  **Thẻ prompt trong thư viện (ngữ cảnh chat):**
  - Nhấn vào thẻ trong bảng thư viện (khi `isChatRoute=true`) sẽ chèn nội dung prompt production trực tiếp vào chat.
  - Menu ba chấm (`Ellipsis`) trên mỗi thẻ: **Preview** (biểu tượng mắt), **Edit** (biểu tượng bút, nếu người dùng có quyền `EDIT`), **Delete** (biểu tượng thùng rác, nếu người dùng có quyền `DELETE`).

  **Hộp thoại xem trước (`PreviewPrompt`):**
  - Modal hiển thị `PromptDetails` với tiêu đề, nội dung production (markdown), bảng biến, chip lệnh và nút **Use Prompt** (`com_ui_use_prompt`, biểu tượng `Send`).
  - Nút **Share** cũng hiển thị nếu người dùng có quyền chia sẻ.

  **Nút chuyển đổi Auto-Send:**
  - Nút chuyển đổi có nhãn `com_nav_auto_send_prompts` (với hộp kiểm) trong thanh bên prompts. Khi hoạt động, chọn một prompt sẽ gọi `submitPrompt()`, hàm này gọi `submitMessage({ text: parsedText })` trong `useSubmitMessage.ts` để gửi tin nhắn ngay lập tức. Khi không hoạt động, `submitPrompt()` gọi `setActivePrompt(newText)` để đặt văn bản vào textarea mà không gửi.

- **Hành vi chức năng:**
  1. FR-1 — Gõ `/` trong textarea chat kích hoạt popover prompts; trường tìm kiếm nhận focus và được điền sẵn với bất kỳ văn bản nào được gõ sau `/`.
  2. FR-2 — Combobox khớp với tất cả các nhóm prompt (trường `value` là `group.command ?? group.name`; `label` bao gồm tiền tố lệnh, tên và one-liner).
  3. FR-3 — Chọn một prompt (Enter/Tab/nhấn) xóa ký tự `/` khỏi textarea thông qua `removeCharIfLast`, sau đó:
     - Nếu `detectVariables(group.productionPrompt.prompt)` là true → mở `VariableDialog`.
     - Ngược lại → gọi `submitPrompt(group.productionPrompt.prompt)` và ghi lại lượt sử dụng.
  4. FR-4 — Nhấn vào thẻ prompt trong bảng thư viện (route chat) theo logic phát hiện biến giống nhau (FR-3).
  5. FR-5 — Nhấn **Use Prompt** trong hộp thoại xem trước cũng theo logic phát hiện biến.
  6. FR-6 — `useRecordPromptUsage` được gọi với `group._id` mỗi khi sử dụng thành công (không có biến), và ở cuối lần gửi form biến.
  7. FR-7 — Trạng thái toggle **Auto-Send Prompts** được lưu trong Recoil (`store.autoSendPrompts`). Khi `autoSendPrompts` là true, `submitPrompt()` gọi `submitMessage({ text: parsedText })` trực tiếp (kích hoạt lần gọi API `ask()` ngay lập tức); khi false, nó gọi `setActivePrompt(newText)` để đặt văn bản vào textarea mà không gửi. Điểm sử dụng downstream nằm trong `useSubmitMessage.ts`, không phải trong `ChatForm`.
  8. FR-8 — Popover đóng khi nhấn `Escape`, khi `Backspace` với tìm kiếm trống, và khi mất focus (sau độ trễ 150 ms để cho phép các sự kiện nhấn chuột đăng ký).

- **Trạng thái & trường hợp đặc biệt:**
  - Không có prompt production được đặt: `text?.trim()` là falsy; nhấn vào thẻ không có tác dụng.
  - Nhóm prompt không có lệnh: trường `value` trong combobox lùi về `group.name`; tìm kiếm `/` vẫn khớp theo tên.
  - Hủy hộp thoại biến: textarea giữ nguyên nội dung trước đó; không có lượt sử dụng nào được ghi lại.
  - Đang tải popover: nếu truy vấn nhóm vẫn đang lấy dữ liệu, spinner được hiển thị trong thân popover.
- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử người dùng gõ `/` trong ô nhập chat, thì popover lệnh prompts xuất hiện với trường tìm kiếm.
  2. AC-2 — Giả sử người dùng gõ `/report`, thì chỉ các nhóm prompt có lệnh hoặc tên chứa "report" được liệt kê.
  3. AC-3 — Giả sử một prompt không có biến được chọn, thì nội dung prompt production được đặt vào ô nhập chat và popover đóng lại.
  4. AC-4 — Giả sử một prompt có biến được chọn, thì Hộp thoại điền biến mở ra trước khi bất kỳ văn bản nào được gửi.
  5. AC-5 — Giả sử người dùng chọn một prompt từ bảng thư viện trên một route chat, thì prompt production được chèn (hoặc hộp thoại biến được hiển thị) sử dụng logic giống như bảng lệnh.

---

### Chia sẻ Prompt

- **Mục đích:** Cho phép chủ sở hữu được cấp quyền của một nhóm prompt cấp cho người dùng hoặc nhóm khác quyền xem hoặc chỉnh sửa prompt, và tùy chọn đặt nó ở chế độ công khai (hiển thị cho tất cả người dùng).
- **Điều kiện tiên quyết / truy cập:**
  - Nút **Share** chỉ được render khi tất cả các điều kiện sau đây đúng:
    1. Người dùng hiện tại là `author` của nhóm prompt, hoặc có `SystemRoles.ADMIN`, hoặc có `PermissionBits.SHARE` trên tài nguyên.
    2. Người dùng có quyền toàn cục `PROMPTS › SHARE`.
    3. Nhóm prompt đã được tải đầy đủ (`!isLoadingGroup`).
  - Ít nhất một trong `hasPeoplePickerAccess` (tìm kiếm người dùng/nhóm) hoặc `canSharePublic` phải là true để hộp thoại chia sẻ hoạt động.
- **Thành phần giao diện:**
  - Nút **Share**: chỉ biểu tượng (`Share2Icon`), `size="icon"`, `variant="outline"`, `size=9`, tooltip `com_ui_share`. Nằm trong thanh `HeaderActions` (trình soạn thảo prompt) và trong `PromptActions` (hộp thoại xem trước).
  - **Hộp thoại Share** (`GenericGrantAccessDialog`): modal với tiêu đề `com_ui_share_var` (ví dụ: "Share {tên prompt}"), biểu tượng `Users`.
  - **Phần tìm kiếm người dùng** (`UnifiedPeopleSearch`): trường tìm kiếm có nhãn `com_ui_search_people_placeholder`; chỉ hiển thị khi `hasPeoplePickerAccess` là true.
  - **Danh sách người được cấp quyền** (`SelectedPrincipalsList`): hiển thị mỗi người được cấp quyền với avatar, tên, bộ chọn vai trò (`AccessRolesPicker`) và nút xóa.
  - **Phần Public Access** (`PublicSharingToggle`): chỉ hiển thị khi `canSharePublic` là true.
    - Toggle có nhãn **"Share everyone"** (`com_ui_share_everyone`) với biểu tượng `Globe` và thẻ thông tin khi di chuột.
    - Khi bật: bộ chọn cấp độ quyền **Everyone Permission Level** (`com_ui_everyone_permission_level`) xuất hiện với hiệu ứng chuyển tiếp có animation.
  - Biểu ngữ cảnh báo: hiển thị khi `hasChanges && !hasAtLeastOneOwner` — `com_ui_at_least_one_owner_required`.
  - Nút **Cancel** (`com_ui_cancel`) và nút **Save Changes** (`com_ui_save_changes`, bị vô hiệu hóa cho đến khi có thay đổi hoặc trong khi đang lưu).
  - Trạng thái trống (chưa có chia sẻ): thẻ viền đứt nét với biểu tượng `Users`, `com_ui_no_individual_access`, `com_ui_search_above_to_add_people`.
- **Hành vi chức năng:**
  1. FR-1 — Mở hộp thoại sẽ tải các quyền hiện tại của nhóm prompt (`useResourcePermissionState`); các người được cấp quyền hiện có được hiển thị với `isExisting: true`.
  2. FR-2 — Tìm kiếm và chọn một người dùng hoặc nhóm sẽ thêm họ vào danh sách `allShares` cục bộ với `isExisting: false` và vai trò người xem mặc định.
  3. FR-3 — Thay đổi vai trò của một người được cấp quyền cập nhật trạng thái cục bộ; không có lần gọi API nào được thực hiện cho đến khi nhấn **Save Changes**.
  4. FR-4 — Nhấn nút xóa sẽ lọc bỏ người được cấp quyền khỏi `allShares` cục bộ.
  5. FR-5 — Bật toggle **Share everyone** đánh dấu `isPublic = true`; bộ chọn cấp độ quyền trở nên hiển thị với vai trò người xem mặc định.
  6. FR-6 — Nhấn **Save Changes** gọi `updatePermissionsMutation` với `{ updated, removed, public, publicAccessRoleId }` được tính từ việc so sánh `allShares` với `currentShares`. Khi thành công: toast `com_ui_permissions_updated_success`; khi lỗi: toast `com_ui_permissions_failed_update`.
  7. FR-7 — Nút **Save Changes** bị vô hiệu hóa khi không có thay đổi nào, khi mutation đang thực thi, hoặc khi có thay đổi nhưng không có người được cấp quyền nào giữ vai trò chủ sở hữu.
  8. FR-8 — Nhấn **Cancel** đặt lại trạng thái cục bộ về các quyền đã lấy lần cuối và đóng hộp thoại.
  9. FR-9 — Các nhóm prompt được chia sẻ với tất cả người dùng (`isPublic: true`) hiển thị huy hiệu `EarthIcon` trên thẻ danh sách với tooltip `com_ui_sr_global_prompt`. Các prompt được chia sẻ bởi người dùng khác hiển thị huy hiệu biểu tượng `User` với tooltip `com_ui_by_author`.
- **Trạng thái & trường hợp đặc biệt:**
  - Hộp thoại mở trong khi đang tải quyền: hiển thị placeholder skeleton cho danh sách người được cấp quyền.
  - Lỗi tải quyền: hiển thị lỗi nội tuyến `com_ui_permissions_failed_load` thay cho thân hộp thoại.
  - Tất cả chủ sở hữu bị xóa: biểu ngữ cảnh báo xuất hiện và **Save Changes** bị vô hiệu hóa.
  - Người dùng không có quyền people-picker nhưng có thể chia sẻ công khai: chỉ phần Public Access được hiển thị.
- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử tác giả mở hộp thoại chia sẻ, thì hộp thoại hiển thị với các người được cấp quyền hiện có và vai trò của họ.
  2. AC-2 — Giả sử tác giả tìm kiếm và chọn một người dùng, khi nhấn **Save Changes**, thì người dùng được cấp quyền truy cập và toast thành công được hiển thị.
  3. AC-3 — Giả sử toggle **Share everyone** được bật và lưu, thì thẻ prompt trong thư viện của người dùng khác hiển thị huy hiệu `EarthIcon`.
  4. AC-4 — Giả sử tất cả chủ sở hữu bị xóa khỏi danh sách, thì **Save Changes** bị vô hiệu hóa và cảnh báo yêu cầu chủ sở hữu hiển thị.
  5. AC-5 — Giả sử người dùng không phải tác giả và không có quyền `SHARE` xem prompt, thì không có nút Share nào được render.

---

### Xóa Prompt

- **Mục đích:** Xóa vĩnh viễn một nhóm prompt (và tất cả các phiên bản của nó) khỏi thư viện.
- **Điều kiện tiên quyết / truy cập:** Người dùng phải có `PermissionBits.DELETE` trên nhóm prompt cụ thể (kiểm tra thông qua `useResourcePermissions`). Có hai luồng xóa riêng biệt:
  1. **Từ trang trình soạn thảo prompt** (component `DeletePrompt` trong `HeaderActions`): xóa phiên bản đang được chọn (một phiên bản prompt đơn lẻ, không phải toàn bộ nhóm).
  2. **Từ thẻ danh sách thư viện** (component `ChatGroupItem`): xóa toàn bộ **nhóm** prompt.
- **Thành phần giao diện:**
  - Nút **Delete** (tiêu đề trình soạn thảo): biểu tượng `Trash2`, `variant="destructive"`, `size="icon"`, `size=9`, tooltip `com_ui_delete`. Ẩn khi `canDelete` là false.
  - Mục menu **Delete** (menu ba chấm thẻ danh sách): biểu tượng `Trash` + nhãn `com_ui_delete`.
  - **Hộp thoại xác nhận** (luồng trình soạn thảo — `OGDialogTemplate`):
    - Tiêu đề: `com_ui_delete_prompt`
    - Nội dung: `com_ui_delete_confirm_prompt_version_var` với `{0: promptName}`.
    - Nút **Delete**: `bg-surface-destructive hover:bg-surface-destructive-hover text-white`.
    - Nút **Cancel** (`com_ui_cancel`) được hiển thị mặc định (`OGDialogTemplate` mặc định `showCancelButton=true`). `showCloseButton={false}` chỉ loại bỏ biểu tượng X trên tiêu đề; nút Cancel và thao tác nhấn ra ngoài để đóng (mặc định của Radix Dialog) vẫn hoạt động.
  - **Hộp thoại xác nhận** (luồng thẻ danh sách — `OGDialogTemplate`):
    - Tiêu đề: `com_ui_delete_prompt`
    - Nội dung: nhãn sử dụng `com_ui_prompt_delete_confirm` với `{0: group.name}`.
    - Nút **Delete** với `variant="destructive"`; hiển thị `Spinner` trong khi `deleteGroup.isLoading`.
- **Hành vi chức năng:**
  1. FR-1 — Trong trình soạn thảo, nhấn nút **Delete** mở hộp thoại xác nhận; xác nhận gọi `useDeletePrompt` với `{ _id: promptId, groupId }`.
  2. FR-2 — Trong thẻ danh sách, chọn **Delete** từ menu overflow đặt `deleteOpen: true`; xác nhận gọi `useDeletePromptGroup` với `{ id: group._id }`.
  3. FR-3 — Khi xóa nhóm thành công từ danh sách:
     - Thông báo live polite được phát: `com_ui_prompt_deleted_group` với `{0: group.name}`.
     - Nếu nhóm bị xóa là prompt đang mở trong route `/prompts/{id}`, router điều hướng đến `/prompts/new`.
  4. FR-4 — Khi xóa nhóm gặp lỗi: toast với `status: 'error'` và thông báo `com_ui_prompt_delete_error`.
  5. FR-5 — Nút **Delete** trong trình soạn thảo bị vô hiệu hóa (`disabled={isLoadingGroup || !promptId}`) trong khi nhóm đang tải hoặc chưa giải quyết được ID phiên bản.
  6. FR-6 — Xóa một phiên bản đơn lẻ (luồng trình soạn thảo) xóa phiên bản đó khỏi danh sách phiên bản nhưng giữ nguyên nhóm; nếu phiên bản bị xóa là phiên bản production, con trỏ production được cập nhật phía máy chủ (cần xác minh thủ công trên sản phẩm đang chạy: hành vi API chính xác — liệu `productionId` bị xóa hay được gán lại — khi phiên bản production bị xóa).
- **Trạng thái & trường hợp đặc biệt:**
  - Đang xóa: nút **Delete** trong thẻ danh sách hiển thị `Spinner` và bị ngầm chặn cho đến khi mutation giải quyết xong.
  - Nhóm prompt không tìm thấy sau khi xóa: router thay thế mục lịch sử hiện tại bằng `/prompts/new`.
  - Người dùng không có quyền `DELETE`: nút **Delete** trong tiêu đề trình soạn thảo không được render; mục **Delete** vắng mặt trong dropdown thẻ danh sách.
- **Tiêu chí chấp nhận:**
  1. AC-1 — Giả sử người dùng có quyền `DELETE` và nhấn **Delete** trên thẻ nhóm prompt, khi hộp thoại xác nhận xuất hiện và người dùng xác nhận, thì nhóm bị xóa khỏi danh sách và thông báo live được phát.
  2. AC-2 — Giả sử nhóm bị xóa đang mở trong trình soạn thảo, khi xóa thành công, thì trình duyệt điều hướng đến `/prompts/new`.
  3. AC-3 — Giả sử người dùng không có quyền `DELETE` xem thẻ prompt, thì không có tùy chọn **Delete** nào xuất hiện trong menu overflow của thẻ.
  4. AC-4 — Giả sử xảy ra lỗi trong quá trình xóa, thì một toast với `status: 'error'` được hiển thị và nhóm vẫn còn trong danh sách.
