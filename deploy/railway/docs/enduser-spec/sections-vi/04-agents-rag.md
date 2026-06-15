## Agents & File Search (RAG)

### Tổng quan khái niệm

NuFi Chat cung cấp hai cách khác nhau để trò chuyện với AI:

**Endpoint Nufi thông thường** — chế độ chat mặc định. Người dùng chọn "Nufi" từ bộ
chọn endpoint/model. Các file đính kèm qua nút 📎 được gửi dưới dạng tệp đính kèm
theo tin nhắn và chỉ có hiệu lực trong tin nhắn đó; chúng không được lưu trữ lâu dài
và không khả dụng trong bất kỳ cuộc hội thoại hoặc phiên làm việc nào trong tương
lai. Không có cơ chế tạo sinh tăng cường truy xuất (RAG) trong chế độ này.

**Endpoint Agents** — chế độ nâng cao bổ sung một trợ lý AI có thể cấu hình, lâu dài
("agent"). Agents là *cơ chế duy nhất* mà qua đó RAG hoạt động trong NuFi. Một agent
có thể có tài liệu được tải lên vào kho **Knowledge** của nó; những tài liệu đó được
nhúng (embed) qua dịch vụ `rag_api` vào cơ sở dữ liệu pgvector. Tại thời điểm suy
luận, model nhận được danh sách các tên file Knowledge khả dụng dưới dạng ngữ cảnh
hệ thống và có thể tự động gọi công cụ `file_search`; chỉ khi đó backend mới gửi
truy vấn đến `RAG_API_URL/query` và trả kết quả khớp về cho model dưới dạng kết quả
tool call — trên **tất cả** các cuộc hội thoại với agent đó, không chỉ cuộc hội thoại
hiện tại. Truy xuất **không** xảy ra tự động: nó chỉ diễn ra khi LLM quyết định gọi
công cụ `file_search`.

**Điểm phân biệt quan trọng mà người kiểm thử phải nắm rõ:**

| Chiều so sánh | File Knowledge (agent) | Tệp đính kèm theo tin nhắn (📎) |
|---|---|---|
| Nơi tải lên | Trình chỉnh sửa Agent → mục File Search | Ô nhập chat 📎 |
| Phạm vi | Mọi cuộc hội thoại với agent này, vĩnh viễn | Chỉ cuộc hội thoại / tin nhắn hiện tại |
| Truy xuất | Được nhúng vào pgvector; truy xuất khi LLM gọi công cụ `file_search` | Gửi nội tuyến trong cửa sổ ngữ cảnh |
| RAG? | Có | Không |

**Phạm vi tính năng của NuFi.** Endpoint Agents trong NuFi được cấu hình với
`capabilities: ["file_search"]` mà thôi (xem `librechat.yaml` dòng 34-36). Điều này
có nghĩa là Code Interpreter, Web Search và các nút Actions/Tools **không khả dụng**
trong trình chỉnh sửa agent. Tính năng duy nhất người dùng có thể bật là File Search.

> Lưu ý: Mục **MCP Tools** cũng có thể xuất hiện trong trình chỉnh sửa agent nếu có
> MCP server nào được cấu hình phía máy chủ. Khả năng hiển thị của nó chỉ được kiểm
> soát bởi `availableMCPServers.length > 0` và độc lập với mảng `capabilities`.

---

### Chọn endpoint Agents

**Mục đích:** Định tuyến một cuộc hội thoại qua hạ tầng Agents thay vì endpoint
chat Nufi thông thường.

**Điều kiện tiên quyết / truy cập:** `interface.agents: true` và
`interface.endpointsMenu: true` phải được đặt trong `librechat.yaml` (cả hai đều đã
được bật). Mọi người dùng đã xác thực đều có thể chuyển đổi endpoint.

**Thành phần giao diện:**
- Bộ chọn endpoint / model trên thanh công cụ phía trên (mặc định ghi nhãn "Nufi")
- Mục dropdown ghi nhãn **"Agents"** (`com_ui_agents`)
- Sau khi chọn, bảng bên phải hiển thị bảng điều khiển Agent builder

**Hành vi chức năng:**
1. FR-1 — Nhấp vào bộ chọn endpoint sẽ mở một dropdown liệt kê các endpoint khả
   dụng; "Agents" xuất hiện như một mục trong danh sách.
2. FR-2 — Chọn "Agents" tải bảng điều khiển Agent builder (bảng bên) và chuyển
   đổi endpoint đang hoạt động cho các tin nhắn mới sang `EModelEndpoint.agents`.
3. FR-3 — Nếu chưa có agent nào được tạo, bảng bên hiển thị dropdown bộ chọn agent
   (với "Create New Agent" là văn bản placeholder) và một biểu mẫu agent trống. Nút
   reset "Create New Agent" chỉ xuất hiện sau khi một agent hiện có đã được tải vào
   bảng; không thể bắt đầu cuộc hội thoại cho đến khi chọn một agent.
4. FR-4 — Nếu đã có ít nhất một agent, dropdown tự động chọn agent được dùng gần
   nhất và hiển thị trong bảng điều khiển.

**Trạng thái & trường hợp đặc biệt:**
- Nếu `interface.endpointsMenu` được đặt thành `false`, bộ chọn sẽ bị ẩn và endpoint
  Agents sẽ không thể truy cập được.
- Chuyển từ Agents sang Nufi giữa chừng trong một cuộc hội thoại không xóa cuộc hội
  thoại đó; nó chỉ thay đổi endpoint cho tin nhắn tiếp theo mà thôi.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử người dùng đang ở bất kỳ endpoint nào, khi họ mở bộ chọn endpoint
  và nhấp "Agents", thì bảng bên phải hiển thị giao diện Agent builder.
