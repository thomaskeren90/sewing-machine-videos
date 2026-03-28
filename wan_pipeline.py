#!/usr/bin/env python3
"""
🎬 Wan2.2 + Edge TTS Video Pipeline — 100% Free
=================================================
Generates 90 videos using:
  1. Edge TTS (free) → Indonesian voice MP3
  2. SiliconFlow Wan2.2 (free tier) → Video generation
  3. FFmpeg → Combine audio + video + text overlays

Usage:
  python3 wan_pipeline.py --key YOUR_SILICONFLOW_KEY
  python3 wan_pipeline.py --key YOUR_KEY --resume
  python3 wan_pipeline.py --dry-run

Get free API key: https://cloud.siliconflow.cn (signup → free credits)
"""

import os
import sys
import json
import time
import asyncio
import argparse
import subprocess
import requests
from datetime import datetime
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SCRIPTS_JSON = BASE_DIR / "scripts.json"
AVATAR_IMAGE = BASE_DIR / "avatars" / "main-avatar.jpeg"
OUTPUT_DIR = BASE_DIR / "output"
AUDIO_DIR = BASE_DIR / "audio"
VIDEO_DIR = BASE_DIR / "videos"
CHECKPOINT_FILE = BASE_DIR / "checkpoint.json"
MANIFEST_FILE = BASE_DIR / "manifest.json"

# SiliconFlow API
SF_BASE = "https://api.siliconflow.cn/v1"
SF_T2V_MODEL = "Wan-AI/Wan2.2-T2V-A14B"       # Text-to-Video
SF_I2V_MODEL = "Wan-AI/Wan2.2-I2V-A14B"       # Image-to-Video

# Voice settings
VOICE_ID = "id-ID-GadisNeural"  # Indonesian female
VOICE_RATE = "+0%"              # Normal speed
VOICE_PITCH = "+0Hz"            # Normal pitch

# Video settings
VIDEO_SIZE = "720x1280"         # Portrait 9:16 for TikTok/Shorts
POLL_INTERVAL = 20              # seconds between status checks
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 8            # seconds between API calls


# ─── CHECKPOINT ───────────────────────────────────────────────────────────
def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"completed": [], "failed": [], "audio_done": [], "last_run": None}


def save_checkpoint(cp):
    cp["last_run"] = datetime.now().isoformat()
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2, ensure_ascii=False))


