# Nghiên cứu: làm tiếng lửa giống thật (lửa trại, lò sưởi, củi lách tách)

*Ngày 13/11/2026. Viết cho kênh YouTube âm thanh môi trường có bật kiếm tiền.*

**Giới hạn khi tra cứu.** Môi trường làm việc chỉ đọc được GitHub (raw và API) và kết quả WebSearch.
Các trang freesound.org, huggingface.co, archive.org, pixabay.com, mixkit.co, zapsplat.com, sonniss.com,
bigsoundbank.com, support.google.com, wikibooks và trang các bài báo đều **không mở được**.
Trong tài liệu dùng hai nhãn:

- **[Đ]**: đã đọc trực tiếp file LICENSE, README hoặc mã nguồn.
- **[S]**: chỉ thấy qua đoạn trích của kết quả tìm kiếm. Cần mở trang gốc kiểm tra trước khi dựa vào.

---

## 1. Tóm tắt và đề xuất

**Nên chọn:** lấy **tổng hợp bằng thuật toán** làm lớp chính, và trộn thêm **bản thu thật**
do bạn tự thu hoặc lấy từ nguồn CC0, qua Rain Mixer. AI chỉ dùng để tạo thêm vài âm lẻ khi thiếu.
Nếu dùng thì dùng Stable Audio Open hoặc MOSS-SoundEffect.

Lý do:

1. **Giấy phép sạch nhất.** Tiếng do `fire.py` tạo ra thuộc về bạn hoàn toàn. Không có điều khoản doanh thu,
   vùng lãnh thổ hay "non-commercial" nào ràng buộc.
2. **Hợp với cách kênh đang làm.** Mỗi seed ra một bản khác, dài bao nhiêu cũng được, không lặp.
   Điều này giúp tránh chính sách "nội dung lặp lại / không chân thực" của YouTube [S].
   Cũng ít rủi ro bị người khác nhận Content ID, vì không ai có cùng file với bạn.
3. **Lửa dễ tổng hợp hơn mưa.** Lửa gồm ít lớp, có đặc trưng thống kê rõ:
   - nền gầm trầm;
   - tiếng xì dâng lên theo từng cơn;
   - tiếng nổ lách tách rất ngắn, đến theo chùm, biên độ phân bố đuôi dài.

   Các nghiên cứu và mã nguồn mở đều thống nhất về các thành phần này (xem mục 3).
4. **Bản thử nghiệm đã chạy được.** Một giờ âm thanh mất khoảng 1 phút trên một nhân CPU.
   Số đo và spectrogram trông hợp lý (mục 7). **Chưa ai nghe thử bằng tai.**

Điểm yếu của thuật toán: những chi tiết rất "hữu cơ" như tiếng củi rít dài, tiếng than vỡ và
tiếng vang của lò gạch thật thì bản thu thật vẫn hơn. Vì vậy cách tốt nhất là **trộn**:
- một lớp nền thu thật hoặc CC0;
- lớp tổng hợp để có biến thể và chùm lách tách không bao giờ lặp;
- sự kiện củi sụp tổng hợp hoặc lấy từ bản thu.

## 2. Bảng so sánh các hướng

| Hướng | Độ giống thật (ước lượng) | Công sức | Giấy phép | Dùng cho video kiếm tiền? | Phần cứng |
|---|---|---|---|---|---|
| **Tổng hợp thuật toán** (`fire.py`, theo mô hình Farnell nâng cấp) | Khá đến tốt. Lách tách và gầm thuyết phục; tiếng rít và tiếng vang lò kém bản thu. *Chưa kiểm chứng bằng tai.* | Trung bình. Prototype đã có, cần nghe và chỉnh. | Của bạn hoàn toàn. Chỉ lấy ý tưởng, không chép mã GPL/AGPL. | **Có** | CPU, khoảng 1 phút cho 1 giờ âm thanh |
| **Bản tự thu** | Tốt nhất | Cao: cần mic stereo, chỗ yên tĩnh, nhiều giờ thu và cắt | Của bạn | **Có** | Máy ghi âm stereo |
| **Bản thu CC0** (Freesound CC0, OpenGameArt CC0, BigSoundBank) | Tốt, tùy file | Thấp | CC0 [S] | **Có**. Giữ link và ảnh chụp giấy phép làm bằng chứng. | — |
| **YouTube Audio Library** | Tùy file | Thấp | Giấy phép YouTube [S] | **Có**, YouTube nói không bị Content ID [S] | — |
| **Stable Audio Open 1.0 / Small** (chữ thành âm thanh) | Khá. Lách tách tốt, tiếng nổ to kém [S]. Tối đa 47 s (Small: 11 s). | Thấp đến trung bình | Code MIT [Đ]. Weights: Stability AI Community License [Đ] | **Có điều kiện**: phải đăng ký với Stability, doanh thu dưới 1 triệu USD/năm [Đ] | GPU, VRAM cần kiểm tra. Bản Small chạy được trên CPU [S]. |
| **MOSS-SoundEffect v2.0** (chữ thành âm thanh, 2026) | Chưa rõ, chưa thấy đánh giá về lửa | Trung bình | Apache-2.0 cho cả code và model [Đ] | **Có** theo giấy phép. Nguồn dữ liệu huấn luyện chưa công bố. | GPU (1.3B tham số, 48 kHz, ≤30 s), VRAM cần kiểm tra |
| **HunyuanVideo-Foley** (video thành âm thanh) | Tốt nếu có video lửa để khớp hình [S] | Cao | Tencent Hunyuan Community License [Đ] | **Không** ở EU, Anh, Hàn Quốc [Đ]. Nơi khác được, nhưng video chiếu toàn cầu nên là vùng xám. | GPU 20 GB (12 GB có offload) bản XXL; 16 GB (8 GB) bản XL [Đ] |
| MMAudio | Tốt [S] | Trung bình | Code MIT / weights CC-BY-NC 4.0 [Đ] | **Không** | khoảng 6 GB VRAM [Đ] |
| AudioGen, AudioLDM/AudioLDM2, Tango/Tango2, TangoFlux | Trung bình, 16 kHz (TangoFlux 44.1 kHz) | Trung bình | Đều cấm thương mại (CC-BY-NC / NC-SA / NC-ND, "research-only") [Đ] | **Không** | GPU |
| ThinkSound | — | — | README: Apache 2.0, nhưng ghi "Commercial use is NOT permitted" [Đ] | **Không** | GPU |
| ControlFoley (Xiaomi), Woosh (Sony) | — | — | Code Apache/MIT; weights CC-BY-NC [Đ] | **Không** | GPU |
| Make-An-Audio 2, EzAudio | Trung bình, 16 kHz | Trung bình | MIT [Đ] (weights MIT [S]) | **Cần kiểm tra** (dữ liệu huấn luyện gồm bộ dữ liệu học thuật) | GPU |
| FoleyCrafter | — | — | Apache-2.0, nhưng dựa trên Auffusion. README bảo kiểm tra giấy phép Auffusion [Đ]. | **Cần kiểm tra** | GPU |
| Kling-Foley | — | — | Chưa phát hành weights [Đ] | Không dùng được | — |

