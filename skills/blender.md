# Blender 3D Control

How to control Blender using the `blender` tool in background mode.

## Prerequisites

Blender must be installed and available on PATH. The tool runs Blender in `--background` mode (no GUI needed).

## When to use
- User asks to create 3D models, scenes, or objects
- Need to render images from 3D scenes
- Import/export 3D files (FBX, GLTF, OBJ, STL)
- Modify existing .blend files
- Generate 3D assets or visualizations

## Common workflows

### Create a simple scene and render

```
blender action="create_object" object_type="cube" name="MyCube" location=[0,0,0]
blender action="set_material" object_name="MyCube" color=[1,0,0,1] material_name="Red"
blender action="render" output_path="/tmp/scene.png" resolution=[1920,1080] engine="EEVEE"
```

### Work with an existing .blend file

```
blender action="open_file" blend_file="/path/to/project.blend"
blender action="list_objects" blend_file="/path/to/project.blend"
blender action="render" blend_file="/path/to/project.blend" output_path="/tmp/render.png"
```

### Create text in 3D

```
blender action="create_object" object_type="text" text_body="Hello World" location=[0,0,0]
blender action="set_material" object_name="Text" color=[0,0.5,1,1]
```

### Transform objects

```
blender action="set_transform" object_name="Cube" location=[2,0,1] rotation=[0,0,45] scale=[1,1,2]
```

### Import and export

```
blender action="import_file" file_path="/path/to/model.fbx"
blender action="export_file" output_path="/path/to/output.glb" format="GLTF"
```

### Run custom Python script

For complex operations, use `run_script` with full access to the `bpy` API:

```
blender action="run_script" script="import bpy\nbpy.ops.mesh.primitive_monkey_add()\nobj = bpy.context.active_object\nprint(f'Created: {obj.name}')"
```

## Tips

- All actions run in background mode — no Blender window opens
- Use `blend_file` parameter to work on an existing file across multiple actions
- The `run_script` action gives full access to Blender's Python API for anything the built-in actions don't cover
- Render engines: EEVEE (fast), CYCLES (photorealistic, slow), WORKBENCH (viewport-style)
- For CYCLES, use `samples` to control quality (64 = fast preview, 256+ = production)
- Exported files go to the specified path; use absolute paths
- Blender workspace for temporary files: `~/.lawclaw/blender/`
- `scene_info` gives a JSON overview of the current scene
- Rotation values are in degrees (automatically converted to radians)
- When building complex scenes, consider using `run_script` to do multiple operations in a single call for efficiency
