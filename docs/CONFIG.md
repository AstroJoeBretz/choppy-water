# Configuration reference

Settings live in a TOML file. Run `choppy-water --write-config my.toml` for a commented copy of
the defaults, then keep only the keys you want to change: anything you leave out uses the default.
Unknown keys and sections are rejected with a suggestion, so typos cannot silently do nothing.

Any value can also be overridden on the command line: `--set water.choppiness=0.5`.

All lengths use `units.length`, including feed rates (length per minute). Angles are degrees.

## `[units]`

| Key | Default | Meaning |
|---|---|---|
| `units.length` | `"in"` | Unit for every length in the file: `"in"` or `"mm"`. |

## `[part]`: the piece you are making

| Key | Default | Meaning |
|---|---|---|
| `part.shape` | `"disc"` | `"disc"` (uses `diameter`) or `"rect"` (uses `width` and `length`). The keys for the other shape are ignored. |
| `part.diameter` | `3.0` | Disc diameter. |
| `part.width` | `4.0` | Rectangle size along X. |
| `part.length` | `3.0` | Rectangle size along Y. |
| `part.base_thickness` | `0.25` | Material left under the deepest trough, measured from the flat bottom. |
| `part.max_thickness` | `0.50` | Upper limit for the highest crest. Must not exceed `milling.stock_thickness`. |

## `[water]`: the surface

| Key | Default | Meaning |
|---|---|---|
| `water.method` | `"fft"` | `"fft"`: random sea from a wave spectrum (realistic). `"gerstner"`: sum of 64 sine waves (cheaper, more regular). |
| `water.seed` | `42` | Same seed and settings give the same surface. Change it for a different sea. |
| `water.patch_size` | `6.0` | Size of the simulated square. Keep it at least as large as the part, or the pattern visibly repeats. |
| `water.wavelength_dominant` | `0.8` | The most prominent wavelength. |
| `water.wavelength_min` | `0.3` | Shortest ripple. Keep it at least twice `milling.tool_diameter`, or the cutter smooths it away. |
| `water.wavelength_max` | `1.6` | Longest swell. Must not exceed `patch_size`. |
| `water.wind_direction_deg` | `0.0` | Direction the waves travel, from the +X axis. Crests run perpendicular to it. |
| `water.directional_spread_deg` | `40.0` | How scattered the wave directions are: small = tidy parallel swells, large = chaotic sea. |
| `water.choppiness` | `0.8` | `0` = rounded swells; around `1` = pointed crests; much above `1` folds the surface over itself (the tool reports this). |
| `water.relief` | `0.25` | Peak-to-peak height of the waves over the part. Must fit within `max_thickness - base_thickness`. |
| `water.smoothing` | `0.0` | Gaussian low-pass radius applied to the waves. |

## `[mesh]`: resolution

| Key | Default | Meaning |
|---|---|---|
| `mesh.grid_spacing` | `0.01` | Surface sample spacing. Smaller is smoother but slower and larger. Keep it at or below one tenth of the tool diameter for reliable tool-reach estimates. |
| `mesh.edge_segments` | `720` | Points around a disc's rim. Keep the rim spacing (pi x diameter / segments) within 2x of `grid_spacing`. Ignored for rectangles. |

## `[milling]`: the job

| Key | Default | Meaning |
|---|---|---|
| `milling.stock_thickness` | `1.0` | Thickness of the wood blank. |
| `milling.tool_type` | `"ball"` | Finishing cutter. Only `"ball"` (ball nose) is supported. |
| `milling.tool_diameter` | `0.125` | Ball-nose diameter. |
| `milling.max_slope_deg` | `70.0` | Steepest surface you are happy to cut; the report flags anything steeper. |
| `milling.enforce_tool_limits` | `true` | `true`: fill valleys narrower than the cutter so the STL shows what can actually be cut. `false`: keep the ideal surface and only report the gap. |
| `milling.stepover_pct` | `10.0` | Distance between finishing passes, as a percent of the tool diameter. |
| `milling.stepdown` | `0.1` | Depth per roughing layer. |
| `milling.feed_rate` | `60.0` | Cutting speed (length per minute); drives the time estimate. |
| `milling.plunge_rate` | `20.0` | Recorded for your reference; not used in any calculation yet. |
| `milling.spindle_rpm` | `16000` | Recorded for your reference; not used in any calculation yet. |

## `[output]`

| Key | Default | Meaning |
|---|---|---|
| `output.stl_path` | `"output/choppy_water.stl"` | Where to write the STL. Related files share its name. |
| `output.stl_units` | `"mm"` | Units written into the STL (`"mm"` or `"in"`). STL files carry no unit; most CAM tools assume mm. |
| `output.preview` | `true` | Also write a shaded PNG preview. Needs `matplotlib` (`pip install "choppy-water[preview]"`). |

## Files written

For `output.stl_path = "output/sea.stl"`:

| File | Contents |
|---|---|
| `sea.stl` | Watertight binary STL, flat bottom at z = 0. |
| `sea.png` | Shaded preview of the surface (if `output.preview`). |
| `sea.json` | Resolved config, surface and mesh measurements, milling numbers. Feeding its `config` block back in reproduces the STL. |
| `sea_milling.txt` | Plain-text milling report. |
