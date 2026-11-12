# Blender Timelapse Recorder

Version 1.1.0. Includes an FFmpeg path override and a **Test FFmpeg** button.

A Blender add-on that captures the **full primary desktop display** at a configurable
interval and converts the resulting PNG sequence into an MP4 with FFmpeg.

## Install
1. In Blender, open **Edit → Preferences → Add-ons** (or **Get Extensions**, depending on version).
2. Choose **Install from Disk** and select `blender_timelapse_recorder.py`.
3. Enable **Blender Timelapse Recorder**.
4. In the 3D View, press `N` to open the sidebar, then choose the **Timelapse** tab.

## Use
1. Choose an output folder.
2. Set the capture interval (default: 5 seconds) and output video FPS (default: 30).
3. Click **Start Recording**.
4. Work in Blender. Click **Stop & Build Video** when finished.
5. The add-on creates a timestamped session folder containing PNG frames and `timelapse.mp4`.

## Requirements and platform notes
- **macOS:** `screencapture` is used. Grant **Screen & System Audio Recording / Screen Recording**
  permission to the Blender application in System Settings → Privacy & Security, then restart Blender.
  Capture is of the primary display, not just the Blender window.
- **Linux:** uses `grim` on Wayland, otherwise ImageMagick `import`, or `gnome-screenshot`.
- **Windows:** uses PowerShell and .NET screen capture APIs.
- **FFmpeg:** install FFmpeg. If Blender cannot find it (common when Blender is launched from Finder on macOS), set **FFmpeg Executable** in the panel to the full executable path, such as `/opt/homebrew/bin/ffmpeg` (Apple Silicon Homebrew) or `/usr/local/bin/ffmpeg` (Intel Homebrew). Click **Test FFmpeg** before recording. If encoding fails, the PNG frames remain intact and the add-on displays FFmpeg's error output.

## Notes
- This records the full primary desktop display, including other windows that appear over Blender.
- The first capture occurs shortly after Start is pressed.
- The output MP4 uses H.264 (`libx264`) and `yuv420p` for broad playback compatibility.
- The add-on does not record audio.

# For questions
* Feel free to reach out https://markerstudio.org/*
* Marker Studio by Balint Korka