## Endpoint, Chọn Model & Tham Số

Phần này tài liệu hóa bộ chọn endpoint, bộ chọn model, bảng tham số hội thoại và quản lý preset cho triển khai NuFi Chat. Cấu hình đã triển khai (`librechat.yaml`) bật đúng hai endpoint — **Nufi** (endpoint tương thích OpenAI tùy chỉnh) và **Agents** — và đặt `endpointsMenu`, `modelSelect`, `parameters`, và `presets` đều là `true`.

---

### Bộ Chọn Endpoint & Model (Dropdown Kết Hợp)

#### Mục đích

Cung cấp một điều khiển thống nhất duy nhất — được hiển thị dưới dạng nút kích hoạt hình viên thuốc trong tiêu đề hội thoại — qua đó người dùng chọn cả endpoint (Nufi hoặc Agents) và, với các endpoint có model, model cụ thể sẽ sử dụng. Tổ hợp endpoint/model đã chọn được áp dụng ngay lập tức vào hội thoại đang hoạt động.

#### Điều kiện tiên quyết / truy cập

- Người dùng đã xác thực và có ít nhất một hội thoại đang mở (kể cả trạng thái trống "hội thoại mới").
- `interface.endpointsMenu: true` và `interface.modelSelect: true` được đặt trong `librechat.yaml` (cả hai đều được đặt trong cấu hình của NuFi).
- Bộ chọn chỉ bị ẩn khi cả `modelSelect: false` lẫn không có Model Specs nào được cấu hình — điều này không áp dụng trong trường hợp này.

#### Thành phần giao diện

- **Nút kích hoạt (Trigger button)** — nút hình viên thuốc trong tiêu đề hội thoại (`aria-label="Select a model"`). Hiển thị:
  - Icon endpoint/model (icon đã cấu hình cho endpoint đang chọn, hoặc icon Bot mặc định).
  - **Nhãn hiển thị (display label)**: với endpoint Nufi, chuỗi ID model thô; với endpoint Agents, tên agent. Hiển thị dự phòng là `"Select a model"` (khóa i18n `com_ui_select_model`) khi chưa chọn gì.
- **Bảng dropdown** — mở bên dưới nút kích hoạt. Chứa:
  - Một **combobox tìm kiếm** (`id="model-search"`, nhãn truy cập từ `com_endpoint_search_models`; thuộc tính `placeholder` thực tế là một khoảng trắng `" "`).
  - **Các mục endpoint** — một hàng có thể mở rộng cho mỗi endpoint; với các endpoint có model, hàng mở rộng thành submenu.
  - Trong submenu Nufi: một **trường tìm kiếm theo endpoint** (placeholder `com_endpoint_search_endpoint_models` điền nhãn endpoint), rồi đến danh sách các hàng model.
  - Trong submenu Agents: trường tìm kiếm theo endpoint (placeholder `com_endpoint_search_var` điền "Agents"), rồi đến danh sách các hàng agent.
- **Icon dấu tích (Checkmark icon)** (`CheckCircle2`) — xuất hiện bên cạnh mục đang chọn; một span `VisuallyHidden` thông báo `com_a11y_selected` cho trình đọc màn hình.
- **Nút Pin / Unpin** — xuất hiện khi di chuột hoặc focus vào hàng model; bật/tắt model làm yêu thích. Aria-label là `com_ui_pin` / `com_ui_unpin`.
- **Nút bánh răng cài đặt (Settings gear button)** (`SettingsIcon`) — xuất hiện bên cạnh nhãn endpoint chỉ khi endpoint yêu cầu khóa API do người dùng cung cấp. Không áp dụng cho endpoint Nufi hoặc Agents trong triển khai NuFi (khóa được cấu hình phía server).

#### Hành vi chức năng

**FR-1.** Nhấn vào nút kích hoạt sẽ mở dropdown. Nhấn lần nữa, hoặc nhấn ra ngoài dropdown (trừ dialog và menu preset), sẽ đóng dropdown.

**FR-2.** Khi dropdown đang mở, gõ vào trường tìm kiếm toàn cục sẽ lọc tất cả endpoint và model theo thời gian thực (debounced 200 ms). Kết quả hiển thị dạng danh sách phẳng được nhóm theo tiêu đề endpoint. Nếu truy vấn khớp nhãn endpoint nhưng không khớp ID model nào của nó, tất cả model thuộc endpoint đó sẽ hiển thị. Nếu truy vấn không khớp nhãn endpoint lẫn model nào, không có kết quả nào hiển thị và văn bản `com_files_no_results` được hiển thị. Một live-region (`role="alert" aria-live="polite"`) thông báo số lượng kết quả.

**FR-3.** **Hàng endpoint Nufi** mở rộng thành sub-panel hiển thị các model được tải từ backend (fetch: true trong `librechat.yaml`). Trường tìm kiếm theo endpoint trong sub-panel này lọc model Nufi theo chuỗi đã gõ (khớp chuỗi con không phân biệt hoa thường).