Ghi chú về giấy phép AI:
- **Stability AI Community License** (bản 05/07/2024, đọc qua bản sao trong repo TangoFlux) [Đ]:
  - dùng thương mại phải "register with Stability AI";
  - giấy phép hết hiệu lực nếu doanh thu trên 1 triệu USD/năm;
  - "You own any outputs".

  Theo [S], SAO 1.0 ban đầu phát hành với giấy phép chặt hơn rồi mới chuyển sang Community License.
  **Cần mở thẻ mô hình trên HF và stability.ai/license để xác nhận** trước khi dùng.
- **Tencent Hunyuan** [Đ]:
  - "DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA";
  - cấm hiển thị Output ngoài Territory. Video YouTube hiển thị cả ở EU, nên kể cả khi bạn ở Việt Nam
    vẫn là vùng xám. Không khuyên dùng cho kênh kiếm tiền.
- **Weights CC-BY-NC**: giấy phép không nói rõ về âm thanh tạo ra. Video kiếm tiền là dùng thương mại,
  nên coi như **không**.
- Về dữ liệu huấn luyện: VGGSound có lớp "fire crackling" (492 clip) [Đ]. AudioSet có "Fire", "Crackle" [Đ].
  Các mô hình học từ AudioSet/VGGSound (lấy từ YouTube) có rủi ro về nguồn gốc dữ liệu, kể cả khi giấy phép
  cho phép thương mại. Stable Audio Open học từ Freesound CC nên nguồn sạch hơn [S].

## 3. Hướng thuật toán: điều gì làm tiếng lửa nghe thật

### 3.1 Mô hình gốc: Andy Farnell, *Designing Sound*, Practical 11 "Fire"

Đọc từ bản patch Pure Data phân phối lại theo GPL-3.0 (ARGOPd ExMM138) và bản port SuperCollider [Đ].
Một nguồn nhiễu trắng chung đi vào ba nhánh:

| Thành phần | Cách làm (con số trong patch) | Mức trộn |
|---|---|---|
| **Crackle** (lách tách) | Kích hoạt: nhiễu → `lop~ 1` → `env~` → chỉ nổ khi đường bao chậm nằm trong cửa sổ 50–51 dB, nên tiếng nổ **đến theo chùm**, không đều. Mỗi tiếng: r = random(0..29); đường bao từ 1 giảm về 0 trong r ms rồi **bình phương**; lọc `bp~` tâm **1500 + 500·r Hz** (1.5–16 kHz), Q = 1. Tiếng dài thì sáng hơn. | 0.2 |
| **Hiss** (xì) | `hip~ 1000` × `600·(10·lop~1(nhiễu))⁴`: điều biên mũ 4 nên phần lớn thời gian im, thỉnh thoảng dâng lên | 0.3 |
| **Lapping** (lửa liếm/gầm) | `bp~ 30 Q5` → ×100 → `hip~ 25` → `clip~ ±0.9` → `hip~ 25` → ×0.6. Cắt đỉnh dải 30 Hz đã khuếch đại tạo ra những nhịp "phập phù" có nhiều hài. | 0.6 |
| **polyFire** | 4 bản `firegen` độc lập qua `bp~ 600 Q0.2`, `bp~ 1200 Q0.6`, `bp~ 2600 Q0.4`, `hip~ 1000`, rồi cộng lại: rộng stereo và phổ phong phú | — |

Bản SuperCollider (wikibook, đọc qua bản port BSD3 [Đ]) đơn giản hơn: tiếng nổ dùng `Dust` (Poisson 1–3/s),
dài 20–30 ms, bộ lọc rất rộng.

### 3.2 Nghiên cứu và mã nguồn khác

- **Chadwick & James, "Animating Fire with Sound", SIGGRAPH 2011** [S]:
  - mô phỏng vật lý phần tần số thấp (đến vài trăm Hz);
  - mở rộng lên cao bằng nhiễu phổ lũy thừa hoặc tổng hợp kết cấu từ bản thu, điều biên theo đường bao dải thấp;
  - tiếng ồn cháy tỉ lệ với tốc độ thay đổi nhiệt tỏa ra (dQ/dt); phổ giảm khoảng **f^-2.5** (đo được 2.1–3.4).
