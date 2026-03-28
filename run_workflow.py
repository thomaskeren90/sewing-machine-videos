#!/usr/bin/env python3
"""
🚀 MASTER WORKFLOW — Run everything in one command
===================================================
This is your one-stop script to go from 0 to 90 videos.

Usage:
  python3 run_workflow.py --api heygen --key YOUR_KEY
  
Steps:
  1. Parse all 90 scripts
  2. Upload your avatar
  3. Batch generate videos (with checkpointing)
  4. Post to TikTok/YouTube (instructions)
"""

import os
import sys
import json
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def step_1_parse():
    """Parse markdown scripts into JSON."""
    print("\n📋 STEP 1: Parsing 90 scripts...")
    result = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "parse_scripts.py")],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ Parse failed: {result.stderr}")
        return False
    return True


def step_2_verify_avatar(avatar_path):
    """Verify avatar image exists."""
    print("\n👤 STEP 2: Checking avatar...")
    if os.path.exists(avatar_path):
        size = os.path.getsize(avatar_path)
        print(f"  ✅ Avatar found: {avatar_path} ({size // 1024}KB)")
        return True
    else:
        print(f"  ❌ Avatar not found: {avatar_path}")
        print(f"  💡 Copy your avatar image to: {avatar_path}")
        return False


def step_3_dry_run():
    """Preview what will be generated."""
    print("\n🔍 STEP 3: Dry run preview...")
    result = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "generate_videos.py"), "--dry-run"],
        capture_output=True, text=True
    )
    print(result.stdout)
    return True


def step_4_generate(api, key, resume=False):
    """Run batch video generation."""
    print(f"\n🎬 STEP 4: Generating 90 videos via {api.upper()}...")
    
    cmd = [
        sys.executable, 
        os.path.join(BASE_DIR, "generate_videos.py"),
        "--api", api,
        "--key", key
    ]
    if resume:
        cmd.append("--resume")
    
    result = subprocess.run(cmd)
    return result.returncode == 0


def step_5_report():
    """Generate final report."""
    print("\n📊 STEP 5: Generating report...")
    
    manifest_path = os.path.join(BASE_DIR, "manifest.json")
    checkpoint_path = os.path.join(BASE_DIR, "checkpoint.json")
    
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f"  ✅ {len(manifest)} videos generated")
    
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        print(f"  ✅ {len(checkpoint.get('completed', []))} completed")
        if checkpoint.get('failed'):
            print(f"  ⚠️  {len(checkpoint['failed'])} failed (use --resume to retry)")
    
    output_dir = os.path.join(BASE_DIR, "output")
    if os.path.exists(output_dir):
        files = [f for f in os.listdir(output_dir) if f.endswith(".mp4")]
        total_size = sum(
            os.path.getsize(os.path.join(output_dir, f)) 
            for f in files
        )
        print(f"  📁 {len(files)} MP4 files in output/")
        print(f"  💾 Total size: {total_size / (1024*1024):.1f} MB")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="🚀 Master Video Workflow")
    parser.add_argument("--api", choices=["heygen", "did"], default="heygen")
    parser.add_argument("--key", help="API key")
    parser.add_argument("--resume", action="store_true", help="Resume generation")
    parser.add_argument("--avatar", default=None, help="Avatar image path")
    parser.add_argument("--dry-run-only", action="store_true", help="Only preview")
    
    args = parser.parse_args()
    
    avatar_path = args.avatar or os.path.join(BASE_DIR, "avatars", "main-avatar.jpeg")
    
    print("=" * 60)
    print("🧵 SEWING MACHINE VIDEO FACTORY — 90 Videos")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Step 1
    if not step_1_parse():
        sys.exit(1)
    
    # Step 2
    if not step_2_verify_avatar(avatar_path):
        sys.exit(1)
    
    # Step 3
    step_3_dry_run()
    
    if args.dry_run_only:
        print("\n✅ Dry run complete. Run without --dry-run-only to generate.")
        return
    
    # Step 4
    api_key = args.key
    if not api_key:
        env_var = "HEYGEN_API_KEY" if args.api == "heygen" else "DID_API_KEY"
        api_key = os.environ.get(env_var)
    
    if not api_key:
        print(f"\n❌ No API key! Pass --key or set {env_var}")
        print(f"\n📖 Get your key:")
        if args.api == "heygen":
            print("   → https://app.heygen.com/settings/api")
        else:
            print("   → https://studio.d-id.com/account-settings")
        sys.exit(1)
    
    step_4_generate(args.api, api_key, args.resume)
    
    # Step 5
    step_5_report()
    
    print("\n" + "=" * 60)
    print("🎉 WORKFLOW COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