**FR-4.** Nhấn vào hàng model trong Nufi sẽ chọn endpoint và model đó, đồng thời bắt đầu hoặc tiếp tục hội thoại với cài đặt đó ngay lập tức. Nút kích hoạt cập nhật để phản ánh lựa chọn mới.

**FR-5.** **Hàng endpoint Agents** mở rộng thành sub-panel liệt kê các agent khả dụng theo tên (được giải quyết qua bản đồ agents). Chọn một agent đặt `endpoint = "agents"` và `agent_id = <id agent đã chọn>` cho hội thoại.

**FR-6.** Thông báo cho trình đọc màn hình: sau khi chọn một model, một thông báo lịch sự được phát ra sử dụng `com_ui_model_selected` kèm tên hiển thị.

**FR-7.** Mỗi hàng model có nút bật/tắt pin/unpin cho yêu thích. Model đã ghim hiển thị icon pin liên tục (luôn hiển thị); model chưa ghim chỉ hiện icon khi di chuột/focus.

#### Trạng thái & trường hợp đặc biệt

- **Backend không khả dụng (endpoint model Nufi lỗi):** Danh sách model của Nufi chỉ chứa mục placeholder `"loading..."` (mục mặc định duy nhất được cấu hình trong `librechat.yaml`). Dropdown hiển thị mục đơn này. Không có spinner hay thông báo lỗi trong dropdown; chuỗi placeholder là phản hồi duy nhất. (cần xác minh thực tế trên sản phẩm đang chạy: liệu spinner tải hay trạng thái lỗi có được hiển thị ngoài model placeholder duy nhất hay không — phân tích mã tĩnh nhất quán với việc chỉ hiển thị `"loading..."`.)
- **Backend trả về danh sách model rỗng:** Nếu backend trả về mảng rỗng, dropdown của Nufi không hiển thị hàng model nào (sub-panel trống). Không có thông báo "không có model" rõ ràng nào được hiển thị trong luồng code này.
- **Endpoint Assistants đang tải model:** Trong khi dữ liệu assistants đang được tải (`isAssistantsEndpoint` trả về true và `endpoint.models === undefined`), một `Spinner` được hiển thị trong sub-panel Assistants thay vì các hàng model. Điều này áp dụng cho các endpoint legacy `assistants` / `azureAssistants`, không áp dụng cho endpoint Agents.
- **Chưa chọn endpoint:** Nút kích hoạt hiển thị chuỗi đã bản địa hóa `"Select a model"`.
- **modelSelect: false + không có Model Specs:** Toàn bộ component bộ chọn không được hiển thị. Không áp dụng trong triển khai NuFi.

#### Tiêu chí chấp nhận

**AC-1.** Giả sử trang đã tải và đã xác thực, khi người dùng xem tiêu đề hội thoại, thì nút kích hoạt bộ chọn model hiển thị và cho thấy nhãn endpoint đang chọn hoặc "Select a model".

**AC-2.** Giả sử bộ chọn đang đóng, khi người dùng nhấn nút kích hoạt, thì dropdown mở ra và liệt kê hàng endpoint "Nufi" và "Agents".

**AC-3.** Giả sử dropdown đang mở, khi người dùng gõ một phần tên model vào ô tìm kiếm toàn cục, thì chỉ các endpoint và model khớp xuất hiện trong vòng 200 ms.

**AC-4.** Giả sử dropdown đang mở và người dùng gõ một chuỗi không có kết quả khớp, khi tìm kiếm hoàn tất, thì văn bản "No results" (hoặc bản tương đương đã bản địa hóa) được hiển thị.

**AC-5.** Giả sử người dùng nhấn vào một model trong Nufi, khi lựa chọn hoàn tất, thì nút kích hoạt cập nhật hiển thị ID model đã chọn và endpoint cùng model của hội thoại được đặt tương ứng.

**AC-6.** Giả sử endpoint backend model Nufi không khả dụng, khi người dùng mở sub-panel Nufi, thì mục "loading..." được hiển thị là tùy chọn model duy nhất và không có lỗi không xử lý nào xảy ra.

**AC-7.** Giả sử một model đã được chọn, khi người dùng kích hoạt nút bật/tắt pin cho model đó, thì model được đánh dấu là yêu thích và icon pin luôn hiển thị liên tục trên hàng đó.

---

### Bảng Tham Số Hội Thoại

#### Mục đích

Hiển thị các tham số suy luận cấp model — temperature, top-p, các penalty, giới hạn token, và các tùy chọn phụ trợ — để người dùng có thể tinh chỉnh hành vi của model theo từng hội thoại mà không cần rời khỏi giao diện chat. Các tham số được áp dụng ngay lập tức cho hội thoại đang hoạt động và tồn tại trong suốt vòng đời của hội thoại (hoặc đến khi đặt lại).

#### Điều kiện tiên quyết / truy cập