- AC-2 — Giả sử chưa có agent nào tồn tại, khi endpoint Agents được chọn, thì nút
  bắt đầu cuộc hội thoại bị vô hiệu hóa / không hoạt động cho đến khi chọn một agent.

---

### Tạo agent

**Mục đích:** Định nghĩa một agent lâu dài mới với tên, mô tả, danh mục, hướng dẫn,
model và tùy chọn ảnh đại diện (avatar).

**Điều kiện tiên quyết / truy cập:** Người dùng phải đang ở endpoint Agents. Bảng
bên Agent builder phải được mở. Người dùng thông thường (không phải admin) có thể
tạo agent của riêng mình.

**Thành phần giao diện (lấy từ `AgentConfig.tsx` và `AgentPanel.tsx`):**
- **Bộ chọn Agent** (phía trên cùng của bảng) — `ControlCombobox`, aria-label
  `com_ui_agent`; placeholder hiển thị "Create New Agent"
  (`com_ui_create_new_agent`) khi để trống
- **Nút "Create New Agent"** — xuất hiện khi đang tải một agent hiện có; đặt lại
  biểu mẫu về trống để tạo agent mới
- **Avatar** — ảnh có thể nhấp, kích thước 80×80 px (`com_ui_upload_agent_avatar_label`);
  mở menu để tải lên hoặc đặt lại
- **Trường Name** — bắt buộc (`*`), nhãn `com_ui_name`, placeholder
  `com_agents_name_placeholder` ("Optional: The name of the agent"), maxLength 256
- **Trường Description** — tùy chọn, nhãn `com_ui_description`, placeholder
  `com_agents_description_placeholder` ("Optional: Describe your Agent here"),
  maxLength 512
- **Bộ chọn Category** — bắt buộc (`*`), nhãn `com_ui_category`; một `ControlCombobox`
  với các danh mục: General, Finance, HR, IT, R&D, Sales, After Sales (và có thể có
  danh mục khác do admin định nghĩa). Mặc định là "general".
- **Textarea Instructions** — nhãn `com_ui_instructions`, placeholder
  `com_agents_instructions_placeholder` ("The system instructions that the agent uses"),
  chiều cao tối thiểu 100 px, có thể thay đổi kích thước. Nút "Variables"
  (`com_ui_variables`) mở dropdown để chèn các biến động đặc biệt (ví dụ:
  `{{current_date}}`).
- **Nút Model** — nhãn `com_ui_model` (bắt buộc `*`); điều hướng đến bảng phụ Model
  Parameters để chọn nhà cung cấp và model
- **Mục Support Contact** (tùy chọn) — các trường: Name (tối thiểu 3 ký tự) và Email
  (được xác thực định dạng)
- **Nút Create / Save** ở chân trang — hiển thị "Create" (`com_ui_create`) khi chưa
  có `agent_id`, "Save" (`com_ui_save`) khi đang chỉnh sửa

**Hành vi chức năng:**
1. FR-1 — Gửi biểu mẫu mà không có **Name** kích hoạt thông báo lỗi nội tuyến
   (`com_ui_agent_name_is_required`).
2. FR-2 — Gửi biểu mẫu mà không chọn **Provider** và **Model** kích hoạt thông báo
   lỗi toast (`com_agents_missing_provider_model`).
3. FR-3 — Khi tạo thành công, một toast **"Successfully created {name}"** xuất hiện
   (`com_assistants_create_success` nối với tên agent) và ID agent mới xuất hiện
   trong bộ chọn agent.
4. FR-4 — Tải lên avatar tách biệt với việc tạo/cập nhật agent: việc tải lên avatar
   kích hoạt `POST /api/agents/:id/avatar` sau khi agent được lưu; một toast thành
   công `com_ui_upload_agent_avatar` được hiển thị.
5. FR-5 — Category mặc định là "general" cho các agent mới.
6. FR-6 — ID agent (do máy chủ gán) xuất hiện dưới dạng văn bản in nghiêng nhỏ ngay
   bên dưới trường Name ngay sau khi tạo.
7. FR-7 — Name trong Support Contact yêu cầu tối thiểu 3 ký tự; email phải có định
   dạng hợp lệ; vi phạm sẽ hiển thị thông báo lỗi nội tuyến.

**Trạng thái & trường hợp đặc biệt:**
- Tạo agent thứ hai trong khi đang xem agent đầu tiên: nhấp "Create New Agent" để
  đặt lại biểu mẫu; agent hiện tại không bị xóa.
- Tải lên avatar thất bại: toast `com_agents_avatar_upload_error` được hiển thị;
  bản thân agent vẫn được lưu nhưng không có avatar.
- Name vượt quá 256 ký tự: `maxLength` được trình duyệt thực thi; không có lỗi
  máy chủ bổ sung nào được mong đợi.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử biểu mẫu để trống, khi người dùng gửi mà không điền Name, thì một
  lỗi nội tuyến (`"Agent name is required"`) xuất hiện bên dưới trường Name và không
  có lệnh gọi API nào được thực hiện.
- AC-2 — Giả sử đã điền Name nhưng chưa chọn Model, khi người dùng gửi, thì một
  toast lỗi xuất hiện và không có agent nào được tạo.
- AC-3 — Giả sử tất cả các trường bắt buộc hợp lệ, khi người dùng nhấp Create, thì
  một toast thành công hiển thị tên agent mới và bảng điều khiển chuyển sang chế độ
  chỉnh sửa cho agent đó.
- AC-4 — Giả sử một agent đã tồn tại, khi người dùng tải lên ảnh avatar, thì một
  toast thành công "Successfully updated agent avatar" xuất hiện và avatar được hiển
  thị trong vòng tròn 80×80.

---

### Cấu hình model cho agent

**Mục đích:** Chọn nhà cung cấp LLM và model nào cung cấp sức mạnh cho agent, và
tùy chọn tinh chỉnh các tham số suy luận.