- **Kersten & Purwins, DAFx 2012** [S]: tách tiếng lửa thành *transient* (gom thành cụm) cộng với nhiễu nền lọc LPC.
  Cũng là mô hình hai lớp: tiếng nổ + nền.
- **McDermott & Simoncelli** (thống kê kết cấu âm thanh) [S]: lửa là ví dụ kinh điển.
  Các transient băng rộng, **đồng thời trên nhiều dải tần**, là thứ làm tai nghe ra lửa chứ không phải nước.
- **Phát xạ âm của gỗ** (arXiv 1506.04563) [S]: năng lượng sự kiện theo luật lũy thừa P(E) ∝ E^-1.4.
  Đây là gỗ bị nén, không phải gỗ cháy, nhưng là bằng chứng gần nhất cho biên độ đuôi dài.
- **shapeof.world `fire-dsp.js`** (AGPL-3.0 [Đ]: **chỉ lấy ý tưởng, không chép mã**).
  Tác giả nói đã chỉnh theo 6 bản thu lửa trại thật:
  - Thời gian nổ: quá trình gamma (shape 2) + **Hawkes tự kích thích** (branching 0.3, 70 ms).
  - Biên độ: năng lượng theo **P(E) ∝ E^-1.6**, khoảng 35 dB động.
  - Hình dạng: mỗi tiếng nổ gồm 1–8 xung con cách nhau 0.8–10 ms, τ khoảng 1 ms (giảm −20 dB trong 2–3 ms);
    lọc thông dải 1.5–8 kHz, Q 0.6–1.6, cộng thêm phần băng rộng và "thân" 160–800 Hz.
  - Pop to và củi sụp có chế độ riêng (mục 3.4).
- **sfxwright** (MIT [Đ]) và **loam** (MIT [Đ]): bản Python kiểu Farnell, có thể tham khảo và dùng mã.
- **Sound Design Toolkit (SDT)** (GPL-3.0+ [Đ]): không có model lửa. Model `breaking` có quỹ năng lượng
  giảm dần, dùng được làm mẫu cho tràng tiếng vụn khi củi sụp.
- **Nemisindo**: dịch vụ thương mại, không thấy mô hình hay giấy phép công khai [S].

### 3.3 Danh sách các yếu tố quyết định độ thật

1. **Tiếng nổ lách tách đến theo chùm, không đều.** Poisson thuần nghe như "máy". Nên dùng:
   - Hawkes hoặc ngưỡng đường bao chậm (Farnell) để tạo chùm;
   - tốc độ nền dao động chậm theo "sức lửa".
   Đo bằng hệ số biến thiên khoảng cách (CV): Poisson ≈ 1, lửa thật > 1.
2. **Biên độ đuôi dài** (luật lũy thừa, số mũ năng lượng khoảng 1.4–1.6): rất nhiều tiếng tí tách nhỏ,
   ít tiếng "đốp" to, dải động trên 30 dB.
3. **Tiếng nổ rất ngắn**: phần lớn 0.3–5 ms, tiếng to 5–30 ms, tắt nhanh theo hàm mũ hoặc bình phương.
   Thường gồm vài xung con sát nhau. Phổ băng rộng, có đỉnh cộng hưởng ngẫu nhiên 1.5–9 kHz, Q thấp.
4. **Nền gầm trầm** (< 300 Hz, nhấn 30–120 Hz), phổ dốc (khoảng f^-2.5 đến f^-3),
   điều biên chậm kiểu log-normal; cộng thêm lớp "liếm" phập phù 150–2000 Hz nhấp nháy vài Hz.
5. **Tiếng xì** trên 1 kHz, điều biên mũ cao (^4) nên dâng từng cơn. Thỉnh thoảng có **tiếng rít hẹp**
   2–7 kHz của nhựa cây hoặc hơi nước phụt ra, cao độ trôi, dài 0.5–6 s.
6. **Sự kiện hiếm**: pop lớn có tiếng ngân "hốc" 1.2–4.5 kHz và đuôi xì hơi nước; **củi sụp** gồm:
   - tiếng thụp 55–90 Hz;
   - tiếng gõ gỗ 350–700 Hz;
   - tiếng vụn than;
   - một tràng lách tách;
   - sau đó lửa bùng lên và tốc độ nổ tăng tạm thời.
7. **Nhiều bản độc lập, lệch stereo** (polyFire) để có bề rộng.
8. **Không gian**: lửa trại khô và rộng; lò sưởi có phản xạ phòng ngắn (RT60 khoảng 0.3–0.6 s) và tiếng gạch.

### 3.4 Củi đổ/sụp

Công thức ghép từ shapeof.world (ý tưởng) và SDT `breaking`:
1. Tiếng thụp: sin tắt dần 55–90 Hz, τ khoảng 60 ms, thêm mode thứ hai ×2.1–2.9 và một cụm nhiễu < 180 Hz.
2. Gỗ gõ gỗ: mode 350–700 Hz, τ 15–25 ms.
3. Tiếng sột soạt của mảnh vụn: nhiễu dải quanh 2.5 kHz, khoảng 280 ms.
4. Than vỡ leng keng: 4–14 tiếng ping nhỏ, khoảng cách tăng dần.
5. Tràng lách tách: 4–12 tiếng trong khoảng 0.4 s.
6. Sau đó: tiếng gầm +3 dB và tốc độ nổ ×2–4, giảm dần trong 5–15 s.

## 4. Bản thu thật

### 4.1 Nguồn

