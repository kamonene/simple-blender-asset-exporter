"""Bake-and-export pipeline.

Runs inside a headless Blender on a temporary *copy* of the user's file
(launched by the add-on), so it can modify the scene freely.

Bakes all materials of the chosen collection into one shared albedo
texture (emission-shader materials via the EMIT pass, everything else via
the DIFFUSE color pass), replaces the materials with simple baked ones and
exports a GLB. Roughness, metallic, alpha and IOR are carried over as
plain values.
"""

import math
import sys
import traceback

import bpy


def find_node(mat, node_type):
    return next((n for n in mat.node_tree.nodes if n.type == node_type), None)


def ensure_uvs(context, obj):
    if obj.data.uv_layers:
        return
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),
                             island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')


def pack_uvs(context, objs):
    """Pack the UV islands of all objects into one shared 0-1 layout."""
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:
        obj.select_set(True)
    context.view_layer.objects.active = objs[0]
    context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')


def bake_albedo(context, obj, mat, image):
    """Bake one material's color into the shared image.

    Emission-based materials (no Principled BSDF) are baked via the EMIT
    pass - the DIFFUSE pass would bake them black.
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    context.scene.render.bake.use_selected_to_active = False

    emission_only = (find_node(mat, 'BSDF_PRINCIPLED') is None
                     and find_node(mat, 'EMISSION') is not None)

    # the selected+active image node tells Cycles where to bake to; only
    # this material gets one, so only its faces are written
    tree = mat.node_tree
    node = tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    node.select = True
    tree.nodes.active = node

    # use_clear=False: many materials bake into the same image
    if emission_only:
        bpy.ops.object.bake(type='EMIT', margin=8, use_clear=False)
    else:
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'},
                            margin=8, use_clear=False)
    tree.nodes.remove(node)


def make_baked_material(name, source_mat, image):
    mat = bpy.data.materials.new(name + "_baked")
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = find_node(mat, 'BSDF_PRINCIPLED')

    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.image = image
    tex.location = (-400, 200)
    tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])

    src_bsdf = find_node(source_mat, 'BSDF_PRINCIPLED')
    if src_bsdf is None:
        # emission-based source: flat shaded, no highlights
        bsdf.inputs['Roughness'].default_value = 1.0
        return mat

    # carry over plain (unlinked) scalar values from the source material
    for socket in ('Metallic', 'Roughness', 'Alpha', 'IOR'):
        src_input = src_bsdf.inputs[socket]
        if not src_input.is_linked:
            bsdf.inputs[socket].default_value = src_input.default_value
    if (not src_bsdf.inputs['Alpha'].is_linked
            and src_bsdf.inputs['Alpha'].default_value < 1.0):
        for attr, value in (('blend_method', 'BLEND'),
                            ('surface_render_method', 'BLENDED')):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, value)
                except (AttributeError, TypeError):
                    pass
    return mat


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    glb_path, col_name, res_str, samples_str = argv
    res = int(res_str)
    samples = int(samples_str)

    context = bpy.context
    scene = context.scene

    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples

    col = bpy.data.collections.get(col_name)
    if col is None:
        col = scene.collection

    objs = list(col.all_objects)
    if not objs:
        raise RuntimeError(f"Collection '{col_name}' is empty")
    for obj in objs:
        obj.hide_viewport = False
        obj.hide_render = False
        try:
            obj.hide_set(False)
        except RuntimeError:
            pass

    mesh_objs = [
        o for o in objs
        if o.type == 'MESH' and any(
            s.material and s.material.use_nodes for s in o.material_slots)
    ]

    if mesh_objs:
        for obj in mesh_objs:
            ensure_uvs(context, obj)
        pack_uvs(context, mesh_objs)

        # Godot names extracted textures "<glb>_<image name>.png", so keep
        # the embedded image name generic to avoid "name_name.png"
        image = bpy.data.images.new("albedo", res, res)
        image.colorspace_settings.name = 'sRGB'

        # bake every slot first, replace after: swapping a slot early would
        # let later bakes write into the finished image
        replacements = []
        for obj in mesh_objs:
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None or not mat.use_nodes:
                    continue
                bake_albedo(context, obj, mat, image)
                baked = make_baked_material(f"{obj.name}_{mat.name}",
                                            mat, image)
                replacements.append((slot, baked))
        for slot, baked in replacements:
            slot.material = baked

    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
    context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
    )
    print("PIPELINE OK:", glb_path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
