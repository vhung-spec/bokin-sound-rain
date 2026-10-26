"""Rain Mixer Studio: giao diện mix tiếng mưa chạy trên máy của bạn (python rainmix.py studio)."""
from __future__ import annotations

import json
import secrets
import threading
import time
import traceback
import uuid
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

import rain
import rainmix

PAGE = Path(__file__).with_name("studio.html")
AUDIO_TYPES = {".wav": "audio/wav", ".flac": "audio/flac", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
               ".opus": "audio/ogg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".aif": "audio/aiff", ".aiff": "audio/aiff"}
MAX_PREVIEW_SECONDS = 180


class BadRequest(Exception):
    pass


class Studio:
    def __init__(self, library_dir: Path, recipes_dir: Path, outdir: Path):
        self.library = rainmix.Library(library_dir)
        self.recipes_dir, self.outdir = recipes_dir, outdir
        self.jobs: dict[str, dict] = {}
        self.export_lock = threading.Lock()  # one export at a time keeps the machine responsive

    # -- state

    def state(self) -> dict:
        folders = []
        for folder, files in self.library.folders().items():
            items = []
            for rel in files:
                try:
                    duration = self.library.info(rel, loudness=False)["duration"]
                except (OSError, RuntimeError, ValueError):
                    duration = None
                items.append({"path": rel, "name": Path(rel).name, "duration": duration})
            durations = [i["duration"] for i in items if i["duration"]]
            short = bool(durations) and float(np.median(durations)) < 15
            folders.append({"name": folder, "files": items, "suggested_type": "events" if short else "bed"})
        self.library.save()
        synth = [{"id": f"synth:{key}", "label": desc, "kind": "bed"} for key, (desc, _) in rain.PRESETS.items()]
        synth += [{"id": f"synth:{key}", "label": label, "kind": "events"} for key, label in rainmix.SYNTH_EVENTS.items()]
        return {
            "library": folders,
            "library_dir": str(self.library.root.resolve()),
            "outdir": str(self.outdir.resolve()),
            "synth": synth,
            "recipes": sorted(p.stem for p in self.recipes_dir.glob("*.json")),
            "layer_defaults": asdict(rainmix.Layer()),
            "recipe_defaults": {k: v for k, v in asdict(rainmix.Recipe()).items() if k != "layers"},
            "formats": [e.lstrip(".") for e in rain.AUDIO_CODECS],
        }

    # -- recipes

    def load_recipe(self, name: str) -> dict:
        path = self.recipes_dir / f"{rainmix.slugify(name)}.json"
        if not path.is_file():
            raise BadRequest(f"không có công thức '{name}'")
        return rainmix.Recipe.from_dict(json.loads(path.read_text(encoding="utf-8"))).to_dict()

    def save_recipe(self, body: dict) -> dict:
        recipe = rainmix.Recipe.from_dict(body.get("recipe") or {})
        name = rainmix.slugify(body.get("name") or recipe.name)
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        path = self.recipes_dir / f"{name}.json"
        path.write_text(json.dumps(recipe.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"name": name}

    # -- audio

    def preview(self, body: dict) -> tuple[bytes, dict]:
        recipe = rainmix.Recipe.from_dict(body.get("recipe") or {})
        seconds = float(np.clip(float(body.get("seconds", 30)), 2, MAX_PREVIEW_SECONDS))
        seed = int(body.get("seed") or 0)
        started = time.time()
        data, warnings = rainmix.preview_wav(recipe, self.library, seed, seconds)
        return data, {"warnings": warnings, "render_seconds": round(time.time() - started, 2)}

    # -- export

    def export(self, body: dict) -> dict:
        recipe = rainmix.Recipe.from_dict(body.get("recipe") or {})
        seed_text = str(body.get("seed") or "").strip()
        seed0 = int(seed_text) if seed_text else secrets.randbelow(2**31)
        videos_dir = str(body.get("videos") or "").strip()
        slug = rainmix.slugify(recipe.name)
        outputs = []
        if videos_dir:
            try:
                videos = rain.find_videos([videos_dir])
            except SystemExit as e:
                raise BadRequest(str(e))
            if not videos:
                raise BadRequest(f"không có video nào trong {videos_dir}")
            for video in videos:
                ext = ".webm" if video.suffix.lower() == ".webm" else ".mp4"
                outputs.append((self.outdir / f"{video.stem}_rain{ext}", rain.media_duration(video), video))
        else:
            try:
                seconds = rain.parse_duration(str(body.get("duration") or "10m"))
            except Exception as e:
                raise BadRequest(str(e))
            fmt = str(body.get("format") or "flac")
            if f".{fmt}" not in rain.AUDIO_CODECS:
                raise BadRequest(f"định dạng không hỗ trợ: {fmt}")
            count = int(np.clip(int(body.get("count") or 1), 1, 500))
            outputs = [(self.outdir / f"{slug}_{i + 1:04d}_s{seed0 + i}.{fmt}", seconds, None) for i in range(count)]
        job = {"id": uuid.uuid4().hex[:8], "recipe": recipe.name, "status": "queued", "total": len(outputs),
               "done": 0, "current": "", "progress": 0.0, "files": [], "errors": [], "warnings": [], "skipped": [],
               "outdir": str(self.outdir.resolve()), "started": time.time()}
        self.jobs[job["id"]] = job
        threading.Thread(target=self._run_export, args=(job, recipe, seed0, outputs), daemon=True).start()
        return {"job": job["id"]}

    def _run_export(self, job, recipe, seed0, outputs):
        with self.export_lock:
            job["status"] = "running"
            try:
                job["warnings"] += self.library.prepare(recipe)
                for i, (out, seconds, video) in enumerate(outputs):
                    if out.exists():
                        job["skipped"].append(out.name)
                        job["done"] += 1
                        continue
                    job["current"], job["progress"] = out.name, 0.0
                    spec = {"recipe": recipe.to_dict(), "library": str(self.library.root), "seed": seed0 + i,
                            "seconds": seconds, "output": str(out), "video": str(video) if video else None,
                            "progress": lambda f: job.__setitem__("progress", f)}
                    try:
                        row = rainmix.run_mix_job(spec)
                        rain.append_manifest(self.outdir / "manifest.csv", [row])
                        job["files"].append(row["file"])
                    except Exception as e:
                        job["errors"].append(f"{out.name}: {e}")
                    job["done"] += 1
                job["status"] = "done"
            except Exception as e:
                job["errors"].append(str(e))
                job["status"] = "error"
            job["current"] = ""


def make_handler(studio: Studio):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RainMixerStudio/1.0"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def _json(self, data, status=200):
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise BadRequest("dữ liệu gửi lên không phải JSON")

        def _send_file(self, path: Path, content_type: str):
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range", "")
            if header.startswith("bytes=") and size:
                first, _, last = header[6:].split(",")[0].partition("-")
                if first:
                    start, end = int(first), min(int(last) if last else size - 1, size - 1)
                elif last:
                    start = max(0, size - int(last))
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as fh:
                fh.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    piece = fh.read(min(65536, remaining))
                    if not piece:
                        break
                    self.wfile.write(piece)
                    remaining -= len(piece)

        def _handle(self, method):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if method == "GET" and url.path == "/":
                    self._send_file(PAGE, "text/html; charset=utf-8")
                elif method == "GET" and url.path == "/api/state":
                    self._json(studio.state())
                elif method == "GET" and url.path == "/api/recipe":
                    self._json(studio.load_recipe(query.get("name", "")))
                elif method == "POST" and url.path == "/api/recipe":
                    self._json(studio.save_recipe(self._body()))
                elif method == "GET" and url.path == "/api/file":
                    path = studio.library.resolve(query.get("path", ""))
                    if not path.is_file():
                        raise BadRequest("không có file này")
                    self._send_file(path, AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream"))
                elif method == "POST" and url.path == "/api/preview":
                    data, meta = studio.preview(self._body())
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Mix-Info", json.dumps(meta))  # ASCII-escaped JSON
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                elif method == "POST" and url.path == "/api/export":
                    self._json(studio.export(self._body()))
                elif method == "GET" and url.path == "/api/jobs":
                    jobs = sorted(studio.jobs.values(), key=lambda j: j["started"], reverse=True)
                    self._json({"jobs": jobs})
                else:
                    self._json({"error": "không tìm thấy"}, 404)
            except (BadRequest, ValueError) as e:
                self._json({"error": str(e)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                traceback.print_exc()
                self._json({"error": f"lỗi: {e}"}, 500)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def serve(library_dir: Path, recipes_dir: Path, outdir: Path, port=8765, open_browser=True):
    library_dir.mkdir(parents=True, exist_ok=True)
    recipes_dir.mkdir(parents=True, exist_ok=True)
    studio = Studio(library_dir, recipes_dir, outdir)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(studio))
    except OSError as e:
        raise SystemExit(f"Không mở được cổng {port} ({e}); thử --port khác, ví dụ --port 8780")
    url = f"http://127.0.0.1:{port}/"
    print(f"Rain Mixer Studio đang chạy tại {url}")
    print(f"Thư viện âm thanh: {library_dir.resolve()}")
    print("Nhấn Ctrl+C để tắt.")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã tắt Studio.")
    finally:
        server.server_close()
    return 0
