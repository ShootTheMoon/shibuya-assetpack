"""Day / night lighting preset. Costs ZERO triangles and touches 100% of the pixels.

Why this is the first item after the pixel-share measurement: ground 31.6% + facades 28.0%
+ sky 25.4% of an eye-level frame, and light multiplies all of them. Every other fix this
session moved categories that occupy under 1% of the frame.

Four things were measured wrong in the scene, not guessed:

  1. `use_raytracing` was FALSE. In EEVEE Next that switches off screen-traced GI, ambient
     occlusion and reflections in one go - the single largest reason the render is flat.
     `use_fast_gi` was on but at ray_count 2 / quality 0.25, which is a rough ambient term,
     not contact shading.
  2. The world was a flat Background colour (0.26, 0.35, 0.5) at strength 1.3 - a uniform
     dome, so ambient arrives equally from every direction and nothing has a lit side.
     Replaced with a real Sky Texture: horizon-to-zenith gradient plus sun-side brightening.
  3. All 137 NL_Pole night lamps (1400 W each) were rendering during the DAY. They belong
     to the night preset; place_nightlights.py builds them and nothing ever switched them
     off.
  4. Sun angular size 1.50 deg gives razor shadow edges, and shadow_ray_count was 1.

The AgX `look` enum in this build contains only 'NONE', so contrast cannot come from a view
transform preset - exposure plus the existing SHIBUYA_COMP glare chain carry it instead.

    setup_lighting.run(mode="day")   # or "night"
"""
import bpy
import math

from mathutils import Vector

SUN = "SUN_CHK"
NIGHT_PREFIX = "NL_Pole"


def _sun_object():
    o = bpy.data.objects.get(SUN)
    if o is not None and o.type == 'LIGHT' and o.data.type == 'SUN':
        return o
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and o.data.type == 'SUN':
            return o
    return None


def _sky(world, sun):
    """world dome from a Sky Texture aimed at the existing sun"""
    world.use_nodes = True
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
    if bg is None:
        bg = nt.nodes.new('ShaderNodeBackground')
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_WORLD'), None)
    if out is None:
        out = nt.nodes.new('ShaderNodeOutputWorld')
    sky = next((n for n in nt.nodes if n.type == 'TEX_SKY'), None)
    if sky is None:
        sky = nt.nodes.new('ShaderNodeTexSky')
        sky.name = sky.label = "SKY"
        sky.location = (-320, 0)
    sky.sky_type = 'MULTIPLE_SCATTERING'      # Nishita; PREETHAM has no ozone/altitude
    sky.sun_disc = False                      # the SUN lamp is the light source, not this
    if sun is not None:
        # direction the light TRAVELS is -Z of the lamp, so the sun sits along +that
        d = -(sun.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0)))
        d.normalize()
        sky.sun_elevation = math.asin(max(-1.0, min(1.0, d.z)))
        # azimuth measured from +X. With sun_disc off an error here only shifts the soft
        # sun-side brightening, so it is checked in the render rather than asserted.
        sky.sun_rotation = math.atan2(d.y, d.x)
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return sky, bg


def _drop_contrast(sc):
    """Remove the S-curve this script used to insert, and re-link around it.

    It was a mistake twice over. First the Factor socket is named "Factor" in this build,
    not "Fac", so the name lookup raised into a bare except and left the node unconfigured -
    the compositor returned a black frame (mean 0.0003) and the night preset looked like a
    lighting failure through four renders. Setting the socket by index fixed one render and
    then produced a black frame again on the next, including in DAYLIGHT.

    A tone curve is a nice-to-have. SHIBUYA_COMP already carries Fog Glow and Streaks, and
    AgX does the tone mapping. Two black deliveries is more than it is worth, so it goes.
    """
    g = getattr(sc, "compositing_node_group", None)
    if g is None:
        return
    out = next((n for n in g.nodes if n.type == 'GROUP_OUTPUT'), None)
    if out is None:
        return
    cur = g.nodes.get("SHIBUYA_CURVE")
    if cur is not None:
        # Capture the upstream by NAME. Holding the socket pointer across nodes.remove()
        # leaves it stale, the re-link silently does nothing, and Group Output ends up with
        # no input at all - which renders black and is exactly what got saved into v031.
        up = (cur.inputs["Image"].links[0].from_node.name
              if cur.inputs["Image"].links else None)
        g.nodes.remove(cur)
        if up and not out.inputs[0].links:
            n = g.nodes.get(up)
            if n is not None:
                g.links.new(n.outputs["Image"], out.inputs[0])
        print("     SHIBUYA_CURVE removed - it returned a black frame; AgX + Glare carry tone")

    # Unconditional repair. Whatever happened above, a compositor whose output is
    # unconnected renders the whole frame black, so never leave without checking.
    if not out.inputs[0].links:
        tail = None
        for cand in ("Glare.001", "Glare", "Render Layers"):
            n = g.nodes.get(cand)
            if n is not None and "Image" in n.outputs:
                tail = n
                break
        if tail is not None:
            g.links.new(tail.outputs["Image"], out.inputs[0])
            print("     !! compositor output was UNCONNECTED - relinked from %s" % tail.name)