Tất cả các dòng dưới đây đều là **[S]**: không mở được trang nào để đọc trực tiếp.
**Phải đọc trang giấy phép trước khi dùng.**

| Nguồn | Giấy phép | Ghi nguồn? | Video kiếm tiền? |
|---|---|---|---|
| Freesound | Mỗi file một giấy phép (CC0 / CC BY / CC BY-NC) | CC0: không. CC BY: có. | CC0 và CC BY: có. **Tránh BY-NC.** Ví dụ một file CC0: freesound.org/s/729396 (lửa trại, Tascam DR-05X), có bản cắt loop liền mạch ở /s/729395 |
| OpenGameArt | "Fireplace sound loop" (CC0, WAV 10 MB); "Fire Crackling" của AntumDeluge (CC0) | Không | Có |
| BigSoundBank | CC0 | Không | Có |
| YouTube Audio Library | Giấy phép YouTube hoặc CC BY | Tùy file | Có, an toàn nhất về Content ID. Chưa xác nhận có tiếng lửa. |
| Pixabay, Mixkit | Giấy phép riêng của từng trang, cho dùng thương mại | Không | Có |
| ZapSplat (bản miễn phí) | Standard License | **Có**, phải ghi nguồn | Có |
| Sonniss GDC Bundle | Royalty-free | Không | Có. Chưa xác nhận có tiếng lửa. |
| BBC Sound Effects | Chỉ cá nhân/giáo dục | — | **Không** |

**Rủi ro Content ID:** YouTube ghi rằng hiệu ứng âm thanh, nền âm thanh và tài liệu công cộng không đủ điều kiện
đăng ký Content ID [S]. Dù vậy vẫn có người nhận sai: năm 2018 một video nhiễu trắng 10 giờ bị 5 lượt nhận
[S, Tubefilter]. Cách phòng:
- lưu link, ngày tải và ảnh chụp giấy phép;
- không đăng nguyên một file CC0 phổ biến; luôn trộn lớp hoặc xử lý;
- ưu tiên bản tự thu hoặc tiếng tổng hợp làm lớp chính.

### 4.2 Tự thu tiếng lửa

- **Thiết bị**:
  - dùng cặp mic stereo, bố trí XY, ORTF hoặc MS; hai mic omni cách nhau khoảng 30 cm cũng được;
  - mic tự ồn thấp, vì than hồng rất nhỏ tiếng;
  - thu 24-bit/48 kHz, hoặc 32-bit float nếu máy có;
  - đỉnh khoảng −12 đến −6 dBFS, vì tiếng nổ to hơn nền rất nhiều.
- **Vị trí**: cách lửa khoảng 30 cm đến 1 m, tránh nhiệt và tàn lửa. Luôn dùng chắn gió lông,
  kể cả trong nhà, vì khí nóng bốc lên tạo luồng gió. Đặt gần thì đỡ tạp âm và tiếng phòng.
- **Tạp âm**: tắt tủ lạnh, quạt, điều hòa, đồng hồ, điện thoại. Ngoài trời, thu đêm khuya, xa đường và đường bay,
  để ý tiếng côn trùng. Đeo tai nghe kín để nghe kiểm tra, và ghi chú lại chỗ có tiếng lạ để cắt.
- **Củi**:
  - gỗ mềm có nhựa (thông) nổ giòn và nhiều;
  - gỗ cứng (sồi) nổ thưa, trầm hơn;
  - quả thông khô nổ rất nhiều;
  - củi ẩm thì xì và rít hơi nước; nên thu riêng một lần.
- **Giai đoạn**: thu cả lúc lửa mới bùng, lúc cháy đều và lúc còn than. Mỗi lần thu 20–60 phút.
  Thêm củi thì thu riêng một lần, đừng làm giữa chừng một lần thu.
- **Hậu kỳ**:
  - xử lý tối thiểu: không khử ồn mạnh, không dùng gate;
  - lọc ù điện bằng notch 50 Hz (Việt Nam) và các hài, hoặc high-pass 30–40 Hz;
  - cắt các tiếng nổ quá đặc trưng, vì lặp trong video 10 giờ sẽ bị nhận ra;
  - làm loop bằng crossfade công suất đều 2–5 s ở đoạn ổn định;
  - chồng hai loop có độ dài khác nhau (ví dụ 7 và 11 phút);
  - **hoặc đưa vào `library/` và để Rain Mixer cắt ghép theo seed**: cách này tốt hơn loop cố định.

## 5. Thiết kế tích hợp vào repo

### 5.1 Module `fire.py`

Module mới, cùng phong cách với `rain.py` và dùng lại các hàm của nó. Bản thử nghiệm
`prototypes/fire_proto.py` chính là phác thảo của module này.

```
FireParams (dataclass, frozen)          PRESETS = {campfire, fireplace, crackling, embers}
  roar_level, roar_high_hz              tiếng gầm 25–300 Hz, căn bậc hai của sức lửa
  lap_level, lap_low/high_hz,           lửa liếm 150–2000 Hz × đường bao nhấp nháy đã chỉnh lưu
    lap_flicker_hz, lap_depth
  crackle_rate, crackle_branch,         Hawkes: tiếng gốc/giây, số tiếng con trung bình,
    crackle_cluster_ms                    khoảng cách trong chùm
  crackle_alpha, crackle_level          số mũ Pareto của biên độ, độ lớn
  crackle_low/high_hz, pop_share        dải cộng hưởng, tỉ lệ tiếng nổ có thân trầm
  hiss_level, hiss_sparsity             tiếng xì, mức "từng cơn"
  whistle_per_min, whistle_level        tiếng rít nhựa/hơi nước
  collapse_per_min, collapse_level      củi sụp (kéo theo lửa bùng và nổ dày lên)
  intensity_db, intensity_seconds       biến "sức lửa" dao động chậm (dùng rain.Swell)
  width, room, room_rt60                stereo; phản xạ phòng cho lò sưởi
```

