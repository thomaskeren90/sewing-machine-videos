#!/usr/bin/env python3
"""
🎬 Batch Video Generator — 90 Sewing Machine Videos
====================================================
Generates avatar videos from scripts.json using HeyGen or D-ID API.

Usage:
  python3 generate_videos.py --api heygen --key YOUR_KEY
  python3 generate_videos.py --api did --key YOUR_KEY
  python3 generate_videos.py --resume              # Resume from last checkpoint
  python3 generate_videos.py --dry-run              # Preview without API calls

Requirements:
  pip install requests
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_JSON = os.path.join(BASE_DIR, "scripts.json")
AVATAR_IMAGE = os.path.join(BASE_DIR, "avatars", "main-avatar.jpeg")  # Main avatar (TiMi jacket)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CHECKPOINT_FILE = os.path.join(BASE_DIR, "checkpoint.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "manifest.json")

# HeyGen API config
HEYGEN_BASE = "https://api.heygen.com/v2"

# D-ID API config
DID_BASE = "https://api.d-id.com"

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920  # Vertical 9:16 for TikTok/Shorts
POLL_INTERVAL = 15   # seconds between status checks
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 5  # seconds between API calls


# ─── CHECKPOINT SYSTEM ────────────────────────────────────────────────────
def load_checkpoint():
    """Load progress checkpoint."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {"completed": [], "failed": [], "last_run": None}


def save_checkpoint(checkpoint):
    """Save progress checkpoint."""
    checkpoint["last_run"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2)