def run(mode="day"):
    sc = bpy.context.scene
    ee = sc.eevee
    sun = _sun_object()

    # ---- ray tracing: the actual fix ----
    ee.use_raytracing = True
    rt = ee.ray_tracing_options
    rt.resolution_scale = '2'        # STRING enum, not int. Half res; full doubles the cost
    rt.screen_trace_quality = 0.50   # was 0.25
    rt.trace_max_roughness = 1.00    # was 0.5 - diffuse surfaces are most of the frame
    rt.use_denoise = True
    ee.use_fast_gi = True
    ee.fast_gi_ray_count = 4         # was 2
    ee.fast_gi_step_count = 12       # was 8
    ee.fast_gi_quality = 0.50        # was 0.25

    # ---- shadows ----
    ee.use_shadows = True
    ee.shadow_ray_count = 2          # was 1
    ee.shadow_step_count = 8         # was 6
    ee.taa_render_samples = max(ee.taa_render_samples, 96)

    sky, bg = _sky(sc.world, sun)
    night = (mode == "night")

    if night:
        sky.air_density = 1.0
        # The guard has to be on the ASSIGNMENT, not the value - this build's
        # ShaderNodeTexSky has air_density but no dust_density, so the ternary computed a
        # number and then raised on the attribute it was meant to protect. The day branch
        # got it right; only the night branch, which nothing had rendered yet, was wrong.
        if hasattr(sky, "dust_density"):
            sky.dust_density = 4.0
        bg.inputs["Strength"].default_value = 0.045
        if sun is not None:
            sun.data.energy = 0.05
            sun.data.color = (0.55, 0.65, 1.0)
            sun.data.angle = math.radians(6.0)
        sc.view_settings.exposure = 0.8
    else:
        # Iteration 2, driven by measurement rather than taste. Iteration 1 used
        # air 1.6 / dust 1.4 / exposure +0.25 and lifted mean luminance 33% while contrast
        # stayed flat (std 0.216 -> 0.222) and the AERIAL LOST contrast outright
        # (0.160 -> 0.129). Haze plus exposure is not lighting - it is a grey wash. The
        # sky strength is what rescued the shadowed facades (0.152 -> 0.273), so that
        # stays; the haze and the exposure lift go, and the sun goes back up to carry
        # direction.
        sky.air_density = 1.0
        if hasattr(sky, "dust_density"):
            sky.dust_density = 0.4
        bg.inputs["Strength"].default_value = 0.32
        if sun is not None:
            sun.data.energy = 5.5
            sun.data.color = (1.0, 0.95, 0.88)
            sun.data.angle = math.radians(2.6)       # was 1.50 - softer contact edges
        sc.view_settings.exposure = 0.0

    # ---- the night lamps belong to the night preset ----
    n_lamp = 0
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and o.name.startswith(NIGHT_PREFIX):
            o.hide_render = not night
            o.hide_viewport = not night
            if night:
                o.data.energy = 1400.0
            n_lamp += 1

    _drop_contrast(sc)

    print("  lighting mode=%s | raytracing ON (res/%s, quality %.2f) | shadows rays=%d steps=%d"
          % (mode, rt.resolution_scale, rt.screen_trace_quality,
             ee.shadow_ray_count, ee.shadow_step_count))
    if sun is not None:
        print("     sun %s energy=%.2f angle=%.1fdeg | sky elev=%.1fdeg rot=%.1fdeg strength=%.3f"
              % (sun.name, sun.data.energy, math.degrees(sun.data.angle),
                 math.degrees(sky.sun_elevation), math.degrees(sky.sun_rotation),
                 bg.inputs["Strength"].default_value))
    print("     %d %s* lamps -> %s | exposure %.2f | samples %d"
          % (n_lamp, NIGHT_PREFIX, "ON" if night else "OFF (were rendering in daylight)",
             sc.view_settings.exposure, ee.taa_render_samples))
    return n_lamp


if globals().get("__name__") == "__main__":
    run("day")
    print("LIGHTING SET")
