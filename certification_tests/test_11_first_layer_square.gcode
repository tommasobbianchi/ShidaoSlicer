; CERTIFICATION TEST 4.2: First Layer Square
; Square outline perimeter - 20x20mm in XZ plane

M117 Test 4.2: First Layer Square
G28
M140 S80
M104 S235
M190 S80
M109 S235

M117 Drawing square outline
G92 E0
G1 Z0.3 F500
G1 X90 Y0.3 Z0.3 F3000  ; Move to start position

; Draw 20x20mm square perimeter
; Remember: Y constant (belt), X and Z vary
M117 Side 1 of 4
G1 X110 Y0.3 Z0.3 E1 F900   ; Bottom edge (20mm in X)
G4 P1000
M117 Side 2 of 4
G1 X110 Y0.3 Z20.3 E2 F900  ; Right edge (20mm in Z)
G4 P1000
M117 Side 3 of 4
G1 X90 Y0.3 Z20.3 E3 F900   ; Top edge (20mm in X)
G4 P1000
M117 Side 4 of 4
G1 X90 Y0.3 Z0.3 E4 F900    ; Left edge (20mm in Z) - back to start

M117 Square complete - retracting
G92 E0
G1 E-1.5 F1800
G1 Z10 F500

M104 S0
M140 S0
M117 Test 4.2 COMPLETE

; VERIFICATION:
; [ ] All 4 sides uniform and adhered
; [ ] Corners well-formed
; [ ] Dimensions 20x20mm (measure!)
; [ ] No gaps or over-extrusion
