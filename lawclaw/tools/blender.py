"""Blender 3D control tool.

Runs Blender in background mode via its Python API.
Blender must be installed and accessible on PATH.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool

# Default workspace for Blender files
_BLENDER_WORKSPACE = Path.home() / ".lawclaw" / "blender"

# Blender binary — allow override via env
_BLENDER_BIN = os.environ.get("BLENDER_BIN", shutil.which("blender") or "blender")


class BlenderTool(Tool):
    name = "blender"
    description = (
        "Control Blender 3D in background mode. "
        "Actions: run_script, render, create_object, delete_object, "
        "list_objects, set_material, set_transform, import_file, "
        "export_file, open_file, save_file, scene_info."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "run_script", "render", "create_object", "delete_object",
                    "list_objects", "set_material", "set_transform",
                    "import_file", "export_file", "open_file", "save_file",
                    "scene_info",
                ],
                "description": "Blender action to perform.",
            },
            "script": {
                "type": "string",
                "description": "Python script to execute in Blender (for 'run_script'). Has access to 'bpy' module.",
            },
            "blend_file": {
                "type": "string",
                "description": "Path to .blend file (for 'open_file', 'save_file', or as context for other actions).",
            },
            "object_type": {
                "type": "string",
                "enum": [
                    "cube", "sphere", "cylinder", "cone", "torus", "plane",
                    "circle", "monkey", "empty", "camera", "light", "text",
                ],
                "description": "Type of object to create (for 'create_object').",
            },
            "object_name": {
                "type": "string",
                "description": "Name of the object to target (for 'delete_object', 'set_material', 'set_transform').",
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "description": "XYZ location [x, y, z] (for 'create_object', 'set_transform').",
            },
            "rotation": {
                "type": "array",
                "items": {"type": "number"},
                "description": "XYZ rotation in degrees [x, y, z] (for 'set_transform').",
            },
            "scale": {
                "type": "array",
                "items": {"type": "number"},
                "description": "XYZ scale [x, y, z] (for 'set_transform').",
            },
            "color": {
                "type": "array",
                "items": {"type": "number"},
                "description": "RGBA color [r, g, b, a] values 0-1 (for 'set_material').",
            },
            "material_name": {
                "type": "string",
                "description": "Material name (for 'set_material').",
            },
            "output_path": {
                "type": "string",
                "description": "Output file path (for 'render', 'export_file', 'save_file').",
            },
            "file_path": {
                "type": "string",
                "description": "File path to import (for 'import_file').",
            },
            "format": {
                "type": "string",
                "enum": ["PNG", "JPEG", "BMP", "TIFF", "OPEN_EXR", "FBX", "GLTF", "OBJ", "STL"],
                "description": "File format (for 'render': image format; for 'export_file': export format).",
            },
            "resolution": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Resolution [width, height] in pixels (for 'render'). Default [1920, 1080].",
            },
            "engine": {
                "type": "string",
                "enum": ["EEVEE", "CYCLES", "WORKBENCH"],
                "description": "Render engine (for 'render'). Default EEVEE.",
            },
            "samples": {
                "type": "integer",
                "description": "Render samples (for 'render'). Higher = better quality, slower.",
            },
            "text_body": {
                "type": "string",
                "description": "Text content (for 'create_object' with object_type='text').",
            },
            "name": {
                "type": "string",
                "description": "Name for the created object (for 'create_object').",
            },
        },
        "required": ["action"],
    }

    def __init__(self, workspace: str | Path | None = None) -> None:
        self._workspace = Path(workspace) if workspace else _BLENDER_WORKSPACE
        self._workspace.mkdir(parents=True, exist_ok=True)

    async def execute(  # type: ignore[override]
        self,
        action: str,
        script: str = "",
        blend_file: str = "",
        object_type: str = "",
        object_name: str = "",
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        scale: list[float] | None = None,
        color: list[float] | None = None,
        material_name: str = "",
        output_path: str = "",
        file_path: str = "",
        format: str = "",
        resolution: list[int] | None = None,
        engine: str = "",
        samples: int = 0,
        text_body: str = "",
        name: str = "",
    ) -> str:
        try:
            return await self._dispatch(
                action=action, script=script, blend_file=blend_file,
                object_type=object_type, object_name=object_name,
                location=location, rotation=rotation, scale=scale,
                color=color, material_name=material_name,
                output_path=output_path, file_path=file_path,
                fmt=format, resolution=resolution, engine=engine,
                samples=samples, text_body=text_body, name=name,
            )
        except FileNotFoundError:
            return (
                "Error: Blender not found. Make sure Blender is installed and on PATH. "
                f"Tried: {_BLENDER_BIN}"
            )
        except Exception as exc:
            logger.exception("Blender tool error")
            return f"Error executing blender '{action}': {exc}"

    async def _dispatch(  # noqa: C901
        self,
        *,
        action: str,
        script: str,
        blend_file: str,
        object_type: str,
        object_name: str,
        location: list[float] | None,
        rotation: list[float] | None,
        scale: list[float] | None,
        color: list[float] | None,
        material_name: str,
        output_path: str,
        file_path: str,
        fmt: str,
        resolution: list[int] | None,
        engine: str,
        samples: int,
        text_body: str,
        name: str,
    ) -> str:
        # -- run arbitrary Python script --
        if action == "run_script":
            if not script:
                return "[ERROR] 'script' is required for 'run_script'."
            return await self._run_blender_script(script, blend_file)

        # -- scene info --
        if action == "scene_info":
            return await self._run_blender_script(
                _SCENE_INFO_SCRIPT, blend_file,
            )

        # -- list objects --
        if action == "list_objects":
            return await self._run_blender_script(
                _LIST_OBJECTS_SCRIPT, blend_file,
            )

        # -- create object --
        if action == "create_object":
            if not object_type:
                return "[ERROR] 'object_type' is required for 'create_object'."
            loc = location or [0, 0, 0]
            py = _build_create_script(object_type, loc, name, text_body)
            return await self._run_blender_script(py, blend_file)

        # -- delete object --
        if action == "delete_object":
            if not object_name:
                return "[ERROR] 'object_name' is required for 'delete_object'."
            py = _build_delete_script(object_name)
            return await self._run_blender_script(py, blend_file)

        # -- set material --
        if action == "set_material":
            if not object_name:
                return "[ERROR] 'object_name' is required for 'set_material'."
            rgba = color or [0.8, 0.8, 0.8, 1.0]
            mat_name = material_name or f"Mat_{object_name}"
            py = _build_material_script(object_name, mat_name, rgba)
            return await self._run_blender_script(py, blend_file)

        # -- set transform --
        if action == "set_transform":
            if not object_name:
                return "[ERROR] 'object_name' is required for 'set_transform'."
            py = _build_transform_script(object_name, location, rotation, scale)
            return await self._run_blender_script(py, blend_file)

        # -- render --
        if action == "render":
            out = output_path or str(self._workspace / "render.png")
            res = resolution or [1920, 1080]
            eng = engine or "EEVEE"
            img_fmt = fmt or "PNG"
            py = _build_render_script(out, res, eng, img_fmt, samples)
            result = await self._run_blender_script(py, blend_file)
            if "Error" not in result:
                return f"Rendered to: {out}\n{result}"
            return result

        # -- import file --
        if action == "import_file":
            if not file_path:
                return "[ERROR] 'file_path' is required for 'import_file'."
            py = _build_import_script(file_path)
            return await self._run_blender_script(py, blend_file)

        # -- export file --
        if action == "export_file":
            if not output_path:
                return "[ERROR] 'output_path' is required for 'export_file'."
            export_fmt = fmt or "GLTF"
            py = _build_export_script(output_path, export_fmt)
            return await self._run_blender_script(py, blend_file)

        # -- open file --
        if action == "open_file":
            if not blend_file:
                return "[ERROR] 'blend_file' is required for 'open_file'."
            return await self._run_blender_script(_SCENE_INFO_SCRIPT, blend_file)

        # -- save file --
        if action == "save_file":
            out = output_path or blend_file
            if not out:
                return "[ERROR] 'output_path' or 'blend_file' is required for 'save_file'."
            py = f"import bpy\nbpy.ops.wm.save_as_mainfile(filepath={out!r})\nprint('Saved:', {out!r})"
            return await self._run_blender_script(py, blend_file)

        return f"Unknown action: {action}"

    async def _run_blender_script(self, script: str, blend_file: str = "") -> str:
        """Run a Python script inside Blender's background mode."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(self._workspace),
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            cmd = [_BLENDER_BIN, "--background"]
            if blend_file:
                cmd.append(blend_file)
            cmd.extend(["--python", script_path])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120.0,
            )

            output = stdout.decode("utf-8", errors="replace")
            errors = stderr.decode("utf-8", errors="replace")

            # Extract lines from our script (skip Blender boot noise)
            result_lines = []
            for line in output.splitlines():
                # Skip Blender startup messages
                if line.startswith(("Blender ", "Read ", "Fra:", "Info:")):
                    continue
                result_lines.append(line)

            result = "\n".join(result_lines).strip()

            if proc.returncode != 0 and not result:
                # Grab relevant error info
                err_lines = [
                    l for l in errors.splitlines()
                    if "Error" in l or "Traceback" in l or "File" in l
                ]
                return f"Blender error (exit {proc.returncode}):\n" + "\n".join(err_lines[-10:])

            return result or "Done (no output)"

        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Script templates