# ─── HEYGEN API ───────────────────────────────────────────────────────────
class HeyGenAPI:
    """HeyGen video generation API client."""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def upload_avatar(self, image_path):
        """Upload avatar image and get avatar ID."""
        url = f"{HEYGEN_BASE}/avatar/photo"
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                headers={"X-Api-Key": self.api_key},
                files={"file": ("avatar.jpeg", f, "image/jpeg")}
            )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("avatar_id")
        else:
            print(f"  ⚠️ Avatar upload failed: {resp.status_code} — {resp.text}")
            return None
    
    def list_avatars(self):
        """List available avatars."""
        resp = requests.get(f"{HEYGEN_BASE}/avatars", headers=self.headers)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("avatars", [])
        return []
    
    def list_voices(self, language="id"):
        """List available Indonesian voices."""
        resp = requests.get(f"{HEYGEN_BASE}/voices", headers=self.headers)
        if resp.status_code == 200:
            voices = resp.json().get("data", {}).get("voices", [])
            return [v for v in voices if language in v.get("language", "").lower() 
                    or "indonesian" in v.get("name", "").lower()]
        return []
    
    def generate_video(self, script_text, title, avatar_id=None, voice_id=None):
        """Generate a video from script text."""
        url = f"{HEYGEN_BASE}/video/generate"
        
        # Build video input
        video_input = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id or "default",
                        "avatar_style": "normal"
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script_text,
                        "voice_id": voice_id or "id-ID-ArdiNeural",
                        "speed": 1.0
                    },
                    "background": {
                        "type": "color",
                        "value": "#FFFFFF"
                    }
                }
            ],
            "dimension": {
                "width": VIDEO_WIDTH,
                "height": VIDEO_HEIGHT
            },
            "aspect_ratio": "9:16",
            "test": False,
            "title": title
        }
        
        resp = requests.post(url, headers=self.headers, json=video_input)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("video_id")
        else:
            print(f"  ❌ Generation failed: {resp.status_code} — {resp.text}")
            return None
    
    def check_status(self, video_id):
        """Check video generation status."""
        resp = requests.get(
            f"{HEYGEN_BASE}/video_status/{video_id}",
            headers=self.headers
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return data.get("status"), data.get("video_url")
        return "error", None


# ─── D-ID API ─────────────────────────────────────────────────────────────
class DIDAPI:
    """D-ID video generation API client."""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def upload_image(self, image_path):
        """Upload image to D-ID."""
        url = f"{DID_BASE}/images"
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                headers={"Authorization": f"Basic {self.api_key}"},
                files={"image": ("avatar.jpeg", f, "image/jpeg")}
            )
        if resp.status_code in (200, 201):
            return resp.json().get("id")
        return None
    
    def generate_video(self, script_text, title, image_url=None, voice_id=None):
        """Generate talking avatar video."""
        url = f"{DID_BASE}/talks"
        
        payload = {
            "source_url": image_url,
            "script": {
                "type": "text",
                "input": script_text,
                "provider": {
                    "type": "microsoft",
                    "voice_id": voice_id or "id-ID-ArdiNeural"
                }
            },
            "config": {
                "result_format": "mp4",
                "fluent": True,
                "pad_audio": 0.0,
                "stitch": True
            }
        }
        
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code in (200, 201):
            return resp.json().get("id")
        else:
            print(f"  ❌ D-ID generation failed: {resp.status_code} — {resp.text}")
            return None
    
    def check_status(self, talk_id):
        """Check talk generation status."""
        resp = requests.get(
            f"{DID_BASE}/talks/{talk_id}",
            headers=self.headers
        )
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            if status == "done":
                return "completed", data.get("result_url")
            elif status == "error":
                return "error", None
            return "processing", None
        return "error", None


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────
def load_scripts():
    """Load all 90 scripts."""
    with open(SCRIPTS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def download_video(url, output_path):
    """Download video from URL."""
    resp = requests.get(url, stream=True)
    if resp.status_code == 200:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False


def generate_all(api_type, api_key, resume=False, dry_run=False, 
                 start_from=1, end_at=90, avatar_id=None, voice_id=None):
    """Main batch generation pipeline."""
    
    scripts = load_scripts()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Load checkpoint if resuming
    checkpoint = load_checkpoint() if resume else {"completed": [], "failed": []}
    
    # Init API client
    if api_type == "heygen":
        api = HeyGenAPI(api_key)
        if not avatar_id:
            print("📎 Uploading avatar image...")
            avatar_id = api.upload_avatar(AVATAR_IMAGE)
            if avatar_id:
                print(f"  ✅ Avatar uploaded: {avatar_id}")
            else:
                print("  ⚠️ Using default avatar")
        
        # List Indonesian voices
        voices = api.list_voices("id")
        if voices:
            print(f"  🎤 Found {len(voices)} Indonesian voices")
            if not voice_id:
                voice_id = voices[0].get("voice_id")
                print(f"  Using: {voices[0].get('name', voice_id)}")
    else:
        api = DIDAPI(api_key)
        avatar_id = None  # D-ID uses URL
    
    # Build manifest
    manifest = []
    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE, "r") as f:
            manifest = json.load(f)
    
    total = len(scripts)
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    print(f"\n🎬 Starting batch generation: {total} videos")
    print(f"   API: {api_type.upper()}")
    print(f"   Range: {start_from}–{end_at}")
    print(f"   Resume: {resume}")
    print(f"   Dry run: {dry_run}")
    print("=" * 60)
    
    for script in scripts:
        vid_num = script["id"]
        
        # Skip if outside range
        if vid_num < start_from or vid_num > end_at:
            continue
        
        # Skip if already completed
        if str(vid_num) in [str(c) for c in checkpoint["completed"]]:
            skip_count += 1
            print(f"  ⏭️  [{vid_num:03d}/90] Already done: {script['title'][:40]}...")
            continue
        
        # Generate filename
        safe_title = script["title"][:30].replace(" ", "-").replace("/", "-")
        output_file = os.path.join(OUTPUT_DIR, f"V{vid_num:03d}-{safe_title}.mp4")
        
        print(f"\n  🎬 [{vid_num:03d}/90] {script['title'][:50]}")
        print(f"     Category: {script['category']}")
        print(f"     Script: {script['script'][:80]}...")
        
        if dry_run:
            print(f"     [DRY RUN] Would generate → {output_file}")
            continue
        
        # API call with retries
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if api_type == "heygen":
                    video_ref = api.generate_video(
                        script["script"], 
                        script["title"],
                        avatar_id=avatar_id,
                        voice_id=voice_id
                    )
                else:
                    video_ref = api.generate_video(
                        script["script"],
                        script["title"]
                    )
                
                if not video_ref:
                    raise Exception("No video reference returned")
                
                print(f"     ⏳ Job submitted: {video_ref} (attempt {attempt})")
                
                # Poll for completion
                while True:
                    time.sleep(POLL_INTERVAL)
                    status, video_url = api.check_status(video_ref)
                    
                    if status == "completed" and video_url:
                        if download_video(video_url, output_file):
                            file_size = os.path.getsize(output_file)
                            print(f"     ✅ Downloaded: {output_file} ({file_size // 1024}KB)")
                            
                            # Update manifest
                            manifest.append({
                                "id": vid_num,
                                "title": script["title"],
                                "category": script["category"],
                                "file": output_file,
                                "script": script["script"],
                                "product": script["product"],
                                "platform": script["platform"],
                                "generated_at": datetime.now().isoformat(),
                                "api": api_type,
                                "job_id": video_ref
                            })
                            
                            # Save manifest
                            with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
                                json.dump(manifest, f, ensure_ascii=False, indent=2)
                            
                            # Update checkpoint
                            checkpoint["completed"].append(vid_num)
                            save_checkpoint(checkpoint)
                            success_count += 1
                            break
                        else:
                            raise Exception("Download failed")
                    
                    elif status == "error":
                        raise Exception("Generation failed on server")
                    
                    else:
                        print(f"     ⏳ Status: {status}...")
                
                break  # Success, exit retry loop
                
            except Exception as e:
                print(f"     ⚠️ Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RATE_LIMIT_DELAY * attempt)
                else:
                    print(f"     ❌ FAILED after {MAX_RETRIES} attempts")
                    checkpoint["failed"].append({
                        "id": vid_num,
                        "error": str(e),
                        "time": datetime.now().isoformat()
                    })
                    save_checkpoint(checkpoint)
                    fail_count += 1
        
        # Rate limit delay between videos
        time.sleep(RATE_LIMIT_DELAY)
    
    # Final report
    print("\n" + "=" * 60)
    print(f"📊 BATCH COMPLETE")
    print(f"   ✅ Success: {success_count}")
    print(f"   ⏭️  Skipped: {skip_count}")
    print(f"   ❌ Failed:  {fail_count}")
    print(f"   📁 Output:  {OUTPUT_DIR}")
    print(f"   📋 Manifest: {MANIFEST_FILE}")
    
    if checkpoint["failed"]:
        print(f"\n⚠️ Failed videos (retry with --resume):")
        for f in checkpoint["failed"]:
            print(f"   Video {f['id']}: {f['error']}")


# ─── CLI ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🎬 Batch Video Generator — 90 Sewing Machine Videos"
    )
    parser.add_argument("--api", choices=["heygen", "did"], default="heygen",
                        help="API provider (default: heygen)")
    parser.add_argument("--key", required=False,
                        help="API key (or set HEYGEN_API_KEY / DID_API_KEY env var)")
    parser.add_argument("--avatar-id", default=None,
                        help="HeyGen avatar ID (skip upload)")
    parser.add_argument("--voice-id", default=None,
                        help="Voice ID for TTS")
    parser.add_argument("--avatar-image", default=AVATAR_IMAGE,
                        help="Path to avatar image")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without making API calls")
    parser.add_argument("--start", type=int, default=1,
                        help="Start from video number (1-90)")
    parser.add_argument("--end", type=int, default=90,
                        help="End at video number (1-90)")
    parser.add_argument("--scripts", default=SCRIPTS_JSON,
                        help="Path to scripts.json")
    
    args = parser.parse_args()
    
    # Resolve API key
    api_key = args.key
    if not api_key:
        if args.api == "heygen":
            api_key = os.environ.get("HEYGEN_API_KEY")
        else:
            api_key = os.environ.get("DID_API_KEY")
    
    if not api_key and not args.dry_run:
        print("❌ API key required! Use --key or set HEYGEN_API_KEY / DID_API_KEY")
        sys.exit(1)
    
    # Update globals if custom paths
    global SCRIPTS_JSON, AVATAR_IMAGE
    SCRIPTS_JSON = args.scripts
    AVATAR_IMAGE = args.avatar_image
    
    generate_all(
        api_type=args.api,
        api_key=api_key,
        resume=args.resume,
        dry_run=args.dry_run,
        start_from=args.start,
        end_at=args.end,
        avatar_id=args.avatar_id,
        voice_id=args.voice_id
    )


if __name__ == "__main__":
    main()