# ─── STEP 1: EDGE TTS (FREE INDONESIAN VOICE) ────────────────────────────
def generate_audio(script_text, output_path):
    """Generate Indonesian voice MP3 using Edge TTS (free, Microsoft)."""
    cmd = [
        "edge-tts",
        "--voice", VOICE_ID,
        "--rate", VOICE_RATE,
        "--pitch", VOICE_PITCH,
        "--text", script_text,
        "--write-media", str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def batch_generate_audio(scripts, checkpoint):
    """Generate audio for all 90 scripts."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    success = 0
    skip = 0
    
    print("\n🎤 STEP 1: Generating Indonesian voiceovers...")
    
    for script in scripts:
        vid = script["id"]
        audio_file = AUDIO_DIR / f"V{vid:03d}.mp3"
        
        if vid in checkpoint.get("audio_done", []) and audio_file.exists():
            skip += 1
            continue
        
        print(f"  🎤 [{vid:03d}/90] {script['title'][:45]}...")
        
        if not script["script"]:
            print(f"     ⚠️ No script text, skipping")
            continue
        
        if generate_audio(script["script"], audio_file):
            size = audio_file.stat().st_size
            print(f"     ✅ {size // 1024}KB")
            checkpoint.setdefault("audio_done", []).append(vid)
            save_checkpoint(checkpoint)
            success += 1
        else:
            print(f"     ❌ TTS failed")
        
        time.sleep(0.5)  # Small delay to be nice
    
    print(f"\n  📊 Audio: {success} generated, {skip} skipped")
    return success


# ─── STEP 2: SILICONFLOW WAN2.2 VIDEO GENERATION ─────────────────────────
class SiliconFlowAPI:
    """SiliconFlow Wan2.2 API client."""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def upload_image(self, image_path):
        """Upload image and get URL for I2V."""
        url = f"{SF_BASE}/image/upload"
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": ("avatar.jpeg", f, "image/jpeg")}
            )
        if resp.status_code == 200:
            return resp.json().get("url")
        return None
    
    def submit_t2v(self, prompt, size="720x1280"):
        """Submit text-to-video job (Wan2.2)."""
        url = f"{SF_BASE}/video/submit"
        payload = {
            "model": SF_T2V_MODEL,
            "prompt": prompt,
            "negative_prompt": "blurry, low quality, distorted, ugly, bad anatomy",
            "image_size": size
        }
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code == 200:
            return resp.json().get("requestId")
        print(f"     ❌ Submit failed: {resp.status_code} — {resp.text[:200]}")
        return None
    
    def submit_i2v(self, prompt, image_url, size="720x1280"):
        """Submit image-to-video job (Wan2.2)."""
        url = f"{SF_BASE}/video/submit"
        payload = {
            "model": SF_I2V_MODEL,
            "prompt": prompt,
            "negative_prompt": "blurry, low quality, distorted, ugly",
            "image_size": size,
            "image": image_url
        }
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code == 200:
            return resp.json().get("requestId")
        print(f"     ❌ Submit failed: {resp.status_code} — {resp.text[:200]}")
        return None
    
    def check_status(self, request_id):
        """Poll video generation status."""
        url = f"{SF_BASE}/video/status"
        resp = requests.post(url, headers=self.headers, json={"requestId": request_id})
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            if status == "Succeed":
                # Get video URL from response
                videos = data.get("results", {}).get("videos", [])
                if videos:
                    return "completed", videos[0].get("url")
                # Alternative response format
                return "completed", data.get("url") or data.get("videoUrl")
            elif status == "Failed":
                return "error", data.get("message", "Unknown error")
            return "processing", None
        return "error", None


def build_video_prompt(script):
    """Build Wan2.2 prompt from script for product video."""
    title = script.get("title", "")
    category = script.get("category", "")
    product = script.get("product", "")
    
    # Create a vivid video prompt based on the script type
    prompts = {
        "01 Unboxing": f"A cute cartoon dumpling character with a crown opens a sewing machine box on a clean white table. Excited expression. Unboxing product reveal. Bright studio lighting. Vertical 9:16 format.",
        "02 Comparison": f"A cute cartoon dumpling character with a crown comparing two sewing machines side by side on a desk. Pointing at features. Product comparison showcase. Clean background. Vertical 9:16.",
        "03 Spare Parts": f"A cute cartoon dumpling character with a crown presenting sewing machine spare parts neatly arranged. Needles, bobbins, belts on display. Product showcase. Vertical 9:16.",
        "04 Tutorial": f"A cute cartoon dumpling character with a crown demonstrating sewing machine operation. Step by step tutorial style. Close-up of hands working. Bright lighting. Vertical 9:16.",
        "05 Before After": f"A cute cartoon dumpling character with a crown showing a rusty sewing machine transforming into a shiny new one. Before and after restoration. Vertical 9:16.",
        "06 Tips": f"A cute cartoon dumpling character with a crown giving tips about sewing machine maintenance. Holding oil bottle and tools. Educational style. Vertical 9:16.",
        "07 Problem Solving": f"A cute cartoon dumpling character with a crown fixing a sewing machine problem. Troubleshooting repair scene. Workshop background. Vertical 9:16.",
        "08 Review": f"A cute cartoon dumpling character with a crown reviewing a sewing machine. Rating stars appearing. Product review style. Clean background. Vertical 9:16.",
        "09 Price List": f"A cute cartoon dumpling character with a crown presenting sewing machine price list. Numbers and product images floating. Sales catalog style. Vertical 9:16.",
        "10 Behind Scenes": f"A cute cartoon dumpling character with a crown in a sewing machine workshop warehouse. Behind the scenes tour. Boxes and shelves. Vertical 9:16.",
        "11 Testimonial": f"A cute cartoon dumpling character with a crown reading happy customer reviews. Speech bubbles with stars. Testimonial showcase. Vertical 9:16.",
        "12 Quick Demo": f"A cute cartoon dumpling character with a crown doing a quick sewing machine demo. Fast stitching action. Speed showcase. Vertical 9:16.",
        "13 Myth Busters": f"A cute cartoon dumpling character with a crown debunking myths. Question marks and checkmarks. Myth vs fact style. Vertical 9:16.",
        "14 Trending": f"A cute cartoon dumpling character with a crown doing a trendy dance with a sewing machine. Viral content style. Fun energetic. Vertical 9:16.",
        "15 Closing Cta": f"A cute cartoon dumpling character with a crown holding a sale sign. Call to action. Buy now promotion. Bright colors. Vertical 9:16."
    }
    
    return prompts.get(category, f"A cute cartoon dumpling character with a crown presenting sewing machine products. Product showcase video. Clean bright background. Vertical 9:16 format.")


def download_video(url, output_path):
    """Download video from URL."""
    resp = requests.get(url, stream=True, timeout=120)
    if resp.status_code == 200:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False


def combine_audio_video(video_path, audio_path, output_path, title="", price=""):
    """Combine video + audio using ffmpeg, add text overlay."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        "-vf", f"scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="🎬 Wan2.2 Video Pipeline")
    parser.add_argument("--key", help="SiliconFlow API key")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audio-only", action="store_true", help="Only generate audio")
    parser.add_argument("--video-only", action="store_true", help="Only generate videos")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=90)
    parser.add_argument("--mode", choices=["t2v", "i2v"], default="i2v",
                        help="Text-to-Video or Image-to-Video (default: i2v)")
    
    args = parser.parse_args()
    
    # Load scripts
    scripts = json.loads(SCRIPTS_JSON.read_text())
    checkpoint = load_checkpoint() if args.resume else {"completed": [], "failed": [], "audio_done": []}
    
    print("=" * 60)
    print("🎬 WAN2.2 + EDGE TTS VIDEO PIPELINE")
    print(f"   Scripts: {len(scripts)}")
    print(f"   Avatar: {AVATAR_IMAGE}")
    print(f"   Mode: {'Image→Video' if args.mode == 'i2v' else 'Text→Video'}")
    print(f"   Range: {args.start}–{args.end}")
    print("=" * 60)
    
    # ── STEP 1: Audio ──
    if not args.video_only:
        batch_generate_audio(scripts, checkpoint)
    
    if args.audio_only:
        print("\n✅ Audio-only mode complete!")
        return
    
    # ── STEP 2: Video ──
    if args.dry_run:
        print("\n🔍 DRY RUN — Video generation preview:")
        for s in scripts:
            if args.start <= s["id"] <= args.end:
                prompt = build_video_prompt(s)
                print(f"  [{s['id']:03d}] {s['title'][:40]}")
                print(f"       Prompt: {prompt[:80]}...")
        print(f"\n✅ Dry run complete. Use --key to generate.")
        return
    
    api_key = args.key or os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        print("\n❌ Need SiliconFlow API key!")
        print("   1. Sign up: https://cloud.siliconflow.cn")
        print("   2. Get free credits")
        print("   3. Run: python3 wan_pipeline.py --key YOUR_KEY")
        return
    
    api = SiliconFlowAPI(api_key)
    
    # Upload avatar for I2V
    avatar_url = None
    if args.mode == "i2v":
        print("\n📎 Uploading avatar...")
        avatar_url = api.upload_image(AVATAR_IMAGE)
        if avatar_url:
            print(f"  ✅ Avatar URL: {avatar_url[:60]}...")
        else:
            print("  ⚠️ Upload failed, falling back to T2V mode")
            args.mode = "t2v"
    
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load manifest
    manifest = []
    if MANIFEST_FILE.exists():
        manifest = json.loads(MANIFEST_FILE.read_text())
    
    success = 0
    fail = 0
    skip = 0
    
    print(f"\n🎬 Generating videos via Wan2.2 ({args.mode.upper()})...")
    
    for script in scripts:
        vid = script["id"]
        
        if vid < args.start or vid > args.end:
            continue
        
        if vid in checkpoint.get("completed", []):
            skip += 1
            continue
        
        video_file = VIDEO_DIR / f"V{vid:03d}-raw.mp4"
        final_file = OUTPUT_DIR / f"V{vid:03d}.mp4"
        audio_file = AUDIO_DIR / f"V{vid:03d}.mp3"
        
        print(f"\n  🎬 [{vid:03d}/90] {script['title'][:50]}")
        
        prompt = build_video_prompt(script)
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Submit video generation
                if args.mode == "i2v" and avatar_url:
                    request_id = api.submit_i2v(prompt, avatar_url)
                else:
                    request_id = api.submit_t2v(prompt)
                
                if not request_id:
                    raise Exception("No request ID returned")
                
                print(f"     ⏳ Job: {request_id[:20]}... (attempt {attempt})")
                
                # Poll for completion
                while True:
                    time.sleep(POLL_INTERVAL)
                    status, result = api.check_status(request_id)
                    
                    if status == "completed" and result:
                        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
                        if download_video(result, video_file):
                            print(f"     ✅ Video downloaded: {video_file.stat().st_size // 1024}KB")
                            
                            # Combine with audio if available
                            if audio_file.exists():
                                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                                if combine_audio_video(video_file, audio_file, final_file):
                                    print(f"     🎵 Audio combined → {final_file.name}")
                                else:
                                    # Just copy video if ffmpeg fails
                                    import shutil
                                    shutil.copy(video_file, final_file)
                                    print(f"     ⚠️ FFmpeg failed, video only")
                            else:
                                import shutil
                                shutil.copy(video_file, final_file)
                            
                            # Update checkpoint & manifest
                            checkpoint["completed"].append(vid)
                            save_checkpoint(checkpoint)
                            
                            manifest.append({
                                "id": vid,
                                "title": script["title"],
                                "category": script["category"],
                                "video_file": str(video_file),
                                "final_file": str(final_file),
                                "audio_file": str(audio_file),
                                "prompt": prompt,
                                "mode": args.mode,
                                "request_id": request_id,
                                "generated_at": datetime.now().isoformat()
                            })
                            MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
                            
                            success += 1
                            break
                        else:
                            raise Exception("Download failed")
                    
                    elif status == "error":
                        raise Exception(f"Generation failed: {result}")
                    
                    else:
                        elapsed = (time.time() % 100)
                        print(f"     ⏳ Processing...")
                
                break
                
            except Exception as e:
                print(f"     ⚠️ Attempt {attempt}/{MAX_RETRIES}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RATE_LIMIT_DELAY * attempt)
                else:
                    checkpoint["failed"].append({"id": vid, "error": str(e)})
                    save_checkpoint(checkpoint)
                    fail += 1
        
        time.sleep(RATE_LIMIT_DELAY)
    
    # Report
    print("\n" + "=" * 60)
    print(f"📊 PIPELINE COMPLETE")
    print(f"   🎤 Audio: {len(checkpoint.get('audio_done', []))}/90")
    print(f"   🎬 Video: {success} generated")
    print(f"   ⏭️  Skipped: {skip}")
    print(f"   ❌ Failed: {fail}")
    print(f"   📁 Output: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
