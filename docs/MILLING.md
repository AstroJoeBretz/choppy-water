# From STL to wood

A suggested workflow. It is general guidance, not a recipe tested against a particular CAM
package or machine, so run the toolpath simulation and a test cut on scrap first.

## Geometry

The STL is a closed solid in millimetres (unless you set `output.stl_units`). The flat bottom sits
at z = 0 and the waves rise to at most `part.max_thickness`. It is centred on X/Y = 0.

The design assumes you carve the top of the stock and then cut the outline free, so the flat
bottom is simply the underside of the blank. Because the part is thinner than the stock, the
cutter removes everything above the surface, and a profile pass releases the disc or rectangle.

## Steps

1. **Stock.** Set the stock to your blank (default 1 in thick). Align the stock bottom with the
   model bottom (z = 0) and centre X/Y on the model. Keep the model's units as mm when importing.
2. **Roughing.** Use a flat end mill or an adaptive clearing strategy with the layer depth from
   the report. Leave a little material (for example 0.3 mm) for the finishing pass.
3. **Finishing.** Use a ball-nose cutter of the diameter in your config (`milling.tool_diameter`)
   with a parallel raster, using the stepover from `*_milling.txt`. Running the raster along or
   across the wave direction changes the finish: try both in simulation.
4. **Profile.** Cut the outline (disc diameter or rectangle size) through the full depth, using
   tabs so the part stays put until the end. The STL contains the outline walls, so you can also
   derive the profile from the model's silhouette.

## Reading the report

`*_milling.txt` lists, in your config's units:

- **Valleys too fine to cut.** Share of the part narrower than the ball nose, and how deep the
  material left behind is. With `milling.enforce_tool_limits = true` the STL already has those
  valleys filled in, so the model matches what the cutter can actually produce.
- **Steepest slope.** Walls steeper than `milling.max_slope_deg` give a rougher finish. Lower
  `water.choppiness` or use a smaller tool.
- **Stepover and scallop height.** Ridges left between passes on a flat area. Reduce
  `milling.stepover_pct` for a smoother surface at the cost of time.
- **Estimated time.** Finishing pass only. It excludes roughing, rapid moves, ramping and the
  profile cut.
- **Roughing layers.** How many passes of `milling.stepdown` it takes to clear down to the deepest
  trough.

## Wood

Fine, sharp crests are fragile across the grain and can tear out. If a first test cut is rough,
try a lower `water.choppiness`, a longer `water.wavelength_min`, a denser wood, or a sharper
(and possibly smaller) finishing cutter.
