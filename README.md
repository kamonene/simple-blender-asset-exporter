# Simple Blender Asset Exporter

A one-click Blender add-on that bakes a collection down to a single texture
and exports it as a GLB for Godot — without touching your open scene.

**Pipeline:** snapshot the current file to a temporary copy → run a
headless Blender on that copy → pack all UVs into one atlas → bake every
material's color into one image → replace materials with simple baked
ones → export GLB. Your session is never modified at all.

## Requirements

- Blender 4.2 or newer (uses the extension format)

## Install

Build the extension zip (or grab one from `dist/`):

```sh
blender --command extension build --source-dir simple_godot_exporter --output-dir dist
```

Then in Blender: **Edit → Preferences → Get Extensions → ⌄ (top-right) →
Install from Disk…** and pick the zip. Or from the command line:

```sh
blender --command extension install-file -r user_default -e dist/simple_godot_exporter-0.3.2.zip
```

## Settings

In **Edit → Preferences → Add-ons → Simple Godot Exporter** you can set a
**Default Export Folder** (e.g. your Godot project's asset folder). With it
set, leaving Output File empty exports `<blend name>.glb` into that folder;
without it, the GLB lands next to the .blend file. The refresh button next
to Output File fills the field with that default path.

**Relative Folder** mirrors your folder structure into the export folder:
with relative folder `godot`, a file at `godot/birds/pigeons/pigeon1.blend`
exports to `<default folder>/birds/pigeons/pigeon1.glb`. If the folder
isn't in the .blend's path, it's ignored.

## Use

1. Open the sidebar in the 3D viewport (`N`) and pick the **Godot** tab.
2. Choose the collection to export (defaults to the active collection),
   the output `.glb` path, bake size and samples.
3. Click **Export to Godot**.

The GLB lands at the chosen path with the single baked texture embedded —
one file, one image. Drop the `.glb` into your Godot project and it
imports as a scene with StandardMaterial3D materials; use Godot's
"Extract Textures" on import if you want the PNG as a separate file.

## Notes

- Everything is packed into one shared UV atlas and baked into a single
  color texture embedded in the GLB. Re-exporting replaces the file.
- Emission-shader materials (a common flat-shading setup) are baked via the
  emission pass so their colors come through instead of baking black.
- Materials are still replaced per slot, so each keeps its own properties —
  a transparent glass material stays transparent.
- Transmission glass is converted to alpha-blended glass (alpha =
  1 − transmission, min 0.15), since game engines don't render glTF
  transmission. Its base color still bakes correctly.
- Roughness, metallic, alpha and IOR are carried over as plain values from
  the source materials; procedural maps for those channels are not baked.
- Objects without UVs get an automatic Smart UV Project unwrap.
- Baking runs in a background Blender process on a temporary copy of your
  file (unsaved changes included), so the UI freezes briefly but nothing in
  your scene ever changes.