- **Biến thể theo seed:**
  - `vary(params, variation, rng)` lệch mọi thông số theo thang log, giống `rain.vary_params`;
  - mỗi thành phần có RNG riêng `default_rng([seed, 1000+i])`, nên thêm một thành phần mới không làm đổi các thành phần cũ;
  - bộ tiếng nổ (64 nhỏ + 24 lớn) được làm mới dần trong khi chạy, nên bản dài không lặp.
- **Độ lớn:** hiệu chỉnh LUFS trên 30 s đầu như `rain_chunks`. Mặc định **−20 LUFS**, không phải −18 như mưa,
  vì tiếng lửa có hệ số đỉnh cao (khoảng 21–24 dB). Như vậy giữ được tiếng nổ mà không phải nén.
- **Dòng lệnh**: giống `rain.py`, gồm `presets`, `render`, `batch`, `video`, và dùng lại
  `FFmpegSink`, `finish`, `run_jobs`, `manifest.csv`.

### 5.2 Đưa vào Rain Mixer

Phần này **cần sửa `rainmix.py`**, nên để một lần làm riêng khi bạn đồng ý; lần này chưa sửa:
- `Layer.source = "synth:fire_campfire"` (tiền tố `fire_` → `fire.PRESETS`): trong `SynthBed`,
  gọi `fire.fire_chunks` thay vì `rain.rain_chunks`;
- thêm `SYNTH_EVENTS`: `"log_collapse"` (củi sụp) và `"fire_pop"` (pop lớn có xì hơi), dùng `collapse_wave`;
- công thức mẫu mới trong `recipes/`, ví dụ `lo_suoi_dem_mua.json`:

```json
{"name": "Lò sưởi đêm mưa", "loudness": -19, "layers": [
  {"name": "Lửa (bản thu)", "source": "lua_lo_suoi", "gain_db": 0, "swell_db": 2},
  {"name": "Lửa (tổng hợp)", "source": "synth:fire_fireplace", "gain_db": -4, "swell_db": 0},
  {"name": "Mưa ngoài cửa sổ", "source": "synth:light", "gain_db": -9, "lowpass_hz": 5000},
  {"name": "Củi sụp", "type": "events", "source": "synth:log_collapse", "per_minute": 0.2, "min_gap_seconds": 60}
]}
```

### 5.3 Kết hợp với mưa và gió

- **Lò sưởi trong nhà, mưa ngoài trời:** mưa lọc thấp 4–6 kHz và nhỏ hơn lửa 8–12 dB. Như vậy mưa nghe như
  ngoài cửa sổ, lửa là tiêu điểm.
- **Gió thổi vào lửa trại:** nối đường "sức gió" của `rain.Wind` vào `intensity` của lửa. Cơn giật làm
  lửa gầm to hơn (+2–4 dB) và nổ dày hơn, giống `wind_drive_db` đang dùng cho mưa. Cần một tham số
  `wind_drive_db` cho lửa.
- **Mưa rơi vào lửa trại:** sự kiện mới "giọt xèo". Đó là tiếng xì ngắn 3–8 kHz, 50–300 ms, sau mỗi
  giọt mưa trúng than. Tốc độ tỉ lệ với `drop_rate` của mưa, và `hiss_level` của lửa tăng theo cường độ mưa.

## 6. Bản thử nghiệm: `prototypes/fire_proto.py`

```bash
python prototypes/fire_proto.py demo --outdir prototypes/out        # 4 preset × 30 s + số đo + spectrogram
python prototypes/fire_proto.py render -p crackling -d 10m -s 7 -o lua.flac
```

Chỉ dùng numpy và ffmpeg (như repo). Import `rain` để dùng lại `ShapedNoise`, `Swell`, `band`, `widen`,
`Convolver`, `loudness_lufs`, `finish`, `FFmpegSink`. **Không sửa file nào có sẵn.**

Các thành phần đã làm:
- roar;
- lap (Farnell "lapping", làm bằng đường bao nhấp nháy đã chỉnh lưu);
- crackle: Hawkes theo chùm, biên độ Pareto, xung nhiễu 0.3–15 ms qua 1–2 cộng hưởng 1.2–9 kHz, đôi khi có xung con,
  tiếng to có thân 250–1200 Hz;
- hiss điều biên log-normal;
- whistle;
- collapse, kèm lửa bùng lên và nổ dày hơn;
- IR phòng cho lò sưởi.

**Chưa làm:**
- tiếng ngân "hốc" và đuôi xì hơi nước của pop lớn;
- tiếng than vỡ leng keng khi củi sụp;
- phổ dốc kiểu f^-2.5 cho tiếng gầm (đang dùng bộ lọc band của `rain.py`);
- polyFire nhiều dải;
- nối với gió và mưa.

## 7. Kết quả đo (seed 1–4, 30 giây mỗi preset)

