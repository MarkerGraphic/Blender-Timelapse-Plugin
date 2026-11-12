# 888b     d888                  888                             .d8888b.  888                  888 d8b         
# 8888b   d8888                  888                            d88P  Y88b 888                  888 Y8P         
# 88888b.d88888                  888                            Y88b.      888                  888             
# 888Y88888P888  8888b.  888d888 888  888  .d88b.  888d888       "Y888b.   888888 888  888  .d88888 888  .d88b. 
# 888 Y888P 888     "88b 888P"   888 .88P d8P  Y8b 888P"            "Y88b. 888    888  888 d88" 888 888 d88""88b
# 888  Y8P  888 .d888888 888     888888K  88888888 888                "888 888    888  888 888  888 888 888  888
# 888   "   888 888  888 888     888 "88b Y8b.     888          Y88b  d88P Y88b.  Y88b 888 Y88b 888 888 Y88..88P
# 888       888 "Y888888 888     888  888  "Y88888 888           "Y8888P"   "Y888  "Y88888  "Y88888 888  "Y88P" 

# by Balint Korka, markerstudio.org

bl_info = {
    "name": "Blender Timelapse Recorder",
    "author": '<a href="{https://markerstudio.org/}">markerstudio.org by Balint Korka</a>',
    "version": (1, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Timelapse",
    "description": "Capture the full desktop while working in Blender and encode the frames with FFmpeg",
    "category": "System",
}

import bpy
import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from bpy.props import StringProperty, FloatProperty, IntProperty, BoolProperty


_TIMER_RUNNING = False
_RECORDING = False
_FRAME_COUNT = 0
_NEXT_CAPTURE = 0.0
_SESSION_DIR = ""
_LAST_ERROR = ""
_TIMER_INTERVAL = 0.25


def _capture_command(output_file):
    """Return a full-screen capture command for the current OS."""
    if sys.platform == "darwin":
        # macOS may require Screen Recording permission for Blender.app.
        return ["screencapture", "-x", output_file]
    if sys.platform.startswith("linux"):
        # Prefer grim on Wayland, then ImageMagick import, then gnome-screenshot.
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("grim"):
            return ["grim", output_file]
        if shutil.which("import"):
            return ["import", "-window", "root", output_file]
        if shutil.which("gnome-screenshot"):
            return ["gnome-screenshot", "-f", output_file]
        raise RuntimeError(
            "No supported screenshot utility found. Install grim (Wayland), "
            "ImageMagick (import), or gnome-screenshot."
        )
    if sys.platform == "win32":
        # PowerShell + .NET captures the virtual desktop into a PNG.
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height); "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
            f"$bmp.Save('{output_file.replace(chr(39), chr(39)+chr(39))}',"
            "[System.Drawing.Imaging.ImageFormat]::Png); "
            "$g.Dispose(); $bmp.Dispose();"
        )
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]
    raise RuntimeError("Unsupported operating system for desktop capture.")


def _capture_frame(scene):
    global _FRAME_COUNT, _LAST_ERROR
    filename = os.path.join(_SESSION_DIR, "frame_{:05d}.png".format(_FRAME_COUNT))
    try:
        cmd = _capture_command(filename)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if result.returncode != 0 or not os.path.exists(filename):
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(detail or "Screenshot command did not create an image.")
        _FRAME_COUNT += 1
        _LAST_ERROR = ""
        scene.tl_frame_count = _FRAME_COUNT
        return True
    except Exception as exc:
        _LAST_ERROR = str(exc)
        scene.tl_last_error = _LAST_ERROR
        return False


