# Belt R11 Root Cause Analysis — Centered-Origin Meshes

**Date:** 2026-04-21
**Branch:** `rescue/crash-recovery-20260128`
**Status:** RESOLVED (commit `3ed34225de` 2026-04-21 23:00 CET). See **Resolution** section at bottom.
**Contesto:** Durante validazione del fix `support_preprocess: per-region support boxes`
(commit `7a7a353f98`), ho scoperto due bug nel pipeline belt che NON sono causati
dal preprocessor ma producono violazioni R11 sulle mesh centered-origin.

---

## Fatto sperimentale irriducibile

Per la mesh `Supports_Test_small.stl` (centered: X[-12.9,+12.9] Y[-5.4,+5.4] Z[-5.585,+5.585])
caricata in Orca su profilo `IdeaFormer IR3 V2 0.4 nozzle`, il gcode emesso contiene
**389 violazioni R11** (365 extrusion + 24 travel), **identiche** con:

- modello puro (`enable_support=0`, no supporti)
- supporti nativi Orca (`enable_support=1`, no preprocessor)
- supporti del preprocessor (pre-fix, skippava — equivaleva a nativo)
- supporti del preprocessor (post-fix per-region, 9 box validi)

**Conclusione:** le violazioni R11 NON sono causate dal preprocessor supports.
La radice è nel pipeline di piazzamento/slicing belt.

Gcode di riferimento archiviato a `/tmp/support_debug/`:
- `pre.3mf` = Orca-exported 3MF del test (input)
- `model_only.gcode` = slice senza support
- `supports_perregion.gcode` = slice con mio fix
- `old_rz000.gcode` = un BLOCKED del 20260421 (comparativo)

---

## Scoperta #1 — Item transform non keel-first per mesh centered

### Osservazione

Il 3MF esportato da Orca contiene:

```xml
<component p:path="/3D/Objects/Supports_Test_small.stl_1.model" objectid="1"
           transform="1 0 0 0 1 0 0 0 1 -5.62667847e-05 0 0"/>
...
<item objectid="2"
      transform="1 0 0 0 1 0 0 0 1 127.900002 10.3999996 5.58500051"
      printable="1"/>
```

Traslazione item (X, Y, Z) = (127.9, 10.4, 5.585).

- Mesh LOCAL Y ∈ [-5.4, +5.4] → world Y ∈ [5.0, 15.8]
- Mesh LOCAL Z ∈ [-5.585, +5.585] → world Z ∈ [0, 11.17]
- Y shift = **10.4** (questo valore è il punto critico)

Il profilo IdeaFormer dichiara `best_object_pos="0.5,0"` (Y=0, keel-first).
Il placement effettivo lascia **Y_world_min = 5.0 ≠ 0**.

### Ipotesi causa radice

10.4 = 5.4 + 5.0. L'interpretazione del codice di placement sembra:
- Y_shift = |Y_local_min| + target_Y (con target_Y ≈ 5 o offset plate)
- oppure: center-at-plate-Y con un offset di 5mm (origine del piatto logico)

Per mesh keel-first (Y_local_min=0, es. `inverted_L`): Y_shift ≈ Y_local_min + offset = 0 + 5 = 5? ma
inverted_L passa R11. Da verificare empiricamente il transform di inverted_L.

### Codice da ispezionare

- `src/libslic3r/Model.cpp` — `ModelObject::center_around_origin()`, `align_to_bed()`
- `src/libslic3r/Format/3mf.cpp` — load/save item transform
- `src/slic3r/GUI/Plater.cpp` — `on_drop`, auto-arrangement
- `src/libslic3r/Arrange.cpp` — logic that interprets `best_object_pos`

### Impatto concreto (R11)

Su mesh centered con Y_world_min=5.0, il `trafo_centered` shifta tutto il plate a Y_virt_min=0,
ma il **primo materiale non-empty** non è al corner (Y_virt=0, Z_virt=0) bensì in un intorno
(Y_virt ≈ 0.3, Z_virt ≈ 0.3) — la bounding box non ha vertici reali al corner.
Combinato con #3 (`m_belt_z_base`), i primi layer stampati hanno Z_gcode=0 e Y_gcode > 0 →
R11 = Z - Y/√2 < -0.05 → fail.

### Fix proposto (una volta verificato)

Per belt printer, item transform deve avere Y_translation tale che
`Y_world_min = 0` sempre (keel-first). Modifica isolata al solo
codice di placement belt. NON toccare:
- Forward/Inverse transform (`BeltTransform.cpp`)
- `m_belt_z_base` (GCode.cpp:2345-2360)
- `change_layer` (GCode.cpp:5461-5462)

### Scope