- `interface.parameters: true` được đặt trong `librechat.yaml` (đã đặt).
- Endpoint của hội thoại đang hoạt động là "param endpoint": cả `custom` (Nufi) và `agents` đều đủ điều kiện thông qua tập `paramEndpoints` được định nghĩa trong `schemas.ts`.
- Tham số của endpoint Nufi (`custom`) được truy cập qua **thanh bên phải (SidePanel right rail)** — icon `SlidersHorizontal` trong điều hướng của SidePanel bên phải, mở bảng **Parameters** (`Panel.tsx`). Liên kết này được thêm vào nav khi `isParamEndpoint === true && !isAgentsEndpoint` (`useSideNavLinks.ts:181-194`).
- Nút bánh răng trong tiêu đề (`Settings2`, `id="parameters-button"`) mở OptionsPopover **chỉ** được hiển thị khi `interface.parameters === true` VÀ `paramEndpoint === false` (tức là endpoint KHÔNG nằm trong `paramEndpoints`). Do cả `custom` (Nufi) và `agents` đều nằm trong `paramEndpoints`, nút bánh răng trong tiêu đề **không bao giờ được hiển thị** cho cả hai endpoint trong triển khai NuFi.

#### Thành phần giao diện

Có hai bề mặt riêng biệt hiển thị tham số:

**(a) Bảng Parameters trong SidePanel trong hội thoại (`Panel.tsx`)** — đường dẫn chính cho endpoint Nufi:
- Icon `SlidersHorizontal` trong nav của SidePanel bên phải mở bảng **Parameters**.
- Bảng hiển thị tham số từ `paramSettings[EModelEndpoint.custom]` (mảng `openAI` phẳng, `parameterSettings.ts`).
- Bố cục: **lưới CSS 2 cột** (`grid-cols-2`, `Panel.tsx:146`).
- Chứa nút chính **"Save as preset"** và nút **"Reset Model Parameters"** (`RotateCcw`).

**(b) Hộp thoại Edit Preset (component `EndpointSettings`)** — dùng khi chỉnh sửa preset đã lưu:
- Sử dụng `presetSettings[EModelEndpoint.custom]` = `openAIColumns` → `OpenAISettings`.
- Hiển thị **bố cục hai cột** với Cột 1 (3/5 chiều rộng trên `md+`) từ `openAICol1` và Cột 2 (2/5 chiều rộng trên `md+`) từ `openAICol2`.
- Vùng chứa có thể cuộn, chiều cao tối đa **500 px (trên thiết bị di động)** / **350 px (trên máy tính bảng/máy tính để bàn, từ breakpoint `md:` trở lên)**.

#### Tham Số — Cột 1

| Khóa tham số | Nhãn giao diện (`labelCode`) | Component | Mặc định | Khoảng / Tùy chọn | Mã mô tả |
|---|---|---|---|---|---|
| `model` | `com_ui_model` | `dropdown` | (model hiện tại) | Model tải từ backend | Bộ chọn model (khi hiển thị trong ngữ cảnh chỉnh sửa preset) |
| `modelLabel` | `com_endpoint_custom_name` | `input` | `""` (trống) | Văn bản tự do | Ghi đè tên hiển thị cho hội thoại này (Custom Name) |
| `promptPrefix` | `com_endpoint_prompt_prefix` | `textarea` | `""` (trống) | Văn bản tự do | Hướng dẫn hệ thống / tùy chỉnh được thêm vào đầu mỗi yêu cầu (Prompt Prefix) |

#### Tham Số — Cột 2

