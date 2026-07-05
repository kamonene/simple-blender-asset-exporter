"""Simple Godot Exporter.

One-click pipeline: snapshot the current file to a temporary copy, then run
a headless Blender on that copy which bakes everything into a single albedo
texture, replaces the materials and exports a GLB. The open Blender session
is never modified.
"""

import os
import shutil
import subprocess
import tempfile

import bpy


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class SGE_Props(bpy.types.PropertyGroup):
    collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Collection",
        description="Collection to export (defaults to the active collection)",
    )
    export_path: bpy.props.StringProperty(
        name="Output File",
        subtype='FILE_PATH',
        default="",
        description="Where to write the .glb file. Leave empty to export "
                    "next to the .blend file with the same name",
    )
    resolution: bpy.props.EnumProperty(
        name="Bake Size",
        items=[
            ('512', "512", ""),
            ('1024', "1024", ""),
            ('2048', "2048", ""),
            ('4096', "4096", ""),
        ],
        default='1024',
    )
    samples: bpy.props.IntProperty(
        name="Bake Samples",
        default=16, min=1, max=4096,
        description="Cycles samples used while baking",
    )
    save_textures: bpy.props.BoolProperty(
        name="Save Texture",
        default=True,
        description="Also save the baked PNG next to the GLB "
                    "(in a 'textures' folder), replacing any existing one",
    )


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class SGE_OT_export(bpy.types.Operator):
    bl_idname = "sge.export_to_godot"
    bl_label = "Export to Godot"
    bl_description = ("Bake to a single texture and export a GLB. Runs on a "
                      "temporary copy of the file; this session is untouched")
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.sge_props

        source_col = props.collection or context.collection
        if source_col is None or not source_col.all_objects:
            self.report({'ERROR'}, "No collection selected (or it is empty)")
            return {'CANCELLED'}

        if props.export_path:
            glb_path = bpy.path.abspath(props.export_path)
        else:
            if not bpy.data.filepath:
                self.report({'ERROR'}, "Save the .blend first, or set an "
                                       "output file path")
                return {'CANCELLED'}
            glb_path = os.path.splitext(bpy.data.filepath)[0] + ".glb"
        if not glb_path.lower().endswith(".glb"):
            glb_path += ".glb"
        out_dir = os.path.dirname(glb_path)
        if not out_dir:
            self.report({'ERROR'}, "Export path has no directory "
                                   "(save the .blend or use an absolute path)")
            return {'CANCELLED'}
        os.makedirs(out_dir, exist_ok=True)

        pipeline = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "pipeline.py")
        tmp_dir = tempfile.mkdtemp(prefix="sge_")
        tmp_blend = os.path.join(tmp_dir, "export_copy.blend")
        try:
            # snapshot the file as it is right now; the session keeps its
            # own path and unsaved state
            bpy.ops.wm.save_as_mainfile(filepath=tmp_blend, copy=True)

            cmd = [
                bpy.app.binary_path,
                "--background", tmp_blend,
                "--factory-startup",
                "--python", pipeline,
                "--",
                glb_path,
                source_col.name,
                props.resolution,
                str(props.samples),
                "1" if props.save_textures else "0",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + "\n" + proc.stderr)
                             .strip().splitlines()[-15:])
            print("Godot export failed:\n" + tail)
            self.report({'ERROR'},
                        "Export failed - see console for details")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported {os.path.basename(glb_path)}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class SGE_PT_panel(bpy.types.Panel):
    bl_label = "Godot Export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Godot"

    def draw(self, context):
        layout = self.layout
        props = context.scene.sge_props

        layout.prop(props, "collection")
        layout.prop(props, "export_path")
        layout.prop(props, "resolution")
        layout.prop(props, "samples")
        layout.prop(props, "save_textures")
        layout.separator()
        layout.operator(SGE_OT_export.bl_idname, icon='EXPORT')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (SGE_Props, SGE_OT_export, SGE_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sge_props = bpy.props.PointerProperty(type=SGE_Props)


def unregister():
    del bpy.types.Scene.sge_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
