; CERTIFICATION TEST 3.1: Cold Extrusion Prevention
; Verify printer refuses extrusion when cold

M117 Test 3.1: Cold Protection
G28
M302 S170      ; Set minimum extrusion temperature to 170°C
G92 E0         ; Reset extruder position
M117 Attempting cold extrusion (should FAIL)
G1 E10 F100    ; Try to extrude 10mm (should be blocked)
G4 P2000
M117 Test 3.1 COMPLETE
; EXPECTED: Printer should refuse and show error