**Điều kiện tiên quyết / truy cập:** Agent builder phải được mở. Bảng phụ Model
được truy cập bằng cách nhấp nút **Model** trong builder chính.

**Thành phần giao diện (lấy từ `ModelPanel.tsx`):**
- **Nút "Back to builder"** (biểu tượng chevron-left, `com_ui_back_to_builder`) —
  quay lại bảng cấu hình agent chính
- **Tiêu đề Model Parameters** (`com_ui_model_parameters`)
- **Combobox Provider** — nhãn `com_ui_provider` (bắt buộc `*`); liệt kê tất cả các
  endpoint không phải assistant đã được cấu hình, ngoại trừ `agents` chính nó. Trong
  NuFi, nhà cung cấp duy nhất có thể chọn là **"Nufi"** (endpoint tương thích
  OpenAI tùy chỉnh).
- **Combobox Model** — nhãn `com_ui_model` (bắt buộc `*`); được điền từ danh sách
  model được tải về cho nhà cung cấp đã chọn. Bị vô hiệu hóa cho đến khi chọn nhà
  cung cấp (placeholder: `com_ui_select_provider_first`).
- **Các điều khiển tham số model** — lưới cài đặt được hiển thị động (ví dụ:
  temperature, max tokens) dựa trên khả năng của nhà cung cấp/model
- **Nút Reset Parameters** — `com_ui_reset_var` ("Reset Model Parameters"); đặt lại
  tất cả các ghi đè tham số về mặc định

**Hành vi chức năng:**
1. FR-1 — Chọn một Provider sẽ điền vào dropdown Model với các model khả dụng của
   nhà cung cấp đó; model đầu tiên được tự động chọn.
2. FR-2 — Thay đổi nhà cung cấp sẽ xóa model đã chọn trước đó và tự động chọn
   model đầu tiên của nhà cung cấp mới.
3. FR-3 — Model và nhà cung cấp được dùng gần nhất được lưu vào localStorage
   (`LocalStorageKeys.LAST_AGENT_MODEL`, `LocalStorageKeys.LAST_AGENT_PROVIDER`) để
   các agent mới bắt đầu từ lựa chọn trước đó.
4. FR-4 — Nhấp "Reset Model Parameters" xóa tất cả các ghi đè suy luận và thông báo
   "Model Parameters have been reset." cho trình đọc màn hình.

**Trạng thái & trường hợp đặc biệt:**
- Nếu backend Nufi không thể truy cập, danh sách model hiển thị placeholder
  "loading..." (từ mặc định `librechat.yaml`) cho đến khi tải thành công hoặc hết
  thời gian chờ.
- Trong NuFi chỉ có một nhà cung cấp ("Nufi"); combobox Provider vẫn được hiển thị
  nhưng chỉ có một tùy chọn.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử bảng phụ Model đang mở và Provider là "Nufi", khi người dùng mở
  dropdown Model, thì danh sách chứa ít nhất một model được tải từ backend.
- AC-2 — Giả sử đã chọn một model, khi người dùng nhấp "Back to builder", thì
  builder chính hiển thị tên model đã chọn trong nút Model.
- AC-3 — Giả sử các tham số model đã được thay đổi, khi người dùng nhấp "Reset
  Model Parameters", thì tất cả các tham số trở về trống/mặc định và một thông báo
  live-region xác nhận việc đặt lại.

---

### Bật tính năng File Search

**Mục đích:** Bật tính năng RAG cho một agent, giúp agent có thể truy xuất ngữ cảnh
từ các tài liệu Knowledge đã được tải lên.

**Điều kiện tiên quyết / truy cập:**
- Một agent phải đã được **lưu** (có `agent_id` thực sự; không phải agent tạm thời/
  chưa lưu). Việc tải lên file bị vô hiệu hóa cho đến khi agent được lưu.
- Triển khai NuFi có `rag_api` đang chạy với `RAG_API_URL` được cấu hình và pgvector
  khả dụng.

**Thành phần giao diện (lấy từ `FileSearch.tsx`, `FileSearchCheckbox.tsx`,
`AgentConfig.tsx`):**
- **Tiêu đề mục "File Search"** (`com_assistants_file_search`) bên trong khối
  **Capabilities** (`com_assistants_capabilities`)
- **Hộp kiểm "Enable File Search"** (`com_agents_enable_file_search`) — một điều
  khiển `Checkbox` gắn với `AgentCapabilities.file_search`