# ---------------------------------------------------------------------------

_SCENE_INFO_SCRIPT = """
import bpy, json

scene = bpy.context.scene
info = {
    "scene_name": scene.name,
    "frame_range": [scene.frame_start, scene.frame_end],
    "fps": scene.render.fps,
    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    "render_engine": scene.render.engine,
    "objects": [],
}
for obj in bpy.data.objects:
    info["objects"].append({
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "visible": obj.visible_get(),
    })
print(json.dumps(info, indent=2))
"""

_LIST_OBJECTS_SCRIPT = """
import bpy

if not bpy.data.objects:
    print("Scene is empty — no objects.")
else:
    for obj in bpy.data.objects:
        loc = [round(v, 3) for v in obj.location]
        mats = [m.name for m in obj.data.materials] if hasattr(obj.data, 'materials') and obj.data else []
        mat_str = f"  materials={mats}" if mats else ""
        print(f"  {obj.name} ({obj.type})  loc={loc}{mat_str}")
"""


def _build_create_script(obj_type: str, location: list[float], name: str, text_body: str) -> str:
    loc = tuple(location[:3]) if location else (0, 0, 0)
    lines = ["import bpy", "import math"]

    ops_map = {
        "cube": f"bpy.ops.mesh.primitive_cube_add(location={loc})",
        "sphere": f"bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location={loc})",
        "cylinder": f"bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=2, location={loc})",
        "cone": f"bpy.ops.mesh.primitive_cone_add(radius1=1, depth=2, location={loc})",
        "torus": f"bpy.ops.mesh.primitive_torus_add(location={loc})",
        "plane": f"bpy.ops.mesh.primitive_plane_add(size=2, location={loc})",
        "circle": f"bpy.ops.mesh.primitive_circle_add(radius=1, location={loc})",
        "monkey": f"bpy.ops.mesh.primitive_monkey_add(location={loc})",
        "empty": f"bpy.ops.object.empty_add(location={loc})",
        "camera": f"bpy.ops.object.camera_add(location={loc})",
        "light": f"bpy.ops.object.light_add(type='POINT', location={loc})",
        "text": f"bpy.ops.object.text_add(location={loc})",
    }

    op = ops_map.get(obj_type)
    if not op:
        return f"print('[ERROR] Unknown object type: {obj_type}')"

    lines.append(op)
    lines.append("obj = bpy.context.active_object")

    if name:
        lines.append(f"obj.name = {name!r}")

    if obj_type == "text" and text_body:
        lines.append(f"obj.data.body = {text_body!r}")

    lines.append(f"print(f'Created {{obj.name}} ({obj_type}) at {{list(obj.location)}}')")
    return "\n".join(lines)