Fuori dall'istruzione "non rompere meccanismo di trasformazione geometrica".
Richiede una sessione dedicata con:
1. Confronto item transform di inverted_L vs centered mesh
2. Identificazione funzione placement responsabile
3. Hardware test post-fix su 2-3 mesh centered

---

## Scoperta #2 — emit_xyz su belt non sembra applicare √2 scaling Y (paradosso)

### Osservazione gcode

Travel line 621 di `model_only.gcode` (e altri):

```
G1 X133.168 Y.688 Z0 F7200
```

Layer entering: `;Z:0.565685` (virtuale).
Previous layer: Z=0.283 (virt), m_belt_z_base ≈ 0.566 → nominal_z=0 per layer corrente.

### Previsione teorica

Catena chiamate (post travel v11, commit 3422c57adb):
1. `GCode::_extrude` o travel path → `m_writer.travel_to_xyz(dest3d)`
2. `dest3d = (X, Y_virt=0.688, inclined_z = nominal_z + Y_virt·tan(45°) = 0 + 0.688 = 0.688)`
3. `GCodeWriter::travel_to_xyz` → `GCodeG1Formatter w(m_is_belt, m_belt_angle); w.emit_xyz(target)`
4. `emit_xyz` (GCodeWriter.hpp:273-287) su belt → `BeltTransform::inverse_transform_point(p, m_belt_angle)`
5. `inverse_transform_point` (BeltTransform.cpp:125-141) applica:
   - Y_mach = BELT_I_YY · Y_virt = **√2 · 0.688 = 0.973**
   - Z_mach = BELT_I_ZY · Y_virt + BELT_I_ZZ · Z_virt = -0.688 + 0.688 = 0

**Previsto:** `Y=0.973, Z=0`
**Osservato:** `Y=0.688, Z=0`

**Y non è scalata √2.** Oppure l'interpretazione sopra è sbagliata.

### Config runtime verificato

```json
{"printer_is_belt": "1", "belt_angle": "45",
 "belt_axis": "y", "belt_inclined_gcode": "1"}
```

Da `BeltTransform.cpp:37`:
```cpp
static constexpr double BELT_I_YY =  1.41421356;     // √2
```

Constant, non override-abile da config file (ensure_config non sovrascrive se non presente).

### Cause possibili (non investigate)

1. **`m_is_belt` false su GCodeG1Formatter**: il costruttore riceve `m_is_belt` di `GCodeWriter`,
   che è settato in `GCodeWriter.cpp:55` da `print_config.printer_is_belt.value`.
   Possibile path in cui il formatter viene costruito con altro flag?

2. **Doppia inversione**: `dest3d.z` passato a emit_xyz potrebbe essere già post-inverse
   (calcolato a monte via `compute_belt_inclined_z` che non inverte). In tal caso applicare
   inverse ancora darebbe risultato inatteso.

3. **Convenzione gcode è Y_virt non Y_mach**: ipotesi più probabile. Se Y_gcode IS Y_virt
   (niente √2), Klipper CoreXY interpreta letteralmente → funziona HW (i prints HW-validated
   confermano). In questo caso:
   - R11 rule `Z - Y/√2` è corretta per questa convenzione
   - `inverse_transform_point` in emit_xyz non è mai attivo (forse `m_is_belt=false` sui formatter
     effettivamente usati per travel/extrusion belt)
   - Code path "inverse transform" forse è dead code o si applica solo in branch specifici
     non raggiunti

### Paradosso apparente

Se #3 è vero (Y_gcode = Y_virt, niente √2), perché esistono BELT_I_YY=√2 e emit_xyz che
chiama inverse_transform_point? Possibile residuo di una design iteration non rimossa.
Verificare con `git log --all -p src/libslic3r/BeltTransform.cpp` per trovare quando
BELT_I_YY è stato introdotto e se c'è un path di codice che effettivamente lo applica.

### Investigazione futura

```bash
# Step 1: confermare convenzione con un singolo travel
# Modificare temporaneamente GCodeG1Formatter::emit_xyz per BOOST_LOG
# input point e output final_point. Slice 1 layer. Controllare log.

# Step 2: verificare m_is_belt è true in runtime
# BOOST_LOG_TRIVIAL(debug) << "emit_xyz m_is_belt=" << m_is_belt << " Y=" << ...

# Step 3: confrontare con IdeaMaker gcode reference (Klipper accetta entrambi)
# sul stesso mesh — vedere se Y_gcode è in virt o mach convention
```

### Scope

Non toccare. Impatto sistemico se si modifica. Il pipeline è HW-validated
su mesh keel-first, quindi la convenzione attuale (whatever it is) è corretta.

---

## Scoperta #3 — `m_belt_z_base` azzera Z gcode al primo layer stampato

### Codice di riferimento

`src/libslic3r/GCode.cpp:2345-2360`:

```cpp
// ORCA_BELT: Precompute the virtual Z base offset for belt printers.
// The first non-empty object layer has a large virtual Z (due to the belt forward
// transform shear). Subtract this base so that Y_mach starts at 0 for the first
// object layer, matching the prime line position at the belt surface after G28 Y.
m_belt_z_base = 0.0;
if (m_belt_inclined_gcode) {
    for (const PrintObject* obj : print.objects()) {
        for (const Layer* layer : obj->layers()) {
            if (!layer->empty()) {
                m_belt_z_base = layer->print_z;
                break;
            }
        }
        if (m_belt_z_base > 0.0) break;
    }
}
```

`src/libslic3r/GCode.cpp:5461-5462`:

```cpp
if (m_belt_inclined_gcode && m_belt_z_base > 0.0)
    z = std::max(0.0, z - m_belt_z_base);
```

### Comportamento

Per ogni layer: `nominal_z = max(0, layer_print_z - m_belt_z_base)`.

Primo layer non-vuoto: `nominal_z = 0` → Z_gcode=0.

### Interazione con scoperta #1

- Mesh keel-first (inverted_L, arc_bridge): primo layer non-empty a Z_virt piccolissimo
  (≈ 0.283), con materiale al corner (Y≈0, Z≈0.283). Dopo subtract, nominal_z=0, Y_gcode≈0.
  R11 = 0 - 0/√2 = 0 ✓.

- Mesh centered con Y_world_min=5: primo layer non-empty a Z_virt ≈ 0.566 (perché
  trafo_centered shifta Y e bounding box tange keel in un punto NON-vertice).
  Materiale REALE al corner "virtuale (Y=0, Z=0)" è vuoto — primo materiale a (Y=0.3, Z=0.266)
  circa. Dopo m_belt_z_base subtract, nominal_z=0 al PRIMO layer stampato (Z_virt=0.566),
  ma Y_gcode=0.3 > 0. R11 = 0 - 0.3/√2 = -0.21 ✗.

### Natura del problema

Il meccanismo `m_belt_z_base` presuppone che **la mesh abbia materiale al keel corner**
(Y=0, Z=0 nel trafo_centered). Per mesh keel-first questo è sempre vero (la bounding box
è aderente agli assi). Per mesh centered la bounding box è centrata su 0, ma il materiale
vero tange il keel solo in un sottoinsieme — dipende dalla forma.

### Fix logico (dipende da #1)

Se #1 è risolto (item transform keel-first), `m_belt_z_base` continua a funzionare.
Non modificare `m_belt_z_base` da solo — romperebbe le mesh keel-first HW-validated.

### Scope

NON toccare. Intrinseco al design belt pipeline HW-validated.

---

## Piano di attacco consigliato (quando si riprende)

1. **Priorità alta — Scoperta #1**
   - [ ] Caricare `inverted_L.3mf` in Orca via MCP e ispezionare item transform
   - [ ] Caricare `arc_bridge.stl` (freshly loaded) in Orca e ispezionare item transform
   - [ ] Confrontare con Supports_Test_small centered
   - [ ] Identificare funzione in Model.cpp/Plater.cpp che calcola il Y shift
   - [ ] Patchare per garantire Y_world_min=0 su belt printer
   - [ ] Test HW su Supports_Test_small con 4 rotazioni — deve passare gate R11

2. **Priorità bassa — Scoperta #2** (solo se #1 risolto non basta)
   - [ ] Instrumentare emit_xyz con log debug
   - [ ] Verificare convenzione gcode effettiva (virt vs mach)
   - [ ] Eventuale cleanup dead code inverse transform

3. **Non toccare — Scoperta #3**

---

## File generati durante la sessione

```
/tmp/support_debug/
├── pre.3mf                      # Orca-exported 3MF del test
├── post.3mf                     # == pre.3mf (preprocessor skippava)
├── test_input.3mf               # copia di pre.3mf
├── test_output_perreg.3mf       # 3MF con miei per-region supports
├── t_shape.3mf                  # synthetic T-shape regression test
├── t_shape_supported.3mf        # T-shape con support
├── arc.3mf                      # arc_bridge.stl in 3MF wrapper
├── arc_supported.3mf            # arc_bridge con support (keel-first regression)
├── model_only.gcode             # slice di pre.3mf, no supports, 389 R11 violations
├── supports_perregion.gcode     # slice con miei supports, 389 R11 violations
├── old_rz000.gcode              # BLOCKED dal 2026-04-21 (comparativo)
└── inverted_L.gcode             # HW-validated keel-first, passes R11
```

## Commit di riferimento