def _find_ffmpeg(scene):
    """Find FFmpeg using the user-supplied path, PATH, and common install locations."""
    configured = bpy.path.abspath(scene.tl_ffmpeg_path).strip()
    if configured:
        # Accept either the executable itself or a directory containing it.
        if os.path.isdir(configured):
            candidate = os.path.join(configured, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        else:
            candidate = configured
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
        raise RuntimeError("Configured FFmpeg path is not executable: " + candidate)

    found = shutil.which("ffmpeg")
    if found:
        return found

    candidates = []
    if sys.platform == "darwin":
        candidates = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/local/bin/ffmpeg"]
    elif sys.platform.startswith("linux"):
        candidates = ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/snap/bin/ffmpeg"]
    elif sys.platform == "win32":
        candidates = [
            r"C:\\ffmpeg\\bin\\ffmpeg.exe",
            os.path.join(os.environ.get("ProgramFiles", r"C:\\Program Files"), "FFmpeg", "bin", "ffmpeg.exe"),
        ]

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    raise RuntimeError(
        "FFmpeg executable not found. Install FFmpeg, restart Blender, or set the "
        "'FFmpeg Executable' field to the full path (for example /opt/homebrew/bin/ffmpeg)."
    )


def _encode_video(scene):
    try:
        ffmpeg = _find_ffmpeg(scene)
    except Exception as exc:
        scene.tl_last_error = str(exc)
        return False

    fps = max(1, int(scene.tl_video_fps))
    input_pattern = os.path.join(_SESSION_DIR, "frame_%05d.png")
    output_file = os.path.join(_SESSION_DIR, "timelapse.mp4")

    # Be explicit about the image sequence's first index. Captures start at 00000.
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps), "-start_number", "0",
        "-i", input_pattern,
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", output_file,
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=3600
        )
        if result.returncode != 0:
            scene.tl_last_error = (
                "FFmpeg failed (exit {}). Command: {}\\n{}".format(
                    result.returncode, " ".join(cmd), result.stderr[-3000:]
                )
            )
            return False
        if not os.path.isfile(output_file) or os.path.getsize(output_file) == 0:
            scene.tl_last_error = "FFmpeg exited successfully but did not create a non-empty MP4."
            return False
        scene.tl_last_video = output_file
        scene.tl_last_error = ""
        return True
    except subprocess.TimeoutExpired:
        scene.tl_last_error = "FFmpeg encoding timed out after 1 hour. PNG frames were kept."
        return False
    except Exception as exc:
        scene.tl_last_error = "Could not run FFmpeg: " + str(exc)
        return False

def _record_timer():
    global _NEXT_CAPTURE

    if not _TIMER_RUNNING or not _RECORDING:
        return None  # Stop this Blender timer.

    scene = bpy.context.scene
    if scene is not None and time.monotonic() >= _NEXT_CAPTURE:
        _capture_frame(scene)
        _NEXT_CAPTURE = time.monotonic() + max(0.5, scene.tl_interval)

    return _TIMER_INTERVAL  # Check again in 0.25 seconds.        


