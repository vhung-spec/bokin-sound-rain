# bokin-sound-rain

Công cụ tạo tiếng mưa hàng loạt cho video mưa, kèm tổng hợp các công cụ và dự án mã nguồn mở liên quan.

## Tạo tiếng mưa hàng loạt bằng `rain.py`

`rain.py` tổng hợp tiếng mưa bằng thuật toán, không dùng file thu âm hay mô hình AI,
nên âm thanh hoàn toàn thuộc về bạn. Mỗi bản dùng một **seed** riêng: vị trí từng giọt mưa,
nhịp mưa to nhỏ và tiếng sấm đều khác nhau. Các thông số như độ dày hạt, độ trầm, độ rộng
stereo cũng lệch nhẹ (mặc định khoảng ±16%) so với kiểu mưa gốc. Nhờ vậy các video
nghe cùng một phong cách nhưng không bản nào giống bản nào.

### Cài đặt

- Python 3.9 trở lên, rồi chạy `pip install -r requirements.txt` (chỉ cần numpy)
- [ffmpeg](https://ffmpeg.org/download.html) (có cả `ffprobe`)

### Kiểu mưa (preset)

| Tên | Mô tả |
|---|---|
| `light` | Mưa nhẹ, lất phất |
| `medium` | Mưa vừa, đều hạt (mặc định) |
| `heavy` | Mưa lớn, nặng hạt |
| `storm` | Mưa giông có sấm (khoảng 1 tiếng sấm mỗi 1–2 phút) |
| `roof` | Mưa trên mái tôn |

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
Chạy test bằng `python -m unittest test_rain`.

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

1. **Lớp nền**: tiếng mưa đều, dài (tạo bằng `rain.py`, ffmpeg hoặc bản ghi CC0).
2. **Lớp chi tiết**: chạy mô hình video-to-audio cho những đoạn có hành động rõ
   (giọt rơi xuống vũng nước, mái tôn, sấm). Nếu kiếm tiền, dùng HunyuanVideo-Foley
   hoặc Stable Audio Open.
3. **Trộn** trong Audacity, rồi ghép vào video bằng ffmpeg.
