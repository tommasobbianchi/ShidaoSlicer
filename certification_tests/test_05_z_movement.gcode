; Test 05: Z Movement (Belt Advance)
; Verifica Z MONOTONICALLY INCREASING (nastro va solo avanti!)
; Ideaformer Belt Printer Certification
; 
; ⚠️ CRITICAL: Z usa coordinate RELATIVE (G91) - solo incrementi!

; Home all axes first
G28

; Absolute positioning for XY
G90

; Ensure Y is raised (safe gantry height)
G1 Y10 F1500
G4 P500

; Test Z movement - RELATIVE MODE (always increments)
G91  ; Relative positioning for Z

G1 Z5 F600    ; Belt advances +5mm
G4 P1000

G1 Z5 F600    ; Belt advances +5mm (total +10)
G4 P1000

G1 Z10 F600   ; Belt advances +10mm (total +20)
G4 P1000

G1 Z10 F600   ; Belt advances +10mm (total +30)
G4 P1000

G1 Z15 F600   ; Belt advances +15mm (total +45)
G4 P1000

G90  ; Back to absolute for XY

; Combined XY (absolute) + Z (relative) movement
G1 X50 Y15 F1500
G91
G1 Z5 F600    ; Belt +5mm
G90
G4 P500

G1 X100 Y20 F1500
G91
G1 Z5 F600    ; Belt +5mm
G90
G4 P500

G1 X50 Y10 F1500
G91
G1 Z5 F600    ; Belt +5mm
G90
G4 P500

; ✅ CORRECT: Z only incremented (never decreased)
; Total Z advancement: ~60mm from start position

M400
