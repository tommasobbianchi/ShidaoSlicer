; CERTIFICATION TEST 3.2: Hot Extrusion
; Test extrusion at proper temperature

M117 Test 3.2: Hot Extrusion
G28
M104 S235      ; Set hotend temperature
M109 S235      ; Wait for temperature
M117 Extruding 50mm slowly
G92 E0         ; Reset extruder
G1 E50 F100    ; Extrude 50mm at slow speed
G4 P2000
M117 Retracting 5mm
G92 E0
G1 E-5 F100    ; Retract 5mm
G4 P1000
M104 S0        ; Turn off hotend
M117 Test 3.2 COMPLETE
; VERIFY: Uniform filament extrusion, no grinding