def _build_delete_script(object_name: str) -> str:
    return f"""
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    print(f"[ERROR] Object not found: {object_name!r}")
else:
    bpy.data.objects.remove(obj, do_unlink=True)
    print(f"Deleted: {object_name!r}")
"""


def _build_material_script(object_name: str, mat_name: str, rgba: list[float]) -> str:
    r, g, b = rgba[0], rgba[1], rgba[2]
    a = rgba[3] if len(rgba) > 3 else 1.0
    return f"""
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    print("[ERROR] Object not found: {object_name}")
else:
    mat = bpy.data.materials.get({mat_name!r})
    if mat is None:
        mat = bpy.data.materials.new(name={mat_name!r})
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = ({r}, {g}, {b}, {a})
    if obj.data and hasattr(obj.data, 'materials'):
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
    print(f"Applied material '{mat_name}' to '{object_name}' with color ({r}, {g}, {b}, {a})")
"""


def _build_transform_script(
    object_name: str,
    location: list[float] | None,
    rotation: list[float] | None,
    scale: list[float] | None,
) -> str:
    lines = ["import bpy", "import math"]
    lines.append(f"obj = bpy.data.objects.get({object_name!r})")
    lines.append("if obj is None:")
    lines.append(f"    print('[ERROR] Object not found: {object_name}')")
    lines.append("else:")

    if location:
        lines.append(f"    obj.location = {tuple(location[:3])}")
    if rotation:
        # Convert degrees to radians
        rads = tuple(f"math.radians({d})" for d in rotation[:3])
        lines.append(f"    obj.rotation_euler = ({', '.join(rads)})")
    if scale:
        lines.append(f"    obj.scale = {tuple(scale[:3])}")

    lines.append(f"    print(f'Transformed {object_name}: loc={{list(obj.location)}} rot={{[round(r, 3) for r in obj.rotation_euler]}} scale={{list(obj.scale)}}')")
    return "\n".join(lines)


