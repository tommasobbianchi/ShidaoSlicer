; CERTIFICATION TEST 4.1: First Layer Single Line
; CRITICAL TEST: Single line first layer adhesion
; This is the MOST IMPORTANT test for belt printer certification

M117 Test 4.1: First Layer Line
G28
M140 S80       ; Heat bed to 80°C
M104 S235      ; Heat hotend to 235°C
M190 S80       ; Wait for bed
M109 S235      ; Wait for hotend

M117 First layer line test
G92 E0         ; Reset extruder
G1 Z0.3 F500   ; Move to first layer height (0.3mm)
G1 X50 Y0.3 F3000  ; Move to start position
M117 Extruding line - WATCH CLOSELY
G1 X150 Y0.3 E5 F900  ; Draw 100mm line at SLOW first layer speed
G4 P5000       ; Pause 5 seconds to observe
M117 Retracting and lifting
G92 E0
G1 E-1.5 F1800 ; Retract
G1 Z10 F500    ; Lift nozzle

M104 S0        ; Cool down
M140 S0
M117 Test 4.1 COMPLETE

; CRITICAL VERIFICATION CHECKLIST:
; [ ] Line adheres completely to belt
; [ ] Height uniform at 0.3mm
; [ ] No warping or lifting
; [ ] Width approximately 0.5mm
; [ ] Surface smooth and consistent
; [ ] No gaps or over-extrusion

; IF THIS FAILS, STOP AND DEBUG BEFORE PROCEEDING!