| Preset | LUFS | Đỉnh dBFS | % mẫu vào vùng soft-clip | Crest dB | Số tiếng nổ đã đặt | Transient phát hiện/s | CV khoảng cách | Trọng tâm phổ | Năng lượng 20–200 / 200–1k / 1–4k / 4–12k Hz (%) | LUFS ngắn hạn p10–p90 |
|---|---|---|---|---|---|---|---|---|---|---|
| campfire | −20.2 | −1.0 | 0.005 | 21.0 | 272 (≈9/s) | 6.2 | 1.43 | 672 Hz | 64 / 21 / 10 / 4 | −22.3 … −18.4 |
| fireplace | −20.2 | −1.0 | 0.008 | 21.1 | 194 | 1.3 | 1.43 | 606 Hz | 50 / 35 / 13 / 3 | −22.9 … −18.3 |
| crackling | −20.3 | −1.0 | 0.030 | 23.0 | 799 (≈27/s) | 17.9 | 1.25 | 2179 Hz | 25 / 27 / 28 / 17 | −25.0 … −16.9 |
| embers | −20.1 | −1.0 | 0.003 | 21.7 | 62 | 1.4 | 1.41 | 1343 Hz | 68 / 6 / 10 / 15 | −24.6 … −17.3 |

Số liệu chi tiết nằm trong `prototypes/out/metrics.json`. Spectrogram: `prototypes/out/*.png`
(cả 30 s, đoạn 2 s phóng to, dạng sóng 2 s). File nghe thử: `prototypes/out/*.mp3`
(256 kbps; chạy `demo` để có bản FLAC).

Đọc số đo:
- **Độ lớn ổn định:** cả 4 bản cách đích −20 LUFS trong 0.3 dB.
- **Tiếng nổ nằm trên nền:** dưới 0.03% số mẫu chạm vùng soft-clip (> −3 dBFS). Đó là đỉnh của vài tiếng nổ lớn nhất.
  Crest 21–23 dB nằm trong khoảng thường gặp của bản thu lửa thật, nhưng đó là **ước lượng, chưa đo trên bản thu thật**.
- **Nổ theo chùm:** CV khoảng cách 1.25–1.43 (> 1 = có chùm), đúng ý đồ của Hawkes. Spectrogram phóng to
  cho thấy các vạch dọc băng rộng 1–20 kHz đi theo cụm, nằm trên nền trầm, đúng dáng "transient đồng thời
  nhiều dải" mà nghiên cứu mô tả.
- **Bộ đếm transient đếm thiếu:** nó gộp các tiếng sát nhau, và với lò sưởi thì tiếng vang phòng che bớt.
  Nên chỉ dùng nó để so sánh tương đối giữa các preset.
- **Tốc độ:** 120 s mất 2 s, tức khoảng **1 phút cho 1 giờ** trên một nhân. Cùng seed cho ra kết quả giống hệt;
  khác seed thì tương quan khoảng 0.004.

Quá trình chỉnh trong lần làm này, đều dựa vào số đo và hình:
- ban đầu tiếng nổ chìm hẳn dưới nền (spectrogram không thấy vạch dọc), nên đã tăng mức nổ lên khoảng 12 dB;
- tiếng xì của "embers" trải lên 24 kHz và chiếm 60% năng lượng trên 4 kHz, nên đã thu hẹp còn 2–9 kHz và giảm mức;
- "thân" của tiếng nổ lớn ngân thành vạch ngang khoảng 30 ms, nên đã rút xuống 3–12 ms.

### Chưa kiểm chứng (cần bạn nghe)

- **Chưa ai nghe thử.** Mọi nhận định về "giống thật" chỉ dựa trên số đo và hình.
- Cân bằng giữa gầm, liếm và lách tách, và lớp "lap" có nghe như lửa phập phù hay như tiếng động cơ/gió.
- Tiếng rít (whistle) có nghe tự nhiên hay giống còi điện tử.
- Tiếng củi sụp có thuyết phục không (hiện còn đơn giản).
- Tiếng vang phòng của lò sưởi có làm tiếng nổ "nhòe" quá không.
- Chưa so số đo với một bản thu lửa thật. Nên tải một file CC0 về `library/` rồi chạy `analyse()`
  của prototype để so phổ, crest và CV.

## 8. Nguồn

**Thuật toán**
- Farnell, *Designing Sound*, Practical 11 Fire. Patch Pd (GPL-3.0) [Đ]: https://github.com/gerardparesys/ARGOPd/blob/master/ExMM/ExMM138-Fire-Farnell/ExMM138a-Fire-Farnell.pd
- Pd4P3, bản port Processing (LGPL-2.1) [Đ]: https://github.com/robertesler/Pd4P3/blob/master/examples/Nature/Fire/Fire.pde
- Bản port SuperCollider/Haskell (BSD3) [Đ]: https://github.com/8c6794b6/haskell-sc-scratch/blob/master/designing-sound/src/DesigningSound/Fire.hs
- shapeof.world `fire-dsp.js` (AGPL-3.0, chỉ tham khảo ý tưởng) [Đ]: https://github.com/makerjackie/shapeof.world
- sfxwright (MIT) [Đ]: https://github.com/m4bwav/sfxwright
- loam (MIT) [Đ]: https://github.com/bearbones/loam
- Sound Design Toolkit (GPL-3.0+) [Đ]: https://github.com/SkAT-VG/SDT
- Chadwick & James 2011 [S]: https://www.cs.cornell.edu/projects/Sound/fire/
- Verron & Drettakis 2012 [S]: https://hal.archives-ouvertes.fr/hal-00759818
- Phát xạ âm của gỗ [S]: https://arxiv.org/pdf/1506.04563