| Khóa tham số | Nhãn giao diện (`labelCode`) | Component | Mặc định | Khoảng / Tùy chọn | Mã mô tả |
|---|---|---|---|---|---|
| `maxContextTokens` | `com_endpoint_context_tokens` | `input` (number) | mặc định hệ thống | Số nguyên dương bất kỳ | Số token tối đa được truyền làm cửa sổ ngữ cảnh (Context Tokens) |
| `max_tokens` | `com_endpoint_max_output_tokens` | `input` (number) | undefined (chưa đặt) | Số nguyên dương bất kỳ | Số token tối đa model có thể tạo ra (Max Output Tokens) |
| `temperature` | `com_endpoint_temperature` | `slider` | `1` | 0 – 2, bước 0.01 | Độ ngẫu nhiên của đầu ra (`com_endpoint_openai_temp`) (Temperature) |
| `top_p` | `com_endpoint_top_p` | `slider` | `1` | 0 – 1, bước 0.01 | Lấy mẫu nucleus (`com_endpoint_anthropic_topp`) (Top P) |
| `frequency_penalty` | `com_endpoint_frequency_penalty` | `slider` | `0` | -2 – 2, bước 0.01 | Phạt token lặp lại (`com_endpoint_openai_freq`) (Frequency Penalty) |
| `presence_penalty` | `com_endpoint_presence_penalty` | `slider` | `0` | -2 – 2, bước 0.01 | Phạt lặp lại chủ đề (`com_endpoint_openai_pres`) (Presence Penalty) |
| `stop` | `com_endpoint_stop` | `tags` | `[]` | 0 – 4 chuỗi dừng | Chuỗi dừng (`com_endpoint_openai_stop`) (Stop) |
| `resendFiles` | `com_endpoint_plug_resend_files` | `switch` | `true` (bật) | boolean | Đính kèm lại tệp đã tải lên trong mỗi lượt (`com_endpoint_openai_resend_files`) |
| `imageDetail` | `com_endpoint_plug_image_detail` | `slider` (enum) | `auto` | low / auto / high | Độ phân giải ảnh cho vision (`com_endpoint_openai_detail`) |
| `reasoning_effort` | `com_endpoint_reasoning_effort` | `slider` (enum) | `unset` (auto) | unset / none / minimal / low / medium / high / xhigh | Độ sâu suy luận (`com_endpoint_openai_reasoning_effort`) |
| `reasoning_summary` | `com_endpoint_reasoning_summary` | `slider` (enum) | `""` (rỗng / `com_ui_unset`, hiển thị là "Unset") | none / auto / concise / detailed | Mức độ chi tiết tóm tắt suy luận (`com_endpoint_openai_reasoning_summary`) |
| `verbosity` | `com_endpoint_verbosity` | `slider` (enum) | `none` | none / low / medium / high | Mức độ chi tiết đầu ra (`com_endpoint_openai_verbosity`) |
| `useResponsesApi` | `com_endpoint_use_responses_api` | `switch` | `false` | boolean | Sử dụng OpenAI Responses API (`com_endpoint_openai_use_responses_api`) |
| `web_search` | `com_ui_web_search` | `switch` | `false` | boolean | Bật công cụ tìm kiếm web (`com_endpoint_openai_use_web_search`) |
| `disableStreaming` | `com_endpoint_disable_streaming_label` | `switch` | `false` | boolean | Tắt streaming token (`com_endpoint_disable_streaming`) |
| `fileTokenLimit` | `com_ui_file_token_limit` | `input` (number) | undefined | Số nguyên dương bất kỳ | Giới hạn token theo tệp để đưa vào ngữ cảnh (`com_ui_file_token_limit_desc`) |

> Lưu ý: `reasoning_effort`, `reasoning_summary`, `verbosity`, `useResponsesApi`, và `web_search` là một phần của danh sách tham số `openAI` trong code và do đó xuất hiện trong bảng tham số cho endpoint `custom` (Nufi). Liệu model backend Nufi đã cấu hình có hỗ trợ tất cả các tham số này hay không phụ thuộc vào cài đặt backend; các tham số không được hỗ trợ thường bị hầu hết các server tương thích OpenAI bỏ qua.

#### Điều Khiển Đặt Lại & Lưu Dưới Dạng Preset

Nằm bên dưới lưới tham số trong ngữ cảnh OptionsPopover / Side Panel:

- Nút **"Reset Model Parameters"** (`com_ui_reset_var` với `com_ui_model_parameters`) — xóa tất cả ghi đè cấp hội thoại không bị loại trừ, đưa tham số về giá trị mặc định. Icon: `RotateCcw`.
- Nút **"Save as preset"** — mở `SaveAsPresetDialog` (xem phần Presets) được điền sẵn với giá trị tham số của hội thoại hiện tại.

#### Hành vi chức năng

**FR-1.** Nhấn icon `SlidersHorizontal` trong nav của SidePanel bên phải sẽ mở bảng Parameters cho endpoint Nufi. Nút bánh răng trong tiêu đề (`id="parameters-button"`) không được hiển thị cho endpoint Nufi hoặc Agents (chỉ được hiển thị khi endpoint đang hoạt động không nằm trong `paramEndpoints`).

**FR-2.** Mỗi tham số slider hiển thị một thanh trượt ngang có thể kéo cùng một ô nhập số (trong giao diện `Advanced.tsx` cũ hơn) hoặc một component slider động (trong giao diện SidePanel `Panel.tsx`). Kéo hoặc gõ cập nhật giá trị ngay lập tức; thay đổi được debounced trước khi ghi vào trạng thái hội thoại.

**FR-3.** Double-click vào slider sẽ đặt lại tham số riêng lẻ đó về giá trị mặc định. Trong đường dẫn SidePanel (endpoint Nufi), hành vi này được thực hiện trong `DynamicSlider.tsx` qua `onDoubleClick`.

**FR-4.** Chuỗi Stop (Stop sequences) chấp nhận tối đa 4 mục được nhập dưới dạng tags (nhập kiểu chip). Các tag hiện có có thể được xóa từng cái.

**FR-5.** Các tham số switch boolean (`resendFiles`, `useResponsesApi`, `web_search`, `disableStreaming`) bật/tắt; chúng không ảnh hưởng đến trạng thái nhóm slider.