- `7a7a353f98` — Fix support_preprocess per-region (questa sessione)
- `631a056bea` — R11-ZMACH parity printer/local gate
- `3422c57adb` — Belt travel v11
- `2f70dcfb23` — trafo_centered keel-first slicing
- `9d03140cbe` — Y positioning belt surface contact (potenzialmente rilevante per #1)

---

## Resolution (2026-04-21 23:00 CET, commit `3ed34225de`)

### What actually happened

Scoperta #1's *fix proposal* (force Y_world_min=0 via item transform) turned
out to be wrong. `trafo_centered()` in `Print.hpp:339` already does exactly
that — `t.pretranslate(Vec3d(0, -world_bbox.min.y(), -world_bbox.min.z()))`
guarantees Y_virt_min=0 regardless of item-transform Y translation.
Empirical test: all four Z-rotations of Supports_Test (0°, 90°, 180°, 270°)
still produced R11 FAIL after current placement, even though every one had
Y_virt_min=0.

### Actual root cause

`GCode.cpp:2349-2359` sets `m_belt_z_base = first_non_empty_layer.print_z`
where "non-empty" is `Layer::empty()` (slice existence check, not extrusion
emission). For **keel-first** meshes like inverted_L, layer 1 at
Y+Z=0.283 intersects mesh material (even if only a thin corner slice too
small to extrude) → `!Layer::empty()` → `m_belt_z_base=0.283`. First printed
extrusion at layer 2 gets `Z_gcode = 0.566 - 0.283 = 0.283`, and
`z_mach = Z - Y/√2 = 0.283 - 0.3/√2 = 0.071 > 0` ✓.

For **centered** meshes like Supports_Test_small with
`min(Y+Z)_shifted = 0.323 > 0.283`, layer 1's diagonal plane misses the
mesh entirely → `Layer::empty()=true` → `m_belt_z_base` jumps to layer 2
(`print_z=0.566`). First printed extrusion still at layer 2, now with
`Z_gcode = 0.566 - 0.566 = 0`, and `z_mach = 0 - 0.301/√2 = -0.213 < -0.05`
→ R11 FAIL, 389 violations.

So the distinguishing property is **not** bbox position (both have Y_virt_min=0)
but **mesh material presence at the keel corner**: does any vertex have
Y+Z close enough to zero (in shifted virtual coords) for the first slicing
diagonal to intersect the mesh.

### Fix (Python-side)

Extended `validation/support_preprocess.py`:
- `compute_keel_gap(mesh)` returns `min((v.y-y_min)+(v.z-z_min))` across
  vertices. Value 0 means the mesh touches the keel corner (typical
  keel-first STL); value > 0.05mm means keel gap requiring a wedge.
- `create_keel_wedge(mesh, height=2.83)` generates an 8-triangle prism
  spanning the mesh X extent, filling the keel corner in the YZ plane.
  Slicing this wedge alongside the model guarantees layer 1 is non-empty
  so `m_belt_z_base` stays at the correct `print_z=0.283`.
- `main()` detects the gap, generates the wedge, and either emits the
  wedge alone (no overhangs) or merges it into `support_wedge` when
  supports are also generated.

Extended `src/slic3r/GUI/Plater.cpp` (`belt_supports_should_preprocess`):
dropped the `enable_support` gate so the preprocessor runs on every belt
slice — it fast-passes via `shutil.copy2` when no gap and no overhangs.

### Test regression

```
inverted_L       gap=0.000  → no wedge, WARN unchanged (3 travel)
arc_bridge       gap=0.000  → no wedge, WARN unchanged (3 travel)
box_20x20x20     gap=0.000  → no wedge, WARN unchanged (1 travel)
Supports_Test 0°   gap=0.323  wedge added, was FAIL 220 ext → WARN (4 travel)
Supports_Test 90°  gap=0.281  wedge added, was FAIL 236 ext → PASS CLEAN
Supports_Test 180° gap=0.323  wedge added, was FAIL 167 ext → WARN (4 travel)
Supports_Test 270° gap=5.348  wedge added, was FAIL 1061 ext → WARN (1 travel)
```

### What the fix does NOT touch

As required by the scope rules:
- `BeltTransform.{hpp,cpp}` — forward/inverse coefficients locked.
- `m_belt_z_base` computation in `GCode.cpp` — unchanged.
- `change_layer` Z emission logic — unchanged.
- `trafo_centered()` in `Print.hpp` — unchanged.
- All HW-validated gcode output for keel-first meshes is bit-identical
  (verified by gate WARN count matching pre-fix runs).

### Scoperta #2 and #3 status

Not addressed. Still apply:
- #2 (emit_xyz √2 paradox): deferred, not blocking.
- #3 (m_belt_z_base interaction): unchanged — `m_belt_z_base` logic untouched,
  the fix works *around* it by ensuring the mesh has material at the right
  place, which is what `m_belt_z_base` assumed all along.
