#!/usr/bin/env python3
"""
🎬 Replicate S2V Video Pipeline — 90 Sewing Machine Videos
===========================================================
Generates videos using:
  1. Edge TTS (free) → Indonesian voice MP3
  2. Replicate wan-video/wan-2.2-s2v → Sound-to-Video (audio + image → video)
  3. FFmpeg → Final MP4

Usage:
  REPLICATE_API_TOKEN=r8_xxx python3 replicate_pipeline.py
  REPLICATE_API_TOKEN=r8_xxx python3 replicate_pipeline.py --resume
  python3 replicate_pipeline.py --dry-run
"""

import os
import sys
import json
import time
import subprocess
import argparse
import requests
from datetime import datetime
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SCRIPTS_JSON = BASE_DIR / "scripts.json"
AVATAR_IMAGE = BASE_DIR / "avatars" / "main-avatar.jpeg"
AUDIO_DIR = BASE_DIR / "audio"
VIDEO_DIR = BASE_DIR / "videos"
OUTPUT_DIR = BASE_DIR / "output"
CHECKPOINT_FILE = BASE_DIR / "checkpoint.json"
MANIFEST_FILE = BASE_DIR / "manifest.json"

# Replicate
REPLICATE_MODEL = "wan-video/wan-2.2-s2v"
REPLICATE_API_URL = "https://api.replicate.com/v1"

# TTS
VOICE_ID = "id-ID-GadisNeural"
VOICE_RATE = "+0%"

# Video
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280

# Timing
POLL_INTERVAL = 20
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 10


# ─── CHECKPOINT ───────────────────────────────────────────────────────────
def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"completed": [], "failed": [], "audio_done": [], "last_run": None}


def save_checkpoint(cp):
    cp["last_run"] = datetime.now().isoformat()
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2, ensure_ascii=False))


# ─── STEP 1: EDGE TTS ────────────────────────────────────────────────────
def generate_audio(script_text, output_path):
    """Generate Indonesian voice MP3 using Edge TTS."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "edge-tts",
        "--voice", VOICE_ID,
        "--rate", VOICE_RATE,
        "--text", script_text,
        "--write-media", str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode == 0


def batch_generate_audio(scripts, checkpoint):
    """Generate audio for all 90 scripts."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for i, script in enumerate(scripts):
        vid = script["id"]
        audio_file = AUDIO_DIR / f"V{i+1:03d}.mp3"

        if audio_file.exists() and audio_file.stat().st_size > 100:
            print(f"  ⏭️  [{i+1:03d}/90] Audio exists: {audio_file.name}")
            if vid not in checkpoint.get("audio_done", []):
                checkpoint.setdefault("audio_done", []).append(vid)
                save_checkpoint(checkpoint)
            count += 1
            continue

        print(f"  🎤 [{i+1:03d}/90] Generating audio: {script['title'][:40]}...")

        if generate_audio(script["script"], audio_file):
            size = audio_file.stat().st_size
            print(f"     ✅ {audio_file.name} ({size // 1024}KB)")
            if vid not in checkpoint.get("audio_done", []):
                checkpoint.setdefault("audio_done", []).append(vid)
                save_checkpoint(checkpoint)
            count += 1
        else:
            print(f"     ❌ Audio failed!")

        time.sleep(1)

    return count


# ─── STEP 2: REPLICATE S2V ───────────────────────────────────────────────
def upload_file_to_replicate(file_path, api_token):
    """Upload a file to Replicate and get a URL."""
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://api.replicate.com/v1/files",
            headers={"Authorization": f"Bearer {api_token}"},
            files={"content": (os.path.basename(file_path), f)}
        )
    if resp.status_code in (200, 201):
        return resp.json().get("urls", {}).get("get")
    # Fallback: use file data URI or hosted URL
    print(f"     ⚠️ Upload failed ({resp.status_code}), trying data URI...")
    return None