**FR-6.** Các tham số slider enum (`imageDetail`, `reasoning_effort`, `reasoning_summary`, `verbosity`) chụp vào các vị trí có nhãn rời rạc; các giá trị float trung gian không hợp lệ.

**FR-7.** Nhấn "Reset Model Parameters" gọi `resetParameters`, xóa tất cả khóa tham số không bị loại trừ khỏi đối tượng hội thoại, khiến giao diện trở về mặc định ở lần hiển thị tiếp theo.

**FR-8.** Bảng tham số chỉ đọc khi prop `readonly` được đặt — tất cả ô nhập và slider bị vô hiệu hóa. (cần xác minh thực tế trên sản phẩm đang chạy: những bề mặt nào truyền `readonly: true` — không có vị trí gọi nào truyền `readonly={true}` trong đường dẫn SidePanel dựa trên phân tích tĩnh; có thể được kích hoạt bởi chế độ chỉ đọc của hội thoại được chia sẻ)

**FR-9.** Khi endpoint thay đổi (ví dụ: chuyển từ Nufi sang Agents), hiệu ứng tham số chạy, xóa các khóa không còn trong tập tham số mới, và bảng hiển thị lại với các điều khiển của endpoint mới.

#### Trạng thái & trường hợp đặc biệt

- **Chưa chọn endpoint:** Component EndpointSettings trả về `null` và không có bảng tham số nào được hiển thị.
- **Nút bánh răng trong tiêu đề hiển thị hay ẩn:** Nút bánh răng trong tiêu đề (`id="parameters-button"`) chỉ được hiển thị khi `paramEndpoint === false` (`HeaderOptions.tsx`). Cả `custom` (Nufi) và `agents` đều nằm trong `paramEndpoints`, nên `paramEndpoint === true` với cả hai — nghĩa là **nút bánh răng không bao giờ được hiển thị** cho cả hai endpoint trong triển khai NuFi. Tham số của endpoint Nufi được truy cập qua thanh bên phải của SidePanel (icon `SlidersHorizontal`); tham số của endpoint Agents được truy cập qua SidePanel agent builder.
- **Ô nhập số ngoài khoảng:** Component `DynamicInput` không áp đặt min/max ở cấp độ giao diện cho các trường số; các giá trị ngoài khoảng được truyền đến backend và backend có thể từ chối.
- **`maxContextTokens` hoặc `max_tokens` bị thiếu:** Nếu để trống (undefined), backend sử dụng mặc định riêng của nó; văn bản placeholder là `com_nav_theme_system` đã bản địa hóa ("System").

#### Tiêu chí chấp nhận

**AC-1.** Giả sử endpoint Nufi đang hoạt động, khi người dùng nhấn icon `SlidersHorizontal` trong SidePanel bên phải, thì bảng Parameters mở ra và hiển thị lưới tham số 2 cột.

**AC-2.** Giả sử bảng Parameters trong SidePanel đang mở, khi người dùng kéo thanh trượt Temperature từ 1.0 xuống 0.5 và gửi tin nhắn, thì yêu cầu API bao gồm `temperature: 0.5`.

**AC-3.** Giả sử người dùng đã đặt Temperature thành 0.7, khi họ double-click vào thanh trượt Temperature, thì giá trị trả về 1.0.

**AC-4.** Giả sử người dùng nhập chuỗi "END" vào trường Stop sequences và nhấn Enter, thì một chip có nhãn "END" xuất hiện và mảng `stop` của hội thoại chứa `"END"`.

**AC-5.** Giả sử các tham số đã được chỉnh sửa, khi người dùng nhấn "Reset Model Parameters", thì tất cả điều khiển tham số trở về giá trị mặc định.

**AC-6.** Giả sử temperature được đặt thành 1.5 (trong khoảng hợp lệ), khi người dùng mở lại bảng Parameters trong SidePanel, thì thanh trượt hiển thị 1.5 (trạng thái tồn tại trong suốt vòng đời hội thoại).

**AC-7.** Giả sử endpoint Nufi hoặc Agents được chọn, khi người dùng xem tiêu đề hội thoại, thì không có nút bánh răng tham số nào được hiển thị (cả hai endpoint đều nằm trong `paramEndpoints`, nên `paramEndpoint === true` sẽ ẩn nút trong tiêu đề). Tham số của Nufi được truy cập qua thanh bên phải của SidePanel; tham số của Agents được truy cập qua SidePanel agent builder.

---

### Presets

#### Mục đích

Presets là các bản chụp có tên của endpoint, model và cài đặt tham số của một hội thoại. Chúng có thể được áp dụng cho bất kỳ hội thoại mới hoặc hiện có nào để khôi phục một cấu hình đã biết chỉ với một cú nhấn. Menu presets cung cấp đầy đủ các thao tác CRUD cùng xuất/nhập.

#### Điều kiện tiên quyết / truy cập

