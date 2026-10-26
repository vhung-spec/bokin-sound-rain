# bokin-sound-rain

Công cụ tạo tiếng mưa hàng loạt cho video mưa, kèm tổng hợp các công cụ và dự án mã nguồn mở liên quan.

- **Rain Mixer Studio** (`rainmix.py`): phòng mix trên trình duyệt. Trộn nhiều lớp **bản thu thật**
  và tiếng tổng hợp, nghe thử ngay, lưu thành "công thức", rồi xuất hàng loạt bản, mỗi bản một khác.
- **`rain.py`**: tạo tiếng mưa hoàn toàn bằng thuật toán, không cần bản thu.

## Cài đặt

- Python 3.9 trở lên, rồi chạy `pip install -r requirements.txt` (chỉ cần numpy)
- [ffmpeg](https://ffmpeg.org/download.html) (có cả `ffprobe`)

## Rain Mixer Studio

Tiếng mưa nghe thật nhất vẫn đến từ **bản thu thật**. Rain Mixer lấy các bản thu của bạn,
cắt ra những đoạn ngẫu nhiên và nối mượt bằng crossfade dài 3 giây, nên một bản thu 10 phút
có thể thành bản mưa 3 giờ mà không lặp lại rõ. Nó trộn thêm các lớp khác (mái tôn, mưa ngoài sân,
giọt nước, sấm), rồi cân âm lượng tổng theo LUFS.
Mỗi lần xuất với seed mới, bản mix sẽ khác đi:

- chọn đoạn khác và nối theo thứ tự khác
- âm lượng mỗi lớp lệch nhẹ (khoảng ±1.5 dB), tần số lọc lệch nhẹ (±16%)
- tốc độ phát lệch nhẹ (±3%), nên cao độ và nhịp mưa đổi theo
- tiếng sấm và giọt nước rơi vào lúc khác

### Bắt đầu

1. Chép bản thu vào các thư mục con của `library/`, ví dụ `library/mai_ton/`, `library/sam/`
   (xem [library/README.md](library/README.md)). Chưa có bản thu thì vẫn mix được bằng tiếng tổng hợp.
2. Mở Studio: bấm đúp `mo_studio.bat` (Windows) hoặc `mo_studio.sh` (macOS/Linux),
   hoặc chạy `python rainmix.py studio`. Trình duyệt sẽ mở `http://127.0.0.1:8765/`.
3. Thêm lớp, kéo thanh trượt. Studio tự trộn lại 30 giây để bạn nghe ngay.
   - **S**: nghe riêng một lớp. **▶** trên lớp: nghe một bản thu gốc.
   - **🎲 Bản khác**: nghe một biến thể khác của cùng công thức.
   - Nhấp đúp vào thanh trượt để trả về mặc định.
4. Bấm **Lưu**. Công thức được lưu thành file JSON trong `recipes/`.
5. **Xuất file âm thanh** (chọn số bản và độ dài), hoặc nhập thư mục video rồi bấm
   **Ghép tiếng mưa vào video**: mỗi video nhận một bản mix riêng, dài đúng bằng video.
   File ra nằm trong `output/`, kèm `manifest.csv` ghi seed và thông số từng bản.

### Lớp âm thanh

| Kiểu | Dùng cho | Thanh chỉnh |
|---|---|---|
| **Nền liên tục** | mưa rơi, mái tôn, máng xối, côn trùng | âm lượng, cắt trầm/chói, độ rộng stereo, tốc độ phát, to nhỏ dần |
| **Âm rời rạc** | sấm, giọt nước to, cành cây rơi | tần suất, chênh to nhỏ giữa các lần, trải trái–phải, khoảng cách tối thiểu |

Nguồn của một lớp có thể là:

- một thư mục trong thư viện
- một kiểu mưa tổng hợp của `rain.py` (`synth:roof`, `synth:medium`…)
- tiếng sấm hoặc giọt nước tổng hợp (`synth:thunder`, `synth:drip`)

Có sẵn 3 công thức mẫu: `mai_ton_dem` (mưa mái tôn đêm khuya), `mua_rao_co_sam` (mưa rào có sấm),
`mua_em_de_ngu` (mưa êm dễ ngủ). Các lớp bản thu trong đó dùng thư mục `mai_ton`, `mua_nen`, `giot_nuoc`, `sam`.
Thư mục nào còn trống thì lớp đó được bỏ qua kèm cảnh báo.

### Dùng bằng dòng lệnh

```bash
# Một bản 10 phút
python rainmix.py render mai_ton_dem -d 10m -o mai_ton.flac

# 20 bản, mỗi bản 1 giờ, xuất song song 4 bản
python rainmix.py batch mai_ton_dem -n 20 -d 1h --outdir output -j 4

# Một bản mix riêng cho mỗi video trong thư mục videos/
python rainmix.py video mai_ton_dem videos/ --outdir output
```

Tuỳ chọn chung: `-s` (seed bắt đầu), `--loudness` và `-v` (ghi đè độ lớn tổng và mức khác nhau của
công thức), `--library` và `--recipes` (đường dẫn thư mục khác).

Lần đầu dùng một thư mục, Rain Mixer cần đo độ dài và độ lớn từng file nên sẽ chậm hơn.
Kết quả được lưu trong `library/.rainmix-cache.json`, nên các lần sau nhanh.
Trên máy thử, công thức `mai_ton_dem` (6 lớp, có 2 lớp tổng hợp) xuất 1 giờ mất khoảng 3,5 phút
trên một nhân CPU và dùng khoảng 300 MB RAM, dù bản dài bao nhiêu. Lớp từ bản thu nhanh hơn lớp tổng hợp.

### Lấy bản thu thật ở đâu

- **Tự thu** bằng điện thoại hoặc máy ghi âm: an toàn nhất về bản quyền, và là âm thanh riêng của kênh bạn.
- **Freesound** (lọc giấy phép CC0), **Pixabay Sound Effects**, **gói Sonniss GDC**: xem bảng giấy phép ở cuối trang.
- **Stable Audio Open** chạy trên máy: tạo tiếng mưa từ mô tả chữ, dùng thương mại được nếu doanh thu dưới 1 triệu USD/năm.

## Tạo tiếng mưa bằng thuật toán: `rain.py`

`rain.py` tổng hợp tiếng mưa bằng thuật toán, không dùng file thu âm hay mô hình AI,
nên âm thanh hoàn toàn thuộc về bạn. Mỗi bản dùng một **seed** riêng: vị trí từng giọt mưa,
nhịp mưa to nhỏ và tiếng sấm đều khác nhau. Các thông số như độ dày hạt, độ trầm, độ rộng
stereo cũng lệch nhẹ (mặc định khoảng ±16%) so với kiểu mưa gốc. Nhờ vậy các video
nghe cùng một phong cách nhưng không bản nào giống bản nào.

### Kiểu mưa (preset)

| Tên | Mô tả |
|---|---|
| `light` | Mưa nhẹ, lất phất |
| `medium` | Mưa vừa, đều hạt (mặc định) |
| `heavy` | Mưa lớn, nặng hạt |
| `storm` | Mưa giông có sấm (khoảng 1 tiếng sấm mỗi 1–2 phút) |
| `roof` | Mưa rào trên mái tôn: tiếng ào ào kim loại, xen tiếng "bộp" của giọt to |
| `roof_light` | Mưa nhẹ trên mái tôn: lộp độp từng tiếng |

### Cách dùng

```bash
# Nghe thử một kiểu mưa trong 30 giây
python rain.py render -p roof -d 30s -o thu_roof.flac

# Tạo 50 file, mỗi file 1 giờ, mỗi file chọn ngẫu nhiên 1 trong 3 kiểu mưa, chạy song song 4 file
python rain.py batch -p light,medium,heavy -n 50 -d 1h --outdir output -j 4

# Ghép tiếng mưa riêng cho mọi video trong thư mục videos/
python rain.py video videos/ --outdir output -p medium,heavy -j 2
```

- Chế độ `video` **thay** tiếng gốc bằng tiếng mưa dài đúng bằng video. Hình được giữ nguyên,
  không nén lại nên chạy nhanh. File ra có tên `<tên video>_rain.mp4`.
- Mỗi lần chạy, `manifest.csv` trong thư mục đầu ra được ghi thêm seed, kiểu mưa và toàn bộ thông số của từng file.
  Muốn tạo lại đúng một bản, dùng lại cùng `-p`, `-s` (seed) và `-v`.
- Chạy lại cùng lệnh thì file đã có sẽ được bỏ qua, nên có thể dừng giữa chừng rồi chạy tiếp.
  Thêm `--overwrite` để ghi đè.

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `-p, --preset` | một kiểu, nhiều kiểu cách nhau dấu phẩy, hoặc `all` |
| `-v, --variation` | mức khác nhau giữa các bản: `0` = giống hệt preset, `0.15` = mặc định, `0.3` = khác nhiều |
| `-s, --seed` | seed bắt đầu; file thứ i dùng seed + i (mặc định: ngẫu nhiên) |
| `-d, --duration` | độ dài: `90s`, `10m`, `1h30m`, `01:30:00` |
| `--loudness` | độ lớn trung bình theo LUFS, mặc định `-18` (YouTube chỉ giảm âm lượng video to hơn −14) |
| `--fade` | fade vào/ra, mặc định 3 giây |
| `--format` | (batch) `flac` mặc định, hoặc `wav`, `mp3`, `m4a`, `ogg`, `opus` |
| `-j, --jobs` | số file/video xử lý song song |

Tốc độ đo trên máy thử, mỗi file chạy trên 1 nhân CPU: 1 giờ âm thanh mất khoảng 50 giây.
Tiếng mưa là nhiễu nên nén kém: FLAC khoảng 900 MB mỗi giờ. Nếu cần file nhẹ, dùng `--format mp3` hoặc `m4a`.
Chế độ video ghi âm thanh AAC 256 kbps (khoảng 115 MB mỗi giờ).

Muốn chỉnh âm sắc, sửa bảng `PRESETS` trong `rain.py`. Ý nghĩa từng thông số được chú thích trong `RainParams`.
Mái tôn được mô phỏng như **một tấm kim loại mỏng dùng chung**. Mỗi giọt đập vào tấm tôn tại một
vị trí khác nhau, làm rung cùng một tập cộng hưởng: giọt nhỏ kêu "tách", giọt to kêu "bộp".

Chạy toàn bộ test bằng `python -m unittest test_rain test_rainmix`.

---

*Phần dưới là tra cứu công cụ, thực hiện tháng 10/2026. Giấy phép có thể thay đổi, hãy đọc lại file LICENSE trước khi dùng.*

## Lưu ý về giấy phép khi đăng YouTube có kiếm tiền

Video bật kiếm tiền được tính là **sử dụng thương mại**. Nhiều mô hình AI có code
mở (MIT/Apache) nhưng **trọng số (weights) lại là CC-BY-NC 4.0 = cấm thương mại**,
nên âm thanh tạo ra không nên dùng cho video kiếm tiền.

## 1. AI tạo âm thanh từ video (video-to-audio / Foley)

Đưa video mưa vào, mô hình tự tạo âm khớp với hình (mưa rơi, giọt nước, sấm…).
Các mô hình này thường tạo đoạn ngắn (~8–10 giây), phù hợp để làm một đoạn rồi lặp lại.

| Dự án | Đầu vào | Phần cứng | Giấy phép | Kiếm tiền? |
|---|---|---|---|---|
| [HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley) (Tencent) | video + mô tả text, xuất 48 kHz | XXL: 20 GB VRAM (12 GB khi offload); XL: 16 GB (8 GB khi offload) | Tencent Hunyuan Community License | **Được** (dùng ở Việt Nam), nhưng giấy phép cấm dùng/hiển thị kết quả ở EU, Anh, Hàn Quốc; video YouTube công khai xem được ở đó nên là vùng xám |
| [MMAudio](https://github.com/hkchengrex/MMAudio) | video và/hoặc text, mặc định 8 s | ~6 GB VRAM (16-bit) | code MIT / weights CC-BY-NC 4.0 | Không |
| [ThinkSound / PrismAudio](https://github.com/FunAudioLLM/ThinkSound) | video + text (có suy luận CoT), có giao diện Gradio | không ghi | Apache 2.0, nhưng README ghi "Commercial use is NOT permitted", muốn dùng thương mại phải liên hệ tác giả | Không |
| [ControlFoley](https://github.com/xiaomi-research/controlfoley) (Xiaomi, ACM MM 2026) | video, text, audio mẫu; có node ComfyUI chính thức | GPU NVIDIA, CUDA 11.8+ | code Apache 2.0 / weights CC-BY-NC 4.0 | Không |
| [Woosh](https://github.com/SonyResearch/Woosh) (Sony AI) | text→audio và video→audio | không ghi | code MIT/Apache / weights CC-BY-NC | Không |
| [FoleyCrafter](https://github.com/open-mmlab/FoleyCrafter) | video + prompt | không ghi | Apache 2.0; với thương mại, README bảo kiểm tra giấy phép của Auffusion | Cần kiểm tra |

Danh sách đầy đủ hơn: [Awesome-Vision2Audio](https://github.com/Xiaohao-Liu/Awesome-Vision2Audio).

## 2. AI tạo âm thanh từ mô tả chữ (text-to-audio)

| Dự án | Ghi chú | Kiếm tiền? |
|---|---|---|
| [Stable Audio Open 1.0](https://huggingface.co/stabilityai/stable-audio-open-1.0) | tối đa ~47 s, stereo 44.1 kHz; prompt ví dụ: `heavy rain on a tin roof, distant thunder` | **Được** theo Stability AI Community License nếu doanh thu dưới 1 triệu USD/năm |
| [AudioGen (AudioCraft, Meta)](https://github.com/facebookresearch/audiocraft) | tạo hiệu ứng âm thanh từ text | Không (weights CC-BY-NC 4.0) |

## 3. Tự tổng hợp tiếng mưa bằng thuật toán (procedural)

Âm thanh do bạn tự tạo hoàn toàn: không lo giấy phép, ít rủi ro bị người khác
nhận bản quyền (Content ID), và có thể tạo dài bao nhiêu cũng được.

- **ffmpeg** (đã chạy thử): tạo nền mưa đều từ nhiễu hồng + nhiễu nâu, xem lệnh ở mục 5.
- [Raindrop-Generator](https://github.com/747745124/Raindrop-Generator): plugin VST/AU (C++), mô phỏng giọt mưa theo một bài báo DAFx.
- [Audiokinetic: Generating Rain With Pure Synthesis](https://blog.audiokinetic.com/generating-rain-with-pure-synthesis/):
  bài hướng dẫn thiết kế mưa bằng nhiều lớp nhiễu hồng + tiếng giọt nước.
- Sách *Designing Sound* (Andy Farnell): có bài thực hành làm tiếng mưa bằng Pure Data.
- [Audacity](https://www.audacityteam.org/): trình biên tập âm thanh mã nguồn mở, có bộ tạo nhiễu và EQ,
  dùng để ghép lớp và làm vòng lặp có crossfade.

## 4. Thư viện tiếng mưa thu sẵn

| Nguồn | Giấy phép |
|---|---|
| [Freesound](https://freesound.org/) | mỗi file một giấy phép; lọc **CC0** để dùng thoải mái |
| [Pixabay Sound Effects](https://pixabay.com/sound-effects/search/rain/) | miễn phí, dùng thương mại, không cần ghi nguồn |
| [Sonniss GDC Game Audio Bundle](https://sonniss.com/gameaudiogdc) | royalty-free, dùng thương mại, không cần ghi nguồn; cần xem danh sách file có tiếng mưa không |
| YouTube Audio Library (trong YouTube Studio) | dùng được cho video YouTube |
| [BBC Sound Effects](https://sound-effects.bbcrewind.co.uk/) | chỉ cá nhân/giáo dục, **không** dùng thương mại |

Ứng dụng phát tiếng mưa như [Moodist](https://github.com/remvze/moodist) (MIT) hay
[Blanket](https://github.com/rafaelmardojai/blanket) có code mở, nhưng các file âm thanh bên trong
có nguồn và giấy phép khác nhau, nên đừng thu lại để đưa vào video khi chưa kiểm tra.

## 5. Lệnh ffmpeg dùng ngay

Tạo 60 giây nền mưa stereo (nhiễu hồng cho tiếng rào rào, nhiễu nâu cho tiếng trầm):

```bash
ffmpeg -y \
  -f lavfi -i "anoisesrc=c=pink:r=48000:a=0.5:d=60:s=1" \
  -f lavfi -i "anoisesrc=c=pink:r=48000:a=0.5:d=60:s=2" \
  -f lavfi -i "anoisesrc=c=brown:r=48000:a=0.9:d=60:s=3" \
  -filter_complex "[0][1]join=inputs=2:channel_layout=stereo,highpass=f=300,lowpass=f=8000[hiss];[2]lowpass=f=500,pan=stereo|c0=c0|c1=c0[rumble];[hiss][rumble]amix=inputs=2:weights='0.7 1':normalize=0,tremolo=f=0.2:d=0.15,loudnorm=I=-23:TP=-2[out]" \
  -map "[out]" -ar 48000 rain_bed.wav
```

Chỉnh `lowpass=f=8000` thấp xuống (4000–6000) cho mưa nghe xa/êm hơn, cao lên cho mưa nặng hạt.

Ghép tiếng mưa vào video, tự lặp lại cho bằng độ dài video:

```bash
ffmpeg -i video_mua.mp4 -stream_loop -1 -i rain_bed.wav \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest video_co_tieng.mp4
```

## Quy trình gợi ý

1. **Gom bản thu**: tự thu hoặc lấy bản CC0 / Pixabay, chép vào `library/` theo từng loại.
   Có thể dùng Stable Audio Open hay HunyuanVideo-Foley để tạo thêm tiếng chi tiết
   (giọt rơi xuống vũng nước, sấm) nếu thiếu.
2. **Mix trong Rain Mixer Studio**: dựng công thức, nghe thử vài biến thể bằng 🎲, rồi lưu lại.
3. **Xuất hàng loạt** hoặc ghép thẳng vào video. Mỗi video nhận một bản mix riêng.