def run_s2v_prediction(prompt, image_path, audio_path, api_token):
    """Run wan-2.2-s2v prediction on Replicate."""
    # First upload both files
    print(f"     📤 Uploading image...")
    image_url = upload_file_to_replicate(image_path, api_token)
    if not image_url:
        # Try direct file upload approach
        return None

    print(f"     📤 Uploading audio...")
    audio_url = upload_file_to_replicate(audio_path, api_token)
    if not audio_url:
        return None

    # Create prediction
    resp = requests.post(
        f"{REPLICATE_API_URL}/models/{REPLICATE_MODEL}/predictions",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Prefer": "wait"  # Try to wait for result
        },
        json={
            "input": {
                "prompt": prompt,
                "image": image_url,
                "audio": audio_url,
            }
        }
    )

    if resp.status_code in (200, 201):
        return resp.json()
    else:
        print(f"     ❌ Prediction failed: {resp.status_code} — {resp.text[:200]}")
        return None


def run_s2v_with_replicate_lib(prompt, image_path, audio_path, api_token):
    """Run S2V using replicate Python library."""
    import replicate

    os.environ["REPLICATE_API_TOKEN"] = api_token

    with open(image_path, "rb") as img_f, open(audio_path, "rb") as aud_f:
        output = replicate.run(
            f"{REPLICATE_MODEL}",
            input={
                "prompt": prompt,
                "image": img_f,
                "audio": aud_f,
                "num_frames_per_chunk": 81,
            }
        )

    return output


def download_video(url, output_path):
    """Download video from URL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=300)
    if resp.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False


def poll_prediction(pred_id, api_token, max_wait=600):
    """Poll a Replicate prediction until complete."""
    waited = 0
    while waited < max_wait:
        resp = requests.get(
            f"{REPLICATE_API_URL}/predictions/{pred_id}",
            headers={"Authorization": f"Bearer {api_token}"}
        )
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            if status == "succeeded":
                return data.get("output")
            elif status == "failed":
                print(f"     ❌ Prediction failed: {data.get('error', 'unknown')}")
                return None
            elif status == "canceled":
                return None
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
        print(f"     ⏳ Waiting... ({waited}s)")
    return None


# ─── STEP 3: FFMPEG COMBINE ──────────────────────────────────────────────
def combine_video_audio(video_path, audio_path, output_path):
    """Combine video with audio using ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