**Mô hình AI**
- Stable Audio Tools (MIT) [Đ]: https://github.com/Stability-AI/stable-audio-tools. Bản sao Stability AI Community License [Đ]: https://github.com/declare-lab/TangoFlux/blob/main/STABILITY_AI_COMMUNITY_LICENSE.md. Thẻ mô hình [S]: https://huggingface.co/stabilityai/stable-audio-open-1.0
- MOSS-SoundEffect [Đ]: https://github.com/OpenMOSS/MOSS-TTS
- AudioCraft/AudioGen [Đ]: https://github.com/facebookresearch/audiocraft
- AudioLDM [Đ]: https://github.com/haoheliu/AudioLDM · AudioLDM2: https://github.com/haoheliu/AudioLDM2
- Tango [Đ]: https://github.com/declare-lab/tango · TangoFlux: https://github.com/declare-lab/TangoFlux
- Make-An-Audio 2 [Đ]: https://github.com/bytedance/Make-An-Audio-2 · EzAudio: https://github.com/haidog-yaqub/EzAudio
- MMAudio [Đ]: https://github.com/hkchengrex/MMAudio
- HunyuanVideo-Foley [Đ]: https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley
- ThinkSound [Đ]: https://github.com/FunAudioLLM/ThinkSound
- ControlFoley [Đ]: https://github.com/xiaomi-research/controlfoley
- Woosh [Đ]: https://github.com/SonyResearch/Woosh
- FoleyCrafter [Đ]: https://github.com/open-mmlab/FoleyCrafter
- Kling-Foley [Đ]: https://github.com/klingfoley/Kling-Foley
- VGGSound (lớp "fire crackling") [Đ]: https://github.com/hche11/VGGSound
- Danh mục âm thanh AudioSet [Đ]: https://github.com/audioset/ontology
- YouTube, nội dung tổng hợp [S]: https://support.google.com/youtube/answer/14328491. Chính sách kiếm tiền [S]: https://support.google.com/youtube/answer/1311392

**Bản thu và giấy phép** (tất cả [S])
- Freesound, ví dụ file CC0: https://freesound.org/s/729396 · diễn đàn về thu tiếng lửa: https://freesound.org/forum/freesound-project/44355
- OpenGameArt: https://opengameart.org/content/fireplace-sound-loop · https://opengameart.org/node/16327
- BigSoundBank: https://bigsoundbank.com/droit.html
- YouTube Audio Library: https://support.google.com/youtube/answer/3376882
- Điều kiện Content ID: https://support.google.com/youtube/answer/2605065
- Vụ nhiễu trắng bị nhận Content ID: https://www.tubefilter.com/2018/01/05/white-noise-youtube-content-id/
- Pixabay: https://pixabay.com/service/faq/ · Mixkit: https://mixkit.co/license/ · ZapSplat: https://www.zapsplat.com/faq-category/license-and-usage/
- Sonniss GDC 2026: https://rekkerd.org/sonniss-releases-gdc-2026-game-audio-bundle/
- BBC Sound Effects: https://www.diyphotography.net/the-bbc-sound-effects-archive-is-now-free-to-download-with-over-33000-files/
- Loại gỗ và tiếng lách tách: https://sfxengine.com/blog/fire-crackling-sound-effect

---

## 9. Đã làm: `fire.py`, tiếng lửa tổng hợp trộn thêm một chút bản thu thật

Hướng đã chọn: **lớp chính là tiếng lửa tổng hợp, trộn thêm một chút bản thu thật bên dưới**.
`fire.py` là file mới. Nó dùng lại `rain.py` và `rainmix.py` nhưng không sửa hai file này.

### Chuẩn bị bản thu

Chép bản thu lửa vào `library/lua/`. Tên thư mục tuỳ bạn, nên đặt không dấu.
- Có thể dùng bản tự thu hoặc file CC0. Mỗi file nên dài vài phút trở lên và không có tiếng người hay xe.
- Nhiều file thì các bản xuất ít trùng nhau hơn.
- Không cần chỉnh âm lượng trước, `fire.py` tự cân.
- Có thể chia thư mục theo loại: `lua_trai/`, `lo_suoi/`, `than_hong/`.

### Dùng

```bash
python fire.py presets                                                      # campfire, fireplace, crackling, embers
python fire.py render -p fireplace --real lua -d 10m -o lo_suoi.flac        # tổng hợp + bản thu (nhỏ hơn 6 dB)
python fire.py render -p campfire -d 10m -o lua_trai.flac                   # chỉ tổng hợp
python fire.py batch -p campfire,fireplace --real lua -n 20 -d 1h --outdir output -j 4
python fire.py video videos/ -p fireplace --real lua --outdir output       # thay tiếng gốc của video
```

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `--real THƯ_MỤC` | trộn bản thu trong `library/THƯ_MỤC`; bỏ trống thì chỉ có tiếng tổng hợp |
| `--real-db` | độ lớn bản thu so với tiếng tổng hợp: `-6` (mặc định) là "một chút", `-12` là rất nhẹ, `0` là ngang nhau |
| `-p`, `-s`, `-v`, `-d`, `--loudness`, `--fade`, `-j`, `--format`, `--overwrite` | giống `rain.py`; độ lớn mặc định là −20 LUFS |
| `--library` | thư mục thư viện khác (mặc định `library`) |

Mỗi seed tạo ra một bản khác nhau:
- tiếng lửa tổng hợp mới hoàn toàn;
- bản thu được chọn đoạn khác, nối bằng crossfade 3 giây;
- tốc độ phát bản thu lệch khoảng ±3%;
- tần số cắt trầm lệch khoảng ±15%;
- độ lớn bản thu dâng hạ chậm khoảng ±2 dB.

Như vậy dù chỉ có một bản thu, các video vẫn không trùng nhau. `manifest.csv` ghi seed, preset,
thư mục bản thu, `real_db` và mọi thông số, nên tạo lại được đúng một bản.

### Khác với bản thử nghiệm