- `interface.presets: true` được đặt trong `librechat.yaml` (đã đặt).
- Người dùng phải đã xác thực; presets được lưu trữ theo người dùng trên server.
- Nút Presets (icon `BookCopy`, `id="presets-button"`, `aria-label` từ `com_endpoint_examples`, `data-testid="presets-button"`) hiển thị trong tiêu đề hội thoại khi presets được bật.
- Lưu ý: Presets của endpoint Agents bị loại trừ một cách rõ ràng khỏi hộp thoại Edit Preset (component trả về `null` nếu `isAgentsEndpoint(endpoint)`); presets của endpoint Nufi được hỗ trợ đầy đủ.

#### Thành phần giao diện

**Menu Presets (popover):**
- **Hàng tiêu đề:** Hiển thị `com_endpoint_preset_default_item` ("Default:") theo sau là `<title>` (ví dụ: `Default: Low Temp`) khi có preset mặc định, hoặc `com_endpoint_preset_default_none` ("No default preset active.") khi không có preset mặc định nào, ở bên trái. Ở bên phải: nút **"Clear All"** (icon document-x + `com_ui_clear_all`) và một ô **File Upload** ẩn (để nhập JSON, được kích hoạt qua vùng hộp thoại "Clear All" — xem chi tiết nhập bên dưới).
- **Trạng thái trống:** Nếu không có preset nào, hiển thị `com_endpoint_no_presets`.
- **Danh sách preset:** Mỗi hàng preset chứa:
  - Icon endpoint (được giải quyết bởi `getIconKey`).
  - Tiêu đề preset (từ `getPresetTitle`, bị cắt ngắn với các lớp `max-w`).
  - Nút icon **Pin / Unpin** (`com_ui_pin` / `com_ui_unpin`) — luôn hiển thị cho preset mặc định; hiển thị khi di chuột/focus trong các trường hợp khác.
  - Nút icon **Edit** (`com_ui_edit`) — hiển thị khi di chuột/focus.
  - Nút icon **Delete (Trash)** (`com_ui_delete`) — hiển thị khi di chuột/focus.

**Hộp thoại Edit Preset (`OGDialog`):**
- Tiêu đề: `com_ui_edit_preset_title` (bao gồm tên preset).
- Trường **Preset Name** — `Label` ("Preset name", `com_endpoint_preset_name`), `Input` với placeholder `com_endpoint_set_custom_name`.
- Dropdown **Endpoint** — `SelectDropDown` với nhãn `com_endpoint`, liệt kê các endpoint không phải agents khả dụng. Thay đổi endpoint kích hoạt khởi tạo lại model và cài đặt.
- Hàng **PopoverButtons** — các nút phụ trợ theo endpoint (ví dụ: cho endpoint Google; không có nút thêm cho loại `custom` của Nufi).
- Bảng **EndpointSettings** (cùng bố cục hai cột như bảng tham số hội thoại, được điền với các giá trị đã lưu của preset).
- **Nút hành động:** "Export" (`com_endpoint_export`) và "Save" (`com_ui_save`).

**Hộp thoại Save As Preset (`OGDialog`, tiêu đề `com_endpoint_save_as_preset`):**
- Ô nhập **Preset Name** (`id="preset-custom-name"`, nhãn `com_endpoint_preset_name`, placeholder `com_endpoint_preset_custom_name_placeholder`).
- Được điền sẵn với tiêu đề hội thoại hiện tại hoặc "My Preset" / `com_endpoint_my_preset`.
- Nút **Save** (`com_ui_save`). Nhấn Enter cũng gửi biểu mẫu.

**Hộp thoại Xác Nhận Xóa:**
- Tiêu đề: `com_ui_delete_preset`.
- Nội dung: `com_ui_delete_confirm_strong` với tiêu đề preset in đậm.
- Nút: "Cancel" (`com_ui_cancel`) và "Delete" (`com_ui_delete`, biến thể phá hủy).

#### Hành vi chức năng — Tạo / Lưu Cài Đặt Hiện Tại

**FR-1.** Trong OptionsPopover, nút "Save as preset" mở `SaveAsPresetDialog` được điền sẵn với cài đặt của hội thoại đang hoạt động (tất cả tham số, endpoint, model).

**FR-2.** Trong SidePanel tham số (thanh bên phải), nút chính "Save as preset" mở cùng `SaveAsPresetDialog`.

**FR-3.** Người dùng có thể chỉnh sửa tiêu đề preset trong hộp thoại. Nhấn Enter hoặc nhấn "Save" gọi `useCreatePresetMutation`, POST preset đã làm sạch lên server. Khi thành công, một toast hiển thị "`<title>` saved" và hộp thoại đóng. Khi lỗi, một toast hiển thị `com_endpoint_preset_save_error`.

**FR-4.** Preset xuất hiện ngay lập tức trong menu presets sau khi lưu thành công (cache React Query bị vô hiệu hóa).

#### Hành vi chức năng — Áp Dụng / Chọn Preset