# ─── MAIN PIPELINE ───────────────────────────────────────────────────────
def generate_all(api_token, resume=False, dry_run=False, start_from=1, end_at=90,
                 audio_only=False, video_only=False):
    """Main batch generation pipeline."""

    scripts = json.loads(SCRIPTS_JSON.read_text(encoding="utf-8"))
    for d in [AUDIO_DIR, VIDEO_DIR, OUTPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint() if resume else {"completed": [], "failed": [], "audio_done": [], "last_run": None}

    # ─── STEP 1: AUDIO ──────────────────────────────────────────────────
    if not video_only:
        print("=" * 60)
        print("🎤 STEP 1: Generating Audio (Edge TTS)")
        print("=" * 60)
        audio_count = batch_generate_audio(scripts, checkpoint)
        print(f"\n✅ Audio ready: {audio_count}/{len(scripts)} files\n")

    if audio_only:
        print("✅ Audio-only mode complete.")
        return

    # ─── STEP 2: VIDEO ──────────────────────────────────────────────────
    print("=" * 60)
    print("🎬 STEP 2: Generating Videos (Replicate S2V)")
    print("=" * 60)

    # Check Replicate balance
    print(f"   Model: {REPLICATE_MODEL}")
    print(f"   Range: {start_from}–{end_at}")
    print(f"   Resume: {resume}")
    print(f"   Dry run: {dry_run}")
    print()

    success_count = 0
    fail_count = 0
    skip_count = 0
    manifest = []

    if MANIFEST_FILE.exists():
        manifest = json.loads(MANIFEST_FILE.read_text())

    for i, script in enumerate(scripts):
        vid_num = i + 1
        script_id = script["id"]

        if vid_num < start_from or vid_num > end_at:
            continue

        output_file = OUTPUT_DIR / f"V{vid_num:03d}.mp4"

        # Skip if already done
        if output_file.exists() and output_file.stat().st_size > 1000:
            skip_count += 1
            print(f"  ⏭️  [{vid_num:03d}/90] Already done: {script['title'][:40]}...")
            if script_id not in checkpoint["completed"]:
                checkpoint["completed"].append(script_id)
                save_checkpoint(checkpoint)
            continue

        audio_file = AUDIO_DIR / f"V{vid_num:03d}.mp4"
        if not audio_file.exists():
            audio_file = AUDIO_DIR / f"V{vid_num:03d}.mp3"

        if not audio_file.exists():
            print(f"  ⚠️  [{vid_num:03d}/90] No audio file, skipping")
            fail_count += 1
            continue

        # Build prompt for the video
        category = script.get("category", "")
        title = script.get("title", "")
        prompt = (
            f"Professional product video for sewing machines and spare parts. "
            f"A person presenting {title}. "
            f"Clean background, good lighting, Indonesian setting. "
            f"Lip-sync to Indonesian voiceover. "
            f"Vertical 9:16 format, TikTok/YouTube Shorts style."
        )

        print(f"\n  🎬 [{vid_num:03d}/90] {title[:50]}")
        print(f"     Category: {category}")
        print(f"     Audio: {audio_file.name}")

        if dry_run:
            print(f"     [DRY RUN] Would generate → {output_file}")
            continue

        # Generate video with retries
        video_generated = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"     🚀 Submitting to Replicate (attempt {attempt})...")

                output = run_s2v_with_replicate_lib(
                    prompt, AVATAR_IMAGE, audio_file, api_token
                )

                if output:
                    # output can be a URL string or list of URLs
                    if isinstance(output, list):
                        video_url = output[0] if output else None
                    else:
                        video_url = output

                    if video_url:
                        print(f"     📥 Downloading video...")
                        if download_video(video_url, output_file):
                            size = output_file.stat().st_size
                            print(f"     ✅ Saved: {output_file.name} ({size // 1024}KB)")

                            # Update manifest
                            manifest.append({
                                "id": vid_num,
                                "script_id": script_id,
                                "title": title,
                                "category": category,
                                "file": str(output_file),
                                "generated_at": datetime.now().isoformat(),
                            })
                            MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

                            if script_id not in checkpoint["completed"]:
                                checkpoint["completed"].append(script_id)
                                save_checkpoint(checkpoint)

                            success_count += 1
                            video_generated = True
                            break
                        else:
                            raise Exception("Download failed")
                    else:
                        raise Exception("No video URL in output")
                else:
                    raise Exception("No output from Replicate")

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

        # Rate limit delay
        time.sleep(RATE_LIMIT_DELAY)

    # ─── FINAL REPORT ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 BATCH COMPLETE")
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
        description="🎬 90 Sewing Machine Videos — Replicate S2V Pipeline"
    )
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--start", type=int, default=1, help="Start from video (1-90)")
    parser.add_argument("--end", type=int, default=90, help="End at video (1-90)")
    parser.add_argument("--audio-only", action="store_true", help="Only generate audio")
    parser.add_argument("--video-only", action="store_true", help="Only generate videos (skip audio)")

    args = parser.parse_args()

    api_token = os.environ.get("REPLICATE_API_TOKEN")
    if not api_token and not args.dry_run:
        print("❌ Set REPLICATE_API_TOKEN environment variable!")
        sys.exit(1)

    generate_all(
        api_token=api_token,
        resume=args.resume,
        dry_run=args.dry_run,
        start_from=args.start,
        end_at=args.end,
        audio_only=args.audio_only,
        video_only=args.video_only,
    )


if __name__ == "__main__":
    main()
