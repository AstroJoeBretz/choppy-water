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
| `water.relief` | `0.25` | Peak-to-peak height of this layer over the part. With a chop layer, both reliefs together must fit within `max_thickness - base_thickness`. |
| `water.smoothing` | `0.0` | Gaussian low-pass radius applied to the waves. |

## `[water.chop]`: optional second layer

Add this table for a composite sea: long, calm swells from `[water]` with short, sharp chop on top.
Each layer is generated and choppy-warped on its own (so the chop keeps its sharp crests), then the
two are added. Leave the table out and nothing changes. Any key you omit takes the default below. It shares `water.patch_size`. The two reliefs add up
and must fit the thickness budget, so lower `water.relief` to make room: with the default 0.25 in
budget, `water.relief = 0.17` plus the default chop relief of 0.08 fits exactly. Command-line form:
`--set water.chop.relief=0.08`.

| Key | Default | Meaning |
|---|---|---|
| `water.chop.method` | `"fft"` | `"fft"` or `"gerstner"`, as for `water.method`. |
| `water.chop.seed` | `-1` | `-1` means `water.seed + 1`, so the chop is a different pattern from the swell. |
| `water.chop.wavelength_dominant` | `0.5` | Most prominent chop wavelength. |
| `water.chop.wavelength_min` | `0.25` | Shortest ripple. Keep it at least twice `milling.tool_diameter`. |
| `water.chop.wavelength_max` | `0.9` | Longest chop wavelength. Must not exceed `water.patch_size`. |
| `water.chop.wind_direction_deg` | `0.0` | Direction the chop travels. |
| `water.chop.directional_spread_deg` | `70.0` | Direction scatter; chop is usually less orderly than swell. |
| `water.chop.choppiness` | `0.9` | Sharpness of the chop crests. |
| `water.chop.relief` | `0.08` | Peak-to-peak height of the chop layer. |
| `water.chop.smoothing` | `0.0` | Gaussian low-pass radius applied to the chop. |

The combined surface is stretched to the total relief (`water.relief + water.chop.relief`), because
the crests of the two layers rarely coincide.

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
| `output.directory` | `"output"` | Parent folder for results. Each run gets its own subfolder named after the config file (`choppy_water` when run with no config file). Also settable with `-o DIR`. |
| `output.stl_path` | `""` | Optional exact STL path, used instead of the automatic folder. The other files are written next to it with the same name. |
| `output.stl_units` | `"mm"` | Units written into the STL (`"mm"` or `"in"`). STL files carry no unit; most CAM tools assume mm. |
| `output.preview` | `true` | Also write shaded PNG previews (top-down and a 3D view). Needs `matplotlib` (`pip install "choppy-water[preview]"`); without it the previews are skipped with a warning. |

## Files written

Running `choppy-water --example choppy_gerstner` (or `--config` with your own file) creates a folder named after the config file:

```
output/choppy_gerstner/
    choppy_gerstner.stl
    choppy_gerstner.png
    choppy_gerstner_3d.png
    choppy_gerstner.json
    choppy_gerstner_milling.txt
```

Re-running the same config overwrites that folder's files; a different config gets its own folder.
With no `--config` the folder is `output/choppy_water/`.

| File | Contents |
|---|---|
| `<name>.stl` | Watertight binary STL, flat bottom at z = 0. |
| `<name>.png`, `<name>_3d.png` | Top-down and angled 3D previews (if `output.preview`). |
| `<name>.json` | Resolved config, surface and mesh measurements, milling numbers. `choppy-water --config <name>.json` reproduces the run exactly. |
| `<name>_milling.txt` | Plain-text milling report. |