- **Nút biểu tượng thông tin** (biểu tượng circle-help) — khi di chuột qua, hiển
  thị tooltip HoverCard: `com_agents_file_search_info` ("When enabled, the agent will
  be informed of the exact filenames listed below, allowing it to retrieve relevant
  context from these files.")
- **Nút "Upload for File Search"** (`com_ui_upload_file_search`) — có biểu tượng
  đính kèm; bị vô hiệu hóa khi hộp kiểm không được chọn hoặc agent chưa được lưu

**Hành vi chức năng:**
1. FR-1 — Mục Capabilities chỉ được hiển thị khi `fileSearchEnabled` là true trong
   cấu hình khả năng máy chủ (được đặt qua `capabilities: ["file_search"]` trong
   `librechat.yaml`).
2. FR-2 — Chọn hộp kiểm đặt `AgentCapabilities.file_search = true` trong trạng thái
   biểu mẫu; bỏ chọn đặt thành `false`.
3. FR-3 — Khi được lưu với `file_search: true`, máy chủ thêm `Tools.file_search` vào
   mảng tools của agent (xử lý trong `AgentPanel.onSubmit`).
4. FR-4 — Khi hộp kiểm **không được chọn**, nút "Upload for File Search" bị vô hiệu
   hóa (`disabledUploadButton = fileSearchChecked === false`).
5. FR-5 — Khi agent chưa được lưu (agent tạm thời), nút Upload cũng bị vô hiệu hóa
   và một thông báo bên dưới hiển thị:
   `com_agents_file_search_disabled` ("Agent must be created before uploading
   files for File Search.").

**Trạng thái & trường hợp đặc biệt:**
- Tắt File Search sau khi các file đã được tải lên không xóa các file Knowledge đã
  được nhúng; chúng vẫn được liên kết với agent.
- Nếu `RAG_API_URL` không được cấu hình, `uploadVectors` sẽ ném ra lỗi
  "RAG_API_URL not defined" và bất kỳ lần tải lên nào tiếp theo sẽ thất bại ở
  phía máy chủ.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử biểu mẫu agent chưa được lưu, khi người dùng xem mục File Search,
  thì nút Upload bị vô hiệu hóa và một thông báo gợi ý được hiển thị.
- AC-2 — Giả sử một agent đã được lưu, khi người dùng chọn "Enable File Search" và
  lưu agent, thì danh sách tools của agent bao gồm `file_search`.
- AC-3 — Giả sử File Search không được chọn, khi người dùng cố nhấp nút Upload, thì
  nút bị vô hiệu hóa về mặt hiển thị và không có hộp chọn file nào mở ra.
- AC-4 — Giả sử File Search được bật, khi người dùng di chuột qua biểu tượng thông
  tin, thì một tooltip giải thích hành vi truy xuất được hiển thị.

---

### Tải lên tài liệu Knowledge

**Mục đích:** Nhúng (embed) tài liệu vào kho Knowledge lâu dài của agent để agent
có thể truy xuất các đoạn trích liên quan tại thời điểm chat thông qua RAG.

**Điều kiện tiên quyết / truy cập:**
- Agent phải được lưu (có `agent_id` thực sự).
- Hộp kiểm "Enable File Search" phải được chọn.
- Dịch vụ `rag_api` phải có thể truy cập được.

**Giới hạn file (từ `librechat.yaml` `fileConfig.endpoints.Nufi`):**
- Tối đa **5 files** mỗi agent (`fileLimit: 5`)
- Giới hạn kích thước mỗi file: **20 MB** (`fileSizeLimit: 20`)
- Giới hạn tổng kích thước trên tất cả các file: **50 MB** (`totalSizeLimit: 50`)

**Các loại file được hỗ trợ (từ `librechat.yaml` `supportedMimeTypes`):**
- Hình ảnh: `image/png`, `image/jpeg`, `image/webp`, `image/gif`
- Tài liệu: `application/pdf`, `text/plain`, `text/markdown`, `text/csv`,
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (`.docx`),
  `application/json`

> Lưu ý: Cấu hình file NuFi được áp dụng dưới khóa nhà cung cấp "Nufi"; endpoint
> Agents kế thừa các giới hạn này khi nhà cung cấp của agent là Nufi. **ĐÃ XÁC NHẬN:**
> `useAgentFileConfig` phân giải về cấu hình Nufi đã hợp nhất (fileLimit 5,
> fileSizeLimit 20 MB, totalSizeLimit 50 MB) qua nhánh `endpoints["Nufi"]` trong
> `file-config.ts`.

**Thành phần giao diện (lấy từ `FileSearch.tsx`):**
- **Nút "Upload for File Search"** — có `AttachmentIcon`; nhãn
  `com_ui_upload_file_search`. Kích hoạt một `<input type="file" multiple>` ẩn.
- **Chip / hàng file** — được hiển thị bởi `FileRow` và `FileContainer` bên dưới nút;
  mỗi chip hiển thị tên file và loại file. File không phải hình ảnh hiển thị chip
  `FileContainer`; hình ảnh hiển thị thumbnail `Image`.
- **Nút Remove** trên mỗi chip — `RemoveFile` (nút X); kích hoạt xóa khỏi cả backend
  lưu trữ và cơ sở dữ liệu vector.

**Xử lý phía backend (mô hình lưu trữ kép, lấy từ `processAgentFileUpload`
trong `process.js` và `uploadVectors` trong `VectorDB/crud.js`):**

Máy chủ thực hiện hai bước tuần tự khi một file được tải lên vào
`EToolResources.file_search`:

1. **Tải lên storage** — File được lưu vào backend lưu trữ file được cấu hình
   (hệ thống file cục bộ, S3, Firebase, v.v.) thông qua `handleFileUpload`. Điều
   này cung cấp một bản sao lưu lâu dài của file gốc.
2. **Nhúng vector** — File được POST đến `RAG_API_URL/embed` với:
   - `file_id` — UUID cho tài liệu
   - `file` — luồng file thô
   - `entity_id` — `agent_id` (phân tách các embedding theo agent này)
   
   Phản hồi RAG API bao gồm `known_type` và `status`. Nếu `known_type` là
   `false`, một lỗi "File embedding failed. The filetype ... is not supported" được
   ném ra. Nếu `status` là falsy, "File embedding failed." được ném ra.
   
3. Bản ghi cơ sở dữ liệu được ghi với `embedded: Boolean(responseData.known_type)`
   và `source: FileSources.vectordb`. Danh sách file tài nguyên của agent được cập
   nhật qua `db.addAgentResourceFile`.

**Các trạng thái tải lên file hiển thị cho người dùng:**

| Trạng thái | Chỉ báo trực quan |
|---|---|
| Đang tải lên | **Spinner overlay** trên biểu tượng chip file (`file.progress < 1`) |
| Đã nhúng / Sẵn sàng | Chip hiển thị với kiểu dáng nguồn vectordb (huy hiệu hổ phách/vàng, `FileSources.vectordb`) |
| Nhúng thất bại | Chip file bị **xóa** hoàn toàn; một toast lỗi được hiển thị kèm thông báo lỗi từ máy chủ |

> Lưu ý về nhúng thất bại: Máy chủ trả về 4xx/5xx. Trình xử lý `onError` phía client
> gọi `deleteFileById(file_id)` — xóa chip — rồi hiển thị toast lỗi (ví dụ: "File
> embedding failed. The filetype … is not supported"). Không có chip nào còn lại
> trong giao diện ở trạng thái lỗi.

**Hành vi chức năng:**
1. FR-1 — Nhấp "Upload for File Search" mở hộp chọn file của hệ điều hành với tính
   năng chọn `multiple` được bật.
2. FR-2 — Các file đã chọn được tải lên từng cái một; trong khi tải lên
   (`file.progress < 1`), một spinner overlay được hiển thị trên biểu tượng chip.
3. FR-3 — Máy chủ từ chối các file hình ảnh cho tài nguyên công cụ `file_search`
   (`"Image uploads are not supported for file search tool resources"`).
4. FR-4 — Sau khi nhúng thành công, chip file vẫn còn trong mục Knowledge qua các
   phiên trình chỉnh sửa agent (được lưu trữ trong cơ sở dữ liệu, tải qua
   `useGetAgentFiles(agent_id)`).
5. FR-5 — Xóa chip file Knowledge kích hoạt `DELETE RAG_API_URL/documents`
   (gửi `file_id`) để xóa các embedding, và xóa file khỏi storage và cơ sở dữ liệu.
6. FR-6 — Nếu ID agent là tạm thời (agent chưa lưu), nút upload bị vô hiệu hóa;
   không thể tải lên.
7. FR-7 — Tải lên file có MIME type không có trong `supportedMimeTypes` bị máy chủ
   từ chối qua bộ lọc (`filterFile`) với thông báo "Unsupported file type".
8. FR-8 — Tải lên file vượt quá `fileSizeLimit` (20 MB) bị từ chối với lỗi giới
   hạn kích thước trước khi file đến bước nhúng vector.
9. FR-9 — Tải lên khi tổng kích thước đã tải lên sẽ vượt quá `totalSizeLimit`
   (50 MB) được thực thi ở cấp độ máy chủ.
10. FR-10 — Danh sách file Knowledge được hợp nhất từ cả trạng thái tải lên
    trong bộ nhớ và các file agent được lưu lại được tải từ API, ngăn trùng lặp
    bằng `file_id`.

**Trạng thái & trường hợp đặc biệt:**
- **Loại file không được hỗ trợ**: Máy chủ trả về lỗi; chip file bị xóa và một
  toast lỗi được hiển thị. `.docx`, `.pdf`, `.txt`, `.md`, `.csv`, `.json` được hỗ
  trợ; `.pptx`, `.xlsx`, `.zip` thì không.
- **File quá lớn** (> 20 MB mỗi file): `filterFile` của máy chủ từ chối trước khi
  có bất kỳ hoạt động lưu trữ hoặc nhúng nào xảy ra.
- **Vượt tổng kích thước** (> 50 MB trên tất cả các file): Máy chủ từ chối lần
  tải lên.
- **Nhúng thất bại** (RAG API từ chối hoặc trả về `known_type: false`): Máy chủ
  ném lỗi; chip file bị xóa và một toast lỗi được hiển thị. Nếu bước lưu trữ đã
  thành công trước bước nhúng, file trong storage bị **orphaned** — không có cơ chế
  rollback nào được thực hiện. Quản trị viên nên định kỳ dọn dẹp các đối tượng
  storage bị orphaned.
- **Knowledge trống** (không có file nào được tải lên): Agent hoạt động mà không có
  truy xuất; nó trả lời dựa trên kiến thức huấn luyện / hướng dẫn của mình, không có
  ngữ cảnh tài liệu.
- **RAG_API_URL không thể truy cập**: Tải lên thất bại với "RAG_API_URL not defined"
  hoặc lỗi mạng. Storage chạy **trước** (đã xác nhận); nếu lệnh gọi RAG sau đó thất
  bại, file đã lưu bị orphaned — không có bản ghi DB và không có vector embedding.
- **File đã được nhúng** (cùng file tải lên lại): Không có cơ chế khử trùng lặp ở
  phía client ngoài `file_id`; trùng lặp nhúng ở cấp độ vector DB là trách nhiệm của
  dịch vụ RAG API.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử File Search được bật và agent đã được lưu, khi người dùng nhấp
  "Upload for File Search" và chọn một file `.pdf` dưới 20 MB, thì một chip với
  spinner overlay xuất hiện trong khi tải lên, sau đó chuyển sang chip đã nhúng
  với kiểu dáng hổ phách/vectordb.
- AC-2 — Giả sử File Search được bật, khi người dùng chọn file `.pptx`, thì máy chủ
  trả về lỗi và một toast chỉ ra loại file không được hỗ trợ; không có chip nào
  còn lại.
- AC-3 — Giả sử File Search được bật, khi người dùng chọn file lớn hơn 20 MB, thì
  một lỗi được trả về và không có chip nào được thêm vào.
- AC-4 — Giả sử các file Knowledge đã được tải lên và trình chỉnh sửa agent được đóng
  rồi mở lại, khi người dùng xem agent, thì các file đã tải lên trước đó vẫn xuất
  hiện dưới dạng chip trong mục File Search.
- AC-5 — Giả sử chip file Knowledge đang được hiển thị, khi người dùng nhấp nút xóa
  của nó, thì chip biến mất và một toast "deleting file" được hiển thị; file không
  còn xuất hiện khi tải lại trang.
- AC-6 — Giả sử RAG API không khả dụng, khi người dùng cố tải lên một file Knowledge,
  thì một lỗi được hiển thị và file không được hiển thị là đã nhúng.

---

### Chat với agent (hành vi truy xuất)

**Mục đích:** Sử dụng một agent có File Search được bật để nhận câu trả lời dựa trên
các tài liệu Knowledge đã tải lên.

**Điều kiện tiên quyết / truy cập:**
- Một agent được chọn trong endpoint Agents.
- Agent có File Search được bật (`file_search` trong danh sách tools của nó) và ít
  nhất một file Knowledge đã được nhúng.

**Thành phần giao diện:**
- Ô nhập chat — hộp tin nhắn tiêu chuẩn; không cần thay đổi giao diện đặc biệt nào
  để kích hoạt truy xuất.
- Nút đính kèm 📎 theo tin nhắn — khả dụng để gửi các tệp đính kèm theo từng tin
  nhắn (chỉ giới hạn trong cuộc hội thoại; không được thêm vào Knowledge).
- Tên agent / avatar được hiển thị trong tiêu đề cuộc hội thoại hoặc bảng bên.

**Hành vi chức năng:**
1. FR-1 — Khi người dùng gửi tin nhắn, model nhận được một ghi chú trong ngữ cảnh
   hệ thống liệt kê các tên file Knowledge khả dụng ("Use the `file_search` tool to
   find relevant information within: …"). Model sau đó có thể tự chủ gọi công cụ
   `file_search`; chỉ khi đó backend mới gửi chuỗi truy vấn của tool đến
   `RAG_API_URL/query`, giới hạn theo `entity_id` (agent_id).
2. FR-2 — Các đoạn tài liệu được truy xuất được trả về cho LLM dưới dạng **kết quả
   tool call**, mà model sử dụng để soạn phản hồi. Các đoạn không được chèn trước
   vào ngữ cảnh trước khi tạo sinh.
3. FR-3 — Phản hồi của model có thể tham chiếu nội dung file. Việc các marker trích
   dẫn rõ ràng (ví dụ: chú thích tên file) có xuất hiện hay không phụ thuộc vào
   việc vai trò của người dùng có quyền `FILE_CITATIONS > USE` hay không. (cần xác
   minh thủ công trên sản phẩm đang chạy: xác nhận quyền `FILE_CITATIONS` được cấp
   cho vai trò phù hợp trong cấu hình vai trò của NuFi).
4. FR-4 — Nếu không tìm thấy đoạn liên quan nào trong kho Knowledge (không có kết
   quả khớp), model trả lời từ kiến thức huấn luyện mà không có ngữ cảnh RAG; không
   có lỗi nào được hiển thị cho người dùng.
5. FR-5 — Các tệp đính kèm theo tin nhắn (📎) được gửi dưới dạng ngữ cảnh nội tuyến
   cho tin nhắn đó mà thôi và không ảnh hưởng đến kho Knowledge lâu dài.
6. FR-6 — Chuyển sang cuộc hội thoại mới với **cùng agent** vẫn truy cập được vào
   cùng các tài liệu Knowledge; Knowledge được giới hạn theo agent, không phải theo
   cuộc hội thoại.
7. FR-7 — Chuyển sang cuộc hội thoại mới với **agent khác** (hoặc không có agent)
   sẽ không truy cập được vào Knowledge của agent đầu tiên.

**Trạng thái & trường hợp đặc biệt:**
- **Knowledge trống**: **ĐÃ XÁC NHẬN** — khi `files.length === 0`, tool ngay lập
  tức trả về "No files to search. Instruct the user to add files for the search."
  cho model; không có ngoại lệ nào được ném ra và không có lỗi nào được hiển thị
  cho người dùng.
- **Truy xuất không có kết quả khớp**: Khi không tìm thấy đoạn nào, tool trả về
  "No content found in the files…" dưới dạng kết quả tool; model phản hồi sử dụng
  ngữ cảnh đó. Việc điều này có hiển thị như lỗi đối với người dùng hay không phụ
  thuộc vào phản hồi của model. (cần xác minh thủ công trên sản phẩm đang chạy:
  xác nhận hành vi của model khi không tìm thấy đoạn nào).
- **File Knowledge bị xóa giữa chừng cuộc hội thoại**: Các lượt tiếp theo trong cùng
  cuộc hội thoại sẽ không còn truy xuất từ file đó; các tin nhắn trợ lý trước đó
  không bị ảnh hưởng.
- **Kho Knowledge rất lớn**: Độ trễ truy xuất có thể tăng; thời gian phản hồi có thể
  chậm hơn đáng kể.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử một agent có file Knowledge `.pdf` chứa văn bản "Project Alpha budget
  is $500,000", khi người dùng hỏi "What is the Project Alpha budget?", thì phản hồi
  của trợ lý bao gồm thông tin từ tài liệu (ví dụ: con số ngân sách).
- AC-2 — Giả sử một agent có File Search được bật nhưng không có file Knowledge nào,
  khi người dùng đặt câu hỏi về một chủ đề mà chỉ tài liệu mới có thể trả lời, thì
  agent phản hồi mà không có lỗi (có thể thừa nhận thiếu thông tin).
- AC-3 — Giả sử một cuộc hội thoại đang sử dụng Agent A, khi người dùng bắt đầu một
  cuộc hội thoại mới với Agent A, thì các tài liệu Knowledge giống nhau vẫn khả dụng
  để truy xuất mà không cần tải lên lại.
- AC-4 — Giả sử một cuộc hội thoại đang sử dụng Agent A, khi người dùng chuyển sang
  endpoint Nufi thông thường cho một tin nhắn mới, thì không có truy xuất RAG nào
  xảy ra.

---

### Chỉnh sửa agent

**Mục đích:** Sửa đổi tên, mô tả, hướng dẫn, model, tính năng, file Knowledge hoặc
avatar của một agent hiện có.

**Điều kiện tiên quyết / truy cập:**
- Agent phải đã tồn tại. Người dùng hiện tại phải là tác giả của agent, là admin,
  hoặc có quyền `EDIT` trên tài nguyên agent.
- Người không phải chủ sở hữu và không có quyền `EDIT` sẽ thấy thông báo "not
  available" (`com_agents_not_available`, `com_agents_no_access`).

**Thành phần giao diện:**
- Bộ chọn Agent (phía trên cùng của bảng bên) — chọn một agent hiện có từ dropdown
- Tất cả các trường trong bảng builder chính đều có thể chỉnh sửa (giống như khi
  tạo)
- **Nút Save** (`com_ui_save`) — thay thế "Create" sau khi agent_id đã tồn tại
- **Nút Advanced** — mở bảng cài đặt Nâng cao (liên kết agent, giới hạn đệ quy,
  v.v.; không liên quan đến File Search trong NuFi)
- **Nút Version History** — truy cập các phiên bản agent trước đó (`VersionButton`)

**Hành vi chức năng:**
1. FR-1 — Tải một agent hiện có sẽ điền tất cả các trường biểu mẫu từ dữ liệu agent
   đã lưu, bao gồm trạng thái hộp kiểm `file_search` hiện tại và các file Knowledge.
2. FR-2 — Nhấp "Save" gọi `PATCH /api/agents/:id` với payload đã cập nhật; khi
   thành công, một toast `com_assistants_update_success_name` xuất hiện.
3. FR-3 — Lệnh gọi PATCH API **luôn được gửi** (ngoại trừ trường hợp chỉ tải lên
   avatar). Nếu máy chủ xác định không có thay đổi lâu dài nào xảy ra (phiên bản
   được trả về bằng với phiên bản đã ghi nhận trước đó), một toast thông tin
   "No changes" (`com_ui_no_changes`) được hiển thị.
4. FR-4 — Xóa file Knowledge khỏi trình chỉnh sửa và lưu **không** tự động xóa file
   khỏi vector DB; việc xóa được kích hoạt riêng bằng cách nhấp nút xóa (X) của
   chip file.
5. FR-5 — Thay đổi avatar tuân theo quy trình hai bước giống như khi tạo: cấu hình
   agent được lưu trước, sau đó avatar được tải lên qua một endpoint riêng.

**Trạng thái & trường hợp đặc biệt:**
- Chỉnh sửa agent đang được sử dụng (cuộc hội thoại đang hoạt động): thay đổi có
  hiệu lực cho tin nhắn **tiếp theo**; phản hồi đang xử lý hiện tại không bị ảnh
  hưởng.
- Lịch sử phiên bản: các phiên bản trước có thể được xem nhưng đặc tả về quản lý
  phiên bản được đề cập riêng.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử người dùng là tác giả của agent, khi họ mở trình chỉnh sửa agent và
  thay đổi trường Name, thì nút Save đang hoạt động (trạng thái dirty được phát hiện).
- AC-2 — Giả sử không có trường nào thay đổi, khi người dùng nhấp Save, thì một
  toast thông tin "No changes" xuất hiện.
- AC-3 — Giả sử người dùng chỉnh sửa trường Instructions và nhấp Save, thì một toast
  thành công bao gồm tên agent và các cuộc hội thoại tiếp theo sử dụng hướng dẫn
  đã cập nhật.
- AC-4 — Giả sử người dùng không phải tác giả và không có quyền EDIT, khi họ chọn
  agent từ dropdown, thì tất cả các trường biểu mẫu không thể chỉnh sửa và một thông
  báo chỉ ra không có quyền truy cập được hiển thị.

---

### Xóa agent

**Mục đích:** Xóa vĩnh viễn một agent và các siêu dữ liệu liên quan khỏi hệ thống.

**Điều kiện tiên quyết / truy cập:**
- Agent phải được lưu (không phải tạm thời).
- Người dùng phải là tác giả của agent, là admin, hoặc có quyền `DELETE` trên tài
  nguyên agent.

**Thành phần giao diện (lấy từ `DeleteButton.tsx`):**
- **Nút Delete Agent** — biểu tượng thùng rác (`TrashIcon`), ở chân trang agent; chỉ
  hiển thị cho người dùng có quyền xóa; aria-label `com_ui_delete_agent`
- **Hộp thoại xác nhận** — `OGDialogTemplate` với:
  - Tiêu đề: `com_ui_delete_agent`
  - Nội dung: `com_ui_delete_agent_confirm` ("Are you sure you want to delete this agent?")
  - Nút xác nhận: `com_ui_delete` (kiểu dáng đỏ hủy diệt)

**Hành vi chức năng:**
1. FR-1 — Nhấp nút thùng rác mở hộp thoại xác nhận; không có gì bị xóa cho đến khi
   được xác nhận.
2. FR-2 — Xác nhận gọi `DELETE /api/agents/:id`; khi thành công, một toast thành
   công `com_ui_agent_deleted` xuất hiện.
3. FR-3 — Sau khi xóa, bảng điều khiển tải agent khả dụng tiếp theo trong danh sách,
   hoặc đặt lại về biểu mẫu "Create New Agent" trống nếu không còn agent nào.
4. FR-4 — Nếu agent bị xóa đang là agent trong cuộc hội thoại đang hoạt động, thì
   `agent_id` của cuộc hội thoại được cập nhật sang agent đầu tiên khả dụng.
5. FR-5 — **ĐÃ XÁC NHẬN:** Các file Knowledge **không** bị xóa khỏi cơ sở dữ liệu
   vector khi agent bị xóa. `deleteAgentHandler` chỉ gọi `db.deleteAgent({ id })`;
   không có lệnh gọi xóa RAG API nào được thực hiện. Các embedding pgvector của
   chúng vẫn bị orphaned sau khi agent bị xóa.

**Trạng thái & trường hợp đặc biệt:**
- Lỗi API xóa: toast `com_ui_agent_delete_error` được hiển thị; agent không bị xóa.
- Xóa agent tạm thời: Nút Delete bị ẩn (kiểm tra `isEphemeralAgent` trả về `null`).

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử người dùng có quyền DELETE, khi họ nhấp biểu tượng thùng rác và hủy
  hộp thoại, thì agent không bị xóa và trình chỉnh sửa vẫn mở.
- AC-2 — Giả sử người dùng xác nhận xóa, thì một toast thành công xuất hiện, agent
  không còn xuất hiện trong dropdown bộ chọn, và biểu mẫu được đặt lại.
- AC-3 — Giả sử người dùng không có quyền DELETE, khi họ xem trình chỉnh sửa agent,
  thì nút biểu tượng thùng rác không được hiển thị.

---

### Chia sẻ agent

**Mục đích:** Cấp quyền truy cập cho người dùng hoặc nhóm khác để xem hoặc sử dụng
một agent hiện có. Tùy chọn đặt agent là công khai (khả dụng cho tất cả người dùng).

**Điều kiện tiên quyết / truy cập:**
- Agent phải được lưu (không phải tạm thời).
- Hệ thống phải có `permissions.agents.share: true` được cấu hình cho vai trò của
  người dùng.
- Người dùng hiện tại phải là tác giả, là admin, hoặc có bit quyền `SHARE` trên
  tài nguyên agent.

**Thành phần giao diện (lấy từ `AgentFooter.tsx`, `GenericGrantAccessDialog.tsx`):**
- **Nút Share** — nút biểu tượng `Share2Icon` ở chân trang agent; aria-label
  `com_ui_share_var` ("Share {agent name}"). Hiển thị huy hiệu số đếm khi agent đã
  được chia sẻ với N đối tượng.
- **Hộp thoại Grant Access** — mở khi nhấp nút Share:
  - Tiêu đề: "Share {agent name}" với biểu tượng `Users`
  - **Tìm kiếm người** — ô nhập `UnifiedPeopleSearch`; tìm kiếm người dùng/nhóm để
    thêm
  - **Danh sách quyền** — hiển thị các chia sẻ hiện có kèm vai trò; hỗ trợ xóa
    từng cá nhân
  - **Nút bật/tắt Public sharing** — `PublicSharingToggle`; khi được bật, tất cả
    người dùng có thể thấy/sử dụng agent (được admin kiểm soát qua
    `permissions.agents.allowSharePublic`)
  - **Nút Save** — áp dụng các thay đổi

- **Nút Remote Access** — nút biểu tượng `Globe` riêng biệt; mở một
  `GenericGrantAccessDialog` thứ hai với `ResourceType.REMOTE_AGENT`; cấp quyền
  truy cập qua API (không phải giao diện chat). Điều này cho phép người tiêu thụ
  API bên ngoài sử dụng agent. Chỉ hiển thị khi `permissions.remote_agents.share: true`.

**Hành vi chức năng:**
1. FR-1 — Nút Share chỉ được hiển thị khi người dùng có quyền `SHARE` và
   `hasAccessToShareAgents` là true.
2. FR-2 — Sau khi thêm người dùng/nhóm trong hộp thoại và lưu, những đối tượng đó
   có thể thấy và sử dụng agent từ endpoint Agents của họ.
3. FR-3 — Huy hiệu số đếm chia sẻ trên nút tăng lên để phản ánh tổng số đối tượng
   có quyền truy cập.
4. FR-4 — Chia sẻ công khai (nếu được cho phép) làm cho agent hiển thị với tất cả
   người dùng đã xác thực; agent xuất hiện trong bộ chọn agent của họ với biểu
   tượng địa cầu (`EarthIcon`, màu xanh lá).
5. FR-5 — Nút Duplicate Agent (biểu tượng `CopyPlus`, `com_ui_duplicate_agent`) có
   sẵn riêng cho người dùng có quyền EDIT; nó tạo bản sao của agent thuộc sở hữu
   của người dùng đang sao chép, với toast thành công `com_ui_agent_duplicated`.
6. FR-6 — Xóa người dùng khỏi danh sách chia sẻ và lưu sẽ thu hồi quyền truy cập
   của họ.

**Trạng thái & trường hợp đặc biệt:**
- Không có quyền chia sẻ: Nút Share không được hiển thị.
- `permissions.agents.allowSharePublic: false`: Nút bật/tắt công khai bị ẩn trong
  hộp thoại; agent chỉ có thể được chia sẻ với từng cá nhân/nhóm được chỉ định.
- Chia sẻ với chính mình: Không được mong đợi sẽ bị ngăn chặn ở cấp độ giao diện;
  hành vi do hệ thống định nghĩa.

**Tiêu chí chấp nhận:**
- AC-1 — Giả sử người dùng có quyền SHARE, khi họ nhấp nút Share, thì hộp thoại
  Grant Access mở ra hiển thị ô tìm kiếm người và các chia sẻ hiện có.
- AC-2 — Giả sử người dùng tìm kiếm và thêm "User B" trong hộp thoại rồi lưu, thì
  User B có thể tìm thấy và chọn agent từ endpoint Agents của họ.
- AC-3 — Giả sử người dùng xóa User B khỏi danh sách chia sẻ và lưu, thì User B
  không còn truy cập được agent nữa.
- AC-4 — Giả sử chia sẻ công khai được admin bật, khi người dùng bật "share with
  everyone" và lưu, thì tất cả người dùng đã xác thực thấy agent trong bộ chọn của
  họ với biểu tượng địa cầu.
- AC-5 — Giả sử người dùng không có quyền SHARE, khi họ xem chân trang agent, thì
  nút biểu tượng Share không có trong DOM.