def _build_render_script(
    output_path: str, resolution: list[int], engine: str, img_format: str, samples: int,
) -> str:
    engine_map = {
        "EEVEE": "BLENDER_EEVEE",
        "CYCLES": "CYCLES",
        "WORKBENCH": "BLENDER_WORKBENCH",
    }
    eng = engine_map.get(engine, "BLENDER_EEVEE_NEXT")
    w, h = resolution[0], resolution[1] if len(resolution) > 1 else 1080

    lines = [
        "import bpy, os",
        "scene = bpy.context.scene",
        "",
        "# Set engine with fallback detection",
        f"requested_engine = {eng!r}",
        "available = [item.identifier for item in scene.render.bl_rna.properties['engine'].enum_items]",
        "if requested_engine in available:",
        "    scene.render.engine = requested_engine",
        "else:",
        "    # Fallback for different Blender versions (NEXT suffix variants)",
        "    fallbacks = {",
        "        'BLENDER_EEVEE': 'BLENDER_EEVEE_NEXT',",
        "        'BLENDER_EEVEE_NEXT': 'BLENDER_EEVEE',",
        "        'BLENDER_WORKBENCH': 'BLENDER_WORKBENCH_NEXT',",
        "        'BLENDER_WORKBENCH_NEXT': 'BLENDER_WORKBENCH',",
        "    }",
        "    fb = fallbacks.get(requested_engine, '')",
        "    if fb and fb in available:",
        "        scene.render.engine = fb",
        "    else:",
        "        scene.render.engine = available[0]",
        "    print(f'Engine fallback: {requested_engine} -> {scene.render.engine}')",
        "",
        f"scene.render.resolution_x = {w}",
        f"scene.render.resolution_y = {h}",
        f"scene.render.filepath = {output_path!r}",
        f"scene.render.image_settings.file_format = {img_format!r}",
    ]

    if samples > 0:
        lines.append(f"if scene.render.engine == 'CYCLES':")
        lines.append(f"    scene.cycles.samples = {samples}")
        lines.append(f"elif hasattr(scene, 'eevee'):")
        lines.append(f"    scene.eevee.taa_render_samples = {samples}")

    lines.append("bpy.ops.render.render(write_still=True)")
    lines.append(f"print('Render complete: {w}x{h} {img_format} (' + scene.render.engine + ')')")
    return "\n".join(lines)


def _build_import_script(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".fbx":
        op = f"bpy.ops.import_scene.fbx(filepath={file_path!r})"
    elif ext in (".glb", ".gltf"):
        op = f"bpy.ops.import_scene.gltf(filepath={file_path!r})"
    elif ext == ".obj":
        op = f"bpy.ops.wm.obj_import(filepath={file_path!r})"
    elif ext == ".stl":
        op = f"bpy.ops.wm.stl_import(filepath={file_path!r})"
    else:
        return f"print('[ERROR] Unsupported import format: {ext}')"

    return f"""
import bpy
before = set(obj.name for obj in bpy.data.objects)
{op}
after = set(obj.name for obj in bpy.data.objects)
new_objects = after - before
print(f"Imported from {file_path}: {{list(new_objects)}}")
"""


def _build_export_script(output_path: str, fmt: str) -> str:
    fmt = fmt.upper()
    if fmt == "FBX":
        op = f"bpy.ops.export_scene.fbx(filepath={output_path!r})"
    elif fmt in ("GLTF", "GLB"):
        op = f"bpy.ops.export_scene.gltf(filepath={output_path!r})"
    elif fmt == "OBJ":
        op = f"bpy.ops.wm.obj_export(filepath={output_path!r})"
    elif fmt == "STL":
        op = f"bpy.ops.wm.stl_export(filepath={output_path!r})"
    else:
        return f"print('[ERROR] Unsupported export format: {fmt}')"

    return f"""
import bpy
{op}
print(f"Exported to: {output_path} ({fmt})")
"""