class TL_OT_test_ffmpeg(bpy.types.Operator):
    bl_idname = "timelapse.test_ffmpeg"
    bl_label = "Test FFmpeg"
    bl_description = "Check that Blender can launch the configured FFmpeg executable"

    def execute(self, context):
        scene = context.scene
        try:
            ffmpeg = _find_ffmpeg(scene)
            result = subprocess.run(
                [ffmpeg, "-version"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, universal_newlines=True, timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "ffmpeg -version failed")
            first_line = (result.stdout or "").splitlines()
            version = first_line[0] if first_line else "FFmpeg found"
            scene.tl_last_error = ""
            self.report({"INFO"}, version[:200])
            return {"FINISHED"}
        except Exception as exc:
            scene.tl_last_error = str(exc)
            self.report({"ERROR"}, scene.tl_last_error[:200])
            return {"CANCELLED"}


class TL_OT_start(bpy.types.Operator):
    bl_idname = "timelapse.start"
    bl_label = "Start Recording"
    bl_description = "Capture the full desktop at the selected interval"

    def execute(self, context):
        global _TIMER_RUNNING, _RECORDING, _FRAME_COUNT, _NEXT_CAPTURE, _SESSION_DIR

        scene = context.scene
        if _RECORDING:
            self.report({"WARNING"}, "Timelapse recording is already running.")
            return {"CANCELLED"}

        base = bpy.path.abspath(scene.tl_output_dir).strip()
        if not base:
            self.report({"ERROR"}, "Choose an output folder.")
            return {"CANCELLED"}

        try:
            os.makedirs(base, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            _SESSION_DIR = os.path.join(base, "timelapse_" + stamp)
            os.makedirs(_SESSION_DIR, exist_ok=False)
        except Exception as exc:
            self.report({"ERROR"}, "Cannot create output folder: " + str(exc))
            return {"CANCELLED"}

        _FRAME_COUNT = 0
        scene.tl_frame_count = 0
        scene.tl_last_error = ""
        scene.tl_last_video = ""
        _RECORDING = True
        _TIMER_RUNNING = True
        _NEXT_CAPTURE = time.monotonic()

        if not bpy.app.timers.is_registered(_record_timer):
            bpy.app.timers.register(_record_timer, first_interval=0.1, persistent=True)

        self.report({"INFO"}, "Timelapse recording started.")
        return {"FINISHED"}


class TL_OT_stop(bpy.types.Operator):
    bl_idname = "timelapse.stop"
    bl_label = "Stop & Build Video"
    bl_description = "Stop capture and encode the PNG sequence into an MP4"

    def execute(self, context):
        global _RECORDING, _TIMER_RUNNING
        scene = context.scene
        if not _RECORDING:
            self.report({"WARNING"}, "No recording is running.")
            return {"CANCELLED"}

        _RECORDING = False
        _TIMER_RUNNING = False

        if _FRAME_COUNT < 1:
            scene.tl_last_error = "No frames were captured. Check desktop capture permissions."
            self.report({"ERROR"}, scene.tl_last_error)
            return {"CANCELLED"}

        ok = _encode_video(scene)
        if ok:
            self.report({"INFO"}, "Video created: " + scene.tl_last_video)
        else:
            self.report({"WARNING"}, scene.tl_last_error or "Video encoding failed; PNGs were kept.")
        return {"FINISHED"}


class TL_PT_panel(bpy.types.Panel):
    bl_label = "Timelapse Recorder"
    bl_idname = "TL_PT_timelapse_recorder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Timelapse"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "tl_output_dir")
        layout.prop(scene, "tl_interval")
        layout.prop(scene, "tl_video_fps")
        layout.prop(scene, "tl_ffmpeg_path")
        layout.operator("timelapse.test_ffmpeg", icon="CHECKMARK")

        row = layout.row(align=True)
        row.enabled = not _RECORDING
        row.operator("timelapse.start", icon="REC")

        row = layout.row()
        row.enabled = _RECORDING
        row.alert = True
        row.operator("timelapse.stop", icon="PAUSE")

        layout.separator()
        layout.label(text=("Recording…" if _RECORDING else "Not recording"),
                     icon=("REC" if _RECORDING else "RADIOBUT_OFF"))
        layout.label(text="Captured frames: {}".format(scene.tl_frame_count))

        if _SESSION_DIR:
            layout.label(text="Session: " + os.path.basename(_SESSION_DIR), icon="FILE_FOLDER")
        if scene.tl_last_video:
            layout.label(text="MP4: " + os.path.basename(scene.tl_last_video), icon="FILE_MOVIE")
        if scene.tl_last_error:
            box = layout.box()
            box.alert = True
            box.label(text="Last issue:", icon="ERROR")
            for line in scene.tl_last_error.splitlines()[-4:]:
                box.label(text=line[:90])


_CLASSES = (TL_OT_start, TL_OT_stop, TL_OT_test_ffmpeg, TL_PT_panel)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.tl_output_dir = StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        default="//timelapses",
    )
    bpy.types.Scene.tl_interval = FloatProperty(
        name="Capture Every (seconds)",
        default=5.0,
        min=0.5,
        max=3600.0,
        precision=1,
    )
    bpy.types.Scene.tl_ffmpeg_path = StringProperty(
        name="FFmpeg Executable",
        description="Optional full path to ffmpeg; leave blank for automatic detection",
        subtype="FILE_PATH",
        default="",
    )
    bpy.types.Scene.tl_video_fps = IntProperty(
        name="Video FPS",
        default=30,
        min=1,
        max=120,
    )
    bpy.types.Scene.tl_frame_count = IntProperty(name="Captured Frames", default=0)
    bpy.types.Scene.tl_last_error = StringProperty(name="Last Error", default="")
    bpy.types.Scene.tl_last_video = StringProperty(name="Last Video", default="")


def unregister():
    global _RECORDING, _TIMER_RUNNING
    _RECORDING = False
    _TIMER_RUNNING = False
    if bpy.app.timers.is_registered(_record_timer):
        bpy.app.timers.unregister(_record_timer)

    for prop in (
        "tl_output_dir", "tl_interval", "tl_video_fps", "tl_ffmpeg_path",
        "tl_frame_count", "tl_last_error", "tl_last_video",
    ):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)

    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