**FR-5.** Nhấn vào hàng preset trong menu presets gọi `onSelectPreset`, thực hiện:
  - Hiển thị một toast ngắn `"<title>" Active!` (thời lượng 750 ms; được tạo thành là `${toastTitle} ${localize('com_endpoint_preset_selected_title')}` trong đó `com_endpoint_preset_selected_title` = `"Active!"`).
  - Đánh giá logic chuyển đổi endpoint: nếu hội thoại hiện tại là hội thoại "modular" đang tồn tại và endpoint của preset cũng là modular, nó cập nhật tại chỗ; ngược lại nó bắt đầu một hội thoại mới.
  - Áp dụng tất cả tham số preset vào trạng thái hội thoại.

**FR-6.** Các công cụ trong preset không còn khả dụng với người dùng sẽ bị loại bỏ trước khi áp dụng (`removeUnavailableTools`).

**FR-7.** Nếu preset có `defaultPreset: true`, hội thoại được bắt đầu với `disableParams: true` (bảng tham số không bị ghi đè bởi bất kỳ logic tự tải thêm nào).

#### Hành vi chức năng — Chỉnh Sửa Preset

**FR-8.** Nhấn icon Edit (bút chì) trên hàng preset gọi `onChangePreset`, đặt preset đó làm preset đang hoạt động trong trạng thái Recoil và đặt `presetModalVisible: true`, mở hộp thoại Edit Preset.

**FR-9.** Trong hộp thoại Edit Preset, người dùng có thể thay đổi:
  - Tên preset (ô nhập văn bản).
  - Endpoint (dropdown; thay đổi endpoint đặt lại model về mục đầu tiên khả dụng nếu model hiện tại không có trong danh sách của endpoint mới).
  - Tất cả giá trị tham số trong bảng EndpointSettings.

**FR-10.** Nhấn "Save" gọi `useUpdatePresetMutation`. Khi thành công, một toast hiển thị "`<title>` saved". Danh sách presets được làm mới.

#### Hành vi chức năng — Đặt / Bỏ Preset Mặc Định

**FR-11.** Nhấn nút Pin trên preset không phải mặc định gọi `onSetDefaultPreset(preset, false)`, cập nhật preset với `defaultPreset: true`. Khi thành công, hàng tiêu đề hiển thị `Default: <title>` và hội thoại mới tiếp theo tự động tải preset này. Toast: `"<title>" is now the default preset.` (được tạo thành là `${toastTitle} ${localize('com_endpoint_preset_default')}` trong đó `com_endpoint_preset_default` = `"is now the default preset."`).

**FR-12.** Nhấn nút Pin (Unpin) trên preset mặc định hiện tại gọi `onSetDefaultPreset(preset, true)`, cập nhật với `defaultPreset: false`. Toast: `"<title>" is no longer the default preset.` (được tạo thành là `${toastTitle} ${localize('com_endpoint_preset_default_removed')}` trong đó `com_endpoint_preset_default_removed` = `"is no longer the default preset."`). Trạng thái preset mặc định trong tiêu đề trở về `com_endpoint_preset_default_none` ("No default preset active.").

#### Hành vi chức năng — Xóa Preset

**FR-13.** Nhấn icon Trash trên hàng preset gọi `onDeletePreset`, đặt `presetToDelete` và mở hộp thoại xác nhận xóa.

**FR-14.** Nhấn "Delete" trong hộp thoại xác nhận gọi `deletePresetsMutation.mutate(preset)`. Preset bị xóa lạc quan khỏi danh sách ngay lập tức. Khi thành công, một toast "Preset deleted" (`com_endpoint_preset_delete_success`, severity SUCCESS) được hiển thị và danh sách server được làm mới. Khi lỗi, một toast `com_endpoint_preset_delete_error` (severity ERROR) được hiển thị và danh sách được tải lại để khôi phục trạng thái thực.

**FR-15.** Nhấn "Cancel" đóng hộp thoại mà không thực hiện mutation, và focus trả về nút presets.

#### Hành vi chức năng — Xóa Tất Cả Presets

**FR-16.** Nhấn "Clear All" mở hộp thoại xác nhận (tiêu đề `com_ui_clear_presets`, cảnh báo `com_endpoint_presets_clear_warning`). Xác nhận gọi `deletePresetsMutation.mutate(undefined)` (không có đối số = xóa tất cả), làm trống danh sách preset.

#### Hành vi chức năng — Xuất Preset

**FR-17.** Nhấn "Export" trong hộp thoại Edit Preset gọi `exportPreset`, sử dụng `export-from-json` để tải xuống preset hiện tại dưới dạng tệp JSON. Tên tệp là tiêu đề preset được làm sạch bằng `filenamify` (ví dụ: `My Preset.json`). Bản xuất bao gồm tất cả các trường preset đã làm sạch (endpoint, model, tham số) nhưng loại trừ các trường chỉ dành cho server bị xóa bởi `cleanupPreset`.

#### Hành vi chức năng — Nhập Preset