- Độ lớn được cân trên 60 giây đầu thay vì 30 giây, vì tiếng lửa lên xuống nhiều hơn tiếng mưa.
- Có **limiter nhìn trước khoảng 1 ms**, giới hạn ở −3,3 dBFS:
  - limiter chỉ giảm mượt vài tiếng nổ to nhất (dưới 0,07% số mẫu), không bẻ đỉnh;
  - không bẻ đỉnh thì tiếng nổ không bị méo và đỉnh giữa các mẫu không vượt 0 dB, nên nén AAC trong video vẫn còn khoảng trống;
  - đo trên 12 bản dài 3 phút: đỉnh thật từ −3,0 đến −0,5 dBTP; độ lớn −21,0 đến −18,8 LUFS.
    Bản "embers" dao động nhiều nhất vì nó thưa.
- Tiếng nổ được lọc trên 14 kHz dốc hơn.
- Tốc độ: khoảng 1,5–2 phút CPU cho 1 giờ âm thanh, chưa tính phần đọc bản thu.

### Kiểm thử

`python -m unittest test_fire` chạy 7 test:
- thông số theo seed;
- độ dài và độ lớn của từng preset;
- tái lập theo seed;
- limiter ở ranh giới khối;
- trộn bản thu, dùng một file nhiễu trầm làm "bản thu" giả;
- lệnh `batch` có `--real`.

Các test có sẵn của `rain.py` và `rainmix.py` vẫn qua hết.

**Chưa kiểm chứng:** môi trường này không tải được bản thu lửa thật nào, vì Freesound bị chặn.
Phần trộn chỉ mới thử với nhiễu giả lập, nên cần bạn thử với bản thu thật và nghe xem mức `--real-db` nào hợp.
Mẫu nghe thử tiếng tổng hợp (không có bản thu): `samples/fire_*.mp3`.

## 10. Sửa lỗi "nghe giống tiếng gió" (theo nhận xét khi nghe)

Người nghe nhận xét bản đầu của `fire.py` **giống tiếng gió hơn tiếng lửa**. Số đo khớp với nhận xét đó:
- 64–72% năng lượng nằm dưới 300 Hz, là một tiếng ù-ào liên tục;
- lớp "lửa liếm" là nhiễu dải 180–1800 Hz dâng hạ chậm;
- tiếng xì là nhiễu dải cao dâng hạ chậm;
- hai lớp này được tạo đúng theo công thức của tiếng gió;
- tiếng nổ quá thưa và quá nhỏ.

Thước đo mới `prototypes/windiness.py` đo ba chỉ số:
- độ nhọn của dải 2–10 kHz;
- tỉ lệ dao động chậm (0,1–2 Hz) so với nhanh (4–40 Hz) của đường bao;
- tỉ lệ năng lượng trầm.

Mốc so sánh là preset `wind` của `rain.py`, có tỉ lệ chậm/nhanh **+6,2 dB**.

Các thay đổi:
1. **Lửa liếm theo đúng Farnell**: lọc nhiễu quanh 30 Hz (Q 5), khuếch đại rồi **cắt đỉnh cứng**, sau đó lọc 80–3500 Hz.
   Kết quả là nhịp phành phạch nhiều hài, thay cho tiếng ù dâng hạ.
2. **Tiếng xì theo Farnell**: điều biên bằng (nhiễu lọc ~1 Hz)⁴, nên phần lớn thời gian im và chỉ thỉnh thoảng bùng lên.
   Chuẩn hoá theo công suất (E[x⁸] = 105) để các cơn xì không quá to.
3. **Lớp mới "rì rì" (fizz)**: 60–300 tiếng tách li ti mỗi giây ở 2,5–12 kHz. Lớp này thay cho tiếng xì mịn.
4. **Tiếng gầm giảm mạnh** (0,5 → 0,12), chỉ còn để tạo độ ấm.
5. **Tiếng nổ dày hơn và to hơn**: lửa trại 7 tiếng gốc mỗi giây, củi lách tách 12.
6. Độ lớn được cân **sau** limiter, vì giờ tiếng nổ là phần chính.

Độ lớn từng lớp so với tổng (dB, seed 1, 2 phút):

| Preset | gầm | liếm | xì | rì rì | tiếng nổ + sự kiện | chậm/nhanh dB | % dưới 300 Hz |
|---|---|---|---|---|---|---|---|
| campfire | −11,2 | −11,8 | −12,6 | −5,5 | **−2,8** | −7,9 | 35 |
| fireplace | −13,7 | −13,9 | −14,0 | −6,8 | **−3,6** | −4,9 | 38 |
| crackling | −22,3 | −21,3 | −18,5 | −5,4 | **−1,6** | −7,1 | 7 |
| embers | −9,9 | −20,4 | −9,1 | **−2,4** | −7,3 | −8,6 | 40 |
| *(mốc) gió `rain.py`* | | | | | | **+6,2** | 5 |

Ở bản cũ, tỉ lệ chậm/nhanh của lửa đã âm. Vì vậy chỉ số này **không giải thích được hết** vì sao bản cũ nghe như gió.
Nguyên nhân chính có lẽ là lớp ù-ào liên tục quá lớn so với tiếng nổ. Đây là suy luận từ số đo, cần tai người xác nhận.

Kiểm tra 8 bản dài 3 phút: độ lớn từ −20,8 đến −18,7 LUFS, đỉnh thật ≤ −1,1 dBTP.
Mẫu mới nằm trong `samples/fire_*.mp3`.

**Cần nghe lại.** Lớp "rì rì" dày có thể bị nghe thành tiếng mưa lắc rắc hoặc tiếng nhiễu sóng radio.
Nếu vậy thì giảm `fizz_level` hoặc `fizz_rate`.