**FR-18.** Một component `FileUpload` được nhúng trong vùng tiêu đề menu presets (liên kết với hộp thoại "Clear All"). Người dùng chọn tệp `.json` từ đĩa. Nội dung tệp được phân tích cú pháp dưới dạng JSON và truyền vào `onFileSelected`, gọi `importPreset` → `useCreatePresetMutation`. Khi thành công, toast `com_endpoint_preset_import` được hiển thị. Khi lỗi, toast `com_endpoint_preset_import_error` (severity ERROR).

**FR-19.** `presetId` của preset được nhập được đặt thành `null` trước khi lưu, vì vậy nó luôn được tạo mới (không bao giờ ghi đè lên preset đang tồn tại).

#### Trạng thái & trường hợp đặc biệt

- **Không có preset nào:** Menu chỉ hiển thị hàng tiêu đề với "No default preset active." (`com_endpoint_preset_default_none`) và "Clear All", theo sau là thông báo `com_endpoint_no_presets`.
- **Tiêu đề preset trống:** Mặc định hiển thị là `com_endpoint_preset_title` ("Preset") trong toast; hộp thoại lưu được điền sẵn với "My Preset".
- **Lỗi server khi lưu:** Toast `com_endpoint_preset_save_error` được hiển thị; hộp thoại vẫn mở.
- **Model trong preset không còn khả dụng:** Khi chỉnh sửa preset có model không có trong danh sách model hiện tại, `EditPresetDialog` tự động sửa model thành `models[0]` cho endpoint của preset. Một `console.log` được phát ra.
- **Preset của endpoint Agents:** Hộp thoại Edit Preset không mở cho các preset có endpoint là Agents (`isAgentsEndpoint` kiểm tra và thoát sớm). Các preset đó vẫn có thể được áp dụng qua danh sách preset nhưng không thể chỉnh sửa qua hộp thoại.
- **Nhập tệp JSON không hợp lệ:** Trình phân tích JSON của trình duyệt sẽ ném lỗi; hành vi phụ thuộc vào xử lý lỗi của wrapper `FileUpload`. (cần xác minh: liệu có lỗi hiển thị cho người dùng khi nhập tệp JSON không hợp lệ hay không)
- **Preset có công cụ không khả dụng:** Các công cụ trong preset không có trong tập `availableTools` của người dùng sẽ bị loại bỏ lặng lẽ khi áp dụng (FR-6).

#### Tiêu chí chấp nhận

**AC-1.** Giả sử người dùng đang ở trong một hội thoại sử dụng endpoint Nufi với Temperature đặt thành 0.7, khi họ nhấn "Save as preset", đặt tên là "Low Temp", và nhấn "Save", thì preset xuất hiện trong danh sách presets và một toast xác nhận việc lưu.

**AC-2.** Giả sử preset "Low Temp" tồn tại, khi người dùng mở menu presets và nhấn "Low Temp", thì temperature của hội thoại được đặt thành 0.7 và một toast hiển thị `"Low Temp" Active!`.

**AC-3.** Giả sử preset "Low Temp" tồn tại, khi người dùng nhấn icon Edit, thay đổi tên thành "Very Low Temp", và nhấn "Save", thì danh sách preset hiển thị "Very Low Temp" và server phản ánh bản cập nhật.

**AC-4.** Giả sử preset "Low Temp" tồn tại, khi người dùng nhấn icon Pin, thì tiêu đề hiển thị "Default: Low Temp" và một toast hiển thị `"Low Temp" is now the default preset.`, và hội thoại mới tiếp theo tải với Temperature 0.7.

**AC-5.** Giả sử "Low Temp" là preset mặc định, khi người dùng nhấn icon Unpin (pin đang hoạt động), thì tiêu đề trở về "No default preset active." và một toast hiển thị `"Low Temp" is no longer the default preset.`, và các hội thoại mới không còn tự động tải preset.

**AC-6.** Giả sử người dùng nhấn icon Trash trên "Low Temp" và xác nhận xóa, thì preset bị xóa khỏi danh sách ngay lập tức và một toast thành công được hiển thị.

**AC-7.** Giả sử người dùng nhấn "Export" trong hộp thoại Edit cho "Low Temp", thì một tệp có tên `Low Temp.json` được tải xuống chứa endpoint, model và các giá trị tham số của preset.

**AC-8.** Giả sử người dùng nhấn điều khiển nhập (tải lên tệp) và chọn tệp preset `.json` đã xuất hợp lệ, thì preset xuất hiện trong danh sách và một toast xác nhận việc nhập.

**AC-9.** Giả sử danh sách presets có nhiều mục, khi người dùng mở menu presets, thì tất cả presets được liệt kê với các nút icon pin, edit và delete hiển thị khi di chuột/focus, và nút pin của preset mặc định luôn hiển thị.

**AC-10.** Giả sử "Clear All" được nhấn và xác nhận, khi hộp thoại đóng, thì danh sách presets trống và tiêu đề hiển thị "No default preset active.".
